"""asyncpg connection pool wiring.

Every write path in this service runs inside an explicit transaction. The
schema's ledger trigger takes a row lock per user, so transactions here are
short by construction: acquire, write, commit.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from .config import Settings

_pool: asyncpg.Pool | None = None

_BUDGET_EXHAUSTED = ("max clients reached", "too many connections", "EMAXCONNSESSION")


def _budget_hint(settings: Settings) -> str:
    """Explain the arithmetic, because the raw error names only the cap.

    Every container builds its own pool, so the limit is not per service — and
    a rolling deploy is the peak, because the old containers still hold theirs
    while the new ones open theirs.
    """
    return (
        f"DB_POOL_MAX is {settings.db_pool_max}, per container. Peak usage is "
        "roughly (running containers + the API instances a rolling deploy "
        "doubles) * DB_POOL_MAX, plus one for scripts/migrate.py. Lower "
        "DB_POOL_MAX, cut an instance, or raise the provider's limit — "
        "Supabase's free session pooler allows 15 in total."
    )


async def connect(settings: Settings) -> asyncpg.Pool:
    global _pool
    if _pool is None:
        try:
            _pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=settings.db_pool_min,
                max_size=settings.db_pool_max,
                command_timeout=10,
            )
        except asyncpg.PostgresError as exc:
            message = str(exc)
            if any(marker in message for marker in _BUDGET_EXHAUSTED):
                raise RuntimeError(
                    f"Database refused a new connection: {message}. {_budget_hint(settings)}"
                ) from exc
            raise
    return _pool


async def disconnect() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:  # pragma: no cover - programming error
        raise RuntimeError("Database pool is not initialised.")
    return _pool


@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    async with get_pool().acquire() as conn:
        yield conn


@asynccontextmanager
async def transaction() -> AsyncIterator[asyncpg.Connection]:
    async with get_pool().acquire() as conn, conn.transaction():
        yield conn
