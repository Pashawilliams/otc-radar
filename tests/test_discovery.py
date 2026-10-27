import unittest
from urllib.parse import parse_qs, urlparse

from otc_radar.discovery import directory_links, queries, search_url


class DiscoveryTests(unittest.TestCase):
    def test_chatcrawler_catalog_handles_and_same_catalog_pages(self):
        base = 'https://chatcrawler.link/ru/c/t/telegram/gifts/groups?lang=ru'
        html = ('<a href="/v/Crypto_OTC">Чат</a>'
                '<a href="/v/CollectBot">Бот</a>'
                '<a href="?lang=ru&amp;p=2">2</a>'
                '<a href="https://evil.example/?p=3">3</a>'
                '<a href="/elsewhere?p=4">Other</a>')
        handles, pages = directory_links(html, base)
        self.assertEqual(handles, {'crypto_otc'})
        self.assertEqual(pages, {'https://chatcrawler.link/ru/c/t/telegram/gifts/groups?lang=ru&p=2'})

    def test_direct_tme_links_are_discovered_from_catalogs(self):
        handles, _ = directory_links('<a href="https://t.me/CRYPTO_OTC">Чат</a>', 'https://topgramcat.com/?platform=telegram')
        self.assertIn('crypto_otc', handles)

    def test_tgpulse_only_follows_otc_search_pagination(self):
        base = 'https://tgpulse.com/ru/search?order=best&search=Otc'
        html = ('<a href="/ru/search?order=best&amp;search=Otc&amp;page=2">2</a>'
                '<a href="/ru/search?search=Music&amp;page=2">Music</a>'
                '<a href="/en/search?search=Otc&amp;page=2">English</a>'
                '<a href="https://evil.example/ru/search?search=Otc&amp;page=2">Other</a>')
        _, pages = directory_links(html, base)
        self.assertEqual(pages, {'https://tgpulse.com/ru/search?order=best&search=Otc&page=2'})

    def test_topgramcat_disallowed_pagination_is_not_queued(self):
        _, pages = directory_links('<a href="/?platform=telegram&amp;p=2">2</a>', 'https://topgramcat.com/?platform=telegram')
        self.assertEqual(pages, set())

    def test_query_encoding_and_scope_are_deterministic(self):
        query = 'site:t.me OTC криптовалюта чат'
        parsed = parse_qs(urlparse(search_url(query)).query)
        self.assertEqual(parsed['q'], [query])
        self.assertEqual(parsed['format'], ['rss'])
        self.assertEqual(queries('all'), queries('crypto') + queries('gifts'))


if __name__ == '__main__':
    unittest.main()
