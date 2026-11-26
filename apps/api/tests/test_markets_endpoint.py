"""GET /v1/markets — Postgres for metadata, Redis for price."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from conftest import authorise, mock_http_client
from fixtures import gamma_events as fx

from backend import db
from backend.cache import prices as price_cache
from backend.config import get_settings
from backend.workers import polymarket_discovery as discovery


async def seed(count: int = 3, *, categories: list[str] | None = None) -> list[dict]:
    events = []
    for i in range(count):
        tags = fx.CRYPTO_TAGS if (categories and categories[i] == "Crypto") else None
        events.append(
            fx.event(
                str(i),
                tags=tags,
                markets=[fx.binary_market(f"8{i:04d}", end_in_days=i + 1)],
            )
        )

    def gamma(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        return httpx.Response(200, json=events if offset == 0 else [])

    async with mock_http_client(gamma) as client:
        await discovery.run_discovery(client, get_settings())

    async with db.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM markets ORDER BY lock_at")
    return [dict(r) for r in rows]


async def test_requires_authentication(app_client):
    assert (await app_client.get("/v1/markets")).status_code == 401


async def test_lists_active_markets_soonest_first(app_client):
    await seed(3)
    auth = await authorise(app_client)

    body = (await app_client.get("/v1/markets", headers=auth)).json()

    assert len(body["markets"]) == 3
    lock_times = [m["lock_at"] for m in body["markets"]]
    assert lock_times == sorted(lock_times)
    assert body["next_cursor"] is None

    first = body["markets"][0]
    assert first["event"]["title"]
    assert first["category"] in {"Macro", "Crypto"}
    assert "boosts" not in first, "there are no promotional prices to list"


async def test_price_is_served_from_redis_when_present(app_client):
    markets = await seed(1)
    auth = await authorise(app_client)
    now = datetime.now(UTC)

    await price_cache.write_many(
        [(markets[0]["id"], Decimal("0.7350"), "CLOB_MIDPOINT", now)], ttl_seconds=300
    )

    probability = (await app_client.get("/v1/markets", headers=auth)).json()["markets"][0][
        "probability"
    ]

    assert probability["yes"] == "0.7350"
    assert probability["no"] == "0.2650"
    assert probability["source"] == "CLOB_MIDPOINT"
    assert probability["stale"] is False


async def test_falls_back_to_the_database_on_a_cache_miss(app_client):
    await seed(1)
    auth = await authorise(app_client)

    probability = (await app_client.get("/v1/markets", headers=auth)).json()["markets"][0][
        "probability"
    ]

    assert probability["source"] == "DATABASE"
    assert probability["yes"] == "0.6200"


async def test_an_old_price_is_flagged_rather_than_hidden(app_client):
    """The market still appears — the UI needs to say the number is old, and
    Phase 3's odds engine needs to refuse to price on it."""
    markets = await seed(1)
    auth = await authorise(app_client)
    settings = get_settings()

    stale_at = datetime.now(UTC) - timedelta(seconds=settings.price_staleness_seconds + 60)
    await price_cache.write_many(
        [(markets[0]["id"], Decimal("0.5"), "CLOB_MIDPOINT", stale_at)], ttl_seconds=600
    )

    probability = (await app_client.get("/v1/markets", headers=auth)).json()["markets"][0][
        "probability"
    ]

    assert probability["stale"] is True
    assert probability["age_seconds"] > settings.price_staleness_seconds


async def test_yes_and_no_always_sum_to_one(app_client):
    markets = await seed(1)
    auth = await authorise(app_client)
    await price_cache.write_many(
        [(markets[0]["id"], Decimal("0.123456789"), "CLOB_MIDPOINT", datetime.now(UTC))],
        ttl_seconds=300,
    )

    probability = (await app_client.get("/v1/markets", headers=auth)).json()["markets"][0][
        "probability"
    ]

    assert Decimal(probability["yes"]) + Decimal(probability["no"]) == Decimal(1)


async def test_filters_by_category(app_client):
    await seed(2, categories=["Macro", "Crypto"])
    auth = await authorise(app_client)

    crypto = (await app_client.get("/v1/markets?category=Crypto", headers=auth)).json()
    assert len(crypto["markets"]) == 1
    assert crypto["markets"][0]["category"] == "Crypto"


async def test_pagination_walks_every_market_exactly_once(app_client):
    await seed(5)
    auth = await authorise(app_client)

    seen: list[str] = []
    cursor = None
    for _ in range(10):
        url = f"/v1/markets?limit=2{f'&cursor={cursor}' if cursor else ''}"
        page = (await app_client.get(url, headers=auth)).json()
        seen.extend(m["id"] for m in page["markets"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5


async def test_a_bad_cursor_is_rejected(app_client):
    auth = await authorise(app_client)
    response = await app_client.get("/v1/markets?cursor=not-a-cursor", headers=auth)
    assert response.status_code == 400


async def test_locked_and_resolved_markets_are_not_listed(app_client):
    markets = await seed(3)
    auth = await authorise(app_client)

    async with db.transaction() as conn:
        await conn.execute("UPDATE markets SET status='LOCKED' WHERE id=$1", markets[0]["id"])
        await conn.execute(
            "UPDATE markets SET status='RESOLVED', resolution='YES', resolved_at=NOW() WHERE id=$1",
            markets[1]["id"],
        )

    body = (await app_client.get("/v1/markets", headers=auth)).json()
    assert [m["id"] for m in body["markets"]] == [str(markets[2]["id"])]


async def test_a_boost_left_in_the_table_changes_nothing(app_client):
    """Boost rows from before the site went free-to-play may still exist.
    Nothing reads them: the feed does not list them and a quote ignores them."""
    markets = await seed(1)
    auth = await authorise(app_client)
    await price_cache.write_many(
        [(markets[0]["id"], Decimal("0.50"), "CLOB_MIDPOINT", datetime.now(UTC))],
        ttl_seconds=300,
    )

    async with db.transaction() as conn:
        await conn.execute(
            """
            INSERT INTO odds_boosts (market_id, side, boost_multiplier, ends_at,
                                     max_total_stake, max_stake_per_user)
            VALUES ($1, 'YES', 1.400, NOW() + INTERVAL '2 hours', 1000000, 50000)
            """,
            markets[0]["id"],
        )

    listed = (await app_client.get("/v1/markets", headers=auth)).json()["markets"][0]
    assert "boosts" not in listed

    quote = (
        await app_client.post(
            "/v1/predictions/quote",
            json={"legs": [{"market_id": str(markets[0]["id"]), "side": "YES"}], "stake": 10000},
            headers=auth,
        )
    ).json()
    assert quote["combined_odds"] == "2.000000"


async def test_the_feed_carries_the_rules_a_slip_must_satisfy(app_client):
    """So the page can say "this one is all but settled" before a round trip.
    Advisory only: the server re-checks every one at quote and placement."""
    await seed(1)
    auth = await authorise(app_client)
    settings = get_settings()

    body = (await app_client.get("/v1/markets", headers=auth)).json()

    assert body["max_legs"] == settings.max_legs
    assert body["min_prob"] == "0.01"
    assert body["max_prob"] == "0.99"
    assert body["max_combined_odds"] == "1000.0"
    assert body["min_stake"]["minor"] == settings.min_stake_minor
    assert body["max_stake"]["minor"] == settings.max_stake_minor
    assert body["payout_cap"]["minor"] == settings.payout_cap_minor
    for gone in ("vig_rate", "min_legs", "parlay_bonus_by_legs", "example_stake", "referral_bonus"):
        assert gone not in body


async def test_market_text_is_served_in_english_whatever_the_row_holds(app_client):
    """`question` and `title` may still hold a translation from when the feed
    was localised. The source columns are what the API reads."""
    markets = await seed(1)
    auth = await authorise(app_client)
    async with db.acquire() as conn:
        await conn.execute("UPDATE markets SET question = 'ein übersetzter Text'")
        await conn.execute("UPDATE market_events SET title = 'ein übersetzter Titel'")

    listed = (await app_client.get("/v1/markets", headers=auth)).json()["markets"][0]

    assert listed["question"] == markets[0]["question_source"]
    assert listed["question"].isascii()
    assert listed["event"]["title"].isascii()


async def test_probabilities_are_strings_not_json_numbers(app_client):
    """These feed payout arithmetic; a JSON number is a double in most clients."""
    await seed(1)
    auth = await authorise(app_client)

    raw = (await app_client.get("/v1/markets", headers=auth)).text
    assert '"yes":"0.6200"' in raw.replace(" ", "")


# ----- the public rules -----------------------------------------------------


async def test_the_rules_are_public_and_come_from_the_live_configuration(app_client):
    """The pages that explain the game render from this, so they cannot drift
    from the game. No session: it is what a visitor reads before signing up."""
    settings = get_settings()

    response = await app_client.get("/v1/rules")
    assert response.status_code == 200

    rules = response.json()
    assert rules["signup_bonus"] == {"minor": 100_000, "display": "1,000"}
    assert rules["daily_topup"]["minor"] == settings.daily_topup_minor
    assert rules["max_legs"] == settings.max_legs
    assert rules["max_combined_odds"] == "1000.0"
    assert (rules["min_prob"], rules["max_prob"]) == ("0.01", "0.99")
    assert rules["limit_loosen_delay_hours"] == 24
    assert rules["break_options_hours"] == [24, 72, 168, 720]


async def test_the_rules_state_that_nothing_is_taken(app_client):
    rules = (await app_client.get("/v1/rules")).json()
    assert rules["margin"] == "0"
    assert rules["reference_margin"] == "0.05", "the illustration, labelled as one"


async def test_the_rules_follow_a_retune(app_client):
    get_settings().daily_topup_minor = 50_000
    assert (await app_client.get("/v1/rules")).json()["daily_topup"]["display"] == "500"


# ----- what the feed leaves out, and the orders it can be read in -----------


async def set_prices(markets: list[dict], probabilities: list[str]) -> None:
    async with db.acquire() as conn:
        for market, probability in zip(markets, probabilities, strict=True):
            await conn.execute(
                "UPDATE markets SET raw_yes_prob = $2, price_updated_at = NOW() WHERE id = $1",
                market["id"],
                Decimal(probability),
            )


async def test_a_question_that_is_all_but_settled_is_left_off_the_feed(app_client):
    """Neither side of it can be priced, so a card for it would be two
    buttons that can never work."""
    markets = await seed(4)
    auth = await authorise(app_client)
    await set_prices(markets, ["0.995", "0.004", "0.99", "0.50"])

    body = (await app_client.get("/v1/markets", headers=auth)).json()

    assert {m["id"] for m in body["markets"]} == {str(markets[2]["id"]), str(markets[3]["id"])}


async def test_the_default_order_is_still_soonest_to_close(app_client):
    markets = await seed(3)
    auth = await authorise(app_client)

    body = (await app_client.get("/v1/markets", headers=auth)).json()
    assert [m["id"] for m in body["markets"]] == [str(m["id"]) for m in markets]


async def test_closest_calls_come_first_when_asked_for(app_client):
    """Nearest a coin flip first — the questions with the most to disagree
    with the crowd about."""
    markets = await seed(4)
    auth = await authorise(app_client)
    await set_prices(markets, ["0.90", "0.52", "0.20", "0.45"])

    body = (await app_client.get("/v1/markets?sort=tossup", headers=auth)).json()

    assert [m["id"] for m in body["markets"]] == [
        str(markets[1]["id"]),  # 0.52
        str(markets[3]["id"]),  # 0.45
        str(markets[2]["id"]),  # 0.20
        str(markets[0]["id"]),  # 0.90
    ]


async def test_most_traded_come_first_when_asked_for(app_client):
    markets = await seed(3)
    auth = await authorise(app_client)
    async with db.acquire() as conn:
        for market, volume in zip(markets, [100, 9000, 500], strict=True):
            await conn.execute(
                "UPDATE markets SET volume_usd = $2 WHERE id = $1", market["id"], volume
            )

    body = (await app_client.get("/v1/markets?sort=volume", headers=auth)).json()
    assert [m["id"] for m in body["markets"]] == [
        str(markets[1]["id"]),
        str(markets[2]["id"]),
        str(markets[0]["id"]),
    ]


async def test_an_ordered_feed_pages_through_every_question_once(app_client):
    markets = await seed(5)
    auth = await authorise(app_client)
    await set_prices(markets, ["0.10", "0.30", "0.50", "0.70", "0.90"])

    seen: list[str] = []
    cursor = None
    for _ in range(10):
        url = f"/v1/markets?sort=tossup&limit=2{f'&cursor={cursor}' if cursor else ''}"
        page = (await app_client.get(url, headers=auth)).json()
        seen.extend(m["id"] for m in page["markets"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert len(seen) == 5
    assert set(seen) == {str(m["id"]) for m in markets}
    assert seen[0] == str(markets[2]["id"]), "0.50 is the closest call"


async def test_an_order_the_api_does_not_offer_is_refused(app_client):
    """The ORDER BY is looked up by name from a fixed table, never built from
    the request — so a name that is not in the table is simply invalid."""
    await seed(1)
    auth = await authorise(app_client)

    for attempt in ("payout", "m.id; DROP TABLE markets", ""):
        response = await app_client.get("/v1/markets", params={"sort": attempt}, headers=auth)
        assert response.status_code == 422, attempt


async def test_a_cursor_from_one_order_is_not_accepted_by_another(app_client):
    await seed(3)
    auth = await authorise(app_client)

    by_closing = (await app_client.get("/v1/markets?limit=1", headers=auth)).json()["next_cursor"]
    by_tossup = (await app_client.get("/v1/markets?sort=tossup&limit=1", headers=auth)).json()[
        "next_cursor"
    ]

    crossed = await app_client.get(f"/v1/markets?sort=tossup&cursor={by_closing}", headers=auth)
    assert crossed.status_code == 400
    assert crossed.json()["code"] == "bad_cursor"

    crossed = await app_client.get(f"/v1/markets?cursor={by_tossup}", headers=auth)
    assert crossed.status_code == 400


async def test_an_offset_cursor_cannot_be_made_absurd(app_client):
    import base64
    import json

    await seed(1)
    auth = await authorise(app_client)

    for offset in (-1, 10**9, "5", True):
        forged = base64.urlsafe_b64encode(json.dumps({"o": offset}).encode()).decode().rstrip("=")
        response = await app_client.get(f"/v1/markets?sort=tossup&cursor={forged}", headers=auth)
        assert response.status_code == 400, offset


async def test_the_feed_lists_every_category_with_something_open(app_client):
    """Not only the ones on this page: a filter built from it must not lose
    options as the reader pages or filters."""
    await seed(3, categories=["Macro", "Crypto", "Macro"])
    auth = await authorise(app_client)

    page = (await app_client.get("/v1/markets?limit=1", headers=auth)).json()
    assert page["categories"] == ["Crypto", "Macro"]

    filtered = (await app_client.get("/v1/markets?category=Crypto", headers=auth)).json()
    assert filtered["categories"] == ["Crypto", "Macro"]
    assert {m["category"] for m in filtered["markets"]} == {"Crypto"}


async def test_a_category_with_nothing_left_to_forecast_is_not_offered(app_client):
    markets = await seed(2, categories=["Macro", "Crypto"])
    auth = await authorise(app_client)
    crypto = next(m for m in markets if m["category"] == "Crypto")
    await set_prices([crypto], ["0.999"])

    page = (await app_client.get("/v1/markets", headers=auth)).json()
    assert page["categories"] == ["Macro"]
