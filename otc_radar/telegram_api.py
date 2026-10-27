"""Optional authenticated discovery; no joins, messages or participant scraping."""
import asyncio
import os
import time

from .links import extract, username
from .profiles import classify


def configured():
    keys = ('TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_SESSION')
    present = [bool(os.environ.get(key)) for key in keys]
    if any(present) and not all(present):
        raise ValueError('Set all three TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION secrets')
    return all(present)


async def collect(handles, search_queries, checked_at, deadline, category):
    from telethon import TelegramClient, functions, types, errors
    from telethon.sessions import StringSession

    found, candidates, problems, outcomes = [], set(), [], {}
    client = TelegramClient(StringSession(os.environ['TELEGRAM_SESSION']),
                            int(os.environ['TELEGRAM_API_ID']), os.environ['TELEGRAM_API_HASH'],
                            flood_sleep_threshold=0, request_retries=1, connection_retries=1)
    try:
        await asyncio.wait_for(client.connect(), timeout=min(20, max(1, deadline - time.monotonic())))
        if not await asyncio.wait_for(client.is_user_authorized(), timeout=15):
            raise ValueError('Telegram session is not authorized; create it locally')
        for query in search_queries:
            if time.monotonic() + 5 >= deadline:
                break
            result = await asyncio.wait_for(client(functions.contacts.SearchRequest(q=query, limit=100)), timeout=min(15, max(1, deadline - time.monotonic())))
            candidates.update(handle for chat in result.chats if (handle := username(getattr(chat, 'username', '') or '')))
            await asyncio.sleep(2)
        for handle in dict.fromkeys([*handles, *sorted(candidates)]):
            if time.monotonic() + 5 >= deadline:
                break
            try:
                outcomes[handle] = 'irrelevant_or_not_public_group'
                entity = await asyncio.wait_for(client.get_entity(handle), timeout=min(15, max(1, deadline - time.monotonic())))
                if not isinstance(entity, types.Channel) or not entity.megagroup or not entity.username:
                    continue
                full = await asyncio.wait_for(client(functions.channels.GetFullChannelRequest(entity)), timeout=min(15, max(1, deadline - time.monotonic())))
                description = full.full_chat.about or ''
                candidates.update(extract(description))
                group_category = classify(entity.title, description, entity.username.lower())
                if not group_category or (category != 'all' and group_category not in (category, 'mixed')):
                    continue
                found.append({'id': str(entity.id), 'username': entity.username.lower(),
                              'title': entity.title, 'description': description, 'category': group_category,
                              'members': getattr(full.full_chat, 'participants_count', None),
                              'online': getattr(full.full_chat, 'online_count', None),
                              'first_seen': checked_at, 'last_checked': checked_at,
                              'source_urls': ['https://t.me/' + handle],
                              'evidence_url': 'https://t.me/' + entity.username,
                              'verified': True, 'verification_method': 'mtproto',
                              'language_basis': 'cyrillic_profile'})
                outcomes[handle] = 'verified'
            except errors.FloodWaitError as error:
                outcomes[handle] = 'request_failed'
                problems.append('Telegram FloodWait: retry after ' + str(error.seconds) + ' seconds')
                break
            except ValueError:
                # A public username that cannot resolve is not a transient network error.
                outcomes[handle] = 'irrelevant_or_not_public_group'
            except (errors.RPCError, TimeoutError):
                outcomes[handle] = 'request_failed'
                problems.append('Telegram could not inspect a public candidate')
            await asyncio.sleep(1)
    except errors.FloodWaitError as error:
        problems.append('Telegram FloodWait: retry after ' + str(error.seconds) + ' seconds')
    finally:
        await asyncio.wait_for(client.disconnect(), timeout=5)
    # Only actually inspected handles are returned: budget/FloodWait can leave
    # selected candidates untouched and eligible for a later run.
    return found, candidates, problems, outcomes
