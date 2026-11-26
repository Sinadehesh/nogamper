"""The migration runner, run for real against throwaway databases.

`scripts/migrate.py` is the only program that changes production's schema: a
deploy runs it before traffic moves. It had no tests of its own. Deploys
exercised it — which is to say it was tested in production, and only ever
along the one path production happened to take.

The paths that matter are the ones a deploy takes once. A database that was
migrated by hand before the runner existed has to be *baselined*, and that
path left the runner's own bookkeeping table as the single table in the schema
without row security: migration 0006 protects every table that exists when it
runs, and on a baselined database this one is created afterwards. Nothing
failed, so nothing noticed.

Each test gets its own empty database on the test server and drops it after.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest

REPO = Path(__file__).resolve().parents[3]
MIGRATIONS = sorted((REPO / "db" / "migrations").glob("*.sql"))


def _load_runner():
    """scripts/ is not a package, so the runner is loaded from its path."""
    spec = importlib.util.spec_from_file_location("migration_runner", REPO / "scripts/migrate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_runner()

_TABLES_WITHOUT_RLS = """
SELECT c.relname
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity
 ORDER BY c.relname
"""


@pytest.fixture
async def scratch() -> str:
    """The address of a new, empty database, dropped when the test ends."""
    server = os.environ["DATABASE_URL"]
    name = f"runner_{uuid.uuid4().hex[:12]}"

    admin = await asyncpg.connect(server)
    try:
        # The name is generated on the line above; nothing here is input.
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()

    try:
        yield urlunsplit(urlsplit(server)._replace(path=f"/{name}"))
    finally:
        admin = await asyncpg.connect(server)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()


async def _run(dsn: str, *, baseline: bool = False, dry_run: bool = False) -> int:
    return await runner.migrate(dsn, baseline=baseline, dry_run=dry_run)


async def _query(dsn: str, sql: str) -> list[asyncpg.Record]:
    conn = await asyncpg.connect(dsn)
    try:
        return await conn.fetch(sql)
    finally:
        await conn.close()


async def _tables_without_row_security(dsn: str) -> list[str]:
    return [row["relname"] for row in await _query(dsn, _TABLES_WITHOUT_RLS)]


async def _migrate_by_hand(dsn: str) -> None:
    """Every file replayed as psql would, each inside its own BEGIN/COMMIT.

    This is how a database comes to have the schema and no record of it.
    """
    conn = await asyncpg.connect(dsn)
    try:
        for path in MIGRATIONS:
            await conn.execute(path.read_text(encoding="utf-8"))
    finally:
        await conn.close()


async def test_a_fresh_database_is_migrated_once(scratch, capsys):
    assert await _run(scratch) == 0
    assert f"applied {len(MIGRATIONS)} migration(s)" in capsys.readouterr().out

    recorded = await _query(scratch, "SELECT version, checksum FROM schema_migrations")
    assert sorted(row["version"] for row in recorded) == [path.name for path in MIGRATIONS]
    assert all(row["checksum"] and len(row["checksum"]) == 64 for row in recorded)


async def test_a_second_run_finds_nothing_to_do(scratch, capsys):
    """What every deploy that adds no migration does."""
    await _run(scratch)
    capsys.readouterr()

    assert await _run(scratch) == 0
    out = capsys.readouterr().out
    assert "schema is up to date" in out
    assert "applying" not in out


async def test_a_dry_run_changes_nothing(scratch, capsys):
    assert await _run(scratch, dry_run=True) == 0
    assert "nothing applied" in capsys.readouterr().out

    tables = await _query(
        scratch, "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"
    )
    assert [row["tablename"] for row in tables] == ["schema_migrations"]
    assert await _query(scratch, "SELECT 1 FROM schema_migrations") == []


async def test_a_fresh_database_has_row_security_everywhere(scratch):
    await _run(scratch)
    assert await _tables_without_row_security(scratch) == []


async def test_a_hand_migrated_database_is_refused_until_it_is_baselined(scratch, capsys):
    """Refused rather than guessed at: applying 0001 over a live schema fails,
    and marking a file applied that was not means its changes never land."""
    await _migrate_by_hand(scratch)

    assert await _run(scratch) == 3
    assert "--baseline" in capsys.readouterr().err
    assert await _query(scratch, "SELECT 1 FROM schema_migrations") == []

    assert await _run(scratch, baseline=True) == 0
    recorded = await _query(scratch, "SELECT version FROM schema_migrations")
    assert len(recorded) == len(MIGRATIONS)

    # From here on it is a database like any other.
    capsys.readouterr()
    assert await _run(scratch) == 0
    assert "schema is up to date" in capsys.readouterr().out


async def test_baselining_leaves_no_table_without_row_security(scratch):
    """The gap: 0006 had already run when the tracking table was created."""
    await _migrate_by_hand(scratch)
    assert await _tables_without_row_security(scratch) == []  # true before the runner arrives

    assert await _run(scratch, baseline=True) == 0
    assert await _tables_without_row_security(scratch) == []


async def test_a_refused_run_still_protects_the_table_it_created(scratch):
    """The refusal creates the tracking table too, and a database can sit in
    that state for as long as it takes somebody to read the message."""
    await _migrate_by_hand(scratch)
    assert await _run(scratch) == 3
    assert await _tables_without_row_security(scratch) == []


async def test_a_table_already_left_open_is_closed_on_the_next_run(scratch, capsys):
    """For the databases baselined before this was fixed: no step to remember,
    the next deploy does it."""
    await _run(scratch)
    conn = await asyncpg.connect(scratch)
    try:
        await conn.execute("ALTER TABLE schema_migrations DISABLE ROW LEVEL SECURITY")
    finally:
        await conn.close()
    assert await _tables_without_row_security(scratch) == ["schema_migrations"]
    capsys.readouterr()

    assert await _run(scratch) == 0
    assert "enabled row security on schema_migrations" in capsys.readouterr().out
    assert await _tables_without_row_security(scratch) == []


async def test_the_runner_can_still_read_its_own_records_under_row_security(scratch):
    """Row security with no policy hides every row from everyone but the
    owner. If the runner were not the owner it would see an empty table and
    try to apply 0001 again."""
    await _run(scratch)
    forced = await _query(
        scratch,
        "SELECT relforcerowsecurity FROM pg_class WHERE oid = 'schema_migrations'::regclass",
    )
    assert forced[0]["relforcerowsecurity"] is False
    assert await _run(scratch) == 0


async def test_an_edited_migration_is_refused(scratch, capsys):
    """An applied file that no longer matches what ran is a schema nobody can
    reason about. The runner stops and names it."""
    await _run(scratch)
    conn = await asyncpg.connect(scratch)
    try:
        await conn.execute(
            "UPDATE schema_migrations SET checksum = repeat('0', 64) WHERE version = $1",
            MIGRATIONS[0].name,
        )
    finally:
        await conn.close()
    capsys.readouterr()

    assert await _run(scratch) == 4
    assert MIGRATIONS[0].name in capsys.readouterr().err
