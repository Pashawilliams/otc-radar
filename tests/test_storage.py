from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from otc_radar.storage import merge, read, write


def chat(handle, *, chat_id=None, first_seen='2026-10-20T00:00:00+00:00', source='https://source.example/first'):
    return {'id': chat_id, 'username': handle, 'first_seen': first_seen,
            'last_checked': '2026-10-27T00:00:00+00:00', 'source_urls': [source],
            'members': 10, 'online': None}


class StorageTests(unittest.TestCase):
    def test_same_handle_does_not_duplicate_and_keeps_first_seen(self):
        chats = [chat('crypto_otc')]
        merge(chats, chat('crypto_otc', first_seen='2026-10-27T00:00:00+00:00', source='https://source.example/second'))
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0]['first_seen'], '2026-10-20T00:00:00+00:00')
        self.assertEqual(len(chats[0]['source_urls']), 2)
        self.assertNotIn('crypto_otc', chats[0].get('aliases', []))

    def test_telegram_id_deduplicates_a_renamed_group(self):
        chats = [chat('old_otc', chat_id='12345')]
        merge(chats, chat('new_otc', chat_id='12345', first_seen='2026-10-27T00:00:00+00:00'))
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0]['username'], 'new_otc')
        self.assertEqual(chats[0]['id'], '12345')
        self.assertEqual(chats[0]['aliases'], ['old_otc'])
        self.assertEqual(chats[0]['first_seen'], '2026-10-20T00:00:00+00:00')

    def test_public_refresh_keeps_known_stable_id(self):
        chats = [chat('crypto_otc', chat_id='12345')]
        merge(chats, chat('crypto_otc'))
        self.assertEqual(chats[0]['id'], '12345')

    def test_reused_handle_does_not_inherit_another_groups_history(self):
        chats = [chat('crypto_otc', chat_id='12345', source='https://old.example/')]
        incoming = chat('crypto_otc', chat_id='98765', first_seen='2026-10-27T00:00:00+00:00', source='https://new.example/')
        merge(chats, incoming)
        self.assertEqual(chats, [incoming])
        self.assertEqual(chats[0]['first_seen'], '2026-10-27T00:00:00+00:00')
        self.assertNotIn('https://old.example/', chats[0]['source_urls'])

    def test_different_groups_with_unknown_ids_stay_distinct(self):
        first = chat('first_otc')
        chats = [deepcopy(first)]
        merge(chats, chat('second_otc'))
        self.assertEqual(len(chats), 2)
        self.assertIn(first, chats)

    def test_atomic_json_round_trip_and_missing_default(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / 'nested/state.json'
            self.assertEqual(read(path, {'initial': True}), {'initial': True})
            write(path, {'title': 'Русский OTC', 'online': None})
            self.assertEqual(read(path, {}), {'title': 'Русский OTC', 'online': None})
            self.assertFalse(path.with_suffix('.json.tmp').exists())


if __name__ == '__main__':
    unittest.main()
