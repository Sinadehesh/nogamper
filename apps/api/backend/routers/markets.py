"""GET /v1/markets — the market list the Mini App renders.

Metadata comes from Postgres; the probability comes from Redis when it is
there. That split is the point: the durable row is a fallback that is at worst
one sync tick old, and the cache is what keeps the front door fast.

Prices are never invented. If the cache misses and the stored price is older
than the staleness tolerance, the market still appears — with `stale: true` —
rather than being hidden or shown at a number nobody should bet on.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import db
from ..cache import prices as price_cache
from ..config import Settings, get_settings
from ..repositories import markets as markets_repo
from ..schemas import (
    MarketBoost,
    MarketEventSummary,
    MarketPage,
    MarketSummary,
    Money,
    Probability,
)
from ..security.dependencies import CurrentUser

router = APIRouter(prefix="/v1", tags=["markets"])

_PROB_PLACES = Decimal("0.0001")


def _encode_cursor(lock_at: datetime, market_id: uuid.UUID) -> str:
    raw = json.dumps({"l": lock_at.isoformat(), "i": str(market_id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
        return datetime.fromisoformat(payload["l"]), uuid.UUID(payload["i"])
    except (binascii.Error, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail={"code": "bad_cursor", "detail": "Cursor is not valid."}
        ) from exc


def _probability(
    market_id: uuid.UUID,
    stored_prob: Decimal,
    stored_at: datetime,
    cached: price_cache.CachedPrice | None,
    settings: Settings,
    now: datetime,
) -> Probability:
    if cached is not None:
        probability, source, age = (
            cached.probability,
            cached.source,
            cached.age_seconds(now),
        )
    else:
        probability, source, age = (
            stored_prob,
            "DATABASE",
            (now - stored_at).total_seconds(),
        )

    yes = probability.quantize(_PROB_PLACES)
    return Probability(
        yes=str(yes),
        no=str((Decimal(1) - yes).quantize(_PROB_PLACES)),
        source=source,
        age_seconds=round(age, 1),
        stale=age > settings.price_staleness_seconds,
    )


def _boosts(raw: object) -> list[MarketBoost]:
    entries = json.loads(raw) if isinstance(raw, str) else (raw or [])
    return [
        MarketBoost(
            id=str(entry["id"]),
            side=entry["side"],
            multiplier=entry["multiplier"],
            ends_at=datetime.fromisoformat(entry["ends_at"]),
            remaining_stake=Money.of(int(entry["remaining_stake_minor"])),
            max_stake_per_user=Money.of(int(entry["max_stake_per_user_minor"])),
        )
        for entry in entries
    ]


@router.get(
    "/markets",
    response_model=MarketPage,
    summary="Active markets, soonest cutoff first",
)
async def list_markets(
    _: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    category: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> MarketPage:
    after_lock_at, after_id = _decode_cursor(cursor) if cursor else (None, None)

    async with db.acquire() as conn:
        rows = await markets_repo.list_active_markets(
            conn,
            category=category,
            after_lock_at=after_lock_at,
            after_id=after_id,
            limit=limit + 1,
        )

    has_more = len(rows) > limit
    rows = rows[:limit]

    cached = await price_cache.read_many([row["id"] for row in rows])
    now = datetime.now(UTC)

    markets = [
        MarketSummary(
            id=str(row["id"]),
            question=row["question"],
            description=row["description"],
            category=row["category"],
            image_url=row["image_url"],
            event=MarketEventSummary(
                id=str(row["event_id"]), title=row["event_title"], slug=row["event_slug"]
            ),
            probability=_probability(
                row["id"],
                row["raw_yes_prob"],
                row["price_updated_at"],
                cached.get(row["id"]),
                settings,
                now,
            ),
            liquidity_usd=str(row["liquidity_usd"]),
            volume_usd=str(row["volume_usd"]),
            lock_at=row["lock_at"],
            end_date=row["end_date"],
            boosts=_boosts(row["boosts"]),
        )
        for row in rows
    ]

    next_cursor = _encode_cursor(rows[-1]["lock_at"], rows[-1]["id"]) if has_more and rows else None
    return MarketPage(
        markets=markets,
        next_cursor=next_cursor,
        min_legs=settings.min_legs,
        max_legs=settings.max_legs,
        vig_rate=str(settings.vig_rate),
        parlay_bonus_by_legs=[str(b) for b in settings.parlay_bonus_by_legs],
        example_stake=Money.of(settings.example_stake_minor),
        signup_bonus=Money.of(settings.signup_bonus_minor),
        referral_bonus=Money.of(settings.referral_bonus_minor),
    )
