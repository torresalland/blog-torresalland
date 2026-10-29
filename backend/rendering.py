import re
import html
import math

import bleach
from markdown_it import MarkdownIt
from pygments import highlight
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.formatters import HtmlFormatter


def code_highlight(code, language, attrs=''):
    try:
        lexer = get_lexer_by_name(language) if language else TextLexer()
    except Exception:
        lexer = TextLexer()
    return highlight(code, lexer, HtmlFormatter(nowrap=True))


MARKDOWN = MarkdownIt('commonmark', {'html': False, 'linkify': False, 'typographer': False, 'highlight': code_highlight}).enable('table')
TAGS = {'p','h1','h2','h3','h4','h5','h6','ul','ol','li','strong','em','a','blockquote','pre','code','hr','br','table','thead','tbody','tr','th','td','span','s'}


def render_markdown(text):
    rendered = MARKDOWN.render(str(text)[:200000])
    return bleach.clean(rendered, tags=TAGS, attributes={'a': ['href', 'title'], 'code': ['class'], 'span': ['class'], 'th':['align'], 'td':['align']}, protocols=['https','http','mailto'], strip=True)


def read_time(text):
    return f'{max(1, math.ceil(len(re.findall(r"\w+", text)) / 210))} min de leitura'


def safe_excerpt(text, length=240):
    return re.sub(r'\s+', ' ', re.sub(r'[#*_`\[\]<>]', '', text)).strip()[:length]
