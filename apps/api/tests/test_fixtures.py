"""The test fixture's own teardown, tested.

Twice now a table has been added to the schema and forgotten in a
hand-written truncate list, and both times the rows survived into whatever
test ran next. That failure is quiet by nature: the suite still passes,
right up until the inherited state happens to matter, and then it fails in
CI on a test that is green locally in isolation.

So the teardown is now derived from the catalogue rather than typed out, and
these tests are what keeps that honest — the fixture is infrastructure every
other test rests on, and nothing else would notice it going wrong.
"""

from __future__ import annotations

import conftest
import pytest

from backend import db

pytestmark = pytest.mark.asyncio

SEEDED = {"app_config", "coin_packages", "rewards"}

_ALL_BASE_TABLES = """
SELECT table_name
  FROM information_schema.tables
 WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
"""


async def test_the_truncate_list_is_the_entire_schema(resources):
    async with db.acquire() as conn:
        rows = await conn.fetch(_ALL_BASE_TABLES)

    everything = {row["table_name"] for row in rows}
    assert set(conftest._tables) == everything - conftest._NEVER_TRUNCATE

    assert {"admin_audit_log", "app_config", "leaderboard_seasons"} <= everything


async def test_nothing_a_test_writes_survives_the_reset(resources):
    """Dirty the tables no CASCADE would reach, then prove the reset reaches them.

    `TRUNCATE users CASCADE` cleans anything holding a foreign key to users,
    which is why most of the schema was fine despite the list being wrong.
    The tables below reference nothing, so they were only ever cleaned if
    someone remembered to name them.
    """
    async with db.acquire() as conn:
        await conn.execute("INSERT INTO admin_audit_log (actor, action) VALUES ('t', 'dirty')")
        await conn.execute("UPDATE app_config SET value = '9.99' WHERE key = 'odds.vig_rate'")
        await conn.execute(
            "INSERT INTO leaderboard_seasons (code, starts_at, ends_at) "
            "VALUES ('DIRTY', NOW(), NOW() + INTERVAL '1 day')"
        )
        await conn.execute(
            "INSERT INTO coin_packages (code, title, description, stars_price, coins, sort_order)"
            " VALUES ('TIER_DIRTY', 'x', 'x', 1, 1, 9)"
        )

    await conftest._reset()

    async with db.acquire() as conn:
        counts = {
            # noqa justified: these names come from the catalogue, not a caller.
            table: await conn.fetchval(f'SELECT count(*) FROM "{table}"')  # noqa: S608
            for table in conftest._tables
        }
        vig = await conn.fetchval("SELECT value FROM app_config WHERE key = 'odds.vig_rate'")
        rows = await conn.fetch("SELECT code FROM coin_packages ORDER BY code")
        codes = [row["code"] for row in rows]

    assert {t: n for t, n in counts.items() if n and t not in SEEDED} == {}
    assert vig == "0.05"
    assert codes == ["TIER_1", "TIER_2", "TIER_3"]


async def test_the_seed_comes_from_the_migration(resources):
    """Not from a copy of it living in the fixture."""
    blocks = conftest._seed_statements()
    assert blocks, "the migration must carry a SEED block"

    combined = "\n".join(blocks)
    assert "INSERT INTO app_config" in combined
    assert "INSERT INTO coin_packages" in combined

    assert "ledger_entries" not in combined


async def test_the_suite_signs_with_the_secret_the_app_verifies_with(app_client):
    """One assertion instead of a hundred confusing 401s.

    CI once supplied its own secret, `setdefault` let it through, and every
    test that authenticates failed with `401 Unauthorized` — which reads like
    an auth bug rather than what it was, a fixture signing with a key the app
    had never heard of. The next environment to try it fails here, once,
    saying what is actually wrong.
    """
    from backend.config import get_settings

    settings = get_settings()
    assert settings.jwt_secret == conftest.TEST_JWT_SECRET
    assert settings.admin_player_codes == [conftest.TEST_ADMIN_CODE]
    assert settings.internal_api_key == "", "the suite runs with the web-tier gate open"

    headers = await conftest.authorise(app_client, 9911)
    response = await app_client.get("/v1/me", headers=headers)
    assert response.status_code == 200, response.text
