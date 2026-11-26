#!/usr/bin/env python3
"""Apply pending SQL migrations, exactly once each, atomically.

    DATABASE_URL=postgresql://…?sslmode=require python scripts/migrate.py

Wired to Render's preDeployCommand, so it runs before traffic moves to a new
release and a failure aborts the deploy rather than serving against a
half-migrated schema.

Exit codes: 0 nothing to do or everything applied, 1 bad configuration,
2 a migration failed, 3 the database predates this runner and needs
`--baseline` (see below), 4 an already-applied migration has been edited
since it ran.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import re
import sys
import time
from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"

_CREATE_TRACKING = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    VARCHAR PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum   VARCHAR(64)
)
"""

_ADD_CHECKSUM = """
ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum VARCHAR(64)
"""

LOCK_KEY = 0x6D66_4D49_4752_0001

_BEGIN = re.compile(r"^BEGIN\s*;[ \t]*$", re.MULTILINE)
_COMMIT = re.compile(r"^COMMIT\s*;[ \t]*$", re.MULTILINE)


class ConfigError(Exception):
    """The environment or the migrations directory is wrong."""


class NeedsBaseline(Exception):
    """The database has a schema this runner never recorded applying."""


class MigrationTamperedError(Exception):
    """An already-applied migration has been edited since it ran."""


def strip_transaction_control(sql: str, name: str) -> str:
    """Remove a file's own BEGIN;/COMMIT; so the runner owns the transaction.

    Every migration here opens and closes its own transaction. Left in place,
    the file's COMMIT would commit the runner's transaction, and the version
    row would then be written outside it — so a crash between the two would
    leave a migration applied but unrecorded, and the next run would try to
    apply it again.

    Stripping them means the schema change and its schema_migrations row commit
    together or not at all. New migrations need not include BEGIN/COMMIT at
    all; files without them pass through untouched.
    """
    begins = _BEGIN.findall(sql)
    commits = _COMMIT.findall(sql)

    if not begins and not commits:
        return sql
    if len(begins) != 1 or len(commits) != 1:
        raise ConfigError(
            f"{name}: expected either no top-level transaction control or exactly one "
            f"BEGIN;/COMMIT; pair, found {len(begins)} BEGIN and {len(commits)} COMMIT. "
            "Split the file, or remove its transaction control and let the runner own it."
        )
    if _BEGIN.search(sql).start() > _COMMIT.search(sql).start():
        raise ConfigError(f"{name}: COMMIT; appears before BEGIN;")

    return _COMMIT.sub("", _BEGIN.sub("", sql, count=1), count=1)


def checksum(sql: str) -> str:
    """SHA-256 of the sanitised SQL — the bytes actually executed."""
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def read_and_hash(path: Path) -> tuple[str, str]:
    """The SQL that will run, and its digest.

    Hashing after strip_transaction_control(), not before, so removing a file's
    now-redundant BEGIN;/COMMIT; is not mistaken for tampering. The runner owns
    the transaction either way, so that edit changes nothing about what runs.
    """
    sql = strip_transaction_control(path.read_text(encoding="utf-8"), path.name)
    return sql, checksum(sql)


def discover(directory: Path) -> list[Path]:
    """Every .sql file, in deterministic order.

    sorted() on the filename is why migrations are numbered with a fixed-width
    prefix: 0010 must sort after 0009, and it does only while the padding
    holds.
    """
    if not directory.is_dir():
        raise ConfigError(f"no migrations directory at {directory}")
    files = sorted(directory.glob("*.sql"), key=lambda p: p.name)
    if not files:
        raise ConfigError(f"no .sql files in {directory}")
    return files


async def applied_versions(conn: asyncpg.Connection) -> dict[str, str | None]:
    rows = await conn.fetch("SELECT version, checksum FROM schema_migrations")
    return {row["version"]: row["checksum"] for row in rows}


def verify_checksums(files: list[Path], applied: dict[str, str | None]) -> list[str]:
    """Compare every applied migration against the file on disk.

    Runs before anything is applied, so a tampered 0002 is caught before 0007
    executes against a schema that is not what it was written for.

    Returns the notes worth printing; raises on an actual mismatch.
    """
    notes: list[str] = []
    tampered: list[str] = []
    on_disk = {path.name: path for path in files}

    for version, recorded in sorted(applied.items()):
        path = on_disk.get(version)
        if path is None:
            notes.append(f"  ⚠ {version} is recorded as applied but no longer exists on disk")
            continue
        if recorded is None:
            notes.append(f"  ⚠ {version} predates checksums and cannot be verified")
            continue

        _, actual = read_and_hash(path)
        if actual != recorded:
            tampered.append(f"    {version}\n      recorded {recorded}\n      on disk  {actual}")

    if tampered:
        raise MigrationTamperedError(
            "these migrations have changed since they were applied:\n"
            + "\n".join(tampered)
            + "\n\n  The database was built from the old content, so the file no longer "
            "describes\n  the schema that exists. Restore the file, or write a new "
            "migration for the\n  change you meant to make — never edit one that has run."
        )
    return notes


async def has_application_tables(conn: asyncpg.Connection) -> bool:
    """Is there already a schema here that this runner did not create?"""
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                 WHERE table_schema = 'public'
                   AND table_type = 'BASE TABLE'
                   AND table_name <> 'schema_migrations'
            )
            """
        )
    )


async def ensure_tracking(conn: asyncpg.Connection, *, baseline: bool, files: list[Path]) -> None:
    """Create the tracking table, refusing to guess about a pre-existing schema.

    A database migrated before this runner existed has the full schema and no
    record of it, so a naive run would try to apply 0001 against tables that
    already exist and fail on CREATE TABLE. Guessing which files were already
    applied would be worse than failing: mark one wrongly and its changes never
    land.

    So it stops and asks. `--baseline` records every discovered migration as
    applied without running any of them — the same move as `alembic stamp` or
    `flyway baseline`, and correct only when the schema really is up to date.

    The condition is "nothing recorded, but tables exist" rather than "no
    tracking table". Those differ, and the difference matters: a refusal that
    had already created an empty tracking table would make itself unreachable
    on the next run, and the runner would go straight back to applying 0001
    over a live schema.
    """
    await conn.execute(_CREATE_TRACKING)
    await conn.execute(_ADD_CHECKSUM)

    recorded = await conn.fetchval("SELECT count(*) FROM schema_migrations")
    if recorded:
        return
    if not await has_application_tables(conn):
        return

    if not baseline:
        raise NeedsBaseline(
            "this database already has tables but no recorded migrations, so it was "
            "migrated before this runner existed.\n"
            "  If its schema is up to date, record the existing migrations without "
            "running them:\n"
            "      python scripts/migrate.py --baseline\n"
            "  If it is not up to date, migrate it by hand first, then baseline."
        )

    print(f"  baselining {len(files)} migration(s) as already applied — running none of them")
    async with conn.transaction():
        for path in files:
            _, digest = read_and_hash(path)
            print(f"    recorded  {path.name}  {digest[:12]}…")
            await conn.execute(
                "INSERT INTO schema_migrations (version, checksum) VALUES ($1, $2) "
                "ON CONFLICT DO NOTHING",
                path.name,
                digest,
            )


async def apply_one(conn: asyncpg.Connection, path: Path) -> tuple[float, str]:
    sql, digest = read_and_hash(path)
    started = time.monotonic()

    async with conn.transaction():
        await conn.execute(sql)
        await conn.execute(
            "INSERT INTO schema_migrations (version, checksum) VALUES ($1, $2)",
            path.name,
            digest,
        )

    return time.monotonic() - started, digest


async def migrate(dsn: str, *, baseline: bool, dry_run: bool) -> int:
    files = discover(MIGRATIONS_DIR)
    print(f"  migrations  {MIGRATIONS_DIR}")
    print(f"  found       {len(files)} file(s)")

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", LOCK_KEY)

        try:
            await ensure_tracking(conn, baseline=baseline, files=files)
        except NeedsBaseline as exc:
            sys.stdout.flush()
            print(f"\n✗ {exc}", file=sys.stderr)
            return 3

        applied = await applied_versions(conn)
        pending = [path for path in files if path.name not in applied]

        print(f"  applied     {len(applied)}")
        print(f"  pending     {len(pending)}")

        try:
            for note in verify_checksums(files, applied):
                print(note)
        except MigrationTamperedError as exc:
            sys.stdout.flush()
            print(f"\n✗ {exc}", file=sys.stderr)
            return 4

        if not pending:
            print("\n✓ schema is up to date")
            return 0

        if dry_run:
            print("\n  would apply, in order:")
            for path in pending:
                print(f"    {path.name}")
            print("\n  dry run — nothing applied")
            return 0

        print()
        for path in pending:
            print(f"  applying  {path.name} …", flush=True)
            try:
                elapsed, digest = await apply_one(conn, path)
            except (asyncpg.PostgresError, ConfigError) as exc:
                sys.stdout.flush()
                print(f"\n✗ {path.name} failed and was rolled back", file=sys.stderr)
                print(f"  {type(exc).__name__}: {exc}", file=sys.stderr)
                remaining = pending[pending.index(path) + 1 :]
                if remaining:
                    print(
                        f"  not attempted: {', '.join(p.name for p in remaining)}",
                        file=sys.stderr,
                    )
                return 2
            print(f"  applied   {path.name} in {elapsed:.2f}s  {digest[:12]}…")

        print(f"\n✓ applied {len(pending)} migration(s)")
        return 0
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply pending SQL migrations exactly once each.")
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Record every migration as applied WITHOUT running it. For a database "
        "migrated before this runner existed, whose schema is already up to date.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be applied, and apply nothing.",
    )
    args = parser.parse_args()

    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        print("✗ DATABASE_URL is not set", file=sys.stderr)
        return 1

    host = dsn.split("@")[-1].split("?")[0] if "@" in dsn else "(local)"
    print(f"  database    {host}")

    try:
        return asyncio.run(migrate(dsn, baseline=args.baseline, dry_run=args.dry_run))
    except ConfigError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    except (asyncpg.PostgresError, OSError) as exc:
        print(f"✗ could not connect: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
