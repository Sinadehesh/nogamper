#!/usr/bin/env bash
# Apply the schema and run the invariant suite in a throwaway PostgreSQL cluster.
# Requires PostgreSQL 14+ binaries (initdb, pg_ctl, psql) on PATH.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
PORT="${PGTEST_PORT:-55432}"

cleanup() {
    pg_ctl -D "$WORK/data" -m immediate stop >/dev/null 2>&1 || true
    rm -rf "$WORK"
}
trap cleanup EXIT

initdb -D "$WORK/data" -A trust -U postgres >/dev/null
pg_ctl -D "$WORK/data" -o "-p $PORT -k $WORK -c listen_addresses=" -l "$WORK/pg.log" start >/dev/null

export PGHOST="$WORK" PGPORT="$PORT" PGUSER=postgres

psql -q -c 'CREATE DATABASE appdb;'
for migration in "$ROOT"/db/migrations/*.sql; do
    echo "  applying $(basename "$migration")"
    psql -q -d appdb -v ON_ERROR_STOP=1 -f "$migration"
done
psql -q -d appdb -v ON_ERROR_STOP=1 -f "$ROOT/db/tests/invariants.sql"
