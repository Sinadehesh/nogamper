from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlencode

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.config import Settings

TEST_BOT_TOKEN = "123456:TEST-BOT-TOKEN-do-not-use-in-production"
TEST_JWT_SECRET = "test-jwt-secret-at-least-32-characters-long"
TEST_WEBHOOK_SECRET = "test-webhook-secret-32-chars-long-x"

TEST_ADMIN_TELEGRAM_ID = 909090

os.environ["TELEGRAM_BOT_TOKEN"] = TEST_BOT_TOKEN
os.environ["JWT_SECRET"] = TEST_JWT_SECRET
os.environ["TELEGRAM_WEBHOOK_SECRET"] = TEST_WEBHOOK_SECRET
os.environ["ADMIN_TELEGRAM_IDS"] = str(TEST_ADMIN_TELEGRAM_ID)

os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get("TEST_DATABASE_URL", "postgresql://postgres@localhost:5432/appdb_test"),
)
os.environ.setdefault("REDIS_URL", os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15"))
os.environ.setdefault("WORKERS_ENABLED", "false")

for _name, _value in {
    "SIGNUP_BONUS_MINOR": "100000",
    "MIN_STAKE_MINOR": "1000",
    "MAX_STAKE_MINOR": "5000000",
    "PAYOUT_CAP_MINOR": "500000000",
    "HOUSE_SEED_MINOR": "500000",
    "MAX_MARKET_LIABILITY_MINOR": "2000000000",
    "DAILY_DRIP_MINOR": "25000",
    "STREAK_BONUS_STEP_MINOR": "5000",
    "STREAK_BONUS_MAX_MINOR": "50000",
    "DECAY_FLOOR_MINOR": "50000",
    "BOOST_MAX_TOTAL_STAKE_MINOR": "1000000",
    "BOOST_MAX_STAKE_PER_USER_MINOR": "100000",
    "LEADERBOARD_MIN_VOLUME_MINOR": "100000",
    "LEADERBOARD_FULL_CREDIT_VOLUME_MINOR": "2000000",
    "MIN_LEGS": "1",
    "VIG_RATE": "0.05",
    "PARLAY_BONUS_BY_LEGS": "1.0,1.03,1.06,1.10,1.15",
}.items():
    os.environ.setdefault(_name, _value)


def sign_init_data(fields: dict[str, str], token: str = TEST_BOT_TOKEN) -> str:
    """Build a correctly signed initData string, exactly as Telegram would."""
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": digest})


def make_init_data(
    telegram_id: int = 4242,
    *,
    first_name: str = "Ada",
    auth_date: int | None = None,
    token: str = TEST_BOT_TOKEN,
    **extra: str,
) -> str:
    user = {"id": telegram_id, "first_name": first_name, "username": f"user{telegram_id}"}
    fields = {
        "user": json.dumps(user, separators=(",", ":")),
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": f"AAH{telegram_id}",
        **extra,
    }
    return sign_init_data(fields, token)


@pytest_asyncio.fixture
async def app_client() -> AsyncIterator[AsyncClient]:
    from backend import db
    from backend.cache import prices as price_cache
    from backend.config import get_settings
    from backend.main import create_app

    get_settings.cache_clear()
    application = create_app()

    settings = get_settings()
    await db.connect(settings)
    await price_cache.connect(settings)
    await _reset()

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://api.test") as client:
        yield client

    await price_cache.disconnect()
    await db.disconnect()


@pytest_asyncio.fixture
async def resources() -> AsyncIterator[Settings]:
    """Database and cache without the ASGI app, for driving workers directly."""
    from backend import db
    from backend.cache import prices as price_cache
    from backend.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    await db.connect(settings)
    await price_cache.connect(settings)
    await _reset()

    yield settings

    await price_cache.disconnect()
    await db.disconnect()


_NEVER_TRUNCATE = frozenset({"schema_migrations", "alembic_version", "_sqlx_migrations"})

_DISCOVER_TABLES = """
SELECT table_name
  FROM information_schema.tables
 WHERE table_schema = 'public'
   -- Views and matviews are derived; truncating one is an error, not a reset.
   AND table_type = 'BASE TABLE'
   AND table_name <> ALL($1::text[])
 ORDER BY table_name
"""

_SEED_BEGIN = "-- >>> SEED"
_SEED_END = "-- <<< SEED"

_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "db" / "migrations"

_tables: list[str] | None = None
_seed_sql: list[str] | None = None


def _seed_statements() -> list[str]:
    """The migration's own seed blocks, verbatim.

    Copying the seed into this file would just be the table list problem in a
    different shape: two sources of truth, drifting quietly. Slicing it out of
    the migration means a package repriced there is repriced in tests too,
    with nothing to keep in sync.
    """
    global _seed_sql
    if _seed_sql is not None:
        return _seed_sql

    paths = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    if not paths:
        raise RuntimeError(f"no migrations found at {_MIGRATIONS_DIR}")

    blocks: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        cursor = 0
        while (start := text.find(_SEED_BEGIN, cursor)) != -1:
            end = text.find(_SEED_END, start)
            if end == -1:
                raise RuntimeError(f"{path.name}: {_SEED_BEGIN} with no {_SEED_END}")
            blocks.append(text[start:end])
            cursor = end + len(_SEED_END)

    if not blocks:
        raise RuntimeError(
            f"no {_SEED_BEGIN} block in {_MIGRATIONS_DIR}; reference data would "
            "be truncated and never restored"
        )
    _seed_sql = blocks
    return _seed_sql


async def truncate_all(conn) -> list[str]:
    """Empty every table in the schema. Returns what was truncated."""
    global _tables
    if _tables is None:
        rows = await conn.fetch(_DISCOVER_TABLES, sorted(_NEVER_TRUNCATE))
        _tables = [row["table_name"] for row in rows]
        if not _tables:
            raise RuntimeError("no tables discovered — is the schema applied to the test database?")

    names = ", ".join(f'"{table}"' for table in _tables)
    await conn.execute(f"TRUNCATE {names} RESTART IDENTITY CASCADE")
    return _tables


async def _reset() -> None:
    from backend import db as dbmod
    from backend.cache import prices as price_cache

    async with dbmod.acquire() as conn:
        await truncate_all(conn)
        for statement in _seed_statements():
            await conn.execute(statement)

    await price_cache.get_client().flushdb()


def mock_http_client(handler) -> AsyncClient:
    """An httpx client whose requests are answered by `handler` in-process."""
    from httpx import MockTransport

    return AsyncClient(transport=MockTransport(handler), base_url="http://mock")


async def authorise(client: AsyncClient, telegram_id: int = 5000) -> dict[str, str]:
    """Create a player and return an Authorization header for them."""
    response = await client.post(
        "/v1/auth/session", json={"initData": make_init_data(telegram_id=telegram_id)}
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def bot_token() -> str:
    return TEST_BOT_TOKEN
