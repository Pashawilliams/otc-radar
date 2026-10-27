"""Run only locally; put the resulting secret in GitHub Actions secrets."""
import asyncio
from getpass import getpass


async def main():
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    api_id = int(input('Telegram API ID: '))
    api_hash = getpass('Telegram API hash (hidden): ')
    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        print('\nTELEGRAM_SESSION — secret, grants access to your account. Store only in Actions secrets:\n')
        print(client.session.save())


asyncio.run(main())
