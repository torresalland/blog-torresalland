"""Camada de monetização aplicada na LEITURA: CTA B2B da Yuki e links de afiliado.

Nada é gravado no banco: o Markdown dos artigos continua limpo e a injeção vale
automaticamente para todos os posts já publicados (sem script retroativo).
Qualquer falha devolve o HTML original para nunca derrubar um artigo.
"""
import html
import json
import re
from urllib.parse import quote

from . import config

_TOPICS = {
    'negocios': ('negóci', 'negoci', 'venda', 'vendas', 'marketing', 'tráfego', 'trafego', 'captação', 'captacao',
                 'cliente', 'comercial', 'empreend', 'lead', 'conversão', 'conversao', 'receita', 'startup'),
    'tecnologia': ('tecnolog', 'automação', 'automacao', 'produtividade', 'n8n', 'inteligência artificial', 'ia ',
                   'ia aplicada', 'dados', 'software', 'governança', 'governanca', 'compliance', 'processo', 'api'),
}

_PITCHES = {
    'negocios': {
        'titulo': 'Transforme visitantes em clientes',
        'texto': 'A Yuki cria Páginas de Captação, Sites Institucionais e campanhas de Tráfego Pago para o seu negócio vender mais.',
        'botao': 'Quero um diagnóstico gratuito',
        'zap': 'Olá! Li o artigo "{titulo}" e quero um diagnóstico de Página de Captação, Site e Tráfego Pago.',
    },
    'tecnologia': {
        'titulo': 'Tire o processo do papel (e do improviso)',
        'texto': 'A Yuki implanta Automação de Processos com n8n e IA, com Governança Digital, para sua operação rodar sem retrabalho.',
        'botao': 'Quero um diagnóstico gratuito',
        'zap': 'Olá! Li o artigo "{titulo}" e quero um diagnóstico de Automação com n8n/IA e Governança Digital.',
    },
}

_H2 = re.compile(r'<h2\b[^>]*>(.*?)</h2>', re.S | re.I)
_REFS = re.compile(r'^\W*refer[eê]ncias', re.I)
_TAG = re.compile(r'(<[^>]+>)')
_SKIP = {'a', 'code', 'pre', 'aside', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

_cache = {'mtime': None, 'entries': []}


def classify(post):
    haystack = ' '.join([post.get('category', '')] + list(post.get('tags', [])) + list(post.get('keywords', []))).lower() + ' '
    scores = {k: sum(haystack.count(w) for w in words) for k, words in _TOPICS.items()}
    return 'negocios' if scores['negocios'] > scores['tecnologia'] else 'tecnologia'


def _cta(post, variant):
    pitch = _PITCHES[classify(post)]
    text = pitch['zap'].format(titulo=post.get('title', ''))
    href = f'https://wa.me/{config.YUKI_WHATSAPP}?text={quote(text)}'
    return (
        f'<aside class="cta-box cta-{variant}" aria-label="Diagnóstico Yuki">'
        f'<strong class="cta-title">{html.escape(pitch["titulo"])}</strong>'
        f'<p>{html.escape(pitch["texto"])}</p>'
        f'<a class="cta-button" href="{html.escape(href, quote=True)}">{html.escape(pitch["botao"])}</a>'
        '</aside>'
    )


def inject_cta(content, post):
    if not re.fullmatch(r'\d{10,15}', config.YUKI_WHATSAPP or ''):
        return content
    headings = list(_H2.finditer(content))
    end_at = len(content)
    for m in headings:
        if _REFS.match(re.sub(r'<[^>]+>', '', m.group(1)).strip()):
            end_at = m.start()
            break
    out = content[:end_at] + _cta(post, 'end') + content[end_at:]
    if len(headings) >= 4:
        mid = headings[len(headings) // 2]
        if mid.start() < end_at:
            out = out[:mid.start()] + _cta(post, 'mid') + out[mid.start():]
    return out


def load_affiliates():
    path = config.AFFILIATE_FILE
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return []
    if _cache['mtime'] != mtime:
        raw = json.loads(path.read_text(encoding='utf-8'))
        entries = []
        for item in raw.get('links', []):
            term, url = str(item.get('term', '')).strip(), str(item.get('url', '')).strip()
            if item.get('enabled') and term and url.startswith('https://'):
                entries.append({'term': term, 'url': url, 'store': str(item.get('store', ''))})
        entries.sort(key=lambda e: len(e['term']), reverse=True)
        _cache.update(mtime=mtime, entries=entries)
    return _cache['entries']


def inject_affiliates(content, entries, limit=None):
    limit = config.AFFILIATE_MAX_PER_POST if limit is None else limit
    if not entries or limit <= 0:
        return content
    by_term = {html.escape(e['term'], quote=False).lower(): e for e in entries}
    pattern = re.compile(r'(?<!\w)(' + '|'.join(re.escape(html.escape(e['term'], quote=False)) for e in entries) + r')(?!\w)', re.I)
    used, depth, parts = set(), 0, []
    for token in _TAG.split(content):
        if token.startswith('<'):
            name = re.match(r'</?\s*([a-zA-Z0-9]+)', token)
            if name and name.group(1).lower() in _SKIP and not token.endswith('/>'):
                depth += -1 if token.startswith('</') else 1
                depth = max(depth, 0)
            parts.append(token)
        elif depth or not token.strip():
            parts.append(token)
        else:
            def swap(m):
                key = m.group(1).lower()
                if key in used or len(used) >= limit:
                    return m.group(0)
                used.add(key)
                href = html.escape(by_term[key]['url'], quote=True)
                return f'<a href="{href}" rel="sponsored nofollow noopener" class="affiliate-link">{m.group(1)}</a>'
            parts.append(pattern.sub(swap, token))
    result = ''.join(parts)
    if used:
        result += ('<p class="affiliate-disclosure"><small>Divulgação: este artigo contém links de afiliado. '
                   'Se você comprar por eles, posso receber uma comissão, sem custo extra para você.</small></p>')
    return result


def monetize(content, post):
    try:
        if config.AFFILIATE_ENABLED:
            content = inject_affiliates(content, load_affiliates())
        return inject_cta(content, post)
    except Exception:
        return content
