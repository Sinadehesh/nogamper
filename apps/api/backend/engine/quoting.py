"""Turning a slip request into a priced slip.

This is where the pure arithmetic in `odds.py` meets live state: the market
rows and the cached prices. It reads; it does not write.
`repositories/predictions.py` owns the writing.

The rule that shapes this module: **never quote a price we would not honour.**
A stale price, a locked market, a question that is all but settled — each is a
refusal with a reason, not a number we hope is still true.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import asyncpg

from ..cache import prices as price_cache
from ..config import Settings
from . import odds

__all__ = ["LegRequest", "QuoteError", "SlipQuote", "quote_slip"]


class QuoteError(Exception):
    def __init__(
        self,
        code: str,
        detail: str,
        *,
        market_id: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.market_id = market_id


@dataclass(frozen=True, slots=True)
class LegRequest:
    market_id: uuid.UUID
    side: str


@dataclass(frozen=True, slots=True)
class MarketContext:
    """Everything about one market that pricing depends on."""

    id: uuid.UUID
    event_id: uuid.UUID
    question: str
    category: str
    lock_at: datetime
    status: str
    probability: Decimal
    price_age_seconds: float
    price_source: str


@dataclass(frozen=True, slots=True)
class SlipQuote:
    priced: odds.PricedSlip
    markets: dict[uuid.UUID, MarketContext]


_LOAD_MARKETS = """
SELECT m.id, m.event_id, COALESCE(m.question_source, m.question) AS question,
       m.category, m.lock_at, m.status, m.raw_yes_prob, m.price_updated_at
  FROM markets m
 WHERE m.id = ANY($1::uuid[])
"""


async def load_market_contexts(
    conn: asyncpg.Connection,
    legs: list[LegRequest],
    settings: Settings,
    *,
    now: datetime | None = None,
) -> dict[uuid.UUID, MarketContext]:
    now = now or datetime.now(UTC)
    market_ids = [leg.market_id for leg in legs]

    rows = await conn.fetch(_LOAD_MARKETS, market_ids)
    cached = await price_cache.read_many([row["id"] for row in rows])

    contexts: dict[uuid.UUID, MarketContext] = {}
    for row in rows:
        entry = cached.get(row["id"])
        if entry is not None:
            probability, age, source = (
                entry.probability,
                entry.age_seconds(now),
                entry.source,
            )
        else:
            probability = row["raw_yes_prob"]
            age = (now - row["price_updated_at"]).total_seconds()
            source = "DATABASE"

        contexts[row["id"]] = MarketContext(
            id=row["id"],
            event_id=row["event_id"],
            question=row["question"],
            category=row["category"],
            lock_at=row["lock_at"],
            status=row["status"],
            probability=probability,
            price_age_seconds=age,
            price_source=source,
        )
    return contexts


def _validate_shape(legs: list[LegRequest], settings: Settings) -> None:
    if not legs:
        raise QuoteError("no_legs", "A slip needs at least one pick.")
    if len(legs) > settings.max_legs:
        raise QuoteError("too_many_legs", f"A slip may carry at most {settings.max_legs} picks.")

    seen_markets: set[uuid.UUID] = set()
    for leg in legs:
        if leg.side not in {"YES", "NO"}:
            raise QuoteError("bad_side", f"{leg.side!r} is not YES or NO.")
        if leg.market_id in seen_markets:
            raise QuoteError(
                "duplicate_market",
                "The same question cannot appear twice on one slip.",
                market_id=str(leg.market_id),
            )
        seen_markets.add(leg.market_id)


def _check_market(context: MarketContext, settings: Settings) -> None:
    if context.status != "ACTIVE":
        raise QuoteError(
            "market_not_open",
            f"This question is {context.status.lower()} and no longer taking forecasts.",
            market_id=str(context.id),
        )
    if context.lock_at <= datetime.now(UTC):
        raise QuoteError(
            "market_locked",
            "Forecasts on this question have closed.",
            market_id=str(context.id),
        )
    if context.price_age_seconds > settings.price_staleness_seconds:
        raise QuoteError(
            "price_stale",
            "This question's price is out of date. Try again in a moment.",
            market_id=str(context.id),
        )


def quote_slip(
    legs: list[LegRequest],
    contexts: dict[uuid.UUID, MarketContext],
    *,
    stake_minor: int,
    settings: Settings,
) -> SlipQuote:
    _validate_shape(legs, settings)

    seen_events: set[uuid.UUID] = set()
    priced_legs: list[odds.PricedLeg] = []

    for leg in legs:
        context = contexts.get(leg.market_id)
        if context is None:
            raise QuoteError("market_not_found", "No such question.", market_id=str(leg.market_id))

        # Two outcomes of one event are not independent — "cut by 25bp" and
        # "cut by 50bp" cannot both happen — so multiplying their odds would
        # price a combination that is impossible or, worse, nearly certain.
        if context.event_id in seen_events:
            raise QuoteError(
                "correlated_legs",
                "Two picks on a slip cannot come from the same event.",
                market_id=str(leg.market_id),
            )
        seen_events.add(context.event_id)

        _check_market(context, settings)

        try:
            priced_legs.append(
                odds.price_leg(
                    market_id=str(leg.market_id),
                    side=leg.side,
                    raw_yes_prob=context.probability,
                    min_prob=Decimal(str(settings.min_prob)),
                    max_prob=Decimal(str(settings.max_prob)),
                )
            )
        except odds.OddsError as exc:
            raise QuoteError(exc.code, exc.detail, market_id=str(leg.market_id)) from exc

    try:
        priced = odds.price_slip(
            tuple(priced_legs),
            stake_minor=stake_minor,
            payout_cap_minor=settings.payout_cap_minor,
            max_combined_odds=Decimal(str(settings.max_combined_odds)),
        )
    except odds.OddsError as exc:
        raise QuoteError(exc.code, exc.detail) from exc

    return SlipQuote(priced=priced, markets=contexts)
