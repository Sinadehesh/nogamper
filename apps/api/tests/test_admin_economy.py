"""The operator's revenue view, and the gate in front of it.

Two things are being tested here and only one of them is arithmetic.

The other is that this endpoint reports lifetime takings, per-player stake
distributions and conversion rates — everything a competitor or a curious
player would want and nothing they are entitled to. The gate tests come first
for that reason: a wrong number is embarrassing, an open endpoint is a breach.
"""

from __future__ import annotations

import pytest
from conftest import TEST_ADMIN_TELEGRAM_ID, authorise

from backend import db

ECONOMY = "/v1/admin/economy"


async def buy(user_id, *, stars: int, coins: int, status: str = "PAID", charge: str | None = None):
    """A settled Star purchase, written the way the payment webhook writes one."""
    async with db.transaction() as conn:
        await conn.execute(
            """
            INSERT INTO star_purchases (user_id, package_code, invoice_payload, stars_amount,
                coins_amount, status, telegram_payment_charge_id, paid_at, refunded_at)
            VALUES ($1, 'TIER_1', $2, $3, $4, $5::star_purchase_status, $6, NOW(),
                    CASE WHEN $5 = 'REFUNDED' THEN NOW() END)
            """,
            user_id,
            f"payload-{charge or stars}-{user_id}",
            stars,
            coins,
            status,
            charge or f"charge-{stars}-{user_id}",
        )


async def user_id_for(telegram_id: int):
    async with db.acquire() as conn:
        return await conn.fetchval("SELECT id FROM users WHERE telegram_id = $1", telegram_id)


async def post_ledger(user_id, entry_type: str, amount: int, key: str) -> None:
    """Write a ledger entry the way the app does — a plain INSERT.

    fn_post_ledger_entry is a BEFORE trigger, not something you call: it stamps
    balance_after and moves users.coin_balance off the row being inserted. So
    going through the table is not a shortcut around the invariants, it is the
    only door, and a debit past zero still raises PT001 here exactly as it
    would in production.
    """
    async with db.transaction() as conn:
        await conn.execute(
            """
            INSERT INTO ledger_entries (user_id, entry_type, amount, idempotency_key)
            VALUES ($1, $2::ledger_entry_type, $3, $4)
            """,
            user_id,
            entry_type,
            amount,
            key,
        )


async def test_an_anonymous_caller_gets_nothing(app_client):
    response = await app_client.get(ECONOMY)
    assert response.status_code == 401


async def test_an_ordinary_player_cannot_see_revenue(app_client):
    """404, not 403.

    403 would confirm the route exists and that an allowlist is the only thing
    in the way, which tells a curious player exactly what to go looking for.
    404 is what every unknown path returns, so the admin surface does not
    announce itself.
    """
    headers = await authorise(app_client, telegram_id=4242)
    response = await app_client.get(ECONOMY, headers=headers)

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_an_allowlisted_player_can(app_client):
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    response = await app_client.get(ECONOMY, headers=headers)
    assert response.status_code == 200


async def test_an_empty_allowlist_denies_everyone(app_client, monkeypatch):
    """The failure mode worth engineering against.

    "Unset means unrestricted" is the reading that publishes lifetime revenue
    on the first deploy that forgets the variable, silently, to anyone who
    guesses the path. There is no reading of ADMIN_TELEGRAM_IDS="" that should
    show a stranger the takings.
    """
    from backend.config import get_settings

    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)

    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "")
    get_settings.cache_clear()
    try:
        response = await app_client.get(ECONOMY, headers=headers)
        assert response.status_code == 404
    finally:
        get_settings.cache_clear()


async def test_refunded_stars_do_not_count_as_revenue(app_client):
    """Gross alone is how a refunded month reads as a good one.

    Telegram lets a player refund Stars, so gross is a number you cannot bank.
    Net is what survives to a withdrawal, and it is the one the dashboard
    leads with.
    """
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    admin = await user_id_for(TEST_ADMIN_TELEGRAM_ID)

    await buy(admin, stars=100, coins=1_000_000, charge="kept")
    await buy(admin, stars=40, coins=400_000, status="REFUNDED", charge="given-back")

    body = (await app_client.get(ECONOMY, headers=headers)).json()

    assert body["revenue"]["stars_gross"] == 100
    assert body["revenue"]["stars_refunded"] == 40
    assert body["revenue"]["stars_net"] == 60


async def test_lifetime_and_window_are_reported_apart(app_client):
    """A cumulative total read as a run rate is a business-planning error, so
    the two never share a field."""
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    admin = await user_id_for(TEST_ADMIN_TELEGRAM_ID)

    await buy(admin, stars=50, coins=500_000, charge="recent")
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE star_purchases SET paid_at = NOW() - INTERVAL '200 days' "
            "WHERE telegram_payment_charge_id = 'recent'"
        )
    await buy(admin, stars=25, coins=250_000, charge="today")

    body = (await app_client.get(ECONOMY, headers=headers, params={"days": 7})).json()

    assert body["revenue"]["stars_net"] == 25, "an old purchase leaked into the window"
    assert body["lifetime"]["stars_net"] == 75


async def test_the_daily_series_has_a_row_for_every_day(app_client):
    """A day with no sales must be a zero, not a missing row.

    A chart that drops empty days draws a straight line through them, which
    reads as steady trade during a week when nothing sold at all.
    """
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    body = (await app_client.get(ECONOMY, headers=headers, params={"days": 14})).json()

    assert len(body["daily"]) == 15
    assert all(day["stars"] == 0 for day in body["daily"])


async def test_the_house_edge_is_the_gap_between_stakes_and_payouts(app_client):
    """The vig has no ledger entry of its own.

    It is priced into the odds, so the only place it exists is the difference
    between what players staked and what they were paid back. That makes it
    invisible per-row and the single most important aggregate on the page.
    """
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    admin = await user_id_for(TEST_ADMIN_TELEGRAM_ID)

    await post_ledger(admin, "STAR_PURCHASE_CREDIT", 1_000_000, "funding")
    await post_ledger(admin, "STAKE_DEBIT", -100_000, "bet-1")
    await post_ledger(admin, "PAYOUT_CREDIT", 90_000, "won-1")

    body = (await app_client.get(ECONOMY, headers=headers)).json()

    assert body["balance"]["house_edge"]["minor"] == 10_000
    assert body["balance"]["minted_purchased"]["minor"] == 1_000_000


async def test_free_coins_are_counted_separately_from_bought_ones(app_client):
    """Two different businesses share one balance column: coins given away to
    keep people playing, and coins sold. Netting them hides which is which."""
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    admin = await user_id_for(TEST_ADMIN_TELEGRAM_ID)

    await post_ledger(admin, "DAILY_DRIP_CREDIT", 25_000, "drip")
    await post_ledger(admin, "STREAK_BONUS_CREDIT", 5_000, "streak")
    await post_ledger(admin, "STAR_PURCHASE_CREDIT", 500_000, "bought")

    body = (await app_client.get(ECONOMY, headers=headers)).json()

    assert body["balance"]["minted_free"]["minor"] == 25_000 + 5_000 + 100_000
    assert body["balance"]["minted_purchased"]["minor"] == 500_000


async def test_the_net_change_reconciles_with_the_whole_ledger(app_client):
    """A guard against the balance block drifting from reality.

    minted_free, house_edge and the rest each name a subset of entry types. Add
    a new type and forget to classify it and those subsets quietly stop summing
    to the truth — so net_change is computed over *every* row instead, and this
    test is what notices when they disagree.
    """
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    admin = await user_id_for(TEST_ADMIN_TELEGRAM_ID)

    await post_ledger(admin, "STAR_PURCHASE_CREDIT", 400_000, "in")
    await post_ledger(admin, "STAKE_DEBIT", -50_000, "out")
    await post_ledger(admin, "INACTIVITY_DECAY_DEBIT", -1_000, "decay")

    body = (await app_client.get(ECONOMY, headers=headers)).json()

    from_rows = sum(row["net"]["minor"] for row in body["ledger"])
    assert body["balance"]["net_change"]["minor"] == from_rows

    async with db.acquire() as conn:
        actual = await conn.fetchval("SELECT COALESCE(SUM(amount), 0) FROM ledger_entries")
    assert body["balance"]["net_change"]["minor"] == actual


async def test_break_even_is_derived_from_the_live_settings(app_client):
    """(daily drip + max streak bonus) / vig.

    Written down as a constant it would silently stop being true the first
    time somebody retuned the drip — which is exactly the change that most
    needs this number to move with it.
    """
    from backend.config import get_settings

    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    body = (await app_client.get(ECONOMY, headers=headers)).json()

    settings = get_settings()
    edge = 1 - (1 - settings.vig_rate) ** settings.min_legs
    expected = round((settings.daily_drip_minor + settings.streak_bonus_max_minor) / edge)
    assert body["break_even_daily_stake"]["minor"] == expected


async def test_a_player_below_break_even_is_counted_as_free(app_client):
    """The distribution is the forecast.

    Revenue says what happened last month. The share of active players staking
    below break-even says what will happen next month, because those players
    can play forever without ever spending a Star.
    """
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    admin = await user_id_for(TEST_ADMIN_TELEGRAM_ID)

    await post_ledger(admin, "STAR_PURCHASE_CREDIT", 10_000_000, "funding")
    await post_ledger(admin, "STAKE_DEBIT", -45_000, "small-bets")

    body = (await app_client.get(ECONOMY, headers=headers, params={"days": 30})).json()

    buckets = {b["bucket"]: b["players"] for b in body["break_even_buckets"]}
    assert buckets["far_below"] == 1
    assert body["free_players_share"] == 1.0


async def test_a_heavy_player_lands_above_break_even(app_client):
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    admin = await user_id_for(TEST_ADMIN_TELEGRAM_ID)

    await post_ledger(admin, "STAR_PURCHASE_CREDIT", 900_000_000, "funding")
    await post_ledger(admin, "STAKE_DEBIT", -450_000_000, "big-bets")

    body = (await app_client.get(ECONOMY, headers=headers, params={"days": 30})).json()

    buckets = {b["bucket"]: b["players"] for b in body["break_even_buckets"]}
    assert buckets["far_above"] == 1
    assert body["free_players_share"] == 0.0


async def test_every_bucket_is_present_even_when_empty(app_client):
    """An empty bucket is a finding, not an absence.

    A list whose shape changes with the data cannot be read at a glance or
    compared against last week's, and "no players above break-even" is the most
    important thing this report can say.
    """
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    body = (await app_client.get(ECONOMY, headers=headers)).json()

    assert [b["bucket"] for b in body["break_even_buckets"]] == [
        "far_below",
        "below",
        "at",
        "above",
        "far_above",
    ]
    assert all(b["players"] == 0 for b in body["break_even_buckets"])


async def test_conversion_is_measured_against_players_who_actually_played(app_client):
    """Against total signups it would flatter itself with everyone who opened
    the app once and never placed a bet."""
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    admin = await user_id_for(TEST_ADMIN_TELEGRAM_ID)

    await authorise(app_client, telegram_id=4242)

    await post_ledger(admin, "STAKE_DEBIT", -10_000, "played")
    await buy(admin, stars=50, coins=500_000, charge="paid")

    body = (await app_client.get(ECONOMY, headers=headers)).json()

    assert body["players"]["total"] == 2
    assert body["players"]["staked_in_window"] == 1
    assert body["players"]["conversion_rate"] == 1.0


async def test_package_mix_shows_what_a_star_buys_on_each_tier(app_client):
    """The usual reason one pack outsells another is its coins-per-Star, so the
    rate sits next to the sales rather than a table away."""
    headers = await authorise(app_client, telegram_id=TEST_ADMIN_TELEGRAM_ID)
    body = (await app_client.get(ECONOMY, headers=headers)).json()

    by_code = {p["code"]: p for p in body["packages"]}

    assert by_code["TIER_3"]["coins_per_star"] > by_code["TIER_2"]["coins_per_star"]
    assert by_code["TIER_2"]["coins_per_star"] > by_code["TIER_1"]["coins_per_star"]

    tier1 = by_code["TIER_1"]
    assert tier1["coins_per_star"] == pytest.approx(
        tier1["coins"]["minor"] / tier1["stars_price"] / 100, abs=0.01
    )
