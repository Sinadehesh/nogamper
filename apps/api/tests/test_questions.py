"""Questions, for pages anybody can read: one question, and what moved.

Two things are being held to here.

The first is arithmetic a reader can check. A page that says "from 30% to 55%"
has to be showing where the question stood and where it stands, not a change
figure pasted beside a price it was not measured to.

The second is restraint. A list of the biggest changes is, left alone, a list
of questions that have just been decided — a price going to 1% on the day the
question closes is a result, not news — and a move that has already come back
is not one either. Most of these tests are about what is *left out*.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from conftest import mock_http_client
from fixtures import gamma_events as fx

from backend import db
from backend.cache import history as history_cache
from backend.cache import prices as price_cache
from backend.clients import clob, gamma
from backend.config import Settings, get_settings
from backend.workers import polymarket_discovery as discovery

# ----- helpers -----------------------------------------------------------------


def moved(
    market_id: str,
    *,
    now: str = "0.55",
    day: float | None = 0.25,
    week: float | None = None,
    hour: float | None = None,
    end_in_days: float = 14,
    **overrides: object,
) -> dict:
    """A Gamma market at `now`, having changed by `day` over the last day."""
    changes = {
        "oneHourPriceChange": hour,
        "oneDayPriceChange": day,
        "oneWeekPriceChange": week,
    }
    return fx.binary_market(
        market_id,
        prices=[now, str(Decimal(1) - Decimal(now))],
        end_in_days=end_in_days,
        **{key: value for key, value in changes.items() if value is not None},
        **overrides,
    )


async def discover(*markets: dict) -> None:
    """Bring `markets` in the way production does: through a discovery pass."""
    events = [fx.event(str(index), markets=[market]) for index, market in enumerate(markets)]

    def feed(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        return httpx.Response(200, json=events if offset == 0 else [])

    async with mock_http_client(feed) as client:
        await discovery.run_discovery(client, get_settings())


def source_of(app_client, handler) -> list[httpx.Request]:
    """Answer the API's outbound requests with `handler`; return what it asked."""
    asked: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        return handler(request)

    app_client._transport.app.state.http = mock_http_client(recording)
    return asked


def no_history(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"history": []})


def a_week(points: int = 5, start: float = 0.30, step: float = 0.05):
    base = datetime.now(UTC) - timedelta(hours=points)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "history": [
                    {
                        "t": int((base + timedelta(hours=index)).timestamp()),
                        "p": start + step * index,
                    }
                    for index in range(points)
                ]
            },
        )

    return handler


async def moves(app_client, **params) -> dict:
    response = await app_client.get("/v1/questions/moves", params=params)
    assert response.status_code == 200, response.text
    return response.json()


# ----- reading the source ---------------------------------------------------------


def normalized(raw: dict) -> gamma.NormalizedMarket:
    market = gamma.normalize_market(
        raw,
        category="Macro",
        settings=Settings(jwt_secret="y"),
        stats=gamma.DiscoveryStats(),
        now=datetime.now(UTC),
    )
    assert market is not None
    return market


def test_the_change_figures_are_read_with_the_price_they_were_measured_to():
    market = normalized(moved("1", now="0.55", hour=0.01, day=0.25, week=-0.10))

    assert market.change_1h == Decimal("0.010000")
    assert market.change_24h == Decimal("0.250000")
    assert market.change_7d == Decimal("-0.100000")
    assert market.reference_prob == Decimal("0.550000")


def test_a_market_that_lists_no_first_has_its_changes_turned_to_face_yes():
    """Gamma's figures are all for the market's first outcome. Where that is
    "No", a rise of 25 points is YES falling by 25 — and a page that printed
    it unturned would say the opposite of what happened."""
    market = normalized(
        fx.binary_market(
            "2",
            outcomes=["No", "Yes"],
            prices=["0.70", "0.30"],
            oneDayPriceChange=0.25,
        )
    )

    assert market.change_24h == Decimal("-0.250000")
    assert market.reference_prob == Decimal("0.300000"), "the YES price, not the first one"


def test_no_figure_is_not_the_same_as_no_change():
    """A market younger than a day has no day's change. Recording zero would
    be a claim that it was measured and found still."""
    market = normalized(fx.binary_market("3"))

    assert market.change_1h is None
    assert market.change_24h is None
    assert market.change_7d is None
    assert market.reference_prob is None, "nothing to be a reference for"


@pytest.mark.parametrize("junk", ["up a lot", float("nan"), float("inf"), 1.5, -2, True, [], {}])
def test_a_figure_that_is_not_a_change_in_probability_is_no_figure(junk):
    market = normalized(fx.binary_market("4", oneDayPriceChange=junk, oneWeekPriceChange=0.10))

    assert market.change_24h is None
    assert market.change_7d == Decimal("0.100000"), "one bad figure does not cost the others"


@pytest.mark.parametrize(
    "slug",
    ["Will-It-Happen", "will it happen", "-leading", "trailing-", "double--dash", "a" * 201, "", 7],
)
def test_a_slug_that_is_not_already_an_address_is_not_used_as_one(slug):
    """Not repaired. A slug that had to be lowercased or trimmed is one that
    might then collide with another, and show the wrong question."""
    assert normalized(fx.binary_market("5", slug=slug)).slug is None


def test_a_slug_that_is_an_address_is_kept_exactly():
    assert normalized(fx.binary_market("6", slug="fed-cut-2026")).slug == "fed-cut-2026"


# ----- keeping it ---------------------------------------------------------------------


async def test_discovery_stores_the_address_and_the_changes(resources):
    await discover(moved("7001", slug="fed-cut", hour=0.01, day=0.25, week=0.40))

    async with db.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM markets")

    assert row["slug"] == "fed-cut"
    assert row["change_1h"] == Decimal("0.010000")
    assert row["change_24h"] == Decimal("0.250000")
    assert row["change_7d"] == Decimal("0.400000")
    assert row["change_ref_prob"] == Decimal("0.550000")
    assert (datetime.now(UTC) - row["changes_at"]).total_seconds() < 60


async def test_a_pass_with_no_figures_keeps_the_last_ones_and_their_date(resources):
    """The source omits a figure now and then. Blanking the history a reader
    was shown an hour ago would be worse than showing it with its own date."""
    await discover(moved("7002", slug="first-name", day=0.25))
    async with db.acquire() as conn:
        await conn.execute("UPDATE markets SET changes_at = NOW() - INTERVAL '2 hours'")
        before = await conn.fetchrow("SELECT * FROM markets")

    await discover(fx.binary_market("7002", slug="renamed-since"))

    async with db.acquire() as conn:
        after = await conn.fetchrow("SELECT * FROM markets")
    assert after["change_24h"] == Decimal("0.250000")
    assert after["change_ref_prob"] == before["change_ref_prob"]
    assert after["changes_at"] == before["changes_at"]
    assert after["slug"] == "first-name", "a page's address does not change under it"


async def test_a_pass_with_new_figures_replaces_the_old_ones_whole(resources):
    await discover(moved("7003", now="0.55", day=0.25, week=0.40))
    await discover(moved("7003", now="0.60", day=0.05))

    async with db.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM markets")
    assert row["change_24h"] == Decimal("0.050000")
    assert row["change_7d"] is None, "the week's figure was for another reference price"
    assert row["change_ref_prob"] == Decimal("0.600000")


# ----- what moved --------------------------------------------------------------------


async def test_a_move_is_reported_as_where_it_was_and_where_it_is(app_client):
    await discover(moved("7101", slug="fed-cut", now="0.55", day=0.25))

    body = await moves(app_client)

    assert [m["slug"] for m in body["day"]] == ["fed-cut"]
    move = body["day"][0]
    assert (move["was"], move["now"], move["change"]) == ("0.3000", "0.5500", "0.2500")
    assert move["question"] and move["event_title"] and move["category"] == "Macro"
    assert body["measured_at"] is not None
    assert body["day_threshold"] == "0.0500"
    assert body["week"] == [], "no week's figure was given, so nothing is claimed about the week"


async def test_anybody_may_read_it(app_client):
    """No session and no key: every figure is the market's own."""
    await discover(moved("7100", slug="open-to-all"))
    source_of(app_client, no_history)

    assert (await app_client.get("/v1/questions/moves")).status_code == 200
    assert (await app_client.get("/v1/questions")).status_code == 200
    assert (await app_client.get("/v1/questions/open-to-all")).status_code == 200


async def test_a_fall_is_a_move_too(app_client):
    await discover(moved("7102", slug="falling", now="0.30", day=-0.40))

    move = (await moves(app_client))["day"][0]

    assert (move["was"], move["now"], move["change"]) == ("0.7000", "0.3000", "-0.4000")


async def test_the_live_price_is_what_now_means(app_client):
    """The change figure is up to an hour old. The price beside it is not, so
    the change shown is recomputed between the two numbers on the page."""
    await discover(moved("7103", slug="still-going", now="0.55", day=0.25))
    async with db.acquire() as conn:
        market_id = await conn.fetchval("SELECT id FROM markets")
    await price_cache.write_many(
        [(market_id, Decimal("0.6100"), "CLOB_MIDPOINT", datetime.now(UTC))], ttl_seconds=300
    )

    move = (await moves(app_client))["day"][0]

    assert (move["was"], move["now"], move["change"]) == ("0.3000", "0.6100", "0.3100")


async def test_a_move_that_has_come_back_is_not_reported(app_client):
    await discover(moved("7104", slug="came-back", now="0.55", day=0.25))
    async with db.acquire() as conn:
        market_id = await conn.fetchval("SELECT id FROM markets")
    await price_cache.write_many(
        [(market_id, Decimal("0.3300"), "CLOB_MIDPOINT", datetime.now(UTC))], ttl_seconds=300
    )

    assert (await moves(app_client))["day"] == []


async def test_a_change_below_the_threshold_is_noise_and_is_left_out(app_client):
    await discover(moved("7105", slug="barely", now="0.55", day=0.04))

    assert (await moves(app_client))["day"] == []


async def test_a_question_about_to_close_is_a_result_arriving_not_a_move(app_client):
    await discover(
        moved("7106", slug="closes-tonight", now="0.55", day=0.30, end_in_days=0.5),
        moved("7107", slug="closes-next-week", now="0.55", day=0.30, end_in_days=7),
    )

    assert [m["slug"] for m in (await moves(app_client))["day"]] == ["closes-next-week"]


async def test_a_question_that_is_all_but_decided_is_left_out(app_client):
    await discover(
        moved("7108", slug="decided-now", now="0.985", day=0.40),
        moved("7109", slug="was-decided-then", now="0.30", day=0.29),
        moved("7110", slug="open-both-ends", now="0.50", day=0.20),
    )

    assert [m["slug"] for m in (await moves(app_client))["day"]] == ["open-both-ends"]


async def test_figures_too_old_to_be_the_last_day_are_not_sent_as_it(app_client):
    """A server that has been asleep wakes with yesterday's figures. Until the
    question list has been read again there is no list of moves to send: the
    site keeps the one it last built, with its date on it, instead of building
    a new page out of a day that is over."""
    await discover(moved("7111", slug="stale", now="0.55", day=0.25))
    async with db.acquire() as conn:
        await conn.execute("UPDATE markets SET changes_at = NOW() - INTERVAL '7 hours'")

    response = await app_client.get("/v1/questions/moves")

    assert response.status_code == 503
    assert response.json()["code"] == "figures_not_current"
    assert response.headers["retry-after"] == "60"
    assert "day" not in response.json(), "an out-of-date list is not sent along with the apology"


async def test_prices_from_before_the_server_slept_are_not_called_now(app_client):
    """The other half of "from 30% to 55%". A server that wakes has the prices
    it went to sleep with until its first pass over them, and the figures for
    the day may already have been read again by then."""
    await discover(moved("7113", slug="woken", now="0.55", day=0.25))
    async with db.acquire() as conn:
        await conn.execute("UPDATE markets SET price_updated_at = NOW() - INTERVAL '5 hours'")

    response = await app_client.get("/v1/questions/moves")

    assert response.status_code == 503
    assert response.json()["code"] == "figures_not_current"


async def test_a_question_whose_own_price_is_old_is_left_out(app_client):
    """One question's price can fall behind while the rest are current. It is
    not listed at a price nobody has read lately — unless the cache holds a
    newer one than the database does."""
    await discover(
        moved("7114", slug="read-lately", now="0.55", day=0.25),
        moved("7115", slug="fallen-behind", now="0.55", day=0.30),
        moved("7116", slug="behind-but-cached", now="0.55", day=0.35),
    )
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE markets SET price_updated_at = NOW() - INTERVAL '5 hours'"
            " WHERE slug IN ('fallen-behind', 'behind-but-cached')"
        )
        cached_id = await conn.fetchval("SELECT id FROM markets WHERE slug = 'behind-but-cached'")
    await price_cache.write_many(
        [(cached_id, Decimal("0.5500"), "CLOB_MIDPOINT", datetime.now(UTC))], ttl_seconds=300
    )

    listed = [m["slug"] for m in (await moves(app_client))["day"]]

    assert listed == ["behind-but-cached", "read-lately"]


async def test_with_nothing_measured_there_is_no_list_yet(app_client):
    """An empty database is not a day on which nothing moved."""
    response = await app_client.get("/v1/questions/moves")

    assert response.status_code == 503
    assert response.json()["code"] == "figures_not_current"


async def test_a_quiet_day_is_an_empty_list_not_an_error(app_client):
    """Figures that are current and show nothing above the threshold are a
    finding, and are sent as one."""
    await discover(moved("7112", slug="quiet", now="0.55", day=0.01))

    body = await moves(app_client)

    assert (body["day"], body["week"]) == ([], [])


async def test_only_open_questions_with_a_page_are_listed(app_client):
    await discover(
        moved("7112", slug="retired", now="0.55", day=0.25),
        moved("7113", slug="open", now="0.55", day=0.25),
        moved("7114", now="0.55", day=0.25, slug="No Page For This"),
    )
    async with db.acquire() as conn:
        await conn.execute("UPDATE markets SET status = 'DRAFT' WHERE slug = 'retired'")

    assert [m["slug"] for m in (await moves(app_client))["day"]] == ["open"]


async def test_the_biggest_moves_come_first_and_the_list_is_cut_where_asked(app_client):
    await discover(
        moved("7115", slug="small", now="0.50", day=0.06),
        moved("7116", slug="large", now="0.50", day=-0.40),
        moved("7117", slug="medium", now="0.50", day=0.20),
    )

    everything = await moves(app_client)
    two = await moves(app_client, limit=2)

    assert [m["slug"] for m in everything["day"]] == ["large", "medium", "small"]
    assert [m["slug"] for m in two["day"]] == ["large", "medium"]


async def test_two_questions_at_one_address_are_listed_once(app_client):
    """One address is one page, so it is one line in the list."""
    await discover(
        moved("7121", slug="shared-address", now="0.60", day=0.30),
        moved("7122", slug="shared-address", now="0.50", day=0.10),
    )

    listed = (await moves(app_client))["day"]

    assert [(m["slug"], m["change"]) for m in listed] == [("shared-address", "0.3000")]


async def test_the_week_has_its_own_figure_and_its_own_threshold(app_client):
    await discover(
        moved("7118", slug="slow-climb", now="0.60", day=0.02, week=0.30),
        moved("7119", slug="week-of-noise", now="0.60", day=0.02, week=0.08),
    )

    body = await moves(app_client)

    assert body["day"] == []
    assert [m["slug"] for m in body["week"]] == ["slow-climb"]
    assert body["week"][0]["was"] == "0.3000"
    assert body["week_threshold"] == "0.1000"


# ----- one question -----------------------------------------------------------------


async def test_a_question_is_read_by_its_address(app_client):
    await discover(moved("7201", slug="fed-cut", now="0.55", hour=0.01, day=0.25, week=0.40))
    source_of(app_client, a_week())

    response = await app_client.get("/v1/questions/fed-cut")

    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "fed-cut"
    assert body["question"] == "Will the Fed cut rates by 25 bps in September?"
    assert body["state"] == "open"
    assert body["outcome"] is None
    assert body["probability"]["yes"] == "0.5500"
    assert body["changes"]["hour"] == "0.0100"
    assert body["changes"]["day"] == "0.2500"
    assert body["changes"]["week"] == "0.4000"
    assert body["changes"]["reference"] == "0.5500", "what the changes were measured to"
    assert body["changes"]["measured_at"] is not None
    assert body["event_title"] == "Fed decision in September"


async def test_an_answer_says_when_it_was_put_together(app_client):
    """The pages built from these are kept and served again later. Each prints
    the moment it describes, so the answer has to carry one."""
    await discover(moved("7211", slug="dated"))
    source_of(app_client, no_history)
    before = datetime.now(UTC)

    question = (await app_client.get("/v1/questions/dated")).json()
    listed = await moves(app_client)

    for body in (question, listed):
        as_of = datetime.fromisoformat(body["as_of"])
        assert before <= as_of <= datetime.now(UTC)


async def test_a_questions_old_figures_are_not_shown_as_its_last_day(app_client):
    """A question that has dropped out of the list the site reads keeps the
    last change figures it was given, for ever. They are not this day's."""
    await discover(moved("7212", slug="left-behind", hour=0.01, day=0.25, week=0.40))
    async with db.acquire() as conn:
        await conn.execute("UPDATE markets SET changes_at = NOW() - INTERVAL '7 hours'")
    source_of(app_client, no_history)

    body = (await app_client.get("/v1/questions/left-behind")).json()

    assert body["changes"] == {
        "hour": None,
        "day": None,
        "week": None,
        "reference": None,
        "measured_at": None,
    }
    assert body["probability"]["yes"] == "0.5500", "the price itself is still the live one"


async def test_figures_within_the_allowed_age_are_still_shown(app_client):
    await discover(moved("7213", slug="recent-enough", day=0.25))
    async with db.acquire() as conn:
        await conn.execute("UPDATE markets SET changes_at = NOW() - INTERVAL '5 hours'")
    source_of(app_client, no_history)

    body = (await app_client.get("/v1/questions/recent-enough")).json()

    assert body["changes"]["day"] == "0.2500"


async def test_an_address_nobody_has_is_not_found(app_client):
    asked = source_of(app_client, no_history)

    response = await app_client.get("/v1/questions/no-such-question")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert asked == [], "the source is never asked about a question we do not have"


@pytest.mark.parametrize(
    "address", ["UPPER-CASE", "has space", "trailing-", "a" * 201, "semi;colon"]
)
async def test_something_that_could_not_be_an_address_is_not_looked_up(app_client, address):
    asked = source_of(app_client, no_history)

    assert (await app_client.get(f"/v1/questions/{address}")).status_code == 404
    assert asked == []


async def test_the_chart_is_the_sources_own_week_oldest_first(app_client):
    await discover(moved("7202", slug="charted"))
    asked = source_of(app_client, a_week(points=5, start=0.30, step=0.05))

    body = (await app_client.get("/v1/questions/charted")).json()

    assert body["history_source"] == "source"
    assert [point["yes"] for point in body["history"]] == [
        "0.3000",
        "0.3500",
        "0.4000",
        "0.4500",
        "0.5000",
    ]
    times = [point["at"] for point in body["history"]]
    assert times == sorted(times)
    assert asked[0].url.path.endswith("/prices-history")
    assert asked[0].url.params["market"] == "tok-yes-7202", "the YES token, so the line is YES"


async def test_the_source_is_asked_once_however_often_the_page_is(app_client):
    await discover(moved("7203", slug="popular"))
    asked = source_of(app_client, a_week())

    for _ in range(3):
        assert (await app_client.get("/v1/questions/popular")).status_code == 200

    assert len(asked) == 1


async def test_without_the_source_the_chart_is_this_sites_own_record(app_client):
    await discover(moved("7204", slug="on-our-own"))
    async with db.acquire() as conn:
        market_id = await conn.fetchval("SELECT id FROM markets")
        await conn.execute("DELETE FROM market_price_snapshots")
        await conn.execute(
            """
            INSERT INTO market_price_snapshots (market_id, yes_prob, captured_at)
            VALUES ($1, 0.40, date_trunc('hour', NOW()) - INTERVAL '3 hours'),
                   ($1, 0.42, date_trunc('hour', NOW()) - INTERVAL '170 minutes'),
                   ($1, 0.50, date_trunc('hour', NOW()) - INTERVAL '1 hour'),
                   ($1, 0.10, NOW() - INTERVAL '9 days')
            """,
            market_id,
        )
    asked = source_of(app_client, lambda request: httpx.Response(503, json={"error": "down"}))

    first = (await app_client.get("/v1/questions/on-our-own")).json()
    second = (await app_client.get("/v1/questions/on-our-own")).json()

    assert first["history_source"] == "own"
    # One point an hour, the last price seen in it; nothing older than a week.
    assert [point["yes"] for point in first["history"]] == ["0.4200", "0.5000"]
    assert second["history"] == first["history"]
    assert len(asked) == 1, "an outage is not retried on every page view"


async def test_with_no_history_anywhere_there_is_no_chart_and_still_a_page(app_client):
    await discover(moved("7205", slug="brand-new"))
    async with db.acquire() as conn:
        await conn.execute("DELETE FROM market_price_snapshots")
    source_of(app_client, no_history)

    response = await app_client.get("/v1/questions/brand-new")

    assert response.status_code == 200
    assert response.json()["history"] == []
    assert response.json()["history_source"] == "none"


@pytest.mark.parametrize(
    ("setup", "state", "outcome"),
    [
        ("UPDATE markets SET status = 'LOCKED'", "closed", None),
        ("UPDATE markets SET status = 'SETTLING'", "closed", None),
        (
            "UPDATE markets SET status = 'RESOLVED', resolution = 'YES', resolved_at = NOW()",
            "resolved",
            "yes",
        ),
        (
            "UPDATE markets SET status = 'RESOLVED', resolution = 'NO', resolved_at = NOW()",
            "resolved",
            "no",
        ),
        (
            "UPDATE markets SET status = 'RESOLVED', resolution = 'VOID', resolved_at = NOW()",
            "void",
            None,
        ),
        ("UPDATE markets SET status = 'VOID'", "void", None),
        ("UPDATE markets SET status = 'DRAFT'", "unfollowed", None),
    ],
)
async def test_the_page_says_where_the_question_stands(app_client, setup, state, outcome):
    await discover(moved("7206", slug="whatever-became-of-it"))
    async with db.acquire() as conn:
        await conn.execute(setup)
    source_of(app_client, no_history)

    body = (await app_client.get("/v1/questions/whatever-became-of-it")).json()

    assert (body["state"], body["outcome"]) == (state, outcome)


async def test_two_questions_at_one_address_show_the_one_still_open(app_client):
    await discover(
        moved("7207", slug="shared-address", question="The earlier question?"),
        moved("7208", slug="shared-address", question="The open question?"),
    )
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE markets SET status = 'DRAFT' WHERE question = 'The earlier question?'"
        )
    source_of(app_client, no_history)

    body = (await app_client.get("/v1/questions/shared-address")).json()

    assert body["question"] == "The open question?"


# ----- the list -----------------------------------------------------------------------


async def test_the_list_is_the_questions_worth_sending_a_stranger_to(app_client):
    await discover(
        moved("7301", slug="open-one"),
        moved("7302", slug="resolved-one"),
        moved("7303", slug="cancelled-one"),
        moved("7304", slug="retired-one"),
        moved("7305", slug="Not An Address"),
    )
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE markets SET status = 'RESOLVED', resolution = 'YES', resolved_at = NOW()"
            " WHERE slug = 'resolved-one'"
        )
        await conn.execute(
            "UPDATE markets SET status = 'RESOLVED', resolution = 'VOID', resolved_at = NOW()"
            " WHERE slug = 'cancelled-one'"
        )
        await conn.execute("UPDATE markets SET status = 'DRAFT' WHERE slug = 'retired-one'")

    body = (await app_client.get("/v1/questions")).json()

    assert body["total"] == 2
    assert [(q["slug"], q["state"]) for q in body["questions"]] == [
        ("open-one", "open"),
        ("resolved-one", "resolved"),
    ]
    assert body["questions"][0]["question"] == "Will the Fed cut rates by 25 bps in September?"
    assert body["questions"][0]["category"] == "Macro"


async def test_reading_prices_does_not_reorder_the_list(app_client):
    """The site reads the list a page at a time, and every price read touches
    its question's row. An order that followed that would shift between one
    page and the next, repeating some questions and dropping others."""
    await discover(*(moved(f"73{index:02d}", slug=f"steady-{index}") for index in range(4)))
    before = [q["slug"] for q in (await app_client.get("/v1/questions")).json()["questions"]]

    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE markets SET updated_at = NOW() + INTERVAL '1 hour' WHERE slug = $1",
            before[-1],
        )
    after = [q["slug"] for q in (await app_client.get("/v1/questions")).json()["questions"]]

    assert after == before


async def test_the_list_is_paged(app_client):
    await discover(*(moved(f"74{index:02d}", slug=f"question-{index}") for index in range(5)))

    first = (await app_client.get("/v1/questions", params={"limit": 2})).json()
    rest = (await app_client.get("/v1/questions", params={"limit": 10, "offset": 2})).json()

    assert first["total"] == rest["total"] == 5
    assert len(first["questions"]) == 2
    assert len(rest["questions"]) == 3
    seen = [q["slug"] for q in first["questions"] + rest["questions"]]
    assert sorted(seen) == [f"question-{index}" for index in range(5)]


# ----- the history reader ------------------------------------------------------------


async def test_history_is_read_sorted_and_stripped_of_what_is_not_a_price():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "history": [
                    {"t": 1_800_003_600, "p": 0.52},
                    {"t": 1_800_000_000, "p": 0.5},
                    {"t": "later", "p": 0.9},
                    {"t": 1_800_007_200, "p": 1.7},
                    {"t": 1_800_007_200},
                    "not a point",
                    {"t": 1_800_010_800, "p": "0.61"},
                ]
            },
        )

    async with mock_http_client(handler) as client:
        points = await clob.fetch_price_history(client, "tok", Settings(jwt_secret="y"))

    assert [str(point.probability) for point in points] == ["0.5000", "0.5200", "0.6100"]
    assert [point.at for point in points] == sorted(point.at for point in points)


async def test_an_answer_that_is_not_a_history_is_an_error_not_an_empty_week():
    async with mock_http_client(lambda r: httpx.Response(200, json={"error": "x"})) as client:
        with pytest.raises(clob.PriceUnavailable):
            await clob.fetch_price_history(client, "tok", Settings(jwt_secret="y"))


async def test_a_cached_history_survives_the_round_trip(resources):
    import uuid

    market_id = uuid.uuid4()
    at = datetime.now(UTC).replace(microsecond=0)
    points = [
        clob.PricePoint(at=at - timedelta(hours=1), probability=Decimal("0.4100")),
        clob.PricePoint(at=at, probability=Decimal("0.4300")),
    ]

    assert await history_cache.read(market_id) is None
    await history_cache.write(market_id, points, ttl_seconds=60)
    assert await history_cache.read(market_id) == points

    await history_cache.write(market_id, [], ttl_seconds=60)
    assert await history_cache.read(market_id) == [], "an empty week is a hit, not a miss"

    await price_cache.get_client().set(history_cache.key_for(market_id), json.dumps({"no": 1}))
    assert await history_cache.read(market_id) is None, "something unreadable is a miss"


# ----- configuration -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {"moves_day_threshold": 0},
        {"moves_week_threshold": 1},
        {"moves_decided_margin": 0.5},
        {"moves_min_hours_to_close": -1},
        {"moves_max_age_hours": 0},
        {"moves_price_max_age_seconds": 0},
    ],
)
def test_settings_that_would_report_everything_or_nothing_are_refused(bad):
    with pytest.raises(RuntimeError, match="MOVES_"):
        Settings(jwt_secret="y" * 40, **bad).require_secrets()
