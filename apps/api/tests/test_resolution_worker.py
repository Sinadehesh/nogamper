"""The resolution worker end to end: grade, settle, pay, and don't double-pay."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from conftest import authorise, balance_of, mock_http_client, slowed, user_id_for
from fixtures import gamma_events as fx

from backend import db
from backend.cache import prices as price_cache
from backend.config import get_settings
from backend.workers import polymarket_discovery as discovery
from backend.workers import resolution


async def seed_markets(count: int = 3, probability: str = "0.50") -> list[dict]:
    """One market per event, so slips are never blocked by the correlation rule."""
    events = [
        fx.event(str(i), markets=[fx.binary_market(f"5{i:04d}", prices=[probability, "0.5"])])
        for i in range(count)
    ]

    def gamma(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        return httpx.Response(200, json=events if offset == 0 else [])

    async with mock_http_client(gamma) as client:
        await discovery.run_discovery(client, get_settings())

    async with db.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch("SELECT * FROM markets ORDER BY lock_at")]

    await price_cache.write_many(
        [(m["id"], m["raw_yes_prob"], "CLOB_MIDPOINT", datetime.now(UTC)) for m in rows],
        ttl_seconds=300,
    )
    return rows


async def expire(markets: list[dict]) -> None:
    """Push markets past their upstream end date so they become resolvable."""
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE markets SET end_date = NOW() - INTERVAL '1 hour', "
            "lock_at = NOW() - INTERVAL '2 hours' WHERE id = ANY($1::uuid[])",
            [m["id"] for m in markets],
        )


def gamma_resolver(outcomes: dict[str, str], *, fail: set[str] | None = None):
    """Answer /markets/{id} with a settled outcome per polymarket id.

    `outcomes` maps a polymarket market id to "YES", "NO", "VOID", or "OPEN".
    """
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        market_id = request.url.path.rsplit("/", 1)[-1]
        calls.append(market_id)
        if fail and market_id in fail:
            return httpx.Response(503, json={})

        verdict = outcomes.get(market_id, "OPEN")
        prices = {
            "YES": ["1", "0"],
            "NO": ["0", "1"],
            "VOID": ["0.5", "0.5"],
            "OPEN": ["0.6", "0.4"],
        }[verdict]
        return httpx.Response(
            200,
            json={
                "id": market_id,
                "closed": verdict != "OPEN",
                "clobTokenIds": json.dumps([f"tok-yes-{market_id}", f"tok-no-{market_id}"]),
                "outcomePrices": json.dumps(prices),
            },
        )

    handler.calls = calls  # type: ignore[attr-defined]
    return handler


async def place(app_client, auth, markets, *, stake=10000, sides=None):
    sides = sides or ["YES"] * len(markets)
    response = await app_client.post(
        "/v1/predictions",
        json={
            "legs": [
                {"market_id": str(m["id"]), "side": s} for m, s in zip(markets, sides, strict=True)
            ],
            "stake": stake,
        },
        headers={**auth, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def slip_row(slip_id: str) -> dict:
    async with db.acquire() as conn:
        return dict(
            await conn.fetchrow("SELECT * FROM predictions WHERE id = $1", uuid.UUID(slip_id))
        )


async def drift() -> int:
    async with db.acquire() as conn:
        return await conn.fetchval("SELECT count(*) FROM v_balance_reconciliation")


async def test_a_winning_parlay_is_graded_and_paid(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)
    slip = await place(app_client, auth, markets, stake=20000)
    quoted = slip["potential_payout"]["minor"]

    await expire(markets)
    handler = gamma_resolver({"50000": "YES", "50001": "YES"})
    async with mock_http_client(handler) as client:
        report = await resolution.run_resolution(client, get_settings())

    assert report.markets_resolved == 2
    assert report.slips_settled == 1
    assert report.outcomes == {"YES": 2}

    settled = await slip_row(slip["id"])
    assert settled["status"] == "WON"
    assert settled["settled_payout"] == quoted
    assert await balance_of() == 100_000 - 20_000 + quoted
    assert await drift() == 0


async def test_a_losing_leg_loses_the_slip(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)
    slip = await place(app_client, auth, markets)

    await expire(markets)
    async with mock_http_client(gamma_resolver({"50000": "YES", "50001": "NO"})) as client:
        await resolution.run_resolution(client, get_settings())

    settled = await slip_row(slip["id"])
    assert settled["status"] == "LOST"
    assert settled["settled_payout"] == 0
    assert await balance_of() == 90_000


async def test_a_voided_market_collapses_its_leg_rather_than_killing_the_slip(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)
    slip = await place(app_client, auth, markets, stake=10000)

    await expire(markets)
    async with mock_http_client(gamma_resolver({"50000": "YES", "50001": "VOID"})) as client:
        await resolution.run_resolution(client, get_settings())

    settled = await slip_row(slip["id"])
    assert settled["status"] == "WON"

    async with db.acquire() as conn:
        legs = await conn.fetch(
            "SELECT status, locked_odds FROM prediction_legs WHERE prediction_id = $1"
            " ORDER BY leg_index",
            uuid.UUID(slip["id"]),
        )
    assert sorted(leg["status"] for leg in legs) == ["VOID", "WON"]
    won = next(leg for leg in legs if leg["status"] == "WON")

    # The voided pick settles at 1.0: the slip pays as though it had only
    # ever carried the pick that stood.
    assert settled["settled_payout"] == round(10000 * won["locked_odds"])


async def test_the_settlement_note_is_written_in_english(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)
    slip = await place(app_client, auth, markets)

    await expire(markets)
    async with mock_http_client(gamma_resolver({"50000": "YES", "50001": "VOID"})) as client:
        await resolution.run_resolution(client, get_settings())

    note = (await slip_row(slip["id"]))["settlement_note"]
    assert note is not None
    assert note.startswith("1 pick(s) voided; odds recomputed to ")
    assert note.isascii()


async def insure(slip_id: str, *, premium: int) -> None:
    """Turn a placed slip into one carrying cover, as it could before the site
    went free-to-play. Nothing can create such a slip any more; the ones that
    already exist still have to settle on the terms their owners were shown."""
    async with db.transaction() as conn:
        await conn.execute(
            """
            UPDATE predictions
               SET has_insurance = TRUE, insurance_premium = $2, insurance_rate = 0.25,
                   insurance_min_legs = 4, insurance_max_failed = 1
             WHERE id = $1
            """,
            uuid.UUID(slip_id),
            premium,
        )
        await conn.execute(
            "INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id,"
            "                            idempotency_key)"
            " VALUES ($1, 'INSURANCE_PREMIUM_DEBIT', $2, 'PREDICTION', $3, $4)",
            await user_id_for(),
            -premium,
            uuid.UUID(slip_id),
            f"premium:{slip_id}",
        )


async def test_a_slip_insured_before_the_change_still_settles_on_its_own_terms(app_client):
    markets = await seed_markets(4)
    auth = await authorise(app_client)
    slip = await place(app_client, auth, markets, stake=10000)
    await insure(slip["id"], premium=2500)

    await expire(markets)
    outcomes = {"50000": "YES", "50001": "YES", "50002": "YES", "50003": "NO"}
    async with mock_http_client(gamma_resolver(outcomes)) as client:
        await resolution.run_resolution(client, get_settings())

    settled = await slip_row(slip["id"])
    assert settled["status"] == "INSURED"
    assert settled["settled_payout"] == 10000
    assert await balance_of() == 100_000 - 10_000 - 2500 + 10_000
    assert await drift() == 0


async def test_a_near_miss_on_an_ordinary_slip_is_simply_a_loss(app_client):
    """No slip placed through the website carries cover, so three out of four
    pays nothing — and nothing here suggests it nearly did."""
    markets = await seed_markets(4)
    auth = await authorise(app_client)
    slip = await place(app_client, auth, markets, stake=10000)

    await expire(markets)
    outcomes = {"50000": "YES", "50001": "YES", "50002": "YES", "50003": "NO"}
    async with mock_http_client(gamma_resolver(outcomes)) as client:
        await resolution.run_resolution(client, get_settings())

    settled = await slip_row(slip["id"])
    assert settled["status"] == "LOST"
    assert settled["settled_payout"] == 0
    assert await balance_of() == 90_000


async def test_a_slip_waits_for_its_last_leg(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)
    slip = await place(app_client, auth, markets)

    await expire(markets[:1])
    async with mock_http_client(gamma_resolver({"50000": "YES"})) as client:
        report = await resolution.run_resolution(client, get_settings())

    assert report.markets_resolved == 1
    assert report.slips_still_open == 1
    assert report.slips_settled == 0
    assert (await slip_row(slip["id"]))["status"] == "PENDING"
    assert await balance_of() == 90_000

    await expire(markets)
    async with mock_http_client(gamma_resolver({"50000": "YES", "50001": "YES"})) as client:
        second = await resolution.run_resolution(client, get_settings())

    assert second.slips_settled == 1
    assert (await slip_row(slip["id"]))["status"] == "WON"


async def test_a_market_upstream_has_not_settled_is_left_alone(app_client):
    markets = await seed_markets(1)
    auth = await authorise(app_client)
    slip = await place(app_client, auth, markets)
    await expire(markets)

    async with mock_http_client(gamma_resolver({"50000": "OPEN"})) as client:
        report = await resolution.run_resolution(client, get_settings())

    assert report.markets_resolved == 0
    assert report.markets_pending == 1
    assert (await slip_row(slip["id"]))["status"] == "PENDING"

    async with db.acquire() as conn:
        assert await conn.fetchval("SELECT status FROM markets") in {"ACTIVE", "LOCKED"}


async def test_running_twice_pays_once(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)
    slip = await place(app_client, auth, markets, stake=20000)
    await expire(markets)

    handler = gamma_resolver({"50000": "YES", "50001": "YES"})
    async with mock_http_client(handler) as client:
        await resolution.run_resolution(client, get_settings())
        after_first = await balance_of()
        second = await resolution.run_resolution(client, get_settings())

    assert second.markets_resolved == 0
    assert await balance_of() == after_first

    async with db.acquire() as conn:
        payouts = await conn.fetchval(
            "SELECT count(*) FROM ledger_entries"
            " WHERE ref_id = $1 AND entry_type = 'PAYOUT_CREDIT'",
            uuid.UUID(slip["id"]),
        )
    assert payouts == 1
    assert await drift() == 0


async def test_concurrent_runs_settle_once(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)
    await place(app_client, auth, markets, stake=20000)
    await expire(markets)

    handler = gamma_resolver({"50000": "YES", "50001": "YES"})
    async with mock_http_client(slowed(handler)) as client:
        reports = await asyncio.gather(
            resolution.run_resolution(client, get_settings()),
            resolution.run_resolution(client, get_settings()),
            resolution.run_resolution(client, get_settings()),
        )

    assert sum(1 for r in reports if r.ran) == 1
    assert await drift() == 0


async def test_one_unreachable_market_does_not_stop_the_others(app_client):
    markets = await seed_markets(3)
    auth = await authorise(app_client)
    slip = await place(app_client, auth, markets[:2])
    await expire(markets)

    handler = gamma_resolver({"50000": "YES", "50001": "YES", "50002": "YES"}, fail={"50002"})
    async with mock_http_client(handler) as client:
        report = await resolution.run_resolution(client, get_settings())

    assert report.fetch_failures == 1
    assert report.markets_resolved == 2
    assert (await slip_row(slip["id"]))["status"] == "WON"

    async with db.acquire() as conn:
        status = await conn.fetchval(
            "SELECT status FROM markets WHERE polymarket_market_id = '50002'"
        )
    assert status in {"ACTIVE", "LOCKED"}


async def test_a_total_gamma_outage_changes_nothing(app_client):
    markets = await seed_markets(2)
    auth = await authorise(app_client)
    slip = await place(app_client, auth, markets)
    await expire(markets)

    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    async with mock_http_client(down) as client:
        report = await resolution.run_resolution(client, get_settings())

    assert report.markets_resolved == 0
    assert report.fetch_failures == 2
    assert (await slip_row(slip["id"]))["status"] == "PENDING"
    assert await balance_of() == 90_000
    assert await drift() == 0


async def test_a_slip_graded_but_never_paid_is_swept_up(app_client):
    """Grading and settlement are separate transactions. A worker that dies
    between them leaves a fully-graded slip nobody paid."""
    markets = await seed_markets(2)
    auth = await authorise(app_client)
    slip = await place(app_client, auth, markets, stake=20000)
    quoted = slip["potential_payout"]["minor"]

    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE markets SET status='RESOLVED', resolution='YES', resolved_at=NOW()"
        )
        await conn.execute(
            "UPDATE prediction_legs SET status='WON', settled_at=NOW() WHERE prediction_id=$1",
            uuid.UUID(slip["id"]),
        )
    assert (await slip_row(slip["id"]))["status"] == "PENDING"

    async with mock_http_client(gamma_resolver({})) as client:
        report = await resolution.run_resolution(client, get_settings())

    assert report.markets_checked == 0
    assert report.slips_settled == 1
    assert (await slip_row(slip["id"]))["status"] == "WON"
    assert await balance_of() == 100_000 - 20_000 + quoted


async def test_an_empty_run_is_quiet(app_client):
    async with mock_http_client(gamma_resolver({})) as client:
        report = await resolution.run_resolution(client, get_settings())

    assert report.ran is True
    assert report.markets_checked == 0
    assert report.slips_settled == 0


async def test_markets_overdue_upstream_are_counted(app_client):
    markets = await seed_markets(1)
    settings = get_settings()
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE markets SET end_date = NOW() - make_interval(hours => $1),"
            "                   lock_at  = NOW() - make_interval(hours => $1 + 1)",
            settings.resolution_overdue_hours + 24,
        )

    async with mock_http_client(gamma_resolver({"50000": "OPEN"})) as client:
        report = await resolution.run_resolution(client, get_settings())

    assert report.overdue_markets == 1
    assert markets


async def test_settlement_is_delegated_to_the_database(app_client, monkeypatch):
    """The worker must not carry its own copy of the parlay maths."""
    markets = await seed_markets(2)
    auth = await authorise(app_client)
    await place(app_client, auth, markets)
    await expire(markets)

    from backend.repositories import markets as markets_repo

    calls: list[uuid.UUID] = []
    original = markets_repo.settle_slip

    async def spy(conn, prediction_id):
        calls.append(prediction_id)
        return await original(conn, prediction_id)

    monkeypatch.setattr(markets_repo, "settle_slip", spy)

    async with mock_http_client(gamma_resolver({"50000": "YES", "50001": "YES"})) as client:
        await resolution.run_resolution(client, get_settings())

    assert len(calls) == 1


async def test_grading_uses_the_stored_yes_token_not_the_payload_order(app_client):
    """A market whose upstream token order is reversed must still pay the side
    the player actually backed."""
    markets = await seed_markets(1)
    auth = await authorise(app_client)
    slip = await place(app_client, auth, markets, sides=["NO"])
    await expire(markets)

    def reversed_order(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "50000",
                "closed": True,
                "clobTokenIds": json.dumps(["tok-no-50000", "tok-yes-50000"]),
                "outcomePrices": json.dumps(["1", "0"]),
            },
        )

    async with mock_http_client(reversed_order) as client:
        await resolution.run_resolution(client, get_settings())

    async with db.acquire() as conn:
        resolution_value = await conn.fetchval("SELECT resolution FROM markets")
    assert resolution_value == "NO"

    settled = await slip_row(slip["id"])
    assert settled["status"] == "WON"
    assert settled["settled_payout"] > 0


@pytest.mark.parametrize("side", ["YES", "NO"])
async def test_a_single_settles_on_the_side_it_backed(app_client, side):
    markets = await seed_markets(1)
    auth = await authorise(app_client)
    slip = await place(app_client, auth, markets, sides=[side])
    await expire(markets)

    async with mock_http_client(gamma_resolver({"50000": "YES"})) as client:
        await resolution.run_resolution(client, get_settings())

    expected = "WON" if side == "YES" else "LOST"
    assert (await slip_row(slip["id"]))["status"] == expected
    assert await drift() == 0


async def test_a_void_across_every_leg_returns_the_stake(app_client):
    markets = await seed_markets(4)
    auth = await authorise(app_client)
    slip = await place(app_client, auth, markets, stake=10000)
    total_cost = slip["total_cost"]["minor"]
    assert total_cost == 10000
    await expire(markets)

    outcomes = dict.fromkeys(["50000", "50001", "50002", "50003"], "VOID")
    async with mock_http_client(gamma_resolver(outcomes)) as client:
        await resolution.run_resolution(client, get_settings())

    settled = await slip_row(slip["id"])
    assert settled["status"] == "VOID"
    assert settled["settled_payout"] == total_cost
    assert await balance_of() == 100_000
    assert await drift() == 0
    assert Decimal(str(settled["combined_odds"])) > 1
