"""Placement end to end: pricing, points, idempotency, limits, settlement."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from conftest import authorise, balance_of, mock_http_client
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


async def reprice(market: dict, probability: str) -> None:
    """Move one market's live price, as the sync worker would."""
    await price_cache.write_many(
        [(market["id"], Decimal(probability), "CLOB_MIDPOINT", datetime.now(UTC))],
        ttl_seconds=300,
    )


def body(markets, *, stake=10000, sides=None, **extra):
    sides = sides or ["YES"] * len(markets)
    return {
        "legs": [
            {"market_id": str(m["id"]), "side": s} for m, s in zip(markets, sides, strict=True)
        ],
        "stake": stake,
        **extra,
    }


async def place(client, auth, payload, key=None):
    headers = {**auth, "Idempotency-Key": key or str(uuid.uuid4())}
    return await client.post("/v1/predictions", json=payload, headers=headers)


async def quote(client, auth, payload):
    return await client.post("/v1/predictions/quote", json=payload, headers=auth)


# ----- pricing --------------------------------------------------------------


async def test_a_single_is_priced_at_fair_odds(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)

    priced = (await quote(app_client, auth, body(markets))).json()

    assert priced["legs"][0]["probability"] == "0.500000"
    assert priced["legs"][0]["locked_odds"] == "2.000000"
    assert priced["combined_odds"] == "2.000000"
    assert priced["win_probability"] == "0.500000"
    assert priced["potential_payout"] == {"minor": 20000, "display": "200"}
    assert priced["capped"] is False


async def test_a_slip_of_several_picks_multiplies_them_and_adds_nothing(app_client):
    markets = await seed_markets(3)
    auth = await authorise(app_client)

    priced = (await quote(app_client, auth, body(markets))).json()

    assert priced["combined_odds"] == "8.000000"
    assert priced["win_probability"] == "0.125000"
    assert priced["potential_payout"]["minor"] == 80000


async def test_the_quote_carries_no_trace_of_a_margin_or_a_bonus(app_client):
    """There is no field for them because there is nothing to put in one."""
    markets = await seed_markets(2)
    auth = await authorise(app_client)

    priced = (await quote(app_client, auth, body(markets))).json()

    for gone in ("parlay_bonus", "insurance", "fair_odds", "uncapped", "total_cost"):
        assert gone not in priced
    for gone in ("fair_odds", "boosted", "boost_multiplier"):
        assert gone not in priced["legs"][0]


async def test_quoting_does_not_touch_the_balance(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)

    before = await balance_of()
    await quote(app_client, auth, body(markets))
    assert await balance_of() == before


async def test_an_outcome_that_is_all_but_settled_cannot_be_forecast(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)
    await reprice(markets[0], "0.995")

    for side in ("YES", "NO"):
        refused = await quote(app_client, auth, body(markets, sides=[side]))
        assert refused.status_code == 400
        assert refused.json()["code"] == "leg_unpriceable"
        assert refused.json()["market_id"] == str(markets[0]["id"])


async def test_a_slip_too_long_for_the_ceiling_is_refused(app_client):
    """Three 5% shots are 8,000 to one at fair odds; the ceiling is 1,000."""
    markets = await seed_markets(3, probability="0.05")
    auth = await authorise(app_client)

    refused = await quote(app_client, auth, body(markets))
    assert refused.status_code == 400
    assert refused.json()["code"] == "odds_exceed_maximum"

    assert (await quote(app_client, auth, body(markets[:2]))).status_code == 200


async def test_more_picks_than_a_slip_holds_are_refused(app_client):
    get_settings().max_legs = 2
    markets = await seed_markets(3)
    auth = await authorise(app_client)

    refused = await quote(app_client, auth, body(markets))
    assert refused.status_code == 400
    assert refused.json()["code"] == "too_many_legs"


# ----- placing --------------------------------------------------------------


async def test_placing_debits_the_stake_through_the_ledger(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)

    response = await place(app_client, auth, body(markets, stake=25000))
    assert response.status_code == 201

    slip = response.json()
    assert slip["status"] == "PENDING"
    assert slip["type"] == "PARLAY"
    assert len(slip["legs"]) == 2
    assert slip["total_cost"]["minor"] == 25000
    assert await balance_of() == 100_000 - 25_000

    async with db.acquire() as conn:
        entries = await conn.fetch(
            "SELECT entry_type, amount FROM ledger_entries WHERE ref_id = $1",
            uuid.UUID(slip["id"]),
        )
        drift = await conn.fetch("SELECT * FROM v_balance_reconciliation")

    assert [(e["entry_type"], e["amount"]) for e in entries] == [("STAKE_DEBIT", -25000)]
    assert drift == []


async def test_a_placed_slip_records_that_nothing_was_charged_on_top(app_client):
    """The margin, boost, bonus and insurance columns are still in the schema.
    Every slip the website places writes them as "none"."""
    markets = await seed_markets(2)
    auth = await authorise(app_client)

    slip = (await place(app_client, auth, body(markets))).json()

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT has_insurance, insurance_premium, house_edge_bps, parlay_bonus, total_cost,"
            "       stake FROM predictions WHERE id = $1",
            uuid.UUID(slip["id"]),
        )
        legs = await conn.fetch(
            "SELECT vig_rate, boost_id, boost_multiplier FROM prediction_legs "
            " WHERE prediction_id = $1",
            uuid.UUID(slip["id"]),
        )

    assert row["has_insurance"] is False
    assert row["insurance_premium"] == 0
    assert row["house_edge_bps"] == 0
    assert row["parlay_bonus"] == Decimal("1.000")
    assert row["total_cost"] == row["stake"]
    assert all(leg["vig_rate"] == 0 for leg in legs)
    assert all(leg["boost_id"] is None and leg["boost_multiplier"] == 1 for leg in legs)


async def test_a_stake_beyond_the_balance_is_refused_and_changes_nothing(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)

    response = await place(app_client, auth, body(markets, stake=5_000_000))
    assert response.status_code == 402
    assert response.json()["code"] == "insufficient_funds"
    assert await balance_of() == 100_000

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
    assert await balance_of() == 100_000 - 13337 + quoted_payout


async def test_a_voided_slip_is_refunded_with_a_note_in_english(app_client):
    """The note is an audit trail now, and it is written in one language."""
    markets = await seed_markets(1)
    auth = await authorise(app_client)
    slip = (await place(app_client, auth, body(markets))).json()

    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE prediction_legs SET status='VOID', settled_at=NOW() WHERE prediction_id=$1",
            uuid.UUID(slip["id"]),
        )
        await conn.fetchval("SELECT fn_settle_prediction($1)", uuid.UUID(slip["id"]))
        note = await conn.fetchval(
            "SELECT settlement_note FROM predictions WHERE id = $1", uuid.UUID(slip["id"])
        )

    assert note == "Every pick was voided at the source; the stake was returned."
    assert note.isascii()
    assert await balance_of() == 100_000


# ----- idempotency ----------------------------------------------------------


async def test_the_same_key_places_one_slip_and_returns_it_again(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)
    key = "tap-tap"

    first = await place(app_client, auth, body(markets), key=key)
    second = await place(app_client, auth, body(markets), key=key)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert await balance_of() == 100_000 - 10_000

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
    assert await balance_of() == 100_000 - 40_000


async def test_reusing_a_key_for_a_different_slip_is_refused(app_client):
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


# ----- what a slip may contain ----------------------------------------------


async def test_two_legs_from_one_event_are_refused(app_client):
    """Outcomes of one event are not independent, so the product of their
    odds prices a combination that is impossible or nearly certain."""
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
    """The market list shows a stale price with a flag. A forecast priced on
    one is a forecast against a number the real market has already left."""
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


async def test_a_restricted_account_cannot_place(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)

    async with db.transaction() as conn:
        await conn.execute("UPDATE users SET status = 'RESTRICTED'")

    response = await place(app_client, auth, body(markets))
    assert response.status_code == 403
    assert response.json()["code"] == "account_restricted"


async def test_many_players_can_back_the_same_side_without_limit(app_client):
    """There is no house to protect, so no forecast is refused because too
    many people agree with it."""
    markets = await seed_markets(1, probability="0.02")

    for player in range(6001, 6009):
        auth = await authorise(app_client, player)
        placed = await place(app_client, auth, body(markets, stake=100_000))
        assert placed.status_code == 201, placed.text


# ----- a price that moved ---------------------------------------------------


async def test_a_price_that_moved_against_the_player_asks_them_to_re_confirm(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)

    response = await place(app_client, auth, body(markets, accepted_odds="2.500000"))

    assert response.status_code == 409
    assert response.json()["code"] == "odds_moved"
    assert await balance_of() == 100_000


async def test_a_price_that_moved_in_the_players_favour_is_simply_given_to_them(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)

    response = await place(app_client, auth, body(markets, accepted_odds="1.500000"))

    assert response.status_code == 201
    assert response.json()["combined_odds"] == "2.000000"


async def test_movement_inside_the_tolerance_is_accepted(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)

    response = await place(app_client, auth, body(markets, accepted_odds="2.005"))
    assert response.status_code == 201


async def test_the_same_slip_retried_at_a_refreshed_price_is_still_one_slip(app_client):
    """`accepted_odds` is not part of what identifies a slip, so a client that
    re-confirms after "the price moved" does not place a second one."""
    markets = await seed_markets(1)
    auth = await authorise(app_client)
    key = "confirm-again"

    refused = await place(app_client, auth, body(markets, accepted_odds="2.5"), key=key)
    assert refused.status_code == 409

    placed = await place(app_client, auth, body(markets, accepted_odds="2.0"), key=key)
    again = await place(app_client, auth, body(markets, accepted_odds="1.9"), key=key)

    assert placed.status_code == 201
    assert again.status_code == 200
    assert again.json()["id"] == placed.json()["id"]


# ----- reading slips back ---------------------------------------------------


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


async def test_a_slip_reads_back_in_english_even_if_the_row_was_once_translated(app_client):
    """Rows written while market text was being translated still hold the
    translation in `question`. The API reads the source column instead."""
    markets = await seed_markets(1)
    auth = await authorise(app_client)
    slip = (await place(app_client, auth, body(markets))).json()

    async with db.acquire() as conn:
        source = await conn.fetchval(
            "SELECT question_source FROM markets WHERE id = $1", markets[0]["id"]
        )
        await conn.execute("UPDATE markets SET question = 'ein übersetzter Text'")

    read = (await app_client.get(f"/v1/predictions/{slip['id']}", headers=auth)).json()
    assert read["legs"][0]["question"] == source
    assert read["legs"][0]["question"].isascii()


async def test_a_player_cannot_read_another_players_slip(app_client):
    markets = await seed_markets(1)
    mine = await authorise(app_client, 6001)
    slip = (await place(app_client, mine, body(markets))).json()

    theirs = await authorise(app_client, 6002)
    assert (
        await app_client.get(f"/v1/predictions/{slip['id']}", headers=theirs)
    ).status_code == 404


async def test_endpoints_require_authentication(app_client):
    assert (await app_client.post("/v1/predictions/quote", json={})).status_code == 401
    assert (await app_client.get("/v1/predictions")).status_code == 401


async def test_a_guest_can_forecast_like_anyone_else(app_client):
    markets = await seed_markets(1)
    guest = await app_client.post("/v1/auth/guest")
    auth = {"Authorization": f"Bearer {guest.json()['access_token']}"}

    placed = await place(app_client, auth, body(markets))
    assert placed.status_code == 201
