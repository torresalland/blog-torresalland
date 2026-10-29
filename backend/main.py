import hmac
import html
import json
import os
import re
import secrets
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import config, db, security
from .rendering import render_markdown
from .body_limit import BodyLimitMiddleware


@asynccontextmanager
async def lifespan(app):
    if config.COOKIE_SECURE and not config.ADMIN_PASSWORD_HASH:
        raise RuntimeError('ADMIN_PASSWORD_HASH must be configured before production startup')
    db.init()
    yield


app = FastAPI(title='Állan Torres — Blog CMS', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(BodyLimitMiddleware,maximum=500000)


@app.middleware('http')
async def policy(request: Request, call_next):
    if request.method not in {'GET','HEAD','OPTIONS'}:
        origin = request.headers.get('origin')
        allowed = {config.PUBLIC_ORIGIN}
        if config.PREVIEW_ORIGIN:
            allowed.add(config.PREVIEW_ORIGIN)
        if not config.COOKIE_SECURE:
            allowed.update({'http://127.0.0.1:4000','http://127.0.0.1:4300','http://localhost:4000'})
        if origin and origin not in allowed:
            return JSONResponse({'detail':'Origem não autorizada.'},status_code=403)
        content_length = request.headers.get('content-length','0')
        if not content_length.isdigit() or int(content_length) > 500000:
            return JSONResponse({'detail':'Conteúdo excede o limite de edição.'},status_code=413)
    nonce = secrets.token_urlsafe(24)
    request.state.nonce = nonce
    response = await call_next(request)
    response.headers['Content-Security-Policy'] = f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if config.COOKIE_SECURE:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    if request.url.path.startswith(('/api/','/admin','/painel')):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    elif not request.url.path.startswith(('/assets/','/fonts/')):
        response.headers['Cache-Control'] = 'no-cache, no-store, max-age=0, must-revalidate'
    if request.cookies.get('blog_v2_cache') != '1' and (request.url.path in {'/', '/api/posts', '/blog/posts.json'} or request.url.path.startswith(('/artigo/', '/admin', '/painel'))):
        response.headers['Clear-Site-Data'] = '"cache"'
        response.set_cookie('blog_v2_cache', '1', max_age=365*86400, path='/', samesite='lax', secure=config.COOKIE_SECURE)
    if config.PREVIEW_ORIGIN and request.headers.get('host') == config.PREVIEW_ORIGIN.split('://',1)[-1]:
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response


class Login(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=1024)


class PasswordChangeInput(BaseModel):
    currentPassword: str = Field(min_length=1, max_length=1024)
    newPassword: str = Field(min_length=8, max_length=1024)


class StatusInput(BaseModel):
    status: str = Field(pattern=r'^(DRAFT|PUBLISHED|ARCHIVED)$')


class PostInput(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    slug: str = Field(pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$', max_length=160)
    excerpt: str = Field(default='', max_length=600)
    abstract: str = Field(default='', max_length=3000)
    keywords: list[str] = Field(default_factory=list,max_length=15)
    tags: list[str] = Field(default_factory=list,max_length=15)
    category: str = Field(default='Análise',max_length=100)
    bodyMarkdown: str = Field(default='',max_length=200000)
    status: str = Field(default='DRAFT',pattern=r'^(DRAFT|PUBLISHED|ARCHIVED)$')
    version: int | None = None

    @field_validator('tags','keywords')
    @classmethod
    def short_labels(cls, value):
        if any(len(v) > 80 for v in value):
            raise ValueError('Rótulo com mais de 80 caracteres.')
        return value


class SettingsInput(BaseModel):
    publicationMode: str | None = Field(default=None,pattern=r'^(DRAFT|PUBLISHED)$')
    schedulerEnabled: bool | None = None
    editorialGuidance: str | None = Field(default=None,max_length=10000)
    schedule: list[str] | None = Field(default=None,max_length=6)

    @field_validator('schedule')
    @classmethod
    def valid_schedule(cls, value):
        if value is None:
            return value
        cleaned = []
        for item in value:
            slot = item.strip()
            if not slot:
                continue
            if not re.match(r'^(?:[01]\d|2[0-3]):[0-5]\d$', slot):
                raise ValueError('Use horários no formato HH:MM (ex.: 08:30).')
            if slot not in cleaned:
                cleaned.append(slot)
        if not cleaned:
            raise ValueError('Informe pelo menos um horário para a agenda.')
        return sorted(cleaned)


class GenerationInput(BaseModel):
    topic: str = Field(default='',max_length=1000)
    url: str = Field(default='',max_length=2000)
    publicationMode: str | None = Field(default=None,pattern=r'^(DRAFT|PUBLISHED)$')


class PreviewInput(BaseModel):
    bodyMarkdown: str = Field(default='',max_length=200000)


@app.get('/api/health')
def health():
    with db.connect() as conn:
        conn.execute('SELECT 1')
    return {'status':'ok'}


@app.post('/api/auth/login')
def login(payload: Login, request: Request, response: Response):
    security.check_login_rate(request)
    valid_user = hmac.compare_digest(payload.username.encode('utf-8'), config.ADMIN_USERNAME.encode('utf-8'))
    valid_password = security.verify_password(payload.password, db.get_password_hash())
    if not valid_user or not valid_password:
        raise HTTPException(401,'Usuário ou senha inválidos.')
    security.clear_attempts(request)
    token, csrf = security.create_session()
    response.set_cookie(security.COOKIE_NAME, token, max_age=config.SESSION_HOURS*3600, httponly=True, secure=config.COOKIE_SECURE, samesite='strict', path='/')
    db.event('auth.login',{'user':config.ADMIN_USERNAME})
    return {'user':config.ADMIN_USERNAME, 'csrfToken':csrf}


@app.get('/api/auth/session')
def session(s=Depends(security.require_session)):
    return {'user':config.ADMIN_USERNAME,'csrfToken':s['csrf']}


@app.post('/api/auth/logout')
def logout(request: Request, response: Response, s=Depends(security.require_session)):
    with db.connect() as conn:
        conn.execute('DELETE FROM sessions WHERE token_hash=?',(s['token_hash'],))
    response.delete_cookie(security.COOKIE_NAME, path='/', secure=config.COOKIE_SECURE, httponly=True, samesite='strict')
    return {'ok':True}


@app.post('/api/admin/password',dependencies=[Depends(security.require_session)])
def change_password(data: PasswordChangeInput):
    if not security.verify_password(data.currentPassword, db.get_password_hash()):
        raise HTTPException(401,'A senha atual informada está incorreta.')
    db.set_password_hash(security.password_hash(data.newPassword))
    return {'ok':True,'message':'Senha do painel atualizada com sucesso.'}


@app.get('/api/posts')
def posts():
    return {'posts':db.list_posts(public=True)}


@app.get('/blog/posts.json')
def legacy_posts_json(response: Response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Clear-Site-Data'] = '"cache"'
    return {'posts':db.list_posts(public=True)}


@app.get('/api/posts/{slug}')
def post(slug: str):
    result = db.get_post(slug,public=True)
    if not result:
        raise HTTPException(404,'Artigo não encontrado.')
    return result


@app.get('/api/admin/posts',dependencies=[Depends(security.require_session)])
def admin_posts():
    return {'posts':db.list_posts()}


@app.get('/api/admin/posts/{post_id}',dependencies=[Depends(security.require_session)])
def admin_post(post_id: str):
    result = db.get_post(post_id)
    if not result:
        raise HTTPException(404,'Artigo não encontrado.')
    return result


def persist_post(data, post_id=None):
    try:
        return db.save_post(data.model_dump(), post_id, data.version, actor='admin')
    except db.VersionConflict as exc:
        raise HTTPException(409,str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409,'Já existe um artigo com este slug.') from exc


@app.post('/api/admin/posts',dependencies=[Depends(security.require_session)])
def create_post(data: PostInput):
    return persist_post(data)


@app.put('/api/admin/posts/{post_id}',dependencies=[Depends(security.require_session)])
def update_post(post_id: str, data: PostInput):
    return persist_post(data,post_id)


@app.patch('/api/admin/posts/{post_id}/status',dependencies=[Depends(security.require_session)])
@app.post('/api/admin/posts/{post_id}/status',dependencies=[Depends(security.require_session)])
def change_post_status(post_id: str, data: StatusInput):
    try:
        return db.set_post_status(post_id, data.status)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.delete('/api/admin/posts/{post_id}',dependencies=[Depends(security.require_session)])
def remove_post(post_id: str):
    try:
        return db.delete_post(post_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get('/api/admin/posts/{post_id}/revisions',dependencies=[Depends(security.require_session)])
def post_revisions(post_id: str):
    return {'revisions':db.revisions(post_id)}


@app.get('/api/admin/settings',dependencies=[Depends(security.require_session)])
def settings():
    return db.get_settings()


@app.put('/api/admin/settings',dependencies=[Depends(security.require_session)])
def set_settings(data: SettingsInput):
    values = data.model_dump(exclude_none=True)
    if values.get('schedulerEnabled') and not config.provider_info()['configured']:
        raise HTTPException(409,'Configure uma chave e modelo do provedor antes de ativar a agenda.')
    return db.update_settings(values)


@app.post('/api/admin/sources/refresh',dependencies=[Depends(security.require_session)])
def refresh_sources():
    from . import sources
    collected = sources.collect_all()
    return {'ok':True, 'collected':collected, 'settings':db.get_settings()}


@app.post('/api/admin/backup',dependencies=[Depends(security.require_session)])
def create_backup():
    from datetime import datetime, timezone
    backup_dir = config.DATABASE_PATH.parent / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    backup_file = backup_dir / f'blog_{stamp}.sqlite3'
    with db.connect() as conn:
        bck = sqlite3.connect(str(backup_file))
        conn.backup(bck)
        bck.close()
    return {'ok':True, 'filename':backup_file.name, 'createdAt':db.now()}


@app.post('/api/admin/generate',dependencies=[Depends(security.require_session)])
def generate(data: GenerationInput):
    if not config.provider_info()['configured']:
        raise HTTPException(503,'O provedor de geração ainda não está configurado no servidor.')
    if data.url:
        from .sources import validate_url
        try:
            validate_url(data.url)
        except ValueError as exc:
            raise HTTPException(422,'Use um link HTTP(S) público válido.') from exc
    try:
        return {'job':db.queue_job(data.model_dump(),max_pending=5)}
    except db.QueueFull as exc:
        raise HTTPException(429,str(exc)) from exc


@app.get('/api/admin/jobs',dependencies=[Depends(security.require_session)])
def jobs():
    return {'jobs':db.list_jobs()}


@app.get('/api/admin/jobs/{job_id}',dependencies=[Depends(security.require_session)])
def job(job_id: str):
    result = db.get_job(job_id)
    if not result:
        raise HTTPException(404,'Trabalho não encontrado.')
    return {'job':result}


@app.delete('/api/admin/jobs/{job_id}',dependencies=[Depends(security.require_session)])
def remove_job(job_id: str):
    try:
        return db.delete_job(job_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post('/api/admin/preview',dependencies=[Depends(security.require_session)])
def preview(data: PreviewInput):
    return {'contentHtml':render_markdown(data.bodyMarkdown)}


@app.get('/api/admin/export',dependencies=[Depends(security.require_session)])
def export():
    return JSONResponse({'posts':db.list_posts(),'settings':db.get_settings()},headers={'Content-Disposition':'attachment; filename="blog-export.json"'})


CRAWLER_AGENTS = ('Googlebot','Bingbot','GPTBot','OAI-SearchBot','ChatGPT-User','PerplexityBot','ClaudeBot','Claude-SearchBot','Applebot-Extended','Google-Extended')
PRIVATE_PATHS = ('/api/','/admin','/painel')
MD_TYPE = 'text/markdown; charset=utf-8'


def rfc822(value):
    """RFC 822 date in GMT, as RSS 2.0 requires; None when the stored value is unusable."""
    try:
        moment = datetime.fromisoformat(str(value).replace('Z','+00:00'))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return format_datetime(moment.astimezone(timezone.utc), usegmt=True)


def article_url(slug):
    return f'{config.PUBLIC_ORIGIN}/artigo/{slug}/'


def category_url(category):
    return f'{config.PUBLIC_ORIGIN}/?categoria={quote(category)}'


def one_line(value):
    return ' '.join(str(value or '').split())


def llms_header():
    return [
        f'# {config.AUTHOR} — Blog',
        '',
        f'> Blog autoral de {config.AUTHOR}, {config.AUTHOR_JOB_TITLE}. Análises factuais, com fontes verificadas, sobre Direito, Inteligência Artificial, Automação, Comércio Exterior e Estratégia.',
        '',
        '## Sobre o autor',
        '',
        f'- {config.AUTHOR_BIO}',
        f'- Portfólio: [{config.PORTFOLIO_URL}]({config.PORTFOLIO_URL}/)',
        *[f'- Perfil público: <{url}>' for url in config.AUTHOR_SAME_AS],
        '',
        '## Como citar',
        '',
        f'- Cite o link canônico do artigo e o autor ({config.AUTHOR}). Cada artigo traz resumo executivo, palavras-chave e referências primárias ao final.',
        '- O conteúdo é análise editorial e não constitui aconselhamento jurídico.',
        '',
    ]


def llms_summary_lines(items):
    lines = ['## Últimos artigos', '']
    for p in items:
        entry = f'- [{one_line(p["title"])}]({article_url(p["slug"])}) ({p["date"]}, {one_line(p["category"])})'
        abstract = one_line(p['abstract'] or p['excerpt'])
        lines.append(f'{entry}: {abstract}' if abstract else entry)
    lines.append('')
    return lines


@app.get('/llms.txt')
def llms_txt():
    lines = llms_header() + llms_summary_lines(db.list_posts(public=True,limit=25)) + [
        '## Opcional', '', f'- [Versão completa para agentes]({config.PUBLIC_ORIGIN}/llms-full.txt)', f'- [Feed RSS]({config.PUBLIC_ORIGIN}/feed.xml)', f'- [Sitemap]({config.PUBLIC_ORIGIN}/sitemap.xml)', '',
    ]
    return Response('\n'.join(lines),media_type=MD_TYPE)


@app.get('/llms-full.txt')
def llms_full_txt():
    items = db.list_posts(public=True,limit=25)
    with db.connect() as conn:
        rows = conn.execute("SELECT slug,body_markdown FROM posts WHERE status='PUBLISHED' ORDER BY COALESCE(published_at,created_at) DESC LIMIT 25").fetchall()
    bodies = {row['slug']:row['body_markdown'] for row in rows}
    lines = llms_header() + ['## Artigos completos', '']
    for p in items:
        lines += [
            f'### {one_line(p["title"])}', '',
            f'- URL canônica: {article_url(p["slug"])}',
            f'- Publicado em: {p["date"]} | Categoria: {one_line(p["category"])}',
            f'- Palavras-chave: {", ".join(dict.fromkeys(p["keywords"]+p["tags"]))}', '',
            f'**Resumo executivo:** {one_line(p["abstract"] or p["excerpt"])}', '',
            bodies.get(p['slug'],'').strip(), '', '---', '',
        ]
    return Response('\n'.join(lines),media_type=MD_TYPE)


@app.get('/robots.txt')
def robots():
    blocks = []
    for agent in CRAWLER_AGENTS:
        # A named group replaces the "*" group, so private paths are repeated in each.
        blocks.append(f'User-agent: {agent}\nAllow: /\n'+''.join(f'Disallow: {path}\n' for path in PRIVATE_PATHS))
    blocks.append('User-agent: *\nAllow: /\n'+''.join(f'Disallow: {path}\n' for path in PRIVATE_PATHS))
    body = '\n'.join(blocks)+f'\nSitemap: {config.PUBLIC_ORIGIN}/sitemap.xml\n# LLMs: {config.PUBLIC_ORIGIN}/llms.txt\n'
    return Response(body,media_type='text/plain; charset=utf-8')


@app.get('/sitemap.xml')
def sitemap():
    entries=[(config.PUBLIC_ORIGIN+'/',None,'daily','1.0')]+[(article_url(p['slug']),p['updatedAt'],'weekly','0.8') for p in db.list_posts(public=True)]
    body=''.join('<url><loc>'+xml_escape(url)+'</loc>'+('<lastmod>'+xml_escape(date)+'</lastmod>' if date else '')+f'<changefreq>{freq}</changefreq><priority>{priority}</priority></url>' for url,date,freq,priority in entries)
    return Response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+body+'</urlset>',media_type='application/xml')


@app.get('/feed.xml')
def feed():
    origin = xml_escape(config.PUBLIC_ORIGIN)
    posts_ = db.list_posts(public=True,limit=30)
    items=[]
    for p in posts_:
        pub = rfc822(p['publishedAt'] or p['createdAt'])
        categories = ''.join(f'<category>{xml_escape(c)}</category>' for c in dict.fromkeys([p['category'],*p['tags']][:6]) if c)
        items.append(f'<item><title>{xml_escape(p["title"])}</title><link>{xml_escape(article_url(p["slug"]))}</link><guid isPermaLink="false">{xml_escape(p["id"])}</guid>'+(f'<pubDate>{pub}</pubDate>' if pub else '')+f'<dc:creator>{xml_escape(config.AUTHOR)}</dc:creator>{categories}<description>{xml_escape(p["excerpt"])}</description></item>')
    build = rfc822(max((p['updatedAt'] for p in posts_),default=None)) or format_datetime(datetime.now(timezone.utc),usegmt=True)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><title>Állan Torres</title><link>{origin}</link><description>Direito, IA, automação e negócios internacionais</description><language>pt-BR</language><lastBuildDate>{build}</lastBuildDate><atom:link href="{origin}/feed.xml" rel="self" type="application/rss+xml" />{"".join(items)}</channel></rss>',media_type='application/rss+xml')


@app.get('/{indexnow_key}.txt')
def indexnow_key_file(indexnow_key: str):
    """Ownership proof for IndexNow: the file body is the key itself."""
    if not config.INDEXNOW_KEY or not hmac.compare_digest(indexnow_key.encode('utf-8'),config.INDEXNOW_KEY.encode('utf-8')):
        raise HTTPException(404,'Página não encontrada.')
    return Response(config.INDEXNOW_KEY,media_type='text/plain; charset=utf-8')


DIST = config.ROOT / 'dist'
for directory in ['assets','fonts']:
    if (DIST/directory).is_dir():
        app.mount('/'+directory,StaticFiles(directory=DIST/directory),name=directory)


def page_html(request, path, article=None, not_found=False):
    index = DIST / 'index.html'
    if not index.exists():
        raise HTTPException(503,'Interface ainda não foi compilada.')
    text=index.read_text(encoding='utf-8')
    title = f'{article["title"]} | Állan Torres' if article else 'Blog | Állan Torres — IA, Direito e Estratégia'
    description=article['excerpt'] if article else 'Análises que conectam inteligência artificial, direito, automação, comércio exterior e estratégia empresarial.'
    canonical=config.PUBLIC_ORIGIN+path
    text=re.sub(r'<title>.*?</title>', lambda _: '<title>'+html.escape(title)+'</title>',text,flags=re.S)
    text=re.sub(r'<meta[^>]+name="description"[^>]*>','',text)
    text=re.sub(r'<link[^>]+rel="canonical"[^>]*>','',text)
    text=re.sub(r'<meta[^>]+property="og:(?:title|description|url|type)"[^>]*>','',text)
    meta=f'<meta name="description" content="{html.escape(description,quote=True)}"><link rel="canonical" href="{html.escape(canonical,quote=True)}"><meta property="og:title" content="{html.escape(title,quote=True)}"><meta property="og:description" content="{html.escape(description,quote=True)}"><meta property="og:url" content="{html.escape(canonical,quote=True)}"><meta property="og:type" content="'+('article' if article else 'website')+'">'
    meta+='<link rel="alternate" type="text/markdown" href="/llms.txt" title="LLMs.txt" />'
    if path.startswith(('/admin', '/painel')) or not_found:
        meta+='<meta name="robots" content="noindex,nofollow">'
    if article:
        body=f'<article class="ssr-public"><a href="/">Todos os artigos</a><h1>{html.escape(article["title"])}</h1><section><h2>Resumo executivo</h2><p>{html.escape(article["abstract"])}</p><p>Palavras-chave: {html.escape(". ".join(article["keywords"]))}.</p></section><div class="prose-blog">{article["contentHtml"]}</div><footer><h2>{config.AUTHOR}</h2><p>{html.escape(config.AUTHOR_BIO)}</p><a href="https://torresalland.cloud/">Portfólio</a> · <a href="https://torresalland.cloud/#contato">Fale comigo</a><p>Fontes e referências verificadas para conferência.</p></footer></article>'
        person={'@type':'Person','name':config.AUTHOR,'jobTitle':config.AUTHOR_JOB_TITLE,'url':config.PORTFOLIO_URL,'sameAs':config.AUTHOR_SAME_AS}
        keywords=', '.join(dict.fromkeys([*article['keywords'],*article['tags']]))
        category=article['category']
        posting={'@type':'BlogPosting','@id':canonical+'#article','headline':article['title'],'description':description,'inLanguage':'pt-BR','keywords':keywords,'articleSection':category,'datePublished':article['publishedAt'],'dateModified':article['updatedAt'],'mainEntityOfPage':canonical,'author':person,'publisher':person}
        crumbs={'@type':'BreadcrumbList','@id':canonical+'#breadcrumb','itemListElement':[
            {'@type':'ListItem','position':1,'name':'Home','item':config.PUBLIC_ORIGIN+'/'},
            {'@type':'ListItem','position':2,'name':category,'item':category_url(category)},
            {'@type':'ListItem','position':3,'name':article['title'],'item':canonical},
        ]}
        schema={'@context':'https://schema.org','@graph':[posting,crumbs]}
        meta+='<script type="application/ld+json" nonce="'+request.state.nonce+'">'+json.dumps(schema,ensure_ascii=False).replace('<','\\u003c')+'</script>'
    elif path == '/':
        cards=''.join(f'<article><h2><a href="/artigo/{p["slug"]}/">{html.escape(p["title"])}</a></h2><p>{html.escape(p["excerpt"])}</p><p><a href="/artigo/{p["slug"]}/">Ler artigo completo →</a></p></article>' for p in db.list_posts(public=True))
        body='<main class="ssr-public"><h1>Ideias que conectam tecnologia, direito e negócios</h1>'+cards+'</main>'
    else:
        body=''
    text=text.replace('</head>',meta+'</head>')
    text=text.replace('<div id="root"></div>','<div id="root">'+body+'</div>')
    return HTMLResponse(text,status_code=404 if not_found else 200)


@app.api_route('/artigo/{slug}/', methods=['GET', 'HEAD'])
@app.api_route('/artigo/{slug}', methods=['GET', 'HEAD'])
def article_page(slug: str, request: Request):
    result=db.get_post(slug,public=True)
    return page_html(request,'/artigo/'+slug+'/',result,not_found=not bool(result))


@app.api_route('/admin', methods=['GET', 'HEAD'])
@app.api_route('/admin/', methods=['GET', 'HEAD'])
@app.api_route('/painel', methods=['GET', 'HEAD'])
@app.api_route('/painel/', methods=['GET', 'HEAD'])
def admin_page(request: Request):
    return page_html(request,'/admin')


@app.api_route('/', methods=['GET', 'HEAD'])
def homepage(request: Request):
    return page_html(request,'/')


@app.get('/{path:path}')
def public_file(path: str, request: Request):
    if path.startswith(('.', 'api/', 'admin/', 'painel/')) or any(part.startswith('.') for part in path.split('/')):
        raise HTTPException(404,'Página não encontrada.')
    target=(DIST/path).resolve()
    if target.is_relative_to(DIST.resolve()) and target.is_file() and target.suffix in {'.svg','.png','.jpg','.ico','.webmanifest','.txt','.woff2'}:
        return FileResponse(target)
    raise HTTPException(404,'Página não encontrada.')
