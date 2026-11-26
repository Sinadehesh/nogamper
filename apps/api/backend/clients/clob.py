"""Polymarket CLOB API — live token prices.

## Why the default is the midpoint, not the buy-side price

`/price?token_id=…&side=buy` returns the best ask: what it costs to buy that
token right now. Storing the ask as `raw_yes_prob` breaks the book in a way
that only shows up in the P&L:

    yes_ask = 0.62, yes_bid = 0.58        (a 4c spread, normal for Polymarket)

    stored raw_yes_prob = 0.62
    NO priced by the odds engine as 1 - 0.62 = 0.38
    but the true cost of NO is 1 - yes_bid = 0.42

We would be treating NO as less likely than it is, and decimal odds are
`(1 - vig) / p` — a smaller `p` means a *bigger* payout. Every NO bet would
be sold at a discount, and on a wide spread that discount exceeds the entire
5% vig. The house edge inverts on exactly the markets where the book is
thinnest.

The midpoint has no such asymmetry: `p_yes + p_no = 1` by construction, so
both sides carry the same vig. That is why `price_source` defaults to
"midpoint". Setting it to "ask" restores the literal behaviour — the code
path is kept — but it should be a deliberate choice, not a default.
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
