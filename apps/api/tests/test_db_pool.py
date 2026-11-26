"""What the pool says when the provider's connection allowance is gone.

A connection budget is the one production limit that is invisible locally: a
laptop talks to one Postgres with a cap in the hundreds, while the deployed
stack multiplies DB_POOL_MAX by every container and then doubles the API's
share for the length of a rolling deploy. Supabase's free session pooler
allows 15 in total, and answers the 16th with EMAXCONNSESSION — which
crash-loops every container, because the pool is built in the lifespan before
the app serves anything.

Raw, that arrives as sixty lines of lifespan and asyncpg frames with one
useful sentence at the bottom, and reads like the database is unreachable.
These tests pin the translation of that into the arithmetic that explains it.
"""

from __future__ import annotations

import asyncpg
import pytest

from backend import db
from backend.config import Settings


@pytest.fixture(autouse=True)
def _no_leftover_pool():
    """connect() is a no-op when a pool already exists — including one another
    test left behind, which would make these pass without running."""
    db._pool = None
    yield
    db._pool = None


def settings(**overrides) -> Settings:
    return Settings(telegram_bot_token="x", jwt_secret="y", **overrides)


def _raising(exc: Exception):
    async def create_pool(**_kwargs):
        raise exc

    return create_pool


@pytest.mark.parametrize(
    "message",
    [
        "(EMAXCONNSESSION) max clients reached in session mode - "
        "max clients are limited to pool_size: 15",
        "too many connections for role",
    ],
)
async def test_an_exhausted_connection_budget_explains_the_arithmetic(monkeypatch, message):
    monkeypatch.setattr(
        asyncpg, "create_pool", _raising(asyncpg.exceptions.InternalServerError(message))
    )

    with pytest.raises(RuntimeError) as exc:
        await db.connect(settings(db_pool_max=10))

    text = str(exc.value)
    assert message in text
    assert "DB_POOL_MAX is 10" in text
    assert "rolling deploy" in text
    assert "15" in text


async def test_an_unrelated_database_error_is_left_alone(monkeypatch):
    """Wrapping every failure would bury a wrong password under pool advice."""
    original = asyncpg.exceptions.InvalidPasswordError("password authentication failed")
    monkeypatch.setattr(asyncpg, "create_pool", _raising(original))

    with pytest.raises(asyncpg.exceptions.InvalidPasswordError) as exc:
        await db.connect(settings())

    assert exc.value is original


async def test_the_original_error_is_kept_as_the_cause(monkeypatch):
    """__cause__ is what a traceback needs to stay diagnosable."""
    original = asyncpg.exceptions.InternalServerError("max clients reached in session mode")
    monkeypatch.setattr(asyncpg, "create_pool", _raising(original))

    with pytest.raises(RuntimeError) as exc:
        await db.connect(settings())

    assert exc.value.__cause__ is original
