#!/usr/bin/env python3
"""Tell the IndexNow search engines about every page in the sitemap.

    SITE_URL=https://example.com INDEXNOW_KEY=… python scripts/indexnow.py

IndexNow is a protocol shared by Bing and several other search engines: a site
says "these addresses are new or have changed" and they come and look, without
the site having an account with any of them. Google does not take part.

The site proves it is the one asking by publishing the key at an address on
its own host (apps/web serves it at /indexnow-key.txt when INDEXNOW_KEY is
set). This script checks that the key really is being served there before it
submits anything, because a submission the search engine cannot verify is
discarded without a word.

Run it after publishing something new. It is safe to run again: submitting an
address twice only asks for it to be looked at twice.

Standard library only, so it runs anywhere Python does.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

ENDPOINT = "https://api.indexnow.org/indexnow"
KEY_PATH = "/indexnow-key.txt"
KEY_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,128}$")
LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
TIMEOUT_SECONDS = 30
MAX_URLS = 10_000
"""The protocol's limit for one submission."""


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "indexnow-submit/1.0"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        return response.read().decode("utf-8", errors="replace")


def sitemap_urls(site: str) -> list[str]:
    """Every address in the sitemap that belongs to this site, in order, once."""
    host = urlsplit(site).netloc
    seen: dict[str, None] = {}
    for url in LOC.findall(fetch(f"{site}/sitemap.xml")):
        if urlsplit(url).netloc == host:
            seen.setdefault(url, None)
    return list(seen)


def submit(site: str, key: str, urls: list[str]) -> int:
    body = json.dumps(
        {
            "host": urlsplit(site).netloc,
            "key": key,
            "keyLocation": f"{site}{KEY_PATH}",
            "urlList": urls,
        }
    ).encode()
    request = urllib.request.Request(  # noqa: S310
        ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def main() -> int:
    site = os.environ.get("SITE_URL", "").strip().rstrip("/")
    key = os.environ.get("INDEXNOW_KEY", "").strip()

    if not site.startswith("https://"):
        print("✗ SITE_URL must be the site's https address", file=sys.stderr)
        return 2
    if not KEY_PATTERN.match(key):
        print("✗ INDEXNOW_KEY must be 8 to 128 letters, digits or dashes", file=sys.stderr)
        return 2

    try:
        served = fetch(f"{site}{KEY_PATH}").strip()
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"✗ {site}{KEY_PATH} could not be read: {exc}", file=sys.stderr)
        return 1
    if served != key:
        print(
            f"✗ {site}{KEY_PATH} does not serve this key. Set INDEXNOW_KEY on the site "
            "and redeploy it first.",
            file=sys.stderr,
        )
        return 1

    try:
        urls = sitemap_urls(site)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"✗ the sitemap could not be read: {exc}", file=sys.stderr)
        return 1
    if not urls:
        print("✗ the sitemap lists no addresses on this site", file=sys.stderr)
        return 1
    if len(urls) > MAX_URLS:
        print(f"  the sitemap lists {len(urls)} addresses; submitting the first {MAX_URLS}")
        urls = urls[:MAX_URLS]

    status = submit(site, key, urls)
    # 200: accepted. 202: accepted, and the key will be checked shortly.
    if status in (200, 202):
        print(f"✓ submitted {len(urls)} address(es) from {site} (HTTP {status})")
        return 0
    print(f"✗ IndexNow answered HTTP {status}; nothing was accepted", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
