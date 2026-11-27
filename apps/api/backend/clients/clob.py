"""Polymarket CLOB API — live token prices.

## Why the default is the midpoint, not the buy-side price

`/price?token_id=…&side=buy` returns the best ask: what it costs to buy that
token right now. Storing the ask as `raw_yes_prob` skews the game in a way
that never shows up as an error:

    yes_ask = 0.62, yes_bid = 0.58        (a 4c spread, normal for Polymarket)

    stored raw_yes_prob = 0.62
    NO priced by the odds engine as 1 - 0.62 = 0.38
    but the market's own price for NO is 1 - yes_bid = 0.42

We would be treating NO as less likely than the market does, and fair odds
are `1 / p` — a smaller `p` means a *bigger* payout. Every NO forecast would
pay more than its chance justifies, and every YES forecast less. Odds that
are fair in name and tilted in practice are worse than an honest margin,
because the page says there is none; and the tilt is largest on the markets
with the widest spreads, which are the thinnest and least reliable ones.

The midpoint has no such asymmetry: `p_yes + p_no = 1` by construction, so
both sides are priced from the same estimate. That is why `price_source`
defaults to "midpoint". Setting it to "ask" restores the literal behaviour —
the code path is kept — but it should be a deliberate choice, not a default.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import httpx

from ..config import Settings
from .http import get_json

logger = logging.getLogger(__name__)


class PriceUnavailable(Exception):
    """The CLOB answered, but not with a price we can use."""


@dataclass(frozen=True, slots=True)
class TokenPrice:
    token_id: str
    probability: Decimal
    source: str
    fetched_at: datetime


def _extract(payload: object, keys: tuple[str, ...]) -> Decimal:
    if not isinstance(payload, dict):
        raise PriceUnavailable(f"expected an object, got {type(payload).__name__}")

    for key in keys:
        if key in payload:
            try:
                return Decimal(str(payload[key]))
            except (InvalidOperation, ValueError) as exc:
                raise PriceUnavailable(f"{key}={payload[key]!r} is not a number") from exc

    raise PriceUnavailable(f"none of {keys} present in response")


async def fetch_token_price(
    client: httpx.AsyncClient, token_id: str, settings: Settings
) -> TokenPrice:
    """One price, on the price sync's budget rather than the shared HTTP one.

    `price_fetch_retries` and `price_fetch_timeout_seconds` are deliberately
    tighter than `http_max_retries` / `http_timeout_seconds`. A price fetch runs
    inside a job with a 60-second tick and a 90-second staleness window, and
    every second spent retrying *this* token is a second of freshness taken from
    every other market in the pass. Giving up costs one market 60 seconds of
    staleness; retrying can cost all of them minutes of it. See config.py.
    """
    if settings.price_source == "ask":
        payload = await get_json(
            client,
            f"{settings.clob_api_url}/price",
            params={"token_id": token_id, "side": "buy"},
            max_retries=settings.price_fetch_retries,
            timeout=settings.price_fetch_timeout_seconds,
        )
        probability = _extract(payload, ("price",))
        source = "CLOB_ASK"
    else:
        payload = await get_json(
            client,
            f"{settings.clob_api_url}/midpoint",
            params={"token_id": token_id},
            max_retries=settings.price_fetch_retries,
            timeout=settings.price_fetch_timeout_seconds,
        )
        probability = _extract(payload, ("mid", "midpoint", "price"))
        source = "CLOB_MIDPOINT"

    low = Decimal(str(settings.min_prob))
    high = Decimal(str(settings.max_prob))
    if not (Decimal(0) < probability < Decimal(1)):
        raise PriceUnavailable(f"probability {probability} is outside (0, 1)")

    return TokenPrice(
        token_id=token_id,
        probability=min(max(probability, low), high),
        source=source,
        fetched_at=datetime.now(UTC),
    )


@dataclass(frozen=True, slots=True)
class PricePoint:
    at: datetime
    probability: Decimal


_FOUR_PLACES = Decimal("0.0001")
MAX_HISTORY_POINTS = 400
"""A week of hourly prices is 168 points. This is a ceiling on what one answer
may put on a page, not a target."""


async def fetch_price_history(
    client: httpx.AsyncClient, token_id: str, settings: Settings
) -> list[PricePoint]:
    """The last week of a token's price, hourly, oldest first.

    For reading, not for pricing: this is what a question's page draws its
    chart from, and nothing is ever staked against it. An empty list is a real
    answer — a market opened an hour ago has no week behind it — and is not an
    error. Points that are not a time and a probability are dropped rather
    than guessed at.

    One attempt, on a short clock. The page that asked can be shown without a
    chart; it cannot be shown while this is still retrying.
    """
    payload = await get_json(
        client,
        f"{settings.clob_api_url}/prices-history",
        params={"market": token_id, "interval": "1w", "fidelity": 60},
        max_retries=1,
        timeout=settings.history_timeout_seconds,
    )
    history = payload.get("history") if isinstance(payload, dict) else None
    if not isinstance(history, list):
        raise PriceUnavailable("no history in the response")

    points: list[PricePoint] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        try:
            at = datetime.fromtimestamp(float(item["t"]), tz=UTC)
            probability = Decimal(str(item["p"]))
        except (KeyError, TypeError, ValueError, OverflowError, OSError, InvalidOperation):
            continue
        if not probability.is_finite() or not Decimal(0) <= probability <= Decimal(1):
            continue
        points.append(PricePoint(at=at, probability=probability.quantize(_FOUR_PLACES)))

    points.sort(key=lambda point: point.at)
    return points[-MAX_HISTORY_POINTS:]
