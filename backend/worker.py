"""Durable, serialized editorial worker. Run: python -m backend.worker."""
import logging
import signal
import sqlite3
import threading
from datetime import datetime, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx

from . import config, db, generator

LOG = logging.getLogger('blog.worker')
POLL_SECONDS = 15
HEARTBEAT_SECONDS = 20


def schedule_due(settings, current_time=None):
    """One key per civil date and slot. Catch up today's slots after a restart."""
    if not settings.get('schedulerEnabled'):
        return []
    zone_name = settings.get('timezone', 'America/Sao_Paulo')
    zone = ZoneInfo(zone_name)
    current = current_time or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError('O relógio do agendador precisa de fuso horário.')
    local = current.astimezone(zone)
    queued = []
    for slot in settings.get('schedule', ['08:30','18:30']):
        hour, minute = (int(part) for part in slot.split(':'))
        scheduled = local.replace(hour=hour,minute=minute,second=0,microsecond=0)
        if scheduled <= local:
            due_key = f'{zone_name}/{local.date().isoformat()}/{hour:02d}:{minute:02d}'
            queued.append(db.queue_job({},trigger='SCHEDULE',due_key=due_key))
    return queued


def _saved_generation(job_id):
    with db.connect() as conn:
        row = conn.execute('SELECT * FROM posts WHERE generation_id=?',(job_id,)).fetchone()
    return db.post_dict(row,True) if row else None


def _mark_sources(post, source_ids=()):
    """Idempotent and recoverable from the persisted reference metadata."""
    ids = set(source_ids)
    ids.update(reference['sourceItemId'] for reference in post.get('references',[]) if reference.get('sourceItemId'))
    urls = {reference['url'] for reference in post.get('references',[]) if reference.get('url')}
    with db.connect() as conn:
        for source_id in ids:
            conn.execute("UPDATE feed_items SET status='USED',article_id=? WHERE id=?",(post['id'],source_id))
        for url in urls:
            conn.execute("UPDATE feed_items SET status='USED',article_id=? WHERE url=?",(post['id'],url))


def submit_indexnow(slug):
    """Fire-and-forget IndexNow ping (Bing, Yandex and partners); never blocks or fails a job."""
    host = urlsplit(config.PUBLIC_ORIGIN).hostname or ''
    if not config.INDEXNOW_KEY or not config.COOKIE_SECURE or host in {'localhost','127.0.0.1'}:
        return None
    payload = {
        'host': host,
        'key': config.INDEXNOW_KEY,
        'keyLocation': f'{config.PUBLIC_ORIGIN}/{config.INDEXNOW_KEY}.txt',
        'urlList': [f'{config.PUBLIC_ORIGIN}/artigo/{slug}/', f'{config.PUBLIC_ORIGIN}/'],
    }
    def send():
        try:
            with httpx.Client(timeout=httpx.Timeout(15,connect=5),trust_env=False) as client:
                response = client.post('https://api.indexnow.org/indexnow',json=payload,headers={'Content-Type':'application/json; charset=utf-8'})
            # Never log the key or response body.
            LOG.info('IndexNow: HTTP %s para %s.',response.status_code,slug)
        except httpx.HTTPError as exc:
            LOG.warning('IndexNow indisponível (%s); a indexação seguirá pelo sitemap.',type(exc).__name__)
    thread = threading.Thread(target=send,name='indexnow',daemon=True)
    thread.start()
    return thread


def _heartbeat(job_id, done):
    while not done.wait(HEARTBEAT_SECONDS):
        try:
            db.job_heartbeat(job_id)
            db.worker_heartbeat()
        except Exception:
            LOG.error('Não foi possível atualizar o heartbeat do trabalho %s.',job_id)


def run_job(job):
    """Resume persisted output before generating; generation_id is also UNIQUE."""
    done = threading.Event()
    timer = threading.Thread(target=_heartbeat,args=(job['id'],done),daemon=True)
    timer.start()
    try:
        post = _saved_generation(job['id'])
        if post is None:
            payload = generator.generate_article(job)
            source_ids = payload.pop('_sourceItemIds',[])
            # Respect explicit per-job mode or a user's latest switch to DRAFT during a long model call.
            job_mode = (job.get('payload') or {}).get('publicationMode')
            if job_mode in {'DRAFT', 'PUBLISHED'}:
                payload['status'] = job_mode
            elif db.get_settings().get('publicationMode') != 'PUBLISHED':
                payload['status'] = 'DRAFT'
            try:
                post = db.save_post(payload,actor='worker',generation_id=job['id'])
            except sqlite3.IntegrityError:
                post = _saved_generation(job['id'])
                if post is None:
                    raise
            _mark_sources(post,source_ids)
        else:
            _mark_sources(post)
        db.finish_job(job['id'],post_id=post['id'])
        db.event('generation.completed',{'job':job['id'],'post':post['id'],'status':post['status']})
        if post['status'] == 'PUBLISHED':
            submit_indexnow(post['slug'])
        return post
    except Exception as exc:
        # A crash/error after save must not generate or publish another post.
        persisted = _saved_generation(job['id'])
        if persisted:
            _mark_sources(persisted)
            db.finish_job(job['id'],post_id=persisted['id'])
            return persisted
        known = isinstance(exc,(generator.editorial.QualityError,generator.sources.SourceError))
        message = str(exc)[:900] if known else f'Falha interna do trabalho ({type(exc).__name__}); nenhuma publicação foi feita.'
        db.finish_job(job['id'],error=message)
        db.event('generation.failed',{'job':job['id'],'error':message})
        LOG.warning('Trabalho %s falhou: %s',job['id'],message)
        return None
    finally:
        done.set()
        timer.join(timeout=2)
        db.worker_heartbeat()


def run_once(current_time=None):
    db.worker_heartbeat()
    schedule_due(db.get_settings(),current_time)
    job = db.claim_job()
    return run_job(job) if job else None


def main():
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    db.init()
    stopping = threading.Event()
    def stop(_signal,_frame):
        stopping.set()
    for code in (signal.SIGINT,signal.SIGTERM):
        signal.signal(code,stop)
    LOG.info('Worker iniciado; agenda usa o fuso configurado no painel.')
    while not stopping.is_set():
        try:
            run_once()
        except Exception as exc:
            # No source contents, runtime secrets or provider response bodies in logs.
            LOG.error('Falha no ciclo do worker: %s.',type(exc).__name__)
        stopping.wait(POLL_SECONDS)


if __name__ == '__main__':
    main()
