"""The operator's overview: who is here, and where points went.

The gate tests come first. This report has no revenue in it — there is none —
but it does say how many people use a site about gambling less, and the roster
beside it lists their addresses. Neither is for anyone but the operator.
"""

from __future__ import annotations

import uuid

from conftest import TEST_ADMIN_CODE, authorise, make_admin
from test_predictions import body, place, seed_markets

from backend import db
from backend.config import Settings, get_settings

OVERVIEW = "/v1/admin/overview"


async def settle(slip_id: str, *, won: bool) -> None:
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE prediction_legs SET status = $2::leg_status, settled_at = NOW() "
            " WHERE prediction_id = $1",
            uuid.UUID(slip_id),
            "WON" if won else "LOST",
        )
        await conn.fetchval("SELECT fn_settle_prediction($1)", uuid.UUID(slip_id))


# ----- the gate -------------------------------------------------------------


async def test_an_anonymous_caller_gets_nothing(app_client):
    assert (await app_client.get(OVERVIEW)).status_code == 401


async def test_an_ordinary_player_gets_a_404_not_a_403(app_client):
    """403 would confirm the route exists and that an allowlist guards it."""
    headers = await authorise(app_client, 4242)

    response = await app_client.get(OVERVIEW, headers=headers)
    assert response.status_code == 404
    assert response.json() == {"code": "not_found", "detail": "Not found."}


async def test_an_allowlisted_player_can_read_it(app_client):
    admin = await make_admin(app_client)
    assert (await app_client.get(OVERVIEW, headers=admin)).status_code == 200


async def test_an_empty_allowlist_denies_everyone(app_client):
    """Unset must never mean unrestricted: that would turn a forgotten
    environment variable into a public roster."""
    admin = await make_admin(app_client)
    get_settings().admin_player_codes = []

    assert (await app_client.get(OVERVIEW, headers=admin)).status_code == 404
    assert (await app_client.get("/v1/admin/players", headers=admin)).status_code == 404


async def test_the_allowlist_is_player_codes_and_junk_grants_nothing(caplog):
    """An email address, a number, a code of the wrong length: each is
    dropped and named in the log rather than taking the service down."""
    settings = Settings(
        jwt_secret="x" * 40,
        admin_player_codes=f" {TEST_ADMIN_CODE.lower()} , ada@example.test, 12345, TOOLONG9, ",
    )

    assert settings.admin_player_codes == [TEST_ADMIN_CODE]
    assert "ada@example.test" in caplog.text
    assert "TOOLONG9" in caplog.text


async def test_registering_the_operators_email_first_grants_nothing(app_client):
    """Why the allowlist is codes and not addresses: nothing here verifies an
    email, so anybody can claim one. Nobody can choose a player code."""
    squatter = await app_client.post(
        "/v1/auth/register",
        json={
            "email": "operator@example.test",
            "password": "correct horse battery staple",
            "display_name": "Operator",
        },
    )
    headers = {"Authorization": f"Bearer {squatter.json()['access_token']}"}

    assert squatter.json()["user"]["is_admin"] is False
    assert (await app_client.get(OVERVIEW, headers=headers)).status_code == 404


# ----- what it reports ------------------------------------------------------


async def test_players_are_counted_by_how_they_arrived(app_client):
    admin = await make_admin(app_client)
    await authorise(app_client, 4242)
    await app_client.post("/v1/auth/guest")
    await app_client.post("/v1/auth/guest")

    players = (await app_client.get(OVERVIEW, headers=admin)).json()["players"]

    assert players["total"] == 4
    assert players["registered"] == 2
    assert players["guests"] == 2
    assert players["new_in_window"] == 4
    assert players["forecast_in_window"] == 0


async def test_forecasts_and_points_add_up(app_client):
    markets = await seed_markets(3)
    admin = await make_admin(app_client)
    player = await authorise(app_client, 4242)

    won = (await place(app_client, player, body(markets[:1], stake=10_000))).json()
    lost = (await place(app_client, player, body(markets[1:2], stake=20_000))).json()
    await place(app_client, player, body(markets[2:], stake=5_000))
    await settle(won["id"], won=True)
    await settle(lost["id"], won=False)
    await app_client.post("/v1/economy/claim", headers=player)

    report = (await app_client.get(OVERVIEW, headers=admin)).json()

    assert report["forecasts"] == {"placed": 3, "settled": 2, "won": 1, "lost": 1, "open": 1}
    assert report["players"]["forecast_in_window"] == 1
    assert report["players"]["claimed_in_window"] == 1

    points = report["points"]
    assert points["granted"]["minor"] == 2 * 100_000 + 25_000  # two sign-ups and a top-up
    assert points["staked"]["minor"] == 35_000
    assert points["returned"]["minor"] == 20_000
    assert points["adjusted"]["minor"] == 0


async def test_the_net_change_reconciles_with_the_whole_ledger(app_client):
    markets = await seed_markets(1)
    admin = await make_admin(app_client)
    player = await authorise(app_client, 4242)
    slip = (await place(app_client, player, body(markets, stake=10_000))).json()
    await settle(slip["id"], won=True)

    report = (await app_client.get(OVERVIEW, headers=admin)).json()

    async with db.acquire() as conn:
        ledger_total = await conn.fetchval("SELECT sum(amount) FROM ledger_entries")
        balances = await conn.fetchval("SELECT sum(coin_balance) FROM users")

    assert report["points"]["net_change"]["minor"] == ledger_total == balances
    assert sum(row["net"]["minor"] for row in report["ledger"]) == ledger_total


async def test_there_is_no_revenue_in_the_report(app_client):
    """Not a zero — an absence. Nothing is sold, so there is no line for it."""
    admin = await make_admin(app_client)

    text = (await app_client.get(OVERVIEW, headers=admin)).text.lower()
    for gone in ("stars", "revenue", "paying", "purchase", "house_edge", "break_even"):
        assert gone not in text


async def test_the_brakes_in_use_are_counted(app_client):
    admin = await make_admin(app_client)
    cautious = await authorise(app_client, 4242)
    resting = await authorise(app_client, 4243)
    leaving = await authorise(app_client, 4244)
    await app_client.put("/v1/me/limits", json={"daily_limit_minor": 20_000}, headers=cautious)
    await app_client.post("/v1/me/break", json={"hours": 24}, headers=resting)
    await app_client.post(
        "/v1/me/erase", json={"password": "correct horse battery staple"}, headers=leaving
    )

    report = (await app_client.get(OVERVIEW, headers=admin)).json()

    assert report["safer_play"] == {"with_daily_limit": 1, "on_break": 1, "erased": 1}
    assert report["players"]["total"] == 3, "an erased account is no longer a player"


async def test_the_daily_series_has_a_row_for_every_day(app_client):
    """A day with nothing in it is a row of zeroes, not a missing row — or a
    chart drawn from this would silently close the gap."""
    admin = await make_admin(app_client)

    report = (await app_client.get(f"{OVERVIEW}?days=7", headers=admin)).json()

    assert report["window_days"] == 7
    assert len(report["daily"]) in (8, 9)  # seven days back through today, either side of midnight
    assert sum(day["new_players"] for day in report["daily"]) == 1


async def test_activity_outside_the_window_is_left_out(app_client):
    markets = await seed_markets(1)
    admin = await make_admin(app_client)
    player = await authorise(app_client, 4242)
    await place(app_client, player, body(markets))

    async with db.acquire() as conn:
        await conn.execute("UPDATE predictions SET placed_at = NOW() - INTERVAL '40 days'")

    report = (await app_client.get(f"{OVERVIEW}?days=30", headers=admin)).json()
    assert report["forecasts"]["placed"] == 0
    assert report["forecasts"]["open"] == 1, "open is a count of now, not of the window"


async def test_the_window_is_bounded(app_client):
    admin = await make_admin(app_client)
    assert (await app_client.get(f"{OVERVIEW}?days=0", headers=admin)).status_code == 422
    assert (await app_client.get(f"{OVERVIEW}?days=9999", headers=admin)).status_code == 422
