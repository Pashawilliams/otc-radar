import unittest

from otc_radar.profiles import classify, count, parse_profile


CHECKED = '2026-10-27T00:00:00+00:00'


def profile(extra, *, title='OTC Криптовалюты', description='Покупка и продажа криптовалюты', canonical=None):
    meta = f'<meta property="og:url" content="{canonical}">' if canonical else ''
    return (meta + f'<div class="tgme_page_title"><span dir="auto">{title}</span></div>'
            f'<div class="tgme_page_extra">{extra}</div>'
            f'<div class="tgme_page_description">{description}</div>')


class ProfileTests(unittest.TestCase):
    def test_group_members_online_and_links_are_parsed(self):
        html = profile('1\u00a0234 members, 56 online', description='Обмен криптовалют. Чат <a href="https://t.me/second_otc">@second_otc</a>')
        group, discovered = parse_profile(html, 'FIRST_OTC', CHECKED)
        self.assertEqual(group['username'], 'first_otc')
        self.assertEqual(group['members'], 1234)
        self.assertEqual(group['online'], 56)
        self.assertTrue(group['verified'])
        self.assertEqual(group['last_checked'], CHECKED)
        self.assertIn('second_otc', discovered)

    def test_missing_online_is_unknown_not_zero(self):
        group, _ = parse_profile(profile('23 members'), 'crypto_otc', CHECKED)
        self.assertIsNone(group['online'])

    def test_zero_online_remains_zero(self):
        group, _ = parse_profile(profile('23 members, 0 online'), 'crypto_otc', CHECKED)
        self.assertEqual(group['online'], 0)

    def test_channel_person_bot_and_unavailable_page_are_excluded(self):
        cases = [
            (profile('123 subscribers'), 'crypto_otc'),
            (profile('@some_person'), 'crypto_otc'),
            (profile('123 members'), 'crypto_otc_bot'),
            ('<p>If you have Telegram, you can contact @crypto_otc</p>', 'crypto_otc'),
        ]
        for html, handle in cases:
            with self.subTest(handle=handle, html=html):
                group, _ = parse_profile(html, handle, CHECKED)
                self.assertIsNone(group)

    def test_canonical_url_normalizes_renamed_group(self):
        group, _ = parse_profile(profile('20 members', canonical='https://t.me/NEW_OTC'), 'old_otc', CHECKED)
        self.assertEqual(group['username'], 'new_otc')

    def test_group_must_have_otc_and_russian_profile_evidence(self):
        self.assertIsNone(classify('OTC Exchange', 'Buy and sell USDT', 'crypto_otc'))
        self.assertIsNone(classify('Обмен криптовалюты', 'Купить и продать USDT', 'crypto_exchange'))
        self.assertIsNone(classify('OTC Общение', 'Обсуждение музыки и фотографии', 'music_otc'))

    def test_gifts_crypto_and_mixed_categories(self):
        self.assertEqual(classify('OTC Подарки', 'Покупка и продажа NFT', 'gifts_otc'), 'gifts')
        self.assertEqual(classify('OTC Криптообмен', 'Продажа криптовалют', 'crypto_otc'), 'crypto')
        self.assertEqual(classify('OTC Подарки', 'Подарки и криптовалюта', 'mixed_otc'), 'mixed')

    def test_abbreviated_and_localized_member_counts(self):
        for value, expected in [('1 234', 1234), ('1.5K', 1500), ('2,5М', 2500000), ('0', 0), ('?', None)]:
            with self.subTest(value=value):
                self.assertEqual(count(value), expected)


if __name__ == '__main__':
    unittest.main()
