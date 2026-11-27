"""A question's week of prices, kept for a few minutes.

The history is read from the source when somebody asks for a question's page.
Kept here, a page that is asked for a hundred times in ten minutes costs the
source one request rather than a hundred — and costs this server one, which on
a small machine matters as much.

Best-effort in both directions, like the price cache beside it: if Redis is
down a read is a miss and a write is nothing, and the page is drawn from a
fresh fetch instead of failing.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from ..clients.clob import PricePoint
from .prices import get_client

logger = logging.getLogger(__name__)


def key_for(market_id: UUID) -> str:
    return f"history:1w:{market_id}"


async def read(market_id: UUID) -> list[PricePoint] | None:
    """The cached history, or None for a miss. An empty list is a hit: the
    source was asked and had nothing, and need not be asked again yet."""
    try:
        raw = await get_client().get(key_for(market_id))
    except Exception:
        logger.exception("history cache read failed; fetching instead")
        return None
    if raw is None:
        return None
    try:
        return [
            PricePoint(
                at=datetime.fromtimestamp(float(at), tz=UTC), probability=Decimal(str(probability))
            )
            for at, probability in json.loads(raw)
        ]
    except (json.JSONDecodeError, TypeError, ValueError, InvalidOperation):
        logger.warning("discarding unreadable cached history for %s", market_id)
        return None


async def write(market_id: UUID, points: list[PricePoint], *, ttl_seconds: int) -> None:
    payload = json.dumps(
        [[point.at.timestamp(), str(point.probability)] for point in points],
        separators=(",", ":"),
    )
    try:
        await get_client().set(key_for(market_id), payload, ex=ttl_seconds)
    except Exception:
        logger.exception("history cache write failed; the next page will fetch again")
