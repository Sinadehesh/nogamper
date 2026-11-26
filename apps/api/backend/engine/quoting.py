"""Turning a slip request into a priced slip.

This is where the pure arithmetic in `odds.py` meets live state: the market
rows, the cached prices, and any boost currently running. It reads; it does
not write. `repositories/predictions.py` owns the writing.

The rule that shapes this module: **never quote a price we would not honour.**
A stale price, a locked market, an exhausted boost — each is a refusal with a
reason, not a number we hope is still true.
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
        required_legs: int | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.market_id = market_id
        self.required_legs = required_legs


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
    boost_id: uuid.UUID | None
    boost_multiplier: Decimal
    boost_max_raw_prob: Decimal | None
    boost_side: str | None


@dataclass(frozen=True, slots=True)
class SlipQuote:
    priced: odds.PricedSlip
    markets: dict[uuid.UUID, MarketContext]
    requested_insurance: bool


_LOAD_MARKETS = """
SELECT m.id, m.event_id, m.question, m.category, m.lock_at, m.status,
       m.raw_yes_prob, m.price_updated_at,
       b.id AS boost_id, b.boost_multiplier, b.max_raw_prob AS boost_max_raw_prob,
       b.side AS boost_side
  FROM markets m
  LEFT JOIN LATERAL (
      SELECT ob.id, ob.boost_multiplier, ob.max_raw_prob, ob.side
        FROM odds_boosts ob
       WHERE ob.market_id = m.id
         AND ob.is_active
         AND ob.starts_at <= NOW()
         AND ob.ends_at > NOW()
         AND ob.consumed_stake < ob.max_total_stake
         AND ob.side = ANY($2::outcome_side[])
       ORDER BY ob.boost_multiplier DESC
       LIMIT 1
  ) b ON TRUE
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
    sides = list({leg.side for leg in legs})

    rows = await conn.fetch(_LOAD_MARKETS, market_ids, sides)
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
            boost_id=row["boost_id"],
            boost_multiplier=row["boost_multiplier"] or Decimal(1),
            boost_max_raw_prob=row["boost_max_raw_prob"],
            boost_side=row["boost_side"],
        )
    return contexts


def _validate_shape(legs: list[LegRequest], settings: Settings) -> None:
    if not legs:
        raise QuoteError("no_legs", "A slip needs at least one leg.")
    if len(legs) < settings.min_legs:
        raise QuoteError(
            "too_few_legs",
            f"A slip needs at least {settings.min_legs} legs.",
            required_legs=settings.min_legs,
        )
    if len(legs) > settings.max_legs:
        raise QuoteError("too_many_legs", f"A slip may carry at most {settings.max_legs} legs.")

    seen_markets: set[uuid.UUID] = set()
    for leg in legs:
        if leg.side not in {"YES", "NO"}:
            raise QuoteError("bad_side", f"{leg.side!r} is not YES or NO.")
        if leg.market_id in seen_markets:
            raise QuoteError(
                "duplicate_market",
                "The same market cannot appear twice on one slip.",
                market_id=str(leg.market_id),
            )
        seen_markets.add(leg.market_id)


def _check_market(context: MarketContext, leg: LegRequest, settings: Settings) -> None:
    if context.status != "ACTIVE":
        raise QuoteError(
            "market_not_open",
            f"This market is {context.status.lower()} and no longer taking predictions.",
            market_id=str(context.id),
        )
    if context.lock_at <= datetime.now(UTC):
        raise QuoteError(
            "market_locked",
            "Predictions on this market have closed.",
            market_id=str(context.id),
        )
    if context.price_age_seconds > settings.price_staleness_seconds:
        raise QuoteError(
            "price_stale",
            "This market's price is out of date. Try again in a moment.",
            market_id=str(context.id),
        )


def _boost_for(context: MarketContext, leg: LegRequest) -> tuple[uuid.UUID | None, Decimal]:
    """A boost applies only to its own side, and only to a genuine longshot.

    `max_raw_prob` is what keeps a boost from being pointed at a coin flip,
    where inflating the payout would just be handing money away.
    """
    if context.boost_id is None or context.boost_side != leg.side:
        return None, Decimal(1)

    selected_prob = context.probability if leg.side == "YES" else Decimal(1) - context.probability
    if context.boost_max_raw_prob is not None and selected_prob > context.boost_max_raw_prob:
        return None, Decimal(1)

    return context.boost_id, context.boost_multiplier


def quote_slip(
    legs: list[LegRequest],
    contexts: dict[uuid.UUID, MarketContext],
    *,
    stake_minor: int,
    requested_insurance: bool,
    settings: Settings,
) -> SlipQuote:
    _validate_shape(legs, settings)

    seen_events: set[uuid.UUID] = set()
    priced_legs: list[odds.PricedLeg] = []

    for leg in legs:
        context = contexts.get(leg.market_id)
        if context is None:
            raise QuoteError("market_not_found", "No such market.", market_id=str(leg.market_id))

        if context.event_id in seen_events:
            raise QuoteError(
                "correlated_legs",
                "Two legs of a slip cannot come from the same event.",
                market_id=str(leg.market_id),
            )
        seen_events.add(context.event_id)

        _check_market(context, leg, settings)
        boost_id, multiplier = _boost_for(context, leg)

        try:
            priced_legs.append(
                odds.price_leg(
                    market_id=str(leg.market_id),
                    side=leg.side,
                    raw_yes_prob=context.probability,
                    vig_rate=Decimal(str(settings.vig_rate)),
                    min_prob=Decimal(str(settings.min_prob)),
                    max_prob=Decimal(str(settings.max_prob)),
                    min_leg_odds=Decimal(str(settings.min_leg_odds)),
                    boost_multiplier=multiplier,
                    boost_id=str(boost_id) if boost_id else None,
                )
            )
        except odds.OddsError as exc:
            raise QuoteError(exc.code, exc.detail, market_id=str(leg.market_id)) from exc

    legs_tuple = tuple(priced_legs)
    insurance = odds.price_insurance(
        legs_tuple,
        stake_minor,
        load=Decimal(str(settings.insurance_load)),
        min_rate=Decimal(str(settings.insurance_min_rate)),
        max_rate=Decimal(str(settings.insurance_max_rate)),
        min_legs=settings.insurance_min_legs,
        covers_failed_legs=settings.insurance_covers_failed_legs,
        requested=requested_insurance,
    )

    if requested_insurance and not insurance.available:
        raise QuoteError(
            "insurance_unavailable",
            f"Cover is not available for this slip ({insurance.unavailable_reason}).",
        )

    try:
        priced = odds.price_slip(
            legs_tuple,
            stake_minor=stake_minor,
            payout_cap_minor=settings.payout_cap_minor,
            max_combined_odds=Decimal(str(settings.max_combined_odds)),
            insurance=insurance,
            uncapped_below_probability=Decimal(str(settings.uncapped_below_probability)),
            parlay_bonus=Decimal(str(settings.parlay_bonus(len(legs_tuple)))),
        )
    except odds.OddsError as exc:
        raise QuoteError(exc.code, exc.detail) from exc

    return SlipQuote(priced=priced, markets=contexts, requested_insurance=requested_insurance)
