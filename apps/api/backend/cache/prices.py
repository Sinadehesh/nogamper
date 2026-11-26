"""Redis price cache.

The cache is a latency optimisation, never an authority. Two rules keep it
honest:

  1. Every entry carries a TTL. If the sync worker dies, prices expire rather
     than being served forever at whatever they were when it stopped.
  2. Every read reports its age. The odds engine refuses to price a leg from
     a stale number; the market list marks it so the UI can say so.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from redis.asyncio import Redis

from ..config import Settings

logger = logging.getLogger(__name__)

_redis: Redis | None = None


def key_for(market_id: UUID) -> str:
    return f"market:{market_id}:price"


@dataclass(frozen=True, slots=True)
class CachedPrice:
    probability: Decimal
    source: str
    captured_at: datetime

    def age_seconds(self, now: datetime | None = None) -> float:
        return ((now or datetime.now(UTC)) - self.captured_at).total_seconds()


async def connect(settings: Settings) -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
            health_check_interval=30,
        )
    return _redis


async def disconnect() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def get_client() -> Redis:
    if _redis is None:  # pragma: no cover - programming error
        raise RuntimeError("Redis is not initialised.")
    return _redis


def _encode(price: Decimal, source: str, captured_at: datetime) -> str:
    return json.dumps(
        {"p": str(price), "src": source, "t": captured_at.timestamp()},
        separators=(",", ":"),
    )


def _decode(raw: str | None) -> CachedPrice | None:
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        return CachedPrice(
            probability=Decimal(str(payload["p"])),
            source=str(payload.get("src", "unknown")),
            captured_at=datetime.fromtimestamp(float(payload["t"]), tz=UTC),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, InvalidOperation):
        logger.warning("discarding unreadable cached price: %r", raw)
        return None


async def write_many(
    entries: list[tuple[UUID, Decimal, str, datetime]], *, ttl_seconds: int
) -> None:
    if not entries:
        return
    client = get_client()
    async with client.pipeline(transaction=False) as pipe:
        for market_id, probability, source, captured_at in entries:
            pipe.set(
                key_for(market_id),
                _encode(probability, source, captured_at),
                ex=ttl_seconds,
            )
        await pipe.execute()


async def read_many(market_ids: list[UUID]) -> dict[UUID, CachedPrice]:
    """Best-effort read. A Redis outage degrades to database prices, never to
    an error page: the markets list is the app's front door."""
    if not market_ids:
        return {}
    try:
        raw_values = await get_client().mget([key_for(mid) for mid in market_ids])
    except Exception:
        logger.exception("price cache read failed; falling back to the database")
        return {}

    found: dict[UUID, CachedPrice] = {}
    for market_id, raw in zip(market_ids, raw_values, strict=True):
        decoded = _decode(raw)
        if decoded is not None:
            found[market_id] = decoded
    return found
