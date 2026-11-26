"""Every table in `public` stays closed to PostgREST.

Supabase runs PostgREST in front of this database, answering
https://<ref>.supabase.co/rest/v1/<table> for anyone holding the project's
`anon` key — a key designed to be embedded in client code. Without RLS, the
only thing between the internet and `ledger_entries` is whether someone has
looked that key up.

`0006_lock_down_public_schema.sql` enables RLS on everything and revokes the
PostgREST roles outright. This test is the part that keeps it true: it reads
the catalogue rather than a list, so the table somebody adds next month is
covered by it automatically, and a migration that forgets RLS fails here
instead of arriving as a CRITICAL alert weeks later.
"""

from __future__ import annotations

from backend import db

_TABLES_WITHOUT_RLS = """
SELECT c.relname
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public'
   AND c.relkind = 'r'
   AND NOT c.relrowsecurity
 ORDER BY c.relname
"""


async def test_every_public_table_has_rls_enabled(resources):
    async with db.acquire() as conn:
        unprotected = [row["relname"] for row in await conn.fetch(_TABLES_WITHOUT_RLS)]

    assert unprotected == [], (
        "these tables are exposed to PostgREST with no row security: "
        f"{unprotected}. Add them to a migration that runs "
        "ALTER TABLE ... ENABLE ROW LEVEL SECURITY, following 0006."
    )


async def test_the_application_is_unaffected_by_rls(resources):
    """A table's owner is exempt unless FORCE ROW LEVEL SECURITY is set.

    That exemption is the whole reason this lockdown is safe, and it is quiet
    enough to be worth asserting: if a migration ever adds FORCE, every query
    in the app starts returning nothing and the cause is invisible.
    """
    async with db.acquire() as conn:
        forced = await conn.fetch(
            """
            SELECT c.relname
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relforcerowsecurity
            """
        )
        readable = await conn.fetchval("SELECT count(*) FROM app_config")

    assert [row["relname"] for row in forced] == []
    assert readable > 0, "RLS is filtering the application's own reads"


async def test_no_table_carries_a_policy_that_would_reopen_it(resources):
    """RLS with no policies denies everything to non-owners, which is the
    intent here. A policy would be somebody re-opening a door — legitimate if
    deliberate, worth failing over if not."""
    async with db.acquire() as conn:
        policies = await conn.fetch(
            "SELECT schemaname, tablename, policyname FROM pg_policies WHERE schemaname = 'public'"
        )

    assert [dict(p) for p in policies] == [], (
        "a policy grants PostgREST roles access again. If that is intended, "
        "say so here and narrow this test to the tables it should cover."
    )
