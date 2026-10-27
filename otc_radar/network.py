"""Bounded public HTTP requests. No login, bypasses or private invitations."""
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse


class FetchError(Exception):
    pass


class AllowedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, request, file, code, message, headers, new_url):
        parsed = urlparse(new_url)
        if parsed.scheme != 'https' or parsed.hostname not in self.hosts or parsed.username or parsed.password:
            raise FetchError('Unexpected source redirect')
        return super().redirect_request(request, file, code, message, headers, new_url)


class Client:
    def __init__(self, deadline, allowed_hosts=(), delay=1):
        self.deadline = deadline
        self.allowed_hosts = {'t.me', 'www.bing.com', *allowed_hosts}
        self.delay = delay
        self.next_request = {}
        self.lock = threading.Lock()
        self.opener = urllib.request.build_opener(AllowedRedirect(self.allowed_hosts))

    def get(self, url):
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname not in self.allowed_hosts or parsed.username or parsed.password:
            raise FetchError('Source URL is outside the configured HTTPS allowlist')
        with self.lock:
            now = time.monotonic()
            wait = max(0, self.next_request.get(parsed.hostname, now) - now)
            if now + wait >= self.deadline:
                raise FetchError('Collection time budget reached')
            self.next_request[parsed.hostname] = now + wait + self.delay
        if wait:
            time.sleep(wait)
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise FetchError('Collection time budget reached')
        request = urllib.request.Request(url, headers={
            'User-Agent': 'OTC-Radar/1.0 (public Telegram group directory)',
            'Accept-Language': 'ru,en;q=0.8', 'Accept': 'text/html,application/rss+xml;q=0.9'})
        try:
            with self.opener.open(request, timeout=min(15, remaining)) as response:
                final = urlparse(response.url)
                if final.hostname not in self.allowed_hosts or final.scheme != 'https':
                    raise FetchError('Unexpected source redirect')
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise FetchError('Source page exceeds size limit')
                return raw.decode('utf-8', errors='replace')
        except urllib.error.HTTPError as error:
            raise FetchError('HTTP ' + str(error.code)) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise FetchError('Network unavailable or request timed out') from None
