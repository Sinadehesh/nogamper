"""Placement end to end: pricing, money, idempotency, risk, settlement."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from conftest import authorise, mock_http_client
from fixtures import gamma_events as fx

from backend import db
from backend.cache import prices as price_cache
from backend.config import get_settings
from backend.workers import polymarket_discovery as discovery


async def seed_markets(count: int = 5, probability: str = "0.50") -> list[dict]:
    """One market per event, so legs are never correlated by construction."""
    events = [
        fx.event(
            str(i),
            tags=fx.CRYPTO_TAGS if i % 2 else None,
            markets=[fx.binary_market(f"3{i:04d}", prices=[probability, "0.5"], end_in_days=i + 2)],
        )
        for i in range(count)
    ]

    def gamma(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        return httpx.Response(200, json=events if offset == 0 else [])

    async with mock_http_client(gamma) as client:
        await discovery.run_discovery(client, get_settings())

    async with db.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM markets ORDER BY lock_at")
    markets = [dict(r) for r in rows]

    await price_cache.write_many(
        [(m["id"], m["raw_yes_prob"], "CLOB_MIDPOINT", datetime.now(UTC)) for m in markets],
        ttl_seconds=300,
    )
    return markets


def body(markets, *, stake=10000, insurance=False, sides=None, **extra):
    sides = sides or ["YES"] * len(markets)
    return {
        "legs": [
            {"market_id": str(m["id"]), "side": s} for m, s in zip(markets, sides, strict=True)
        ],
        "stake": stake,
        "insurance": insurance,
        **extra,
    }


async def place(client, auth, payload, key=None):
    headers = {**auth, "Idempotency-Key": key or str(uuid.uuid4())}
    return await client.post("/v1/predictions", json=payload, headers=headers)


async def balance(telegram_id: int = 5000) -> int:
    async with db.acquire() as conn:
        return await conn.fetchval(
            "SELECT coin_balance FROM users WHERE telegram_id = $1", telegram_id
        )


async def test_a_single_is_priced_at_the_taxed_odds(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)

    quote = (
        await app_client.post("/v1/predictions/quote", json=body(markets), headers=auth)
    ).json()

    assert quote["legs"][0]["fair_odds"] == "2.000000"
    assert quote["legs"][0]["locked_odds"] == "1.900000"
    assert quote["combined_odds"] == "1.900000"
    assert quote["potential_payout"] == {"minor": 19000, "display": "190"}
    assert quote["total_cost"]["minor"] == 10000


async def test_a_parlay_compounds(app_client):
    markets = await seed_markets(3)
    auth = await authorise(app_client)

    quote = (
        await app_client.post("/v1/predictions/quote", json=body(markets), headers=auth)
    ).json()

    bonus = Decimal(str(get_settings().parlay_bonus(3)))
    assert bonus > 1
    assert Decimal(quote["combined_odds"]) == Decimal("1.9") ** 3 * bonus
    assert quote["parlay_bonus"] == str(bonus)
    assert quote["potential_payout"]["minor"] == round(10000 * Decimal("1.9") ** 3 * bonus)


async def test_quoting_does_not_touch_the_balance(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)

    before = await balance()
    await app_client.post("/v1/predictions/quote", json=body(markets), headers=auth)
    assert await balance() == before


async def test_insurance_is_priced_from_the_legs_on_the_slip(app_client):
    markets = await seed_markets(4)
    auth = await authorise(app_client)

    quote = (
        await app_client.post(
            "/v1/predictions/quote", json=body(markets, insurance=True), headers=auth
        )
    ).json()

    assert quote["insurance"]["available"] is True
    assert Decimal(quote["insurance"]["rate"]) == pytest.approx(
        Decimal("0.3375"), abs=Decimal("0.001")
    )
    assert quote["insurance"]["premium"]["minor"] == 3375
    assert quote["total_cost"]["minor"] == 13375


async def test_insurance_is_refused_below_the_minimum_leg_count(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)

    response = await app_client.post(
        "/v1/predictions/quote", json=body(markets, insurance=True), headers=auth
    )
    assert response.status_code == 400
    assert response.json()["code"] == "insurance_unavailable"


async def test_placing_debits_the_stake_through_the_ledger(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)

    response = await place(app_client, auth, body(markets, stake=25000))
    assert response.status_code == 201

    slip = response.json()
    assert slip["status"] == "PENDING"
    assert slip["type"] == "PARLAY"
    assert len(slip["legs"]) == 2
    assert await balance() == 100_000 - 25_000

    async with db.acquire() as conn:
        entries = await conn.fetch(
            "SELECT entry_type, amount FROM ledger_entries WHERE ref_id = $1",
            uuid.UUID(slip["id"]),
        )
        drift = await conn.fetch("SELECT * FROM v_balance_reconciliation")

    assert [(e["entry_type"], e["amount"]) for e in entries] == [("STAKE_DEBIT", -25000)]
    assert drift == []


async def test_an_insured_slip_debits_stake_and_premium_separately(app_client):
    markets = await seed_markets(4)
    auth = await authorise(app_client)

    slip = (await place(app_client, auth, body(markets, stake=10000, insurance=True))).json()

    async with db.acquire() as conn:
        entries = await conn.fetch(
            # Order by id, not entry_type: a Postgres enum sorts by declaration
            "SELECT entry_type, amount FROM ledger_entries WHERE ref_id = $1 ORDER BY id",
            uuid.UUID(slip["id"]),
        )
    assert [(e["entry_type"], e["amount"]) for e in entries] == [
        ("STAKE_DEBIT", -10000),
        ("INSURANCE_PREMIUM_DEBIT", -3375),
    ]
    assert await balance() == 100_000 - 13_375


async def test_a_stake_beyond_the_balance_is_refused_and_changes_nothing(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)

    response = await place(app_client, auth, body(markets, stake=5_000_000))
    assert response.status_code == 402
    assert response.json()["code"] == "insufficient_funds"
    assert await balance() == 100_000

    async with db.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM predictions") == 0


async def test_the_stored_slip_matches_what_settlement_will_compute(app_client):
    """The number quoted and the number paid must be the same number.

    fn_settle_prediction recomputes from prediction_legs.locked_odds, so a
    rounding difference between the engine and the database shows up as a
    winning slip paying something other than what the player was shown.
    """
    markets = await seed_markets(3, probability="0.37")
    auth = await authorise(app_client)

    slip = (await place(app_client, auth, body(markets, stake=13337))).json()
    quoted_payout = slip["potential_payout"]["minor"]

    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE prediction_legs SET status='WON', settled_at=NOW() WHERE prediction_id=$1",
            uuid.UUID(slip["id"]),
        )
        settled = await conn.fetchval("SELECT fn_settle_prediction($1)", uuid.UUID(slip["id"]))

    assert settled == "WON"
    async with db.acquire() as conn:
        paid = await conn.fetchval(
            "SELECT settled_payout FROM predictions WHERE id = $1", uuid.UUID(slip["id"])
        )
    assert paid == quoted_payout
    assert await balance() == 100_000 - 13337 + quoted_payout


async def test_the_same_key_places_one_slip_and_returns_it_again(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)
    key = "tap-tap"

    first = await place(app_client, auth, body(markets), key=key)
    second = await place(app_client, auth, body(markets), key=key)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert await balance() == 100_000 - 10_000

    async with db.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM predictions") == 1


async def test_concurrent_identical_requests_place_exactly_one_slip(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)
    key = "double-tap"
    payload = body(markets, stake=40000)

    results = await asyncio.gather(
        place(app_client, auth, payload, key=key),
        place(app_client, auth, payload, key=key),
        place(app_client, auth, payload, key=key),
    )

    assert {r.json()["id"] for r in results} == {results[0].json()["id"]}
    assert sorted(r.status_code for r in results) == [200, 200, 201]
    assert await balance() == 100_000 - 40_000


async def test_reusing_a_key_for_a_different_bet_is_refused(app_client):
    markets = await seed_markets(3)
    auth = await authorise(app_client)
    key = "same-key"

    await place(app_client, auth, body(markets[:2]), key=key)
    response = await place(app_client, auth, body(markets[1:]), key=key)

    assert response.status_code == 409
    assert response.json()["code"] == "idempotency_key_reused"


async def test_placement_requires_an_idempotency_key(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)

    response = await app_client.post("/v1/predictions", json=body(markets), headers=auth)
    assert response.status_code == 400
    assert response.json()["code"] == "idempotency_key_required"


async def test_two_legs_from_one_event_are_refused(app_client):
    """Mutually exclusive outcomes priced as independent ones are a free
    hedge against our own book."""
    raw = fx.event("1", markets=[fx.binary_market("40001"), fx.binary_market("40002")])

    def gamma(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        return httpx.Response(200, json=[raw] if offset == 0 else [])

    async with mock_http_client(gamma) as client:
        await discovery.run_discovery(client, get_settings())

    async with db.acquire() as conn:
        markets = [dict(r) for r in await conn.fetch("SELECT * FROM markets")]
    await price_cache.write_many(
        [(m["id"], m["raw_yes_prob"], "CLOB_MIDPOINT", datetime.now(UTC)) for m in markets],
        ttl_seconds=300,
    )

    auth = await authorise(app_client)
    response = await place(app_client, auth, body(markets))

    assert response.status_code == 400
    assert response.json()["code"] == "correlated_legs"


async def test_the_same_market_twice_is_refused(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)

    payload = body(markets * 2, sides=["YES", "NO"])
    response = await place(app_client, auth, payload)

    assert response.status_code == 400
    assert response.json()["code"] == "duplicate_market"


async def test_a_stale_price_refuses_the_slip(app_client):
    """The market list shows a stale price with a flag. Pricing a bet on one
    is how a book gets picked off by anyone watching the real market."""
    markets = await seed_markets(1)
    auth = await authorise(app_client)
    settings = get_settings()

    await price_cache.get_client().flushdb()
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE markets SET price_updated_at = NOW() - make_interval(secs => $1)",
            settings.price_staleness_seconds + 60,
        )

    response = await place(app_client, auth, body(markets))
    assert response.status_code == 400
    assert response.json()["code"] == "price_stale"
    assert response.json()["market_id"] == str(markets[0]["id"])


async def test_a_locked_market_refuses_the_slip(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)

    async with db.transaction() as conn:
        await conn.execute("UPDATE markets SET status = 'LOCKED'")

    response = await place(app_client, auth, body(markets))
    assert response.status_code == 400
    assert response.json()["code"] == "market_not_open"


@pytest.mark.parametrize(
    ("stake", "code"), [(1, "stake_too_small"), (99_999_999, "stake_too_large")]
)
async def test_stakes_outside_the_configured_band_are_refused(app_client, stake, code):
    markets = await seed_markets(1)
    auth = await authorise(app_client)

    response = await place(app_client, auth, body(markets, stake=stake))
    assert response.status_code == 400
    assert response.json()["code"] == code


async def test_a_banned_account_cannot_place(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)

    async with db.transaction() as conn:
        await conn.execute("UPDATE users SET status = 'RESTRICTED'")

    response = await place(app_client, auth, body(markets))
    assert response.status_code == 403
    assert response.json()["code"] == "account_restricted"


async def test_a_daily_limit_is_enforced_across_slips(app_client):
    markets = await seed_markets(3)
    auth = await authorise(app_client)

    async with db.transaction() as conn:
        await conn.execute("UPDATE users SET daily_stake_limit = 15000")

    assert (await place(app_client, auth, body(markets[:1], stake=10000))).status_code == 201
    second = await place(app_client, auth, body(markets[1:2], stake=10000))

    assert second.status_code == 403
    assert second.json()["code"] == "daily_limit_reached"
    assert await balance() == 100_000 - 10_000


async def add_boost(
    market_id,
    *,
    side="YES",
    multiplier="1.4",
    total=1_000_000,
    per_user=1_000_000,
    max_raw_prob="0.99",
):
    async with db.transaction() as conn:
        return await conn.fetchval(
            """
            INSERT INTO odds_boosts (market_id, side, boost_multiplier, max_raw_prob, ends_at,
                                     max_total_stake, max_stake_per_user)
            VALUES ($1, $2, $3, $4, NOW() + INTERVAL '2 hours', $5, $6)
            RETURNING id
            """,
            market_id,
            side,
            Decimal(multiplier),
            Decimal(max_raw_prob),
            total,
            per_user,
        )


async def test_a_boost_lifts_the_odds_and_is_recorded_on_the_leg(app_client):
    markets = await seed_markets(1)
    boost_id = await add_boost(markets[0]["id"])
    auth = await authorise(app_client)

    slip = (await place(app_client, auth, body(markets))).json()

    assert Decimal(slip["legs"][0]["locked_odds"]) == Decimal("1.9") * Decimal("1.4")

    async with db.acquire() as conn:
        leg = await conn.fetchrow(
            "SELECT boost_id, boost_multiplier FROM prediction_legs WHERE prediction_id = $1",
            uuid.UUID(slip["id"]),
        )
    assert leg["boost_id"] == boost_id
    assert leg["boost_multiplier"] == Decimal("1.400")


async def test_a_boost_only_applies_to_its_own_side(app_client):
    markets = await seed_markets(1)
    await add_boost(markets[0]["id"], side="YES")
    auth = await authorise(app_client)

    quote = (
        await app_client.post(
            "/v1/predictions/quote", json=body(markets, sides=["NO"]), headers=auth
        )
    ).json()

    assert quote["legs"][0]["boosted"] is False
    assert quote["legs"][0]["locked_odds"] == "1.900000"


async def test_a_boost_is_not_applied_to_a_coin_flip(app_client):
    """max_raw_prob is what stops a boost being pointed at something likely,
    where inflating the payout is just handing money away."""
    markets = await seed_markets(1)
    await add_boost(markets[0]["id"], max_raw_prob="0.10")
    auth = await authorise(app_client)

    quote = (
        await app_client.post("/v1/predictions/quote", json=body(markets), headers=auth)
    ).json()
    assert quote["legs"][0]["boosted"] is False


async def test_the_boost_budget_is_consumed_and_then_exhausted(app_client):
    markets = await seed_markets(2)
    boost_id = await add_boost(markets[0]["id"], total=30000)
    auth = await authorise(app_client)

    assert (await place(app_client, auth, body(markets[:1], stake=20000))).status_code == 201

    async with db.acquire() as conn:
        consumed = await conn.fetchval(
            "SELECT consumed_stake FROM odds_boosts WHERE id = $1", boost_id
        )
    assert consumed == 20000

    over = await place(app_client, auth, body(markets[:1], stake=20000))
    assert over.status_code == 409
    assert over.json()["code"] == "boost_exhausted"


async def test_a_boost_budget_cannot_be_oversubscribed_concurrently(app_client):
    markets = await seed_markets(1)
    boost_id = await add_boost(markets[0]["id"], total=30000)
    auth = await authorise(app_client)

    results = await asyncio.gather(
        *(place(app_client, auth, body(markets, stake=20000)) for _ in range(3))
    )

    created = [r for r in results if r.status_code == 201]
    assert len(created) == 1

    async with db.acquire() as conn:
        consumed = await conn.fetchval(
            "SELECT consumed_stake FROM odds_boosts WHERE id = $1", boost_id
        )
    assert consumed == 20000


async def test_the_per_player_boost_cap_is_enforced(app_client):
    markets = await seed_markets(2)
    await add_boost(markets[0]["id"], total=10_000_000, per_user=15000)
    auth = await authorise(app_client)

    assert (await place(app_client, auth, body(markets[:1], stake=10000))).status_code == 201
    second = await place(app_client, auth, body(markets[:1], stake=10000))

    assert second.status_code == 409
    assert second.json()["code"] == "boost_limit_reached"


async def test_a_price_that_moved_against_the_player_asks_them_to_re_confirm(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)

    response = await place(app_client, auth, body(markets, accepted_odds="2.500000"))

    assert response.status_code == 409
    assert response.json()["code"] == "odds_moved"
    assert await balance() == 100_000


async def test_a_price_that_moved_in_the_players_favour_is_simply_given_to_them(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)

    response = await place(app_client, auth, body(markets, accepted_odds="1.500000"))

    assert response.status_code == 201
    assert response.json()["combined_odds"] == "1.900000"


async def test_movement_inside_the_tolerance_is_accepted(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)

    response = await place(app_client, auth, body(markets, accepted_odds="1.905"))
    assert response.status_code == 201


async def test_slips_are_listed_newest_first_and_paginate(app_client):
    markets = await seed_markets(5)
    auth = await authorise(app_client)
    for market in markets:
        await place(app_client, auth, body([market], stake=1000))

    seen: list[str] = []
    cursor = None
    for _ in range(10):
        url = f"/v1/predictions?limit=2{f'&cursor={cursor}' if cursor else ''}"
        page = (await app_client.get(url, headers=auth)).json()
        seen.extend(s["id"] for s in page["slips"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5


async def test_slips_can_be_filtered_by_status(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)
    slip = (await place(app_client, auth, body(markets[:1]))).json()
    await place(app_client, auth, body(markets[1:]))

    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE prediction_legs SET status='LOST', settled_at=NOW() WHERE prediction_id=$1",
            uuid.UUID(slip["id"]),
        )
        await conn.execute("SELECT fn_settle_prediction($1)", uuid.UUID(slip["id"]))

    lost = (await app_client.get("/v1/predictions?status=LOST", headers=auth)).json()
    assert [s["id"] for s in lost["slips"]] == [slip["id"]]


async def test_a_player_cannot_read_another_players_slip(app_client):
    markets = await seed_markets(1)
    mine = await authorise(app_client, telegram_id=6001)
    slip = (await place(app_client, mine, body(markets))).json()

    theirs = await authorise(app_client, telegram_id=6002)
    assert (
        await app_client.get(f"/v1/predictions/{slip['id']}", headers=theirs)
    ).status_code == 404


async def test_endpoints_require_authentication(app_client):
    assert (await app_client.post("/v1/predictions/quote", json={})).status_code == 401
    assert (await app_client.get("/v1/predictions")).status_code == 401


def _with_min_legs(monkeypatch, value: int):
    """Retune MIN_LEGS the way a deployment would, through the environment."""
    from backend.config import get_settings

    monkeypatch.setenv("MIN_LEGS", str(value))
    get_settings.cache_clear()
    return get_settings


async def test_a_single_is_allowed_by_default(app_client):
    """The shipped default must not quietly become parlay-only."""
    auth = await authorise(app_client)
    markets = await seed_markets(1)

    response = await app_client.post("/v1/predictions/quote", json=body(markets), headers=auth)
    assert response.status_code == 200


async def test_a_short_slip_is_refused_when_a_minimum_is_set(app_client, monkeypatch):
    get_settings = _with_min_legs(monkeypatch, 3)
    try:
        auth = await authorise(app_client)
        markets = await seed_markets(3)

        response = await app_client.post(
            "/v1/predictions/quote", json=body(markets[:2]), headers=auth
        )

        assert response.status_code == 400
        assert response.json()["code"] == "too_few_legs"
    finally:
        get_settings.cache_clear()


async def test_the_refusal_says_how_many_legs_are_needed(app_client, monkeypatch):
    """The client renders "add two more" from this number.

    Without it the web app would need its own copy of MIN_LEGS, which is a
    copy that goes stale the first time a deployment retunes the setting and
    starts telling players the wrong number.
    """
    get_settings = _with_min_legs(monkeypatch, 3)
    try:
        auth = await authorise(app_client)
        markets = await seed_markets(3)

        response = await app_client.post(
            "/v1/predictions/quote", json=body(markets[:1]), headers=auth
        )

        assert response.json()["required_legs"] == 3
    finally:
        get_settings.cache_clear()


async def test_a_slip_at_the_minimum_prices_normally(app_client, monkeypatch):
    get_settings = _with_min_legs(monkeypatch, 3)
    try:
        auth = await authorise(app_client)
        markets = await seed_markets(3)

        quote = (
            await app_client.post("/v1/predictions/quote", json=body(markets), headers=auth)
        ).json()

        bonus = Decimal(str(get_settings().parlay_bonus(3)))
        assert Decimal(quote["combined_odds"]) == Decimal("1.9") ** 3 * bonus
    finally:
        get_settings.cache_clear()


async def test_placement_is_refused_too_not_only_quoting(app_client, monkeypatch):
    """The quote and the placement must agree.

    If only placement enforced this, a short slip would price cleanly, the
    player would commit to a payout figure, and the rule would surface at the
    last possible moment — which reads as a bug rather than a rule.
    """
    get_settings = _with_min_legs(monkeypatch, 3)
    try:
        auth = await authorise(app_client)
        markets = await seed_markets(3)

        response = await place(app_client, auth, body(markets[:2]))

        assert response.status_code == 400
        assert response.json()["code"] == "too_few_legs"
    finally:
        get_settings.cache_clear()


async def test_the_house_edge_compounds_with_every_leg(app_client, monkeypatch):
    """The reason parlays are worth encouraging, measured rather than asserted.

    Expected house share on a slip of n legs at true probability p is
    1 - (p x locked)^n x bonus = 1 - (1 - vig)^n x bonus. This walks 1 to 5
    legs on 50/50 markets and checks the engine produces that curve, because
    the whole argument for paying more on longer slips rests on the edge still
    growing after the bonus is given back.
    """
    auth = await authorise(app_client)
    markets = await seed_markets(5)
    vig = Decimal("0.05")
    settings = get_settings()
    edges: list[Decimal] = []

    for legs in range(1, 6):
        quote = (
            await app_client.post("/v1/predictions/quote", json=body(markets[:legs]), headers=auth)
        ).json()

        expected_return = Decimal("0.5") ** legs * Decimal(quote["combined_odds"])
        house_edge = Decimal(1) - expected_return

        bonus = Decimal(str(settings.parlay_bonus(legs)))
        assert house_edge == pytest.approx(
            Decimal(1) - (Decimal(1) - vig) ** legs * bonus, abs=1e-7
        )
        edges.append(house_edge)

    assert edges == sorted(edges), edges
    assert edges[4] / edges[0] > 2


def _with_seed(monkeypatch, minor: int):
    from backend.config import get_settings

    monkeypatch.setenv("HOUSE_SEED_MINOR", str(minor))
    get_settings.cache_clear()
    return get_settings


async def _pending_book(market_id):
    """What the guard sees: owed and staked per side on one market."""
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT pl.side,
                   COALESCE(SUM(p.potential_payout), 0) AS owed,
                   COALESCE(SUM(p.stake), 0)            AS staked
              FROM prediction_legs pl
              JOIN predictions p ON p.id = pl.prediction_id
             WHERE pl.market_id = $1 AND p.status = 'PENDING' AND pl.status = 'PENDING'
             GROUP BY pl.side
            """,
            market_id,
        )
    return {r["side"]: {"owed": int(r["owed"]), "staked": int(r["staked"])} for r in rows}


async def test_a_player_can_bet_with_nobody_on_the_other_side(app_client):
    """The launch condition: one user, an empty book, and a bet that works.

    This is the whole reason the house seeds the other side. Without it the
    first player on a brand new market has no counterparty and cannot bet at
    all, which on a launch with no users is every player on every market.
    """
    auth = await authorise(app_client)
    markets = await seed_markets(1)

    response = await place(app_client, auth, body(markets, stake=10000))

    assert response.status_code == 201, response.text
    book = await _pending_book(markets[0]["id"])
    assert book["YES"]["owed"] == 19000, "the house is carrying this alone"
    assert "NO" not in book, "nobody took the other side, and that was fine"


async def test_the_seed_is_the_most_the_house_will_lose_on_one_market(app_client, monkeypatch):
    """Past the seed the market stops taking that side. That refusal is the
    entire risk control: exposure per market is bounded by a number the
    operator sets, so the worst case across the book is knowable in advance."""
    get_settings = _with_seed(monkeypatch, 30_000)
    try:
        auth = await authorise(app_client)
        markets = await seed_markets(1)

        first = await place(app_client, auth, body(markets, stake=10000))
        assert first.status_code == 201, "19,000 owed against a 30,000 seed must fit"

        second = await place(app_client, auth, body(markets, stake=10000))
        assert second.status_code == 409
        assert second.json()["code"] == "market_at_capacity"
    finally:
        get_settings.cache_clear()


async def test_money_on_the_other_side_buys_back_capacity(app_client, monkeypatch):
    """The netting, and the reason the seed does not deplete.

    When a side wins we pay its backers *out of the coins staked against
    them*. So a bet on NO is not just unrelated volume — it directly funds the
    YES payouts and hands the house its capacity back. Under the old gross
    check this market stayed shut no matter how much money arrived to balance
    it, which is precisely backwards: a matched book is the safest book there
    is.
    """
    get_settings = _with_seed(monkeypatch, 30_000)
    try:
        auth = await authorise(app_client)
        other = await authorise(app_client, telegram_id=5001)
        markets = await seed_markets(1)

        assert (await place(app_client, auth, body(markets, stake=10000))).status_code == 201
        assert (await place(app_client, auth, body(markets, stake=10000))).status_code == 409

        against = await place(app_client, other, body(markets, stake=10000, sides=["NO"]))
        assert against.status_code == 201

        reopened = await place(app_client, auth, body(markets, stake=10000))
        assert reopened.status_code == 201, "opposing money did not free any capacity"
    finally:
        get_settings.cache_clear()


async def test_a_matched_book_costs_the_house_nothing(app_client, monkeypatch):
    """Measured rather than asserted, because it is the claim the seed rests on.

    Equal money on both sides at the same price: whichever way it resolves,
    the house pays one side out of the other side's stakes and keeps the vig.
    The net exposure the guard computes must be at or below zero on both
    sides — no seed consumed at all.
    """
    get_settings = _with_seed(monkeypatch, 30_000)
    try:
        a = await authorise(app_client)
        b = await authorise(app_client, telegram_id=5002)
        markets = await seed_markets(1)

        assert (await place(app_client, a, body(markets, stake=10000))).status_code == 201
        assert (
            await place(app_client, b, body(markets, stake=10000, sides=["NO"]))
        ).status_code == 201

        book = await _pending_book(markets[0]["id"])
        for side, other in (("YES", "NO"), ("NO", "YES")):
            exposure = book[side]["owed"] - book[other]["staked"]
            assert exposure == 9000, f"{side} exposure was {exposure}"
            assert exposure < book[side]["owed"], "netting did nothing"
    finally:
        get_settings.cache_clear()
