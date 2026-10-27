import re
from html import unescape
from urllib.parse import urlencode, urljoin, urlparse, parse_qs

from .links import extract, username

QUERIES = {
    'crypto': ['site:t.me OTC криптовалюта чат', 'site:t.me OTC USDT обмен русский',
               'site:t.me OTC крипто торговля', 'site:t.me OTC токены покупка продажа'],
    'gifts': ['site:t.me OTC подарки чат', 'site:t.me OTC NFT подарки продажа',
              'site:t.me OTC Telegram gifts русский', 'site:t.me OTC стикеры чат'],
}


def queries(category):
    return QUERIES['crypto'] + QUERIES['gifts'] if category == 'all' else QUERIES[category]


def search_url(query):
    return 'https://www.bing.com/search?' + urlencode({'q': query, 'format': 'rss', 'count': 50})


def directory_links(html, base_url):
    """Only explicitly configured public catalog paths become crawl targets."""
    handles = extract(unescape(html))
    host = urlparse(base_url).hostname
    pages = set()
    for raw in re.findall(r'href\s*=\s*[\"\']([^\"\']+)', html, re.I):
        target = urljoin(base_url, unescape(raw))
        parsed = urlparse(target)
        if parsed.hostname != host or parsed.scheme != 'https':
            continue
        if host == 'chatcrawler.link':
            match = re.fullmatch(r'/v/([a-zA-Z0-9_]+)/?', parsed.path)
            if match and (handle := username(match[1])):
                handles.add(handle)
            if parsed.path == urlparse(base_url).path and 'p' in parse_qs(parsed.query):
                pages.add(target.split('#')[0])
        elif host == 'tgpulse.com':
            query = parse_qs(parsed.query)
            if parsed.path == '/ru/search' and query.get('search', [''])[0].lower() == 'otc' and 'page' in query:
                pages.add(target.split('#')[0])
    return handles, pages
