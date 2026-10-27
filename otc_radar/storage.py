import json
import os
from pathlib import Path


def read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default


def write(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def merge(chats, incoming):
    """Deduplicate stable Telegram IDs when available, otherwise canonical handles."""
    found = [item for item in chats if
             (item['username'] == incoming['username'] and
              (item.get('id') is None or incoming.get('id') is None or str(item['id']) == str(incoming['id']))) or
             (incoming.get('id') is not None and str(item.get('id')) == str(incoming['id']))]
    previous = min(found, key=lambda item: item['first_seen']) if found else None
    if previous:
        incoming = {**incoming, 'first_seen': previous['first_seen'],
                    'id': incoming.get('id') or previous.get('id'),
                    'source_urls': sorted(set(incoming.get('source_urls', [])) |
                                          {url for item in found for url in item.get('source_urls', [])}),
                    'aliases': sorted(({item['username'] for item in found} |
                                       {alias for item in found for alias in item.get('aliases', [])}) - {incoming['username']})}
    # A handle reused by a different known group ID replaces its old public entry;
    # the former group's age and evidence must not be attributed to the new group.
    chats[:] = [item for item in chats if item not in found and item['username'] != incoming['username']]
    chats.append(incoming)
