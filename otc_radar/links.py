"""Canonical identities: never mistake invite links, posts or bots for groups."""
import re
from urllib.parse import parse_qs, unquote, urlparse

RESERVED = {'s', 'c', 'joinchat', 'addlist', 'addstickers', 'addemoji', 'share',
            'proxy', 'socks', 'login', 'iv', 'boost', 'contact', 'invoice', 'giftcode'}
USERNAME = re.compile(r'[a-zA-Z][a-zA-Z0-9_]{3,31}\Z')


def username(value):
    value = unquote(str(value)).strip()
    if value.startswith('@'):
        value = value[1:]
    if '://' in value or value.lower().startswith(('t.me/', 'telegram.me/', 'telegram.dog/')):
        url = urlparse(value if '://' in value else 'https://' + value)
        if url.scheme == 'tg' and url.netloc == 'resolve':
            value = parse_qs(url.query).get('domain', [''])[0]
        elif url.scheme in ('https', 'http') and url.hostname in ('t.me', 'telegram.me', 'telegram.dog', 'www.t.me'):
            parts = url.path.strip('/').split('/')
            value = parts[1] if parts[0] == 's' and len(parts) > 1 else parts[0]
        else:
            return None
    if not USERNAME.fullmatch(value):
        return None
    value = value.lower()
    return None if value in RESERVED or value.endswith('bot') else value


def extract(text):
    candidates = re.findall(r'(?:https?://)?(?:t\.me|telegram\.me|telegram\.dog)/[^\s<>"\']+|(?<![\w])@[a-zA-Z][a-zA-Z0-9_]{3,31}', text)
    return {handle for item in candidates if (handle := username(item.rstrip(').,!?;:]}')))}
