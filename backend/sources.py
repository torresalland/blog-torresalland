"""Public-source collection. All redirects and DNS answers are validated and pinned.

Paywalls, access denials and rate limits are reported, never circumvented. Source
text is evidence, never executable instructions. No browser cookies or credentials.
"""
import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import feedparser
import httpx
from bs4 import BeautifulSoup

from . import db

MAX_BYTES = 2 * 1024 * 1024
USER_AGENT = 'AllanTorresBlog/1.0 (+https://blog.torresalland.cloud; public editorial research)'
FEEDS = json.loads(Path(__file__).with_name('feeds.json').read_text(encoding='utf-8'))
SOURCE_MAP = {source['id']: source for source in FEEDS}


class SourceError(ValueError):
    pass


def canonical_url(url: str) -> str:
    parsed = urlsplit(url)
    query = urlencode([(key,value) for key,value in parse_qsl(parsed.query,keep_blank_values=True) if not key.lower().startswith('utm_') and key.lower() not in ('fbclid','gclid','mc_cid','mc_eid')])
    return urlunsplit((parsed.scheme.lower(),parsed.netloc.lower(),parsed.path.rstrip('/') or '/',query,''))


def _public_addresses(host, port):
    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as exc:
        raise SourceError('Não foi possível resolver o domínio público.') from exc
    addresses = []
    for answer in answers:
        ip = ipaddress.ip_address(answer[4][0].split('%')[0])
        mapped = getattr(ip, 'ipv4_mapped', None)
        embedded = getattr(ip, 'sixtofour', None)
        teredo = getattr(ip, 'teredo', None)
        if not ip.is_global or ip.is_multicast or ip.is_reserved or (mapped and not mapped.is_global) or (embedded and not embedded.is_global) or (teredo and any(not address.is_global for address in teredo)):
            raise SourceError('URL aponta para rede privada, local ou reservada.')
        if str(ip) not in addresses:
            addresses.append(str(ip))
    if not addresses:
        raise SourceError('Domínio sem endereço público.')
    return addresses


def validate_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 33 or ord(c) == 127 for c in value) or '\\' in value:
        raise SourceError('URL inválida.')
    try:
        parsed = urlsplit(value)
        port = parsed.port
        host = parsed.hostname
    except ValueError as exc:
        raise SourceError('URL inválida.') from exc
    if parsed.scheme not in ('http', 'https') or not host or parsed.username is not None or parsed.password is not None:
        raise SourceError('Use uma URL pública HTTP ou HTTPS, sem credenciais.')
    if port not in (None, 80, 443) or '%' in host or host.lower().rstrip('.').endswith(('.localhost', '.local', '.internal')):
        raise SourceError('Porta ou domínio não permitido.')
    _public_addresses(host, port or (443 if parsed.scheme == 'https' else 80))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or '/', parsed.query, ''))


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, ip, port, timeout):
        super().__init__(host, port, timeout=timeout)
        self.pinned_ip = ip

    def connect(self):
        self.sock = socket.create_connection((self.pinned_ip, self.port), self.timeout)


class _PinnedHTTPS(_PinnedHTTP):
    def connect(self):
        super().connect()
        self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=self.host)


class PublicTransport(httpx.BaseTransport):
    """Connect to the checked IP, preserving TLS verification and hostname SNI."""
    def handle_request(self, request):
        url = validate_url(str(request.url))
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        ips = _public_addresses(host, port)
        connection_type = _PinnedHTTPS if parsed.scheme == 'https' else _PinnedHTTP
        connection = connection_type(host, ips[0], port, 20)
        started = time.monotonic()
        try:
            target = urlunsplit(('', '', parsed.path or '/', parsed.query, ''))
            connection.request('GET', target, headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,application/xml,application/rss+xml,application/atom+xml,text/xml;q=0.9,*/*;q=0.1', 'Accept-Encoding': 'identity', 'Connection': 'close'})
            response = connection.getresponse()
            declared = response.getheader('Content-Length')
            if declared and int(declared) > MAX_BYTES:
                raise SourceError('Resposta excede o limite de 2 MB.')
            chunks, total = [], 0
            while True:
                if time.monotonic() - started > 45:
                    raise SourceError('Tempo máximo de leitura da fonte excedido.')
                chunk = response.read(min(65536, MAX_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_BYTES:
                    raise SourceError('Resposta excede o limite de 2 MB.')
            body = b''.join(chunks)
            encoding = response.getheader('Content-Encoding', '').lower()
            if encoding == 'gzip':
                decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
                body = decoder.decompress(body, MAX_BYTES + 1)
                if len(body) > MAX_BYTES or decoder.unconsumed_tail:
                    raise SourceError('Resposta descompactada excede o limite.')
            elif encoding not in ('', 'identity'):
                raise SourceError('Codificação de resposta não suportada.')
            headers = [(k, v) for k, v in response.getheaders() if k.lower() not in ('content-encoding', 'content-length', 'transfer-encoding')]
            return httpx.Response(response.status, headers=headers, content=body, request=request)
        except (OSError, http.client.HTTPException, ValueError) as exc:
            if isinstance(exc, SourceError):
                raise
            raise SourceError('Falha ao consultar fonte pública.') from exc
        finally:
            connection.close()


def fetch_public(url):
    current = validate_url(url)
    with httpx.Client(transport=PublicTransport(), follow_redirects=False, trust_env=False) as client:
        for _ in range(6):
            response = client.get(current)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get('location')
                if not location:
                    raise SourceError('Redirecionamento sem destino.')
                current = validate_url(urljoin(current, location))
                continue
            if response.status_code >= 400:
                raise SourceError(f'Fonte retornou HTTP {response.status_code}; acesso não contornado.')
            content_type = response.headers.get('content-type', '').lower()
            if not any(x in content_type for x in ('html', 'xml', 'text/', 'json')):
                raise SourceError('Fonte não fornece um documento textual.')
            return response, current
    raise SourceError('Limite de redirecionamentos atingido.')


def clean_text(html):
    soup = BeautifulSoup(html or '', 'html.parser')
    for node in soup(['script', 'style', 'nav', 'header', 'footer', 'noscript', 'form', 'aside', 'svg']):
        node.decompose()
    text = ' '.join(soup.get_text(' ', strip=True).split())
    for ch in ('\u200b', '\u200c', '\u200d', '\ufeff'):
        text = text.replace(ch, '')
    return text


def normalize_date(value) -> str | None:
    if not value:
        return None
    try:
        if isinstance(value, (tuple, list)):
            dt = datetime(*value[:6], tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        if dt > datetime.now(timezone.utc):
            return None
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def _feed_entries(source, response, final_url):
    if source['kind'] == 'feed':
        parsed = feedparser.parse(response.content)
        for item in parsed.entries[:12]:
            link = item.get('link', '')
            if not link:
                continue
            raw_body = ''
            if item.get('content') and isinstance(item.get('content'), list):
                raw_body = item['content'][0].get('value', '')
            raw_summary = raw_body or item.get('summary', '')
            yield {'source_id':source['id'], 'url':urljoin(final_url, link), 'title':clean_text(item.get('title', '')), 'summary':clean_text(raw_summary)[:6000], 'published_at':normalize_date(item.get('published_parsed') or item.get('updated_parsed'))}
    else:
        soup = BeautifulSoup(response.text, 'html.parser')
        scope = soup.find('main') or soup.find(id='content') or soup
        seen = set()
        for anchor in scope.find_all('a', href=True):
            link = urljoin(final_url, anchor['href'])
            title = ' '.join(anchor.get_text(' ', strip=True).split())
            if len(title) < 35 or link in seen or urlsplit(link).hostname != urlsplit(final_url).hostname or link.rstrip('/') == final_url.rstrip('/'):
                continue
            if any(x in link.lower() for x in ('/login', '/search', '#', 'javascript:', '/contato', '/politica', '/privacy')):
                continue
            seen.add(link)
            yield {'source_id':source['id'], 'url':link, 'title':title[:400], 'summary':'', 'published_at':None}
            if len(seen) >= 12:
                break


def _listing_entries(source, response, final_url):
    if source['id'] == 'wto':
        try:
            feed_response, feed_final = fetch_public('https://www.wto.org/library/rss/latest_news_e.xml')
            entries = list(_feed_entries(dict(source, kind='feed'), feed_response, feed_final))
            if entries:
                return entries
        except SourceError:
            pass
        return list(_feed_entries(source, response, final_url))
    if source['id'] != 'siscomex':
        return list(_feed_entries(source,response,final_url))
    # The user-specified Siscomex homepage is an index of three collections.
    # Discover their explicitly advertised feeds rather than treating its RSS
    # subscription help page as a news item or inventing an endpoint.
    soup = BeautifulSoup(response.text,'html.parser')
    collections = []
    for anchor in soup.find_all('a',href=True):
        url = urljoin(final_url,anchor['href'])
        path = urlsplit(url).path
        if urlsplit(url).hostname == urlsplit(final_url).hostname and path.startswith('/siscomex/pt-br/noticias/noticias-siscomex-') and url not in collections:
            collections.append(url)
    entries = []
    for collection_url in collections[:3]:
        page,page_url = fetch_public(collection_url)
        collection = BeautifulSoup(page.text,'html.parser')
        feed = collection.find('link',rel='alternate',type='application/rss+xml',href=True)
        if not feed:
            continue
        feed_url = urljoin(page_url,feed['href'])
        if urlsplit(feed_url).hostname != urlsplit(final_url).hostname:
            continue
        feed_response,feed_final = fetch_public(feed_url)
        entries.extend(_feed_entries(dict(source,kind='feed'),feed_response,feed_final))
    return entries


def collect_source(source):
    try:
        response, final_url = fetch_public(source['url'])
        entries = _listing_entries(source, response, final_url)
        with db.connect() as conn:
            for entry in entries:
                parsed = urlsplit(entry['url'])
                if parsed.scheme not in ('http', 'https') or not parsed.hostname:
                    continue
                url = canonical_url(entry['url'])
                digest = hashlib.sha256(url.encode()).hexdigest()
                conn.execute('INSERT OR IGNORE INTO feed_items(id,source_id,url,title,summary,published_at,seen_at,content_hash) VALUES(?,?,?,?,?,?,?,?)', (digest,entry['source_id'],url,entry['title'],entry['summary'],entry['published_at'],db.now(),digest))
            conn.execute('INSERT OR REPLACE INTO source_health(source_id,status,checked_at,error,item_count) VALUES(?,?,?,?,?)', (source['id'],'OK' if entries else 'EMPTY',db.now(),None,len(entries)))
        return len(entries)
    except Exception as exc:
        # Deliberately avoid logging response bodies or provider credentials.
        error = str(exc)[:250] if isinstance(exc, SourceError) else type(exc).__name__
        with db.connect() as conn:
            conn.execute('INSERT OR REPLACE INTO source_health(source_id,status,checked_at,error,item_count) VALUES(?,?,?,?,?)', (source['id'],'ERROR',db.now(),error,0))
        return 0


def collect_all():
    count = 0
    with ThreadPoolExecutor(max_workers=5) as pool:
        tasks = [pool.submit(collect_source, source) for source in FEEDS]
        for task in as_completed(tasks):
            count += task.result()
    db.event('sources.collected', {'sources':len(FEEDS),'items':count})
    return count


def _metadata(soup):
    metadata = {}
    for node in soup.find_all('meta'):
        key = node.get('property') or node.get('name')
        if key and node.get('content'):
            metadata[key.lower()] = node['content']
    return metadata


def article_text(soup):
    """Prefer editorial body containers; semantic article may be a related card."""
    selectors = ('[itemprop="articleBody"]','[property="rnews:articleBody"]','.elementor-widget-theme-post-content','#conjur-content','#noticia','.entry-content','.post-content','.td-post-content','#content-core','.documentBody')
    for selector in selectors:
        candidates = [clean_text(str(node)) for node in soup.select(selector)]
        if candidates:
            longest = max(candidates,key=lambda text:len(text.split()))
            if len(longest.split()) >= 180:
                return longest[:40000]
    candidates = [clean_text(str(node)) for node in soup.find_all(['article','main'])]
    candidates = [text for text in candidates if len(text.split()) >= 180]
    if candidates:
        # The smallest complete editorial scope avoids broad navigation shells.
        return min(candidates,key=lambda text:len(text.split()))[:40000]
    content = soup.find(id='content')
    return clean_text(str(content or soup))[:40000]


def read_article(item):
    response, final_url = fetch_public(item['url'])
    soup = BeautifulSoup(response.text, 'html.parser')
    metadata = _metadata(soup)
    date = normalize_date(metadata.get('article:published_time') or metadata.get('datepublished') or metadata.get('date')) or normalize_date(item.get('published_at'))
    if not date:
        time_node = soup.find('time', datetime=True)
        date = normalize_date(time_node.get('datetime')) if time_node else None
    if not date:
        for node in soup.find_all('script', type='application/ld+json'):
            try:
                value = json.loads(node.string or '{}')
                nodes = value if isinstance(value, list) else [value]
                for obj in nodes:
                    if isinstance(obj, dict):
                        for candidate in [obj] + obj.get('@graph', []):
                            date = normalize_date(candidate.get('datePublished'))
                            if date:
                                break
                    if date:
                        break
            except (ValueError, TypeError, AttributeError):
                pass
            if date:
                break
    if not date:
        import re as _re
        for node in soup.select('.documentPublished, .documentModified'):
            m = _re.search(r'(\d{2})/(\d{2})/(\d{4})', node.get_text(' ', strip=True))
            if m:
                day, month, year = m.groups()
                date = normalize_date(f'{year}-{month}-{day}T12:00:00+00:00')
                if date:
                    break
    text = article_text(soup)
    if len(text.split()) < 180:
        raise SourceError('Documento insuficiente ou restrito; não foi usado como evidência.')
    if not date:
        raise SourceError('Fonte sem data de publicação verificável.')
    source = dict(SOURCE_MAP.get(item['source_id'], {'name':urlsplit(final_url).hostname, 'pillar':'Análise', 'primary':False}))
    final_host = urlsplit(final_url).hostname.lower().removeprefix('www.')
    original_host = urlsplit(source.get('url',final_url)).hostname.lower().removeprefix('www.')
    allowed_hosts = [original_host]
    if item['source_id'] == 'search-central':
        allowed_hosts += ['developers.google.com','developers.googleblog.com','blog.google']
    if not any(final_host == host or final_host.endswith('.'+host) for host in allowed_hosts):
        source.update(primary=False,name=final_host)
    heading = soup.find('h1')
    title = metadata.get('og:title') or (heading.get_text(' ',strip=True) if heading else None) or item['title']
    author = metadata.get('author') or source['name']
    result = dict(item, url=final_url, title=title, content=text, published_at=date, author=author, publisher=source['name'], primary=source['primary'], pillar=source['pillar'], accessed_at=db.now())
    if item.get('id'):
        with db.connect() as conn:
            conn.execute('UPDATE feed_items SET content=?,published_at=?,content_hash=? WHERE id=?', (text,date,hashlib.sha256(text.encode()).hexdigest(),item['id']))
    return result
