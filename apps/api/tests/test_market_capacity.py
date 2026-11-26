"""The catalogue must never outgrow what the price sync can keep fresh.

The outage this pins had no failing component. Discovery's defaults — three
categories, twenty pages of a hundred — ingested 7,268 ACTIVE markets. The
price sync refreshes a few hundred per pass against a 90-second staleness
window, so it could never come back round to any given market in time. Every
card in the app read "this price is updating", indefinitely, while every job
ran exactly as designed and nothing raised.

The diagnostics endpoint then reported "Polymarket is the problem", which was
worse than saying nothing: it sent the operator to an upstream that was
working.

Two things are under test. That discovery trims the catalogue to the pricing
budget without ever pulling a market somebody has money on, and that the
endpoint names capacity rather than blaming a healthy upstream.
"""

from __future__ import annotations

import uuid

import pytest

from backend import db
from backend.repositories import diagnostics
from backend.repositories import markets as markets_repo


async def seed_market(
    *, volume: float, priced_secs_ago: int = 0, category: str = "Crypto"
) -> uuid.UUID:
    async with db.transaction() as conn:
        event_id = await conn.fetchval(
            """
            INSERT INTO market_events (polymarket_event_id, slug, title, title_source,
                                       category, end_date)
            VALUES ($1, $1, 'e', 'e', $2, NOW() + INTERVAL '10 days')
            RETURNING id
            """,
            f"evt-{uuid.uuid4()}",
            category,
        )
        return await conn.fetchval(
            """
            INSERT INTO markets (event_id, polymarket_market_id, condition_id, question,
                                 category, yes_token_id, no_token_id, raw_yes_prob,
                                 volume_usd, lock_at, end_date, question_source, status,
                                 price_updated_at)
            VALUES ($1, $2, $2, 'q?', $5, $2 || '-y', $2 || '-n', 0.5, $3,
                    NOW() + INTERVAL '9 days', NOW() + INTERVAL '10 days', 'q?', 'ACTIVE',
                    NOW() - make_interval(secs => $4))
            RETURNING id
            """,
            event_id,
            f"mkt-{uuid.uuid4()}",
            volume,
            float(priced_secs_ago),
            category,
        )


async def status_of(market_id: uuid.UUID) -> str:
    async with db.transaction() as conn:
        return await conn.fetchval("SELECT status::TEXT FROM markets WHERE id = $1", market_id)


async def retire(keep: int, priority: str | None = None) -> int:
    async with db.transaction() as conn:
        return await markets_repo.retire_surplus_markets(
            conn, keep=keep, priority_category=priority
        )


async def test_the_busiest_markets_are_the_ones_kept(resources):
    """Ranked by volume because that is what discovery already pages by: the
    budget should be spent on the markets people are actually trading."""
    busy = await seed_market(volume=9_000)
    quiet = await seed_market(volume=1)

    assert await retire(1) == 1
    assert await status_of(busy) == "ACTIVE"
    assert await status_of(quiet) == "DRAFT"


async def stake_on(market_id: uuid.UUID, *, status: str = "PENDING") -> None:
    """Put an open leg on a market, the way a placed slip does."""
    async with db.transaction() as conn:
        event_id = await conn.fetchval("SELECT event_id FROM markets WHERE id = $1", market_id)
        user_id = await conn.fetchval(
            """
            INSERT INTO users (telegram_id, first_name)
            VALUES (floor(random() * 1e9)::BIGINT, 'staker')
            RETURNING id
            """
        )
        prediction_id = await conn.fetchval(
            """
            INSERT INTO predictions (user_id, idempotency_key, request_fingerprint, type,
                                     leg_count, stake, combined_odds, gross_potential_payout,
                                     payout_cap, potential_payout)
            VALUES ($1, $2, 'fp', 'SINGLE', 1, 10000, 2.0, 20000, 20000, 20000)
            RETURNING id
            """,
            user_id,
            f"idem-{uuid.uuid4()}",
        )
        await conn.execute(
            """
            INSERT INTO prediction_legs (prediction_id, leg_index, market_id, event_id, side,
                                         raw_prob, vig_rate, locked_odds, status, settled_at)
            VALUES ($1, 1, $2, $3, 'YES', 0.5, 0.05, 2.0, $4::leg_status,
                    CASE WHEN $4 = 'PENDING' THEN NULL ELSE NOW() END)
            """,
            prediction_id,
            market_id,
            event_id,
            status,
        )


async def test_a_market_someone_has_money_on_is_never_retired(resources):
    """The one hard rule. Pulling a market out from under an open leg would
    strand the slip it belongs to, so a pending leg outranks the budget even
    when the market is the least traded thing in the catalogue."""
    staked = await seed_market(volume=1)
    await stake_on(staked)
    busy = await seed_market(volume=9_000)

    assert await retire(1) == 0
    assert await status_of(staked) == "ACTIVE"
    assert await status_of(busy) == "ACTIVE"


async def test_a_settled_leg_does_not_protect_a_market_forever(resources):
    """Only *open* money holds a market open. A market whose legs have all
    settled is finished business, and keeping it would spend the budget on
    something nobody can bet on."""
    finished = await seed_market(volume=1)
    await stake_on(finished, status="WON")
    await seed_market(volume=9_000)

    assert await retire(1) == 1
    assert await status_of(finished) == "DRAFT"


async def test_a_catalogue_inside_the_budget_is_left_alone(resources):
    """A retirement that fires when nothing is wrong would quietly shrink the
    app every hour."""
    kept = [await seed_market(volume=100) for _ in range(3)]

    assert await retire(10) == 0
    for market_id in kept:
        assert await status_of(market_id) == "ACTIVE"


async def test_a_retired_market_comes_back_if_its_volume_does(resources):
    """DRAFT rather than VOID or deleted, so this is reversible: the next
    discovery run upserts it and the status CASE promotes it to ACTIVE."""
    quiet = await seed_market(volume=1)
    await seed_market(volume=9_000)
    await retire(1)
    assert await status_of(quiet) == "DRAFT"

    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE markets SET status = 'ACTIVE', volume_usd = 50000 WHERE id = $1", quiet
        )
    assert await retire(1) == 1
    assert await status_of(quiet) == "ACTIVE"


async def test_the_sync_never_fans_out_past_its_budget(resources):
    """A backlog larger than the budget used to become that many simultaneous
    tasks and connections, so the pass got slower exactly when it could least
    afford to."""
    for age in range(5):
        await seed_market(volume=100, priced_secs_ago=age * 100)

    async with db.transaction() as conn:
        capped = await markets_repo.list_syncable_markets(conn, limit=2)
        uncapped = await markets_repo.list_syncable_markets(conn)

    assert len(capped) == 2
    assert len(uncapped) == 5
    assert [m.id for m in capped] == [m.id for m in uncapped[:2]]


async def test_the_active_count_is_read_separately_from_the_capped_list(resources):
    """Once the list is capped its length can no longer tell the sync whether
    it is keeping up — which is the number the warning is about."""
    for _ in range(4):
        await seed_market(volume=100)

    async with db.transaction() as conn:
        assert await markets_repo.count_active_markets(conn) == 4
        assert len(await markets_repo.list_syncable_markets(conn, limit=2)) == 2


def _health(**overrides) -> diagnostics.PriceHealth:
    from datetime import UTC, datetime

    base = dict(
        markets_total=7268,
        markets_active=7268,
        markets_locked=18,
        markets_fresh=0,
        newest_price_at=datetime.now(UTC),
        oldest_price_at=datetime.now(UTC),
        seconds_since_newest=1320.0,
        cache_reachable=True,
        cache_hits=0,
        cache_sampled=20,
        leases=[diagnostics.JobLease("polymarket_price_sync", "srv-1", 5.0, 100.0)],
    )
    return diagnostics.PriceHealth(**{**base, **overrides})


def test_an_oversized_catalogue_is_not_blamed_on_polymarket():
    """The exact state the operator was looking at: 0 of 7268 priced, the job
    cycling normally, and the endpoint saying the CLOB was returning nothing
    usable. It was not. There were simply twenty times more markets than the
    sync was budgeted for."""
    layer, advice = diagnostics.explain(_health(), staleness_seconds=90, max_markets=400)

    assert layer == "capacity"
    assert "7268" in advice
    assert "400" in advice
    assert "nothing here has failed" in advice


def test_a_stale_upstream_within_budget_is_still_blamed_on_the_upstream():
    """The capacity check must not swallow the real upstream failure it sits
    in front of."""
    layer, _ = diagnostics.explain(
        _health(markets_active=120, markets_total=120), staleness_seconds=90, max_markets=400
    )
    assert layer == "upstream"


def test_a_stuck_job_still_outranks_capacity():
    """An oversized catalogue is a permanent condition; a job that will not
    finish is happening now, and is the thing to look at first."""
    stuck = diagnostics.JobLease("polymarket_price_sync", "srv-1", 1200.0, 60.0)
    layer, _ = diagnostics.explain(_health(leases=[stuck]), staleness_seconds=90, max_markets=400)
    assert layer == "worker"


def test_nothing_running_still_outranks_capacity():
    """Trimming the catalogue will not help if no worker is running the sync,
    so that stays the first thing said."""
    layer, _ = diagnostics.explain(_health(leases=[]), staleness_seconds=90, max_markets=400)
    assert layer == "worker"


def test_a_partly_stale_oversized_catalogue_is_capacity_not_a_truncated_pass():
    """With the newest price current, a stale tail normally reads as the
    deadline doing its job — expected under load. When the catalogue is over
    budget that reading is wrong: the tail is permanent, not transient."""
    layer, _ = diagnostics.explain(
        _health(markets_fresh=300, seconds_since_newest=5.0, cache_hits=300),
        staleness_seconds=90,
        max_markets=400,
    )
    assert layer == "capacity"


@pytest.mark.parametrize("active", [399, 400])
def test_a_catalogue_at_or_under_budget_is_never_called_a_capacity_problem(active):
    """The boundary. Reporting capacity at exactly the budget would tell the
    operator to shrink a catalogue that already fits."""
    layer, _ = diagnostics.explain(
        _health(markets_active=active, markets_total=active),
        staleness_seconds=90,
        max_markets=400,
    )
    assert layer != "capacity"


async def test_the_endpoint_reports_capacity_over_a_real_oversized_catalogue(
    app_client, monkeypatch
):
    """The whole path, because the operator reads the banner and not explain().

    This is the state that was on screen: markets priced 0 of thousands, the
    job cycling normally, and the endpoint saying Polymarket was the problem.
    """
    from conftest import TEST_ADMIN_TELEGRAM_ID, authorise
    from test_diagnostics import hold_lease

    from backend.config import get_settings

    monkeypatch.setattr(get_settings(), "price_sync_max_markets", 2)

    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    for _ in range(5):
        await seed_market(volume=100, priced_secs_ago=1800)
    await hold_lease("polymarket_price_sync", held_for_secs=5)

    body = (await app_client.get("/v1/admin/diagnostics", headers=headers)).json()

    assert body["layer"] == "capacity"
    assert body["markets_active"] == 5
    assert body["markets_budget"] == 2
    assert "nothing here has failed" in body["advice"]


async def test_the_priority_category_survives_a_trim_it_would_lose_on_volume(resources):
    """The exemption that makes a niche category possible at all.

    Ranking by volume is right for the catalogue and wrong for the one
    category the feed is built around: a regional market carries a fraction of
    the volume of the crypto and macro markets it is ranked against, so it is
    always the first thing parked. Discovery would then pay to translate and
    write markets the trim removes seconds later, and the tab would be empty
    in production while passing every test with ten markets in it.
    """
    busy = await seed_market(volume=9_000)
    quiet_priority = await seed_market(volume=1, category="Iran")

    assert await retire(1, "Iran") == 1
    assert await status_of(quiet_priority) == "ACTIVE"
    assert await status_of(busy) == "DRAFT"


async def test_the_priority_category_is_counted_against_the_budget_not_added_to_it(resources):
    """The exemption reorders the ranking; it does not raise the ceiling.

    The budget exists because the price sync can only keep so many markets
    inside the staleness window. A priority category that was added on top of
    `keep` would reintroduce the outage this whole module pins, one region at
    a time.
    """
    for _ in range(3):
        await seed_market(volume=9_000)
    for _ in range(3):
        await seed_market(volume=1, category="Iran")

    assert await retire(2, "Iran") == 4

    async with db.transaction() as conn:
        active = await conn.fetch(
            "SELECT category FROM markets WHERE status = 'ACTIVE' ORDER BY category"
        )
    assert [r["category"] for r in active] == ["Iran", "Iran"]


async def test_without_a_priority_category_the_ranking_is_unchanged(resources):
    """The preference is opt-in; an empty setting must behave as it always did."""
    busy = await seed_market(volume=9_000, category="Iran")
    quiet = await seed_market(volume=1, category="Iran")

    assert await retire(1, None) == 1
    assert await status_of(busy) == "ACTIVE"
    assert await status_of(quiet) == "DRAFT"
