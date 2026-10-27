import re
import unicodedata
from html.parser import HTMLParser

from .links import extract, username


class TelegramPage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.fields = {'title': [], 'description': [], 'extra': []}
        self.links = []
        self.canonical = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        field = next((name for name in self.fields if 'tgme_page_' + name in classes), None)
        if tag not in ('meta', 'link', 'img', 'br', 'input', 'hr', 'source', 'wbr'):
            self.stack.append((tag, field))
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonical = attrs.get('href')
        if tag == 'meta' and attrs.get('property') == 'og:url':
            self.canonical = attrs.get('content')

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        for field in {field for _, field in self.stack if field}:
            self.fields[field].append(data)

    def field(self, name):
        return ' '.join(' '.join(self.fields[name]).split())


def count(value):
    value = value.replace('\u00a0', '').replace('\u202f', '').replace(' ', '').replace(',', '.')
    match = re.fullmatch(r'(\d+(?:\.\d+)?)([kKmMкКмМ]?)', value)
    if not match:
        return None
    multiplier = {'k': 1000, 'к': 1000, 'm': 1000000, 'м': 1000000}.get(match[2].lower(), 1)
    return int(float(match[1]) * multiplier)


def classify(title, description, handle):
    text = unicodedata.normalize('NFKC', title + ' ' + description).lower()
    # Cyrillic alone is an explicit heuristic, not proof of every message's language.
    if len(re.findall('[а-яё]', text)) < 3:
        return None
    otc = 'otc' in handle or bool(re.search(r'\botc\b|\bот[сc]\b', text))
    if not otc:
        return None
    gifts = bool(re.search(r'подар[ко]|подарки|gift|\bnft\b|стикер', text))
    crypto = bool(re.search(r'криптовалют|криптообмен|обмен\w* (?:usdt|btc|крипт)|купить usdt|продать btc', text))
    if gifts:
        return 'mixed' if crypto else 'gifts'
    return 'crypto' if crypto or re.search(r'\b(?:crypto|usdt|btc|binance|p2p)\b', text) else None


def parse_profile(html, requested_handle, checked_at):
    page = TelegramPage()
    page.feed(html)
    title, description, extra = (page.field(name) for name in ('title', 'description', 'extra'))
    number = r'([\d][\d\s\u00a0\u202f.,]*\s*[kKmMкКмМ]?)'
    members = re.search(number + r'\s+(?:members?|участник\w*)', extra, re.I)
    handle = username(page.canonical or '') or username(requested_handle)
    category = classify(title, description, handle or '')
    links = extract(description + ' ' + ' '.join(page.links))
    if not members or not category or not handle:
        return None, links
    online = re.search(number + r'\s+(?:online|в сети)', extra, re.I)
    return {'id': None, 'username': handle, 'title': title, 'description': description,
            'category': category, 'members': count(members[1]),
            'online': count(online[1]) if online else None, 'last_checked': checked_at,
            'first_seen': checked_at, 'evidence_url': 'https://t.me/' + handle,
            'source_urls': [], 'verified': True, 'verification_method': 'public_web',
            'language_basis': 'cyrillic_profile'}, links
