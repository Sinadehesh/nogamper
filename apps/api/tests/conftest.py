from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.config import Settings

TEST_JWT_SECRET = "test-jwt-secret-at-least-32-characters-long"
TEST_PASSWORD = "correct horse battery staple"

TEST_ADMIN_PLAYER = 909090
TEST_ADMIN_CODE = "ADMN22"
"""A fixed code, because player codes are random and the allowlist is read
from the environment before any account exists. `make_admin` gives an account
this code; six characters from the schema's own alphabet, so it also passes
the validator that discards anything that could not be one."""

os.environ["JWT_SECRET"] = TEST_JWT_SECRET
os.environ["ADMIN_PLAYER_CODES"] = TEST_ADMIN_CODE
os.environ["INTERNAL_API_KEY"] = ""

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
    "MAX_COMBINED_ODDS": "1000",
    "DAILY_TOPUP_MINOR": "25000",
    "LEADERBOARD_MIN_VOLUME_MINOR": "100000",
    "LEADERBOARD_FULL_CREDIT_VOLUME_MINOR": "2000000",
    # The ingestion tests exercise the priority-category mechanism, which is
    # off by default. They run it against the configuration it was built for:
    # one small regional tag that would otherwise lose every volume ranking.
    "DISCOVERY_CATEGORIES": "Iran,Macro,Crypto",
    "DISCOVERY_PRIORITY_CATEGORY": "Iran",
    "DISCOVERY_PRIORITY_TAG_SLUGS": "iran",
    # The cheapest Argon2 the library allows. These tests register hundreds of
    # accounts; what is under test is that a password is hashed and verified,
    # not how long that takes.
    "PASSWORD_HASH_TIME_COST": "1",
    "PASSWORD_HASH_MEMORY_KIB": "64",
    "PASSWORD_HASH_PARALLELISM": "1",
    # Wide open by default so an ordinary test never trips a throttle by
    # creating a dozen players. The throttle has tests of its own, which
    # narrow these on the live Settings object.
    "SIGNUP_IP_RATE_MAX": "100000",
    "AUTH_IP_RATE_MAX": "100000",
    "LOGIN_RATE_MAX": "100000",
}.items():
    os.environ.setdefault(_name, _value)


def email_for(player: int) -> str:
    """A deterministic address for a numbered test player."""
    return f"player{player}@example.test"


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


async def authorise(client: AsyncClient, player: int = 5000) -> dict[str, str]:
    """Create a registered player — or sign back in as one — and return an
    Authorization header for them.

    Players are numbered rather than named so a test can ask for "another
    one" without inventing an address, and look the same one up again later
    through `email_for`.
    """
    credentials = {"email": email_for(player), "password": TEST_PASSWORD}
    response = await client.post(
        "/v1/auth/register", json={**credentials, "display_name": f"Player {player}"}
    )
    if response.status_code == 409:
        response = await client.post("/v1/auth/login", json=credentials)
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def make_admin(client: AsyncClient, player: int = TEST_ADMIN_PLAYER) -> dict[str, str]:
    """A signed-in player whose code is on the admin allowlist."""
    from backend import db

    headers = await authorise(client, player)
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE users SET player_code = $2 WHERE email = $1",
            email_for(player),
            TEST_ADMIN_CODE,
        )
    return headers


async def user_id_for(player: int = 5000):
    from backend import db

    async with db.acquire() as conn:
        return await conn.fetchval("SELECT id FROM users WHERE email = $1", email_for(player))


async def balance_of(player: int = 5000) -> int:
    from backend import db

    async with db.acquire() as conn:
        return await conn.fetchval(
            "SELECT coin_balance FROM users WHERE email = $1", email_for(player)
        )
