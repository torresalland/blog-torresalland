import os
import re
import json
from pathlib import Path

secret_file = Path(os.environ.get('BLOG_SECRETS_FILE','/run/secrets/blog_runtime'))
if secret_file.is_file():
    # Docker secret: no credential is stored in the image or printed in logs.
    for key, value in json.loads(secret_file.read_text(encoding='utf-8')).items():
        os.environ.setdefault(key, str(value))

ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = Path(os.environ.get('DATABASE_PATH', str(ROOT / 'data' / 'blog.sqlite3')))
PUBLIC_ORIGIN = os.environ.get('PUBLIC_ORIGIN', 'http://127.0.0.1:4300').rstrip('/')
PREVIEW_ORIGIN = os.environ.get('PREVIEW_ORIGIN', '').rstrip('/')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'allan')
ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH', '')
COOKIE_SECURE = PUBLIC_ORIGIN.startswith('https://')
SESSION_HOURS = 12
AUTHOR = 'Állan Torres'
AUTHOR_BIO = 'Head of Legal & AI na Hubex Trade | Direito (UFRN), Inteligência Artificial, Automação & Negócios Internacionais.'
AUTHOR_JOB_TITLE = 'Head of Legal & AI'
PORTFOLIO_URL = 'https://torresalland.cloud'
# Only profiles verified as public. Extra ones (e.g. LinkedIn) via AUTHOR_SAME_AS="url1,url2".
AUTHOR_SAME_AS = list(dict.fromkeys(
    ['https://github.com/torresalland']
    + [u.strip() for u in os.environ.get('AUTHOR_SAME_AS', '').split(',') if u.strip().startswith('https://')]
))
# IndexNow: 8-128 chars [A-Za-z0-9-]. Empty disables submission and the key file.
INDEXNOW_KEY = os.environ.get('INDEXNOW_KEY', '').strip()


# Monetização na leitura (ver monetization.py). Sem número, o CTA da Yuki fica desligado.
YUKI_WHATSAPP = re.sub(r'\D', '', os.environ.get('YUKI_WHATSAPP', ''))
AFFILIATE_ENABLED = os.environ.get('AFFILIATE_ENABLED', '').lower() in ('1', 'true', 'yes')
AFFILIATE_FILE = Path(os.environ.get('AFFILIATE_FILE', str(ROOT / 'backend' / 'affiliate_links.json')))
AFFILIATE_MAX_PER_POST = int(os.environ.get('AFFILIATE_MAX_PER_POST', '3'))


def provider_info():
    provider = os.environ.get('LLM_PROVIDER', 'gemini')
    key_name = {'gemini': 'GEMINI_API_KEY', 'openai': 'OPENAI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY'}.get(provider, '')
    return {'name': provider, 'model': os.environ.get('LLM_MODEL', ''), 'configured': bool(key_name and os.environ.get(key_name))}
