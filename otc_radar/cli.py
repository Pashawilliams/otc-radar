import argparse
import asyncio
import json
import os
from pathlib import Path
import time
from datetime import datetime, timezone

from .discovery import directory_links, queries, search_url
from .links import username
from .network import Client, FetchError
from .profiles import parse_profile
from .storage import read, write, merge
from . import telegram_api

ROOT = Path(__file__).resolve().parent.parent


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def add_candidates(state, handles, source):
    for raw in handles:
        handle = username(raw)
        if not handle or (handle not in state['candidates'] and len(state['candidates']) >= 50000):
            continue
        entry = state['candidates'].setdefault(handle, {'source_urls': [], 'attempts': 0, 'last_attempt': None})
        entry['source_urls'] = sorted(set([*entry['source_urls'], source]))[:12]


def run(args):
    started = now()
    deadline = time.monotonic() + args.budget_seconds
    state = read(ROOT / 'data/state.json', {'schema_version': 1, 'candidates': {}, 'sources': {}, 'query_cursor': 0})
    old_public = read(ROOT / 'web/data/chats.json', {'chats': []})
    chats = state.get('verified_chats', old_public['chats'])
    previous_status = read(ROOT / 'web/data/status.json', {})
    errors, inspected, fetched_sources = [], 0, 0
    source_config = read(ROOT / 'config/sources.json', {'seeds': [], 'pages': [], 'allowed_hosts': []})
    client = Client(deadline, source_config['allowed_hosts'])
    for seed in source_config['seeds']:
        add_candidates(state, [seed['username']], seed['source_url'])
    for page in source_config['pages']:
        state['sources'].setdefault(page, {'last_checked': None})
    # Rotate sources across runs; catalog pagination feeds the same durable queue.
    sources = sorted(state['sources'], key=lambda url: state['sources'][url]['last_checked'] or '')
    for url in sources[:args.max_searches]:
        if time.monotonic() + 20 >= deadline:
            break
        state['sources'][url]['last_checked'] = now()
        try:
            html = client.get(url)
            handles, pages = directory_links(html, url)
            add_candidates(state, handles, url)
            for page in sorted(pages)[:100]:
                if len(state['sources']) < 2000:
                    state['sources'].setdefault(page, {'last_checked': None})
            fetched_sources += 1
        except FetchError as error:
            errors.append({'source': url, 'message': str(error)})
    search_queries = queries(args.category)
    cursor = state.get('query_cursor', 0)
    for offset in range(min(args.max_searches, len(search_queries))):
        if time.monotonic() + 20 >= deadline:
            break
        query = search_queries[(cursor + offset) % len(search_queries)]
        url = search_url(query)
        try:
            handles, _ = directory_links(client.get(url), url)
            add_candidates(state, handles, url)
            fetched_sources += 1
        except FetchError as error:
            errors.append({'source': 'public_search', 'message': str(error)})
    state['query_cursor'] = (cursor + args.max_searches) % len(search_queries)
    known = {row['username']: row for row in chats}
    epoch = time.time()

    def due(handle, entry):
        if not entry['last_attempt']:
            return True
        age = epoch - datetime.fromisoformat(entry['last_attempt']).timestamp()
        return age >= (900 if handle in known or entry.get('result') == 'request_failed' else 7 * 86400)

    pending = [(handle, entry) for handle, entry in state['candidates'].items() if due(handle, entry)]
    new = sorted((item for item in pending if item[0] not in known), key=lambda item: ('otc' not in item[0], item[1]['last_attempt'] or '', item[0]))
    refresh = sorted((item for item in pending if item[0] in known), key=lambda item: known[item[0]]['last_checked'])
    allocation = max(1, args.max_profiles * 2 // 3)
    selected = new[:allocation] + refresh[:args.max_profiles - min(allocation, len(new))]
    selected_handles = {handle for handle, _ in selected}
    selected += [item for item in new[allocation:] if item[0] not in selected_handles][:args.max_profiles - len(selected)]
    use_api = telegram_api.configured()
    if use_api:
        api_found, discovered, problems, outcomes = asyncio.run(telegram_api.collect(
            [handle for handle, _ in selected], ['OTC', 'крипто OTC', 'подарки OTC'][:args.max_searches],
            started, deadline, args.category))
        for row in api_found:
            merge(chats, row)
        add_candidates(state, discovered, 'telegram_global_search')
        for handle, result in outcomes.items():
            add_candidates(state, [handle], 'telegram_global_search')
            entry = state['candidates'][handle]
            entry['last_attempt'] = now()
            entry['attempts'] += 1
            entry['result'] = result
        inspected = len(outcomes)
        errors += [{'source': 'telegram_api', 'message': message} for message in problems]
    else:
        for handle, entry in selected:
            if time.monotonic() + 16 >= deadline:
                break
            inspected += 1
            entry['last_attempt'] = now()
            entry['attempts'] += 1
            url = 'https://t.me/' + handle
            try:
                html = client.get(url)
                group, links = parse_profile(html, handle, now())
                add_candidates(state, links, url)
                entry['result'] = 'irrelevant_or_not_public_group'
                if group and (args.category == 'all' or group['category'] in (args.category, 'mixed')):
                    group['source_urls'] = entry['source_urls']
                    merge(chats, group)
                    entry['result'] = 'verified'
            except FetchError as error:
                entry['result'] = 'request_failed'
                # Transient failures retry on the next run instead of after 7 days.
                entry['last_attempt'] = None
                errors.append({'source': url, 'message': str(error)})
    # A chosen scope changes the public selection, never the underlying candidates.
    public_chats = [row for row in chats if args.category == 'all' or row['category'] in (args.category, 'mixed')]
    # Preserve all verified records separately so changing scope cannot destroy earlier results.
    state['verified_chats'] = chats
    finished = now()
    state['last_run'] = finished
    public = {'schema_version': 1, 'generated_at': finished, 'target': args.target,
              'category_scope': args.category, 'chats': sorted(public_chats, key=lambda row: row['username'])}
    success = inspected > 0 and any(row['last_checked'] >= started for row in public_chats)
    status = {'state': 'partial' if errors or not success else 'ok', 'last_attempt': started,
              'last_success': finished if success else previous_status.get('last_success'),
              'verified_count': len(public_chats), 'candidate_count': len(state['candidates']),
              'inspected_this_run': inspected, 'sources_fetched': fetched_sources,
              'run_url': os.environ.get('GITHUB_SERVER_URL', 'https://github.com') + '/' + os.environ['GITHUB_REPOSITORY'] + '/actions/runs/' + os.environ['GITHUB_RUN_ID'] if os.environ.get('GITHUB_RUN_ID') else None,
              'errors': errors[:20], 'mode': 'mtproto' if use_api else 'public_web', 'refresh_minutes': 15}
    if inspected and not success and errors:
        status['state'] = 'error'
    write(ROOT / 'data/state.json', state)
    write(ROOT / 'web/data/chats.json', public)
    write(ROOT / 'web/data/status.json', status)
    print(json.dumps({key: status[key] for key in ('state', 'verified_count', 'candidate_count', 'inspected_this_run', 'sources_fetched')}, ensure_ascii=False))
    return 0 if success or not errors else 1


def main():
    parser = argparse.ArgumentParser(description='Verify and discover public Russian-language Telegram OTC groups')
    sub = parser.add_subparsers(dest='command', required=True)
    collect = sub.add_parser('collect')
    collect.add_argument('--budget-seconds', type=int, default=300)
    collect.add_argument('--max-profiles', type=int, default=180)
    collect.add_argument('--max-searches', type=int, default=4)
    collect.add_argument('--target', type=int, default=1500)
    collect.add_argument('--category', choices=('crypto', 'gifts', 'all'), default='crypto')
    args = parser.parse_args()
    if not 20 <= args.budget_seconds <= 600 or not 1 <= args.max_profiles <= 1000 or not 0 <= args.max_searches <= 20 or args.target < 1:
        parser.error('Invalid budget, request count or target')
    try:
        raise SystemExit(run(args))
    except Exception as error:
        # Do not include raw exceptions: credential-bearing providers may echo request details.
        try:
            status = read(ROOT / 'web/data/status.json', {})
            status.update({'state': 'error', 'last_attempt': now(),
                           'errors': [{'source': 'collector', 'message': 'Collector stopped: ' + type(error).__name__}],
                           'refresh_minutes': 15})
            write(ROOT / 'web/data/status.json', status)
        except Exception:
            pass
        print('Collection stopped (' + type(error).__name__ + '). Previous records preserved; see README.')
        raise SystemExit(1)
