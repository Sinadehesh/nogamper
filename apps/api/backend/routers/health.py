from __future__ import annotations

import logging

from fastapi import APIRouter

from .. import db
from ..cache import prices as price_cache

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ops"])


@router.get("/health", summary="Liveness")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", summary="Readiness — proves the dependencies answer")
async def ready() -> dict[str, str]:
    async with db.acquire() as conn:
        await conn.fetchval("SELECT 1")

    try:
        await price_cache.get_client().ping()
        cache_status = "ok"
    except Exception:
        logger.warning("readiness: redis is not answering; serving database prices")
        cache_status = "degraded"

    return {"status": "ready", "database": "ok", "cache": cache_status}
