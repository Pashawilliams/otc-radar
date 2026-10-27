from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch
import unittest

from otc_radar import cli
from otc_radar.network import FetchError
from otc_radar.storage import read, write


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(cli, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.api_patch = patch.object(cli.telegram_api, 'configured', return_value=False)
        self.api_patch.start()
        self.addCleanup(self.api_patch.stop)
        write(self.root / 'config/sources.json', {'seeds': [], 'pages': [], 'allowed_hosts': []})

    def run_collector(self, category='all'):
        args = Namespace(category=category, budget_seconds=25, max_profiles=2, max_searches=0, target=1500)
        with redirect_stdout(StringIO()):
            return cli.run(args)

    def test_switching_scope_preserves_collected_groups(self):
        chats = [
            {'id': None, 'username': 'crypto_otc', 'category': 'crypto', 'first_seen': '2026-10-01T00:00:00+00:00', 'last_checked': '2026-10-01T00:00:00+00:00', 'source_urls': []},
            {'id': None, 'username': 'gifts_otc', 'category': 'gifts', 'first_seen': '2026-10-01T00:00:00+00:00', 'last_checked': '2026-10-01T00:00:00+00:00', 'source_urls': []},
        ]
        write(self.root / 'data/state.json', {'schema_version': 1, 'candidates': {}, 'sources': {}, 'query_cursor': 0, 'verified_chats': chats})
        write(self.root / 'web/data/chats.json', {'chats': chats})
        self.run_collector('crypto')
        selected = read(self.root / 'web/data/chats.json', {})['chats']
        self.assertEqual([row['username'] for row in selected], ['crypto_otc'])
        self.run_collector('all')
        selected = read(self.root / 'web/data/chats.json', {})['chats']
        self.assertEqual({row['username'] for row in selected}, {'crypto_otc', 'gifts_otc'})

    def test_network_failure_keeps_previous_snapshot_and_success_timestamp(self):
        chat = {'id': None, 'username': 'crypto_otc', 'category': 'crypto', 'first_seen': '2026-10-01T00:00:00+00:00', 'last_checked': '2026-10-01T00:00:00+00:00', 'source_urls': []}
        write(self.root / 'config/sources.json', {'seeds': [{'username': 'crypto_otc', 'source_url': 'https://t.me/crypto_otc'}], 'pages': [], 'allowed_hosts': []})
        write(self.root / 'web/data/chats.json', {'chats': [chat]})
        write(self.root / 'web/data/status.json', {'last_success': '2026-10-01T00:00:00+00:00'})
        with patch.object(cli.Client, 'get', side_effect=FetchError('HTTP 503')):
            result = self.run_collector()
        self.assertEqual(result, 1)
        self.assertEqual(read(self.root / 'web/data/chats.json', {})['chats'], [chat])
        status = read(self.root / 'web/data/status.json', {})
        self.assertEqual(status['state'], 'error')
        self.assertEqual(status['last_success'], '2026-10-01T00:00:00+00:00')
        self.assertEqual(status['verified_count'], 1)
        self.assertEqual(status['errors'][0]['message'], 'HTTP 503')

    def test_api_attempts_advance_queue_and_leave_uninspected_candidates_pending(self):
        seeds = [{'username': handle, 'source_url': 'https://t.me/' + handle}
                 for handle in ('aaaa_otc', 'bbbb_otc', 'cccc_otc')]
        write(self.root / 'config/sources.json', {'seeds': seeds, 'pages': [], 'allowed_hosts': []})
        provider = AsyncMock(return_value=([], set(), [], {
            'aaaa_otc': 'irrelevant_or_not_public_group',
            'bbbb_otc': 'request_failed',
        }))
        with patch.object(cli.telegram_api, 'configured', return_value=True), \
                patch.object(cli.telegram_api, 'collect', provider):
            self.run_collector()
        candidates = read(self.root / 'data/state.json', {})['candidates']
        for handle in ('aaaa_otc', 'bbbb_otc'):
            self.assertEqual(candidates[handle]['attempts'], 1)
            self.assertIsNotNone(candidates[handle]['last_attempt'])
        self.assertEqual(candidates['cccc_otc']['attempts'], 0)
        self.assertIsNone(candidates['cccc_otc']['last_attempt'])
        self.assertEqual(read(self.root / 'web/data/status.json', {})['inspected_this_run'], 2)
        provider = AsyncMock(return_value=([], set(), [], {}))
        with patch.object(cli.telegram_api, 'configured', return_value=True), \
                patch.object(cli.telegram_api, 'collect', provider):
            self.run_collector()
        self.assertEqual(provider.call_args.args[0], ['cccc_otc'])


if __name__ == '__main__':
    unittest.main()
