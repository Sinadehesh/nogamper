"""CLOB price client — including the reason the default is the midpoint."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from conftest import mock_http_client

from backend.clients import clob
from backend.clients.http import UpstreamUnavailable
from backend.config import Settings


def settings(**overrides) -> Settings:
    return Settings(telegram_bot_token="x", jwt_secret="y", **overrides)


def responder(payload: dict, status: int = 200):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=payload)

    handler.seen = seen  # type: ignore[attr-defined]
    return handler


async def test_midpoint_is_the_default_source():
    handler = responder({"mid": "0.6234"})
    async with mock_http_client(handler) as client:
        price = await clob.fetch_token_price(client, "tok-1", settings())

    assert price.probability == Decimal("0.6234")
    assert price.source == "CLOB_MIDPOINT"
    assert handler.seen[0].url.path == "/midpoint"
    assert handler.seen[0].url.params["token_id"] == "tok-1"


async def test_ask_source_hits_the_buy_side_price_endpoint():
    handler = responder({"price": "0.62"})
    async with mock_http_client(handler) as client:
        price = await clob.fetch_token_price(client, "tok-1", settings(price_source="ask"))

    assert price.source == "CLOB_ASK"
    assert handler.seen[0].url.path == "/price"
    assert handler.seen[0].url.params["side"] == "buy"


def test_the_ask_breaks_no_pricing_and_the_midpoint_does_not():
    """Why `price_source` defaults to midpoint, stated as arithmetic.

    With a 4c spread, taking the ask as raw_yes_prob makes the engine think
    NO is less likely than it is — and decimal odds are (1 - vig) / p, so a
    smaller p pays *more*. The discount on NO exceeds the entire 5% vig.
    """
    yes_bid, yes_ask = Decimal("0.58"), Decimal("0.62")
    vig = Decimal("0.05")

    no_prob_from_ask = Decimal(1) - yes_ask
    true_no_prob = Decimal(1) - yes_bid

    odds_offered = (1 - vig) / no_prob_from_ask
    odds_deserved = (1 - vig) / true_no_prob
    assert odds_offered > odds_deserved

    player_ev = true_no_prob * odds_offered
    assert player_ev > 1

    mid = (yes_bid + yes_ask) / 2
    assert mid + (Decimal(1) - mid) == 1
    assert (Decimal(1) - mid) * ((1 - vig) / (Decimal(1) - mid)) == 1 - vig


@pytest.mark.parametrize("payload", [{"mid": "0"}, {"mid": "1"}, {"mid": "-0.2"}])
async def test_prices_outside_the_open_interval_are_refused(payload):
    """0 and 1 mean resolved or an empty book. Infinite odds are not a product."""
    async with mock_http_client(responder(payload)) as client:
        with pytest.raises(clob.PriceUnavailable):
            await clob.fetch_token_price(client, "tok-1", settings())


@pytest.mark.parametrize("payload", [{}, {"mid": "abc"}, {"other": 1}])
async def test_unusable_payloads_are_refused(payload):
    async with mock_http_client(responder(payload)) as client:
        with pytest.raises(clob.PriceUnavailable):
            await clob.fetch_token_price(client, "tok-1", settings())


async def test_a_price_is_fetched_once_by_default():
    """The default is a single attempt, and that is a deliberate reversal.

    A price fetch runs inside a job with a 60-second tick and a 90-second
    staleness window. Retrying one token is not free — it is paid for out of
    the freshness of every other market in the same pass. With the old shared
    budget (3 attempts, Retry-After honoured up to 30s each) one throttled
    token could burn 90 seconds, so the entire app went stale in order to
    retry a single price. Measured before the fix: a two-market pass against a
    429 took 60.0 seconds and wrote zero rows.

    Giving up costs this one market 60 seconds of staleness, because the next
    tick asks again. That is the cheaper failure by two orders of magnitude.
    """
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"error": "unavailable"})

    async with mock_http_client(handler) as client:
        with pytest.raises(UpstreamUnavailable):
            await clob.fetch_token_price(client, "tok-1", settings())

    assert attempts == 1


async def test_the_shared_http_retry_budget_does_not_govern_prices():
    """http_max_retries is discovery's knob, not this one.

    Worth pinning: these two settings used to be the same value, and a future
    change that quietly re-points prices at the shared budget would restore the
    outage without failing any other test.
    """
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={})

    async with mock_http_client(handler) as client:
        with pytest.raises(UpstreamUnavailable):
            await clob.fetch_token_price(client, "tok-1", settings(http_max_retries=5))

    assert attempts == 1


async def test_a_deployment_may_still_buy_retries_back():
    """The budget is a setting, not a hard-coded 1 — a deployment facing a
    flaky CLOB and few markets can afford them."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(502, json={})
        return httpx.Response(200, json={"mid": "0.44"})

    async with mock_http_client(handler) as client:
        price = await clob.fetch_token_price(client, "tok-1", settings(price_fetch_retries=3))

    assert price.probability == Decimal("0.44")
    assert attempts == 2


async def test_a_404_is_not_retried():
    """Client errors are not transient; retrying them just wastes the budget."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(404, json={"error": "no such token"})

    async with mock_http_client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await clob.fetch_token_price(client, "tok-1", settings())

    assert attempts == 1
