import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException, Request

from . import config, db

COOKIE_NAME = '__Host-blog_session' if config.COOKIE_SECURE else 'blog_session'


def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return 'scrypt$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(digest).decode()


def verify_password(password, encoded):
    try:
        algorithm, salt, expected = encoded.split('$')
        if algorithm != 'scrypt' or len(password) > 1024:
            return False
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(digest, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_session():
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=config.SESSION_HOURS)).isoformat()
    with db.connect() as conn:
        conn.execute('DELETE FROM sessions WHERE expires_at<?',(db.now(),))
        conn.execute('INSERT INTO sessions VALUES(?,?,?)',(token_hash(token), csrf, expires))
    return token, csrf


def require_session(request: Request):
    token = request.cookies.get(COOKIE_NAME, '')
    with db.connect() as conn:
        session = conn.execute('SELECT * FROM sessions WHERE token_hash=? AND expires_at>?',(token_hash(token),db.now())).fetchone()
    if not session:
        raise HTTPException(401,'Entre no painel para continuar.')
    if request.method not in {'GET','HEAD','OPTIONS'}:
        csrf = request.headers.get('x-csrf-token','')
        if not hmac.compare_digest(csrf, session['csrf']):
            raise HTTPException(403,'Sessão de edição inválida. Recarregue o painel.')
    return dict(session)


def check_login_rate(request):
    ip = request.client.host if request.client else 'unknown'
    cutoff = (datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()
    with db.connect() as conn:
        conn.execute('DELETE FROM auth_attempts WHERE created_at<?',(cutoff,))
        count = conn.execute('SELECT COUNT(*) FROM auth_attempts WHERE ip=?',(ip,)).fetchone()[0]
        # The account also has a global budget: forwarded headers can never
        # create unlimited fresh login buckets even behind a changed proxy.
        total = conn.execute('SELECT COUNT(*) FROM auth_attempts').fetchone()[0]
        if count >= 8 or total >= 24:
            raise HTTPException(429,'Muitas tentativas. Aguarde 15 minutos antes de tentar novamente.')
        conn.execute('INSERT INTO auth_attempts VALUES(?,?)',(ip,db.now()))


def clear_attempts(request):
    with db.connect() as conn:
        conn.execute('DELETE FROM auth_attempts WHERE ip=?',(request.client.host if request.client else 'unknown',))
