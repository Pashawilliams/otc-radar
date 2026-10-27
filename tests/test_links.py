import unittest

from otc_radar.links import extract, username


class LinkTests(unittest.TestCase):
    def test_canonicalizes_aliases_posts_and_case(self):
        values = ['@Crypto_OTC', 'crypto_otc', 'https://t.me/CRYPTO_OTC',
                  'http://telegram.me/Crypto_OTC/123?comment=2',
                  'https://t.me/s/Crypto_OTC/123', 'tg://resolve?domain=Crypto_OTC']
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(username(value), 'crypto_otc')

    def test_rejects_invites_private_posts_accounts_bots_and_other_hosts(self):
        values = ['https://t.me/+secretHash', 'https://t.me/joinchat/secretHash',
                  'https://t.me/c/123456/2', 'https://t.me/share/url?url=x',
                  'https://t.me/addlist/secretHash', 'https://evil.example/crypto_otc',
                  'https://t.me/collectBot', '@123numeric', '@bad-name']
        for value in values:
            with self.subTest(value=value):
                self.assertIsNone(username(value))

    def test_extraction_deduplicates_links_and_mentions(self):
        result = extract('@Crypto_OTC https://t.me/crypto_otc https://t.me/s/CRYPTO_OTC/12 @Other_OTC')
        self.assertEqual(result, {'crypto_otc', 'other_otc'})

    def test_parenthesized_plaintext_links_are_discovered(self):
        self.assertIn('crypto_otc', extract('Группа (https://t.me/crypto_otc).'))


if __name__ == '__main__':
    unittest.main()
