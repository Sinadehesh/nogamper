"""Recorded-shape fixtures for the Gamma API.

These mirror the real response: JSON arrays arrive as *strings*, numbers as a
mix of floats and strings, and the category lives in `tags` rather than a
`category` field. Every awkward case here is one the live API actually
produces.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta


def _iso(days: float) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat().replace("+00:00", "Z")


def binary_market(
    market_id: str = "51234",
    *,
    outcomes: list[str] | None = None,
    token_ids: list[str] | None = None,
    prices: list[str] | None = None,
    end_in_days: float = 14,
    **overrides: object,
) -> dict:
    market = {
        "id": market_id,
        "question": "Will the Fed cut rates by 25 bps in September?",
        "conditionId": f"0xcond{market_id}",
        "slug": f"market-{market_id}",
        "description": "Resolves YES if the FOMC lowers the target range by 25 bps.",
        "endDate": _iso(end_in_days),
        "outcomes": json.dumps(outcomes or ["Yes", "No"]),
        "outcomePrices": json.dumps(prices or ["0.62", "0.38"]),
        "clobTokenIds": json.dumps(token_ids or [f"tok-yes-{market_id}", f"tok-no-{market_id}"]),
        "active": True,
        "closed": False,
        "archived": False,
        "acceptingOrders": True,
        "liquidityNum": 45000.0,
        "volumeNum": 220000.5,
        "image": "https://polymarket.example/img.png",
    }
    market.update(overrides)
    return market


def event(
    event_id: str = "12345",
    *,
    tags: list[dict] | None = None,
    markets: list[dict] | None = None,
    **overrides: object,
) -> dict:
    payload = {
        "id": event_id,
        "ticker": f"event-{event_id}",
        "slug": f"event-{event_id}",
        "title": "Fed decision in September",
        "description": "FOMC September meeting.",
        "endDate": _iso(14),
        "image": "https://polymarket.example/event.png",
        "active": True,
        "closed": False,
        "archived": False,
        "liquidity": "150000.25",
        "volume": "980000.75",
        "tags": tags if tags is not None else [{"id": "1", "label": "Macro", "slug": "macro"}],
        "markets": markets if markets is not None else [binary_market()],
    }
    payload.update(overrides)
    return payload


CRYPTO_TAGS = [{"id": "2", "label": "Crypto", "slug": "crypto"}]
SPORTS_TAGS = [{"id": "9", "label": "Sports", "slug": "sports"}]
IRAN_TAGS = [{"id": "7", "label": "Iran", "slug": "iran"}]
IRAN_AND_POLITICS_TAGS = [
    {"id": "5", "label": "Geopolitics", "slug": "geopolitics"},
    {"id": "7", "label": "Iran", "slug": "iran"},
]
"""Geopolitics first, the way Gamma actually returns a regional event: the
priority category has to win on being present, not on being listed first."""

CATEGORICAL_MARKET = binary_market(
    "77777",
    token_ids=["tok-a", "tok-b", "tok-c"],
    outcomes=["25 bps", "50 bps", "No change"],
    prices=["0.4", "0.3", "0.3"],
)
