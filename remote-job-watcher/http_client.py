"""Single retrying HTTP helper (timeout + exponential backoff). No logins, no CAPTCHA handling."""
from __future__ import annotations

import time

import requests

DEFAULT_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}
_SESSION = requests.Session()
_SESSION.headers.update(DEFAULT_HEADERS)


def _retryable(exc: Exception) -> bool:
    resp = getattr(exc, "response", None)
    if resp is not None and 400 <= resp.status_code < 500 and resp.status_code != 429:
        return False  # a client error will not fix itself
    return True


def get(url, settings, params=None, headers=None, log=print) -> requests.Response:
    last = None
    for attempt in range(settings.max_retries):
        try:
            resp = _SESSION.get(url, params=params, headers=headers, timeout=settings.timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as exc:
            last = exc
            if attempt < settings.max_retries - 1 and _retryable(exc):
                wait = settings.backoff_base * (2 ** attempt)
                log(f"  request failed ({exc}); retrying in {wait:g}s...")
                time.sleep(wait)
            else:
                break
    raise last


def get_json(url, settings, **kw):
    return get(url, settings, **kw).json()


def get_text(url, settings, **kw) -> str:
    return get(url, settings, **kw).text
