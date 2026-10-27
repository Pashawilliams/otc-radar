import time
from unittest.mock import Mock
import unittest

from otc_radar.network import AllowedRedirect, Client, FetchError


class NetworkTests(unittest.TestCase):
    def test_unapproved_url_is_rejected_before_open(self):
        client = Client(time.monotonic() + 20)
        client.opener = Mock()
        for url in ['https://evil.example/secret', 'http://t.me/crypto_otc', 'https://user:pass@t.me/crypto_otc']:
            with self.subTest(url=url), self.assertRaises(FetchError):
                client.get(url)
        client.opener.open.assert_not_called()

    def test_redirect_cannot_escape_allowed_hosts(self):
        redirects = AllowedRedirect({'t.me'})
        for url in ['https://evil.example/', 'http://t.me/group', 'https://user:pass@t.me/group']:
            with self.subTest(url=url), self.assertRaises(FetchError):
                redirects.redirect_request(None, None, 302, '', {}, url)

    def test_expired_budget_prevents_network_request(self):
        client = Client(time.monotonic() - 1)
        client.opener = Mock()
        with self.assertRaises(FetchError):
            client.get('https://t.me/crypto_otc')
        client.opener.open.assert_not_called()


if __name__ == '__main__':
    unittest.main()
