"""The shared HTTP helpers — specifically, the timeouts that were not there.

`httpx` reads `timeout=None` as *disable the timeout entirely*, not as "use
the client default"; the sentinel for the latter is `USE_CLIENT_DEFAULT`. Both
helpers here take an optional `timeout` that defaults to None and pass it
straight through, so every caller that did not name a timeout was silently
opting out of having one — including every Telegram send.

An unbounded request inside a scheduled job is the same failure as the price
sync outage in a different coat: one parked connection and the job never
finishes, the lease heartbeat holds it open, and every later tick is refused.
"""

from __future__ import annotations

import time

import httpx
import pytest
from conftest import mock_http_client

from backend.clients.http import UpstreamUnavailable, _timeout, get_json, post_json


def test_no_override_means_the_client_default_not_no_timeout():
    """The bug, in one line. `None` must not reach httpx."""
    assert _timeout(None) is httpx.USE_CLIENT_DEFAULT


def test_an_override_is_passed_through():
    assert _timeout(2.5) == 2.5


def test_zero_is_an_override_and_not_a_missing_value():
    """0 is falsy and means "time out immediately"; a truthiness check here
    would turn the strictest possible timeout into no timeout at all."""
    assert _timeout(0.0) == 0.0


async def _capture_timeout(call) -> object:
    seen: list[object] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions.get("timeout"))
        return httpx.Response(200, json={"ok": True})

    async with mock_http_client(handler) as client:
        await call(client)
    return seen[0]


async def test_a_get_without_an_override_keeps_the_client_timeout():
    seen = await _capture_timeout(lambda c: get_json(c, "http://mock/thing"))
    assert seen is not None, "the request went out with no timeout at all"
    assert seen["read"] is not None


async def test_a_get_override_reaches_the_request():
    seen = await _capture_timeout(lambda c: get_json(c, "http://mock/thing", timeout=3.0))
    assert seen["read"] == 3.0


async def test_a_post_without_an_override_keeps_the_client_timeout():
    """post_json has had the optional-timeout signature all along, so every
    caller that omitted it — the Telegram sends among them — was posting with
    no timeout."""
    seen = await _capture_timeout(lambda c: post_json(c, "http://mock/thing", {"a": 1}))
    assert seen is not None, "the request went out with no timeout at all"
    assert seen["read"] is not None


async def test_an_exhausted_post_names_the_reason_it_gave_up():
    """The failure that read as "the provider is unreachable" with no way to
    tell a 429 from a timeout from a dropped connection apart.

    The retry loop already knew which one it was — it is `last_error` — but
    the exception raised once retries ran out threw that away and reported
    only a count. Against a provider with a hard concurrency limit, "failed
    after 3 attempts" and "failed after 3 attempts: HTTP 429" are two
    different bugs with two different fixes, and only one of those strings
    says which.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={})

    async with mock_http_client(handler) as client:
        with pytest.raises(UpstreamUnavailable, match="HTTP 429"):
            await post_json(client, "http://mock/thing", {"a": 1}, max_retries=1)


async def test_a_single_attempt_never_sleeps_on_retry_after():
    """Why max_retries=1 is the price sync's whole defence.

    Both sleep paths are gated on there being a further attempt, so a
    single-attempt call cannot be made to wait by an upstream — not by
    backoff, and not by a Retry-After header asking for thirty seconds.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={}, headers={"Retry-After": "30"})

    started = time.monotonic()
    async with mock_http_client(handler) as client:
        with pytest.raises(UpstreamUnavailable):
            await get_json(client, "http://mock/thing", max_retries=1)
    assert time.monotonic() - started < 1.0
