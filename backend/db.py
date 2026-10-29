import contextlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta

from . import config, monetization
from .rendering import render_markdown, read_time

DEFAULTS = {'publicationMode': 'PUBLISHED', 'schedulerEnabled': False, 'timezone': 'America/Sao_Paulo', 'schedule': ['08:30', '18:30'], 'editorialGuidance': ''}


def now():
    return datetime.now(timezone.utc).isoformat()


@contextlib.contextmanager
def connect():
    config.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.DATABASE_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=30000')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init():
    with connect() as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS posts (
          id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
          excerpt TEXT NOT NULL, abstract TEXT NOT NULL DEFAULT '', keywords TEXT NOT NULL DEFAULT '[]',
          tags TEXT NOT NULL DEFAULT '[]', category TEXT NOT NULL, body_markdown TEXT NOT NULL,
          references_json TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL CHECK(status IN ('DRAFT','PUBLISHED','ARCHIVED')),
          version INTEGER NOT NULL DEFAULT 1, generation_id TEXT UNIQUE,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, published_at TEXT);
        CREATE TABLE IF NOT EXISTS post_revisions (id INTEGER PRIMARY KEY, post_id TEXT NOT NULL REFERENCES posts(id), version INTEGER NOT NULL, snapshot_json TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, status TEXT NOT NULL, payload_json TEXT NOT NULL, trigger TEXT NOT NULL, due_key TEXT UNIQUE, post_id TEXT REFERENCES posts(id), error TEXT, attempt INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, started_at TEXT, completed_at TEXT, heartbeat_at TEXT);
        CREATE TABLE IF NOT EXISTS feed_items (id TEXT PRIMARY KEY, source_id TEXT NOT NULL, url TEXT NOT NULL UNIQUE, title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '', content TEXT NOT NULL DEFAULT '', published_at TEXT, seen_at TEXT NOT NULL, content_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'NEW', article_id TEXT REFERENCES posts(id));
        CREATE INDEX IF NOT EXISTS feed_items_status ON feed_items(status, published_at DESC);
        CREATE TABLE IF NOT EXISTS source_health (source_id TEXT PRIMARY KEY, status TEXT NOT NULL, checked_at TEXT NOT NULL, error TEXT, item_count INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS auth_attempts (ip TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS auth_attempts_recent ON auth_attempts(ip, created_at);
        CREATE TABLE IF NOT EXISTS audit_events (id INTEGER PRIMARY KEY, action TEXT NOT NULL, details_json TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS worker_health (id INTEGER PRIMARY KEY CHECK(id=1), heartbeat_at TEXT NOT NULL);
        ''')
        for key, value in DEFAULTS.items():
            conn.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', (key, json.dumps(value)))


def event(action, details):
    with connect() as conn:
        conn.execute('INSERT INTO audit_events(action,details_json,created_at) VALUES (?,?,?)', (action, json.dumps(details, ensure_ascii=False), now()))


def get_settings():
    with connect() as conn:
        result = DEFAULTS | {r['key']: json.loads(r['value']) for r in conn.execute('SELECT * FROM settings') if r['key'] in DEFAULTS}
        result['stats'] = {k.lower(): conn.execute('SELECT COUNT(*) FROM posts WHERE status=?',(k,)).fetchone()[0] for k in ['PUBLISHED','DRAFT','ARCHIVED']}
        result['feeds'] = [dict(r) for r in conn.execute('SELECT * FROM source_health ORDER BY source_id')]
        result['feedItemsCount'] = conn.execute("SELECT COUNT(*) FROM feed_items WHERE status='NEW'").fetchone()[0]
        result['worker'] = dict(conn.execute('SELECT * FROM worker_health WHERE id=1').fetchone() or {})
    result['provider'] = config.provider_info()
    return result


def get_password_hash():
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='adminPasswordHash'").fetchone()
    if row and row['value']:
        try:
            value = json.loads(row['value'])
            if isinstance(value, str) and value.startswith('scrypt$'):
                return value
        except Exception:
            pass
    return config.ADMIN_PASSWORD_HASH


def set_password_hash(encoded, actor='admin'):
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO settings VALUES ('adminPasswordHash',?)", (json.dumps(encoded),))
    event('auth.password_changed', {'actor': actor})


def update_settings(values):
    with connect() as conn:
        for key, value in values.items():
            if key in DEFAULTS:
                conn.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value, ensure_ascii=False)))
    event('settings.updated', {key: value for key,value in values.items() if key != 'editorialGuidance'})
    return get_settings()


def post_dict(row, admin=False):
    if row is None:
        return None
    item = dict(row)
    result = {'id': item['id'], 'slug': item['slug'], 'title':item['title'], 'excerpt':item['excerpt'], 'abstract':item['abstract'], 'keywords':json.loads(item['keywords']), 'tags':json.loads(item['tags']), 'category':item['category'], 'contentHtml':render_markdown(item['body_markdown']), 'status':item['status'], 'version':item['version'], 'references':json.loads(item['references_json']), 'createdAt':item['created_at'], 'updatedAt':item['updated_at'], 'publishedAt':item['published_at'], 'date':(item['published_at'] or item['created_at'])[:10], 'readTime':read_time(item['body_markdown']), 'author':config.AUTHOR, 'authorBio':config.AUTHOR_BIO}
    if admin:
        result['bodyMarkdown'] = item['body_markdown']
    else:
        result['contentHtml'] = monetization.monetize(result['contentHtml'], result)
    return result


def list_posts(public=False, limit=200):
    with connect() as conn:
        condition = "WHERE status='PUBLISHED'" if public else ''
        rows = conn.execute(f'SELECT * FROM posts {condition} ORDER BY COALESCE(published_at,created_at) DESC LIMIT ?', (limit,)).fetchall()
    return [post_dict(row, not public) for row in rows]


def get_post(identifier, public=False):
    with connect() as conn:
        if public:
            row = conn.execute("SELECT * FROM posts WHERE slug=? AND status='PUBLISHED'", (identifier,)).fetchone()
        else:
            row = conn.execute('SELECT * FROM posts WHERE id=?', (identifier,)).fetchone()
    return post_dict(row, not public)


class VersionConflict(ValueError):
    pass


def save_post(data, post_id=None, expected_version=None, actor='worker', generation_id=None):
    timestamp = now()
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        old = conn.execute('SELECT * FROM posts WHERE id=?', (post_id,)).fetchone() if post_id else None
        if post_id and not old:
            raise LookupError('Artigo não encontrado.')
        if old and expected_version != old['version']:
            raise VersionConflict('Este artigo foi alterado em outra sessão. Recarregue antes de salvar.')
        post_id = post_id or uuid.uuid4().hex
        status = data.get('status', 'DRAFT')
        published_at = (old['published_at'] if old else None) or (timestamp if status == 'PUBLISHED' else None)
        references = data.get('references', json.loads(old['references_json']) if old else [])
        values = (data['slug'],data['title'],data.get('excerpt',''),data.get('abstract',''),json.dumps(data.get('keywords',[]),ensure_ascii=False),json.dumps(data.get('tags',[]),ensure_ascii=False),data.get('category','Análise'),data.get('bodyMarkdown',''),json.dumps(references,ensure_ascii=False),status,timestamp,published_at)
        if old:
            conn.execute('INSERT INTO post_revisions(post_id,version,snapshot_json,actor,created_at) VALUES(?,?,?,?,?)', (post_id,old['version'],json.dumps(post_dict(old,True),ensure_ascii=False),actor,timestamp))
            conn.execute('UPDATE posts SET slug=?,title=?,excerpt=?,abstract=?,keywords=?,tags=?,category=?,body_markdown=?,references_json=?,status=?,updated_at=?,published_at=?,version=version+1 WHERE id=?', (*values,post_id))
        else:
            conn.execute('INSERT INTO posts(slug,title,excerpt,abstract,keywords,tags,category,body_markdown,references_json,status,updated_at,published_at,id,created_at,generation_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (*values,post_id,timestamp,generation_id))
        row = conn.execute('SELECT * FROM posts WHERE id=?',(post_id,)).fetchone()
    event('post.saved', {'id':post_id,'actor':actor,'status':status,'version':row['version']})
    return post_dict(row, True)


def revisions(post_id):
    with connect() as conn:
        return [{'id':r['id'],'version':r['version'],'actor':r['actor'],'createdAt':r['created_at'],'post':json.loads(r['snapshot_json'])} for r in conn.execute('SELECT * FROM post_revisions WHERE post_id=? ORDER BY id DESC LIMIT 30',(post_id,))]


def set_post_status(post_id, status, actor='admin'):
    if status not in {'DRAFT', 'PUBLISHED', 'ARCHIVED'}:
        raise ValueError('Estado de artigo inválido.')
    timestamp = now()
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        old = conn.execute('SELECT * FROM posts WHERE id=?', (post_id,)).fetchone()
        if not old:
            raise LookupError('Artigo não encontrado.')
        published_at = old['published_at'] or (timestamp if status == 'PUBLISHED' else None)
        conn.execute('INSERT INTO post_revisions(post_id,version,snapshot_json,actor,created_at) VALUES(?,?,?,?,?)', (post_id, old['version'], json.dumps(post_dict(old, True), ensure_ascii=False), actor, timestamp))
        conn.execute('UPDATE posts SET status=?,updated_at=?,published_at=?,version=version+1 WHERE id=?', (status, timestamp, published_at, post_id))
        row = conn.execute('SELECT * FROM posts WHERE id=?', (post_id,)).fetchone()
    event('post.status_changed', {'id': post_id, 'actor': actor, 'status': status, 'version': row['version']})
    return post_dict(row, True)


def delete_post(post_id, actor='admin'):
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        old = conn.execute('SELECT id, title, slug FROM posts WHERE id=?', (post_id,)).fetchone()
        if not old:
            raise LookupError('Artigo não encontrado.')
        conn.execute('DELETE FROM post_revisions WHERE post_id=?', (post_id,))
        conn.execute('UPDATE jobs SET post_id=NULL WHERE post_id=?', (post_id,))
        conn.execute("UPDATE feed_items SET article_id=NULL, status='NEW' WHERE article_id=?", (post_id,))
        conn.execute('DELETE FROM posts WHERE id=?', (post_id,))
    event('post.deleted', {'id': post_id, 'slug': old['slug'], 'title': old['title'], 'actor': actor})
    return {'deleted': True, 'id': post_id}


def delete_job(job_id):
    with connect() as conn:
        row = conn.execute('SELECT status FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row:
            raise LookupError('Trabalho não encontrado.')
        if row['status'] == 'RUNNING':
            raise ValueError('Aguarde o término do trabalho em andamento antes de removê-lo.')
        conn.execute('DELETE FROM jobs WHERE id=?', (job_id,))
    return {'deleted': True, 'id': job_id}


def job_dict(row):
    if row is None:
        return None
    result = dict(row)
    result['payload'] = json.loads(result.pop('payload_json'))
    result['createdAt'] = result['created_at']
    result['postId'] = result['post_id']
    return result


class QueueFull(ValueError):
    pass


def queue_job(payload, trigger='MANUAL', due_key=None, max_pending=None):
    job_id = uuid.uuid4().hex
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if max_pending is not None and conn.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('QUEUED','RUNNING')").fetchone()[0] >= max_pending:
            raise QueueFull('Há cinco trabalhos aguardando. Aguarde a conclusão antes de gerar novamente.')
        conn.execute('INSERT OR IGNORE INTO jobs(id,status,payload_json,trigger,due_key,created_at) VALUES(?,?,?,?,?,?)', (job_id,'QUEUED',json.dumps(payload,ensure_ascii=False),trigger,due_key,now()))
        row = conn.execute('SELECT * FROM jobs WHERE due_key=?' if due_key else 'SELECT * FROM jobs WHERE id=?',(due_key or job_id,)).fetchone()
    return job_dict(row)


def claim_job():
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        stale = (datetime.now(timezone.utc)-timedelta(minutes=20)).isoformat()
        # A crashed job can be retried, while generation_id prevents a second post.
        conn.execute("UPDATE jobs SET status='QUEUED' WHERE status='RUNNING' AND COALESCE(heartbeat_at,started_at)<? AND attempt<3",(stale,))
        conn.execute("UPDATE jobs SET status='FAILED', error='Trabalho interrompido após três tentativas.',completed_at=? WHERE status='RUNNING' AND COALESCE(heartbeat_at,started_at)<? AND attempt>=3",(now(),stale))
        if conn.execute("SELECT 1 FROM jobs WHERE status='RUNNING' LIMIT 1").fetchone():
            return None
        row=conn.execute("SELECT * FROM jobs WHERE status='QUEUED' ORDER BY created_at LIMIT 1").fetchone()
        if row is None:
            return None
        conn.execute("UPDATE jobs SET status='RUNNING',started_at=?,heartbeat_at=?,attempt=attempt+1 WHERE id=?",(now(),now(),row['id']))
        row=conn.execute('SELECT * FROM jobs WHERE id=?',(row['id'],)).fetchone()
    return job_dict(row)


def get_job(job_id):
    with connect() as conn:
        return job_dict(conn.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone())


def list_jobs():
    with connect() as conn:
        return [job_dict(r) for r in conn.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT 30')]


def finish_job(job_id, post_id=None, error=None):
    with connect() as conn:
        conn.execute('UPDATE jobs SET status=?,post_id=?,error=?,completed_at=? WHERE id=?', ('FAILED' if error else 'SUCCEEDED',post_id,str(error)[:1000] if error else None,now(),job_id))


def job_heartbeat(job_id):
    with connect() as conn:
        conn.execute('UPDATE jobs SET heartbeat_at=? WHERE id=?',(now(),job_id))


def worker_heartbeat():
    with connect() as conn:
        conn.execute('INSERT OR REPLACE INTO worker_health VALUES (1,?)',(now(),))
