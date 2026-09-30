"""One shared HTTP client for all sources."""

import json
import re

import httpx

HEADERS = {
    # Look like a normal mobile browser - some sites block unknown clients.
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
}


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True)


_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def next_data(html: str) -> dict:
    """Pull the JSON that Next.js websites (like nba.com) embed in every page."""
    match = _NEXT_DATA.search(html)
    if not match:
        raise ValueError("page layout changed: __NEXT_DATA__ not found")
    return json.loads(match.group(1))
