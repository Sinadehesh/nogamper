"""Unit tests for Gamma normalisation — no network, no database.

This is where Polymarket's loose typing meets our strict schema, so it is
where the interesting failures live.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fixtures import gamma_events as fx

from backend.clients import gamma
from backend.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        telegram_bot_token="x",
        jwt_secret="y",
    )


@pytest.fixture
def stats() -> gamma.DiscoveryStats:
    return gamma.DiscoveryStats()


def normalize(raw, settings, stats):
    return gamma.normalize_event(raw, settings=settings, stats=stats)


def test_normalizes_a_well_formed_macro_event(settings, stats):
    result = normalize(fx.event(), settings, stats)

    assert result is not None
    assert result.category == "Macro"
    assert result.polymarket_event_id == "12345"
    assert len(result.markets) == 1

    market = result.markets[0]
    assert market.yes_token_id == "tok-yes-51234"
    assert market.no_token_id == "tok-no-51234"
    assert market.raw_yes_prob == Decimal("0.62")
    assert market.liquidity_usd == Decimal("45000.0")
    assert stats.markets_kept == 1


def test_lock_at_precedes_end_date_by_the_configured_buffer(settings, stats):
    market = normalize(fx.event(), settings, stats).markets[0]
    assert market.end_date - market.lock_at == timedelta(
        seconds=settings.market_lock_buffer_seconds
    )
    assert market.lock_at < market.end_date


def test_skips_categorical_markets(settings, stats):
    """Three tokens means three outcomes, and our book is binary."""
    result = normalize(fx.event(markets=[fx.CATEGORICAL_MARKET]), settings, stats)

    assert result is None
    assert stats.skips["market_not_binary"] == 1
    assert stats.skips["event_no_usable_markets"] == 1


def test_keeps_the_binary_markets_inside_a_mixed_event(settings, stats):
    result = normalize(
        fx.event(markets=[fx.CATEGORICAL_MARKET, fx.binary_market("60001")]), settings, stats
    )

    assert result is not None
    assert [m.polymarket_market_id for m in result.markets] == ["60001"]
    assert stats.skips["market_not_binary"] == 1


def test_reversed_outcomes_map_tokens_to_the_correct_side(settings, stats):
    """clobTokenIds[i] pairs with outcomes[i]; the order is not guaranteed.

    Assuming index 0 is YES would sell every player the opposite side of the
    bet they thought they placed.
    """
    reversed_market = fx.binary_market(
        "60002",
        outcomes=["No", "Yes"],
        token_ids=["tok-no-60002", "tok-yes-60002"],
        prices=["0.30", "0.70"],
    )
    market = normalize(fx.event(markets=[reversed_market]), settings, stats).markets[0]

    assert market.yes_token_id == "tok-yes-60002"
    assert market.no_token_id == "tok-no-60002"
    assert market.raw_yes_prob == Decimal("0.70")


def test_skips_markets_whose_outcomes_are_not_a_yes_no_pair(settings, stats):
    odd = fx.binary_market("60003", outcomes=["Trump", "Harris"])
    assert normalize(fx.event(markets=[odd]), settings, stats) is None
    assert stats.skips["market_outcomes_not_yes_no"] == 1


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ([{"label": "Macro", "slug": "macro"}], "Macro"),
        ([{"label": "Crypto", "slug": "crypto"}], "Crypto"),
        ([{"label": "Bitcoin", "slug": "bitcoin"}], "Crypto"),
        ([{"label": "Interest Rates", "slug": "interest-rates"}], "Macro"),
        ([{"label": "Politics", "slug": "politics"}], "Politics"),
        ([{"label": "US Politics", "slug": "us-politics"}], "Politics"),
        ([{"label": "Elections", "slug": "elections"}], "Politics"),
        ([{"label": "Geopolitics", "slug": "geopolitics"}], "Politics"),
        ([{"label": "Sports", "slug": "sports"}], None),
        ([], None),
    ],
)
def test_category_is_resolved_from_tags(stats, tags, expected):
    """The alias table, not the default allow-list: Politics resolves here
    under a settings object that wants it, regardless of whether the app's
    own default does."""
    settings = Settings(
        telegram_bot_token="x",
        jwt_secret="y",
        discovery_categories="Macro,Crypto,Politics",
    )
    result = normalize(fx.event(tags=tags), settings, stats)
    assert (result.category if result else None) == expected


def test_category_falls_back_to_the_legacy_field(settings, stats):
    """Older Gamma responses carry `category` instead of `tags`."""
    raw = fx.event(tags=[])
    raw["category"] = "Crypto"
    assert normalize(raw, settings, stats).category == "Crypto"


@pytest.mark.parametrize(
    "tag",
    [
        {"slug": "federal-reserve"},
        {"label": "Federal Reserve"},
        {"label": "federal_reserve"},
        {"label": "  FEDERAL RESERVE  "},
    ],
)
def test_a_tag_matches_in_label_form_or_slug_form(settings, stats, tag):
    """Gamma populates label on some endpoints and slug on others.

    One alias entry has to cover both, or the mapping matches on the endpoint
    it was written against and silently stops matching on the other.
    """
    assert normalize(fx.event(tags=[tag]), settings, stats).category == "Macro"


def test_rejected_tags_are_counted_so_a_renamed_taxonomy_is_visible(settings, stats):
    """An empty market list has two very different causes.

    Either Polymarket genuinely has no macro markets today, or the tag we
    match on was renamed and we are dropping everything. Only the census of
    what we saw and could not place tells those apart.
    """
    events = [
        fx.event("1", tags=[{"label": "Sports", "slug": "sports"}]),
        fx.event("2", tags=[{"label": "Sports", "slug": "sports"}]),
        fx.event("3", tags=[{"label": "Pop Culture", "slug": "pop-culture"}]),
    ]
    list(gamma.normalize_events(events, settings=settings, stats=stats))

    assert stats.events_kept == 0
    assert stats.top_unmatched_tags()["sports"] == 2
    assert stats.top_unmatched_tags()["pop-culture"] == 1


def test_a_tag_counts_once_per_event_not_once_per_spelling(settings, stats):
    """label and slug are the same tag; counting both doubles its weight."""
    list(
        gamma.normalize_events(
            [fx.event("1", tags=[{"label": "Sports", "slug": "sports"}])],
            settings=settings,
            stats=stats,
        )
    )
    assert stats.top_unmatched_tags()["sports"] == 1


def test_a_matched_event_contributes_nothing_to_the_census(settings, stats):
    """Otherwise every kept event's unrelated tags drown out the signal."""
    list(gamma.normalize_events([fx.event("1")], settings=settings, stats=stats))
    assert stats.top_unmatched_tags() == {}


def test_skips_closed_and_archived_events(settings, stats):
    assert normalize(fx.event(closed=True), settings, stats) is None
    assert normalize(fx.event(archived=True), settings, stats) is None
    assert stats.skips["event_closed"] == 2


def test_skips_markets_already_past_their_cutoff(settings, stats):
    expiring = fx.binary_market("60004", end_in_days=0.0001)
    assert normalize(fx.event(markets=[expiring]), settings, stats) is None
    assert stats.skips["market_past_cutoff"] == 1


def test_clamps_extreme_probabilities_into_the_schemas_open_interval(settings, stats):
    """Polymarket reports 0 and 1 on effectively-decided markets; the schema
    rejects both, and 1/0 is not an odds multiplier."""
    certain = fx.binary_market("60005", prices=["1", "0"])
    market = normalize(fx.event(markets=[certain]), settings, stats).markets[0]
    assert market.raw_yes_prob == Decimal(str(settings.max_prob))

    impossible = fx.binary_market("60006", prices=["0", "1"])
    market = normalize(fx.event(markets=[impossible]), settings, stats).markets[0]
    assert market.raw_yes_prob == Decimal(str(settings.min_prob))


@pytest.mark.parametrize(
    "broken",
    [
        {"clobTokenIds": "not json at all"},
        {"clobTokenIds": json.dumps(["only-one"])},
        {"clobTokenIds": json.dumps(["same", "same"])},
        {"clobTokenIds": json.dumps(["", "tok-no"])},
        {"conditionId": ""},
        {"question": ""},
        {"endDate": None},
        {"endDate": "not-a-date"},
    ],
)
def test_unusable_markets_are_skipped_not_crashed_on(settings, stats, broken):
    market = fx.binary_market("60007", **broken)
    assert normalize(fx.event(markets=[market]), settings, stats) is None
    assert sum(stats.skips.values()) >= 1


def test_accepts_arrays_that_arrive_already_parsed(settings, stats):
    """Some Gamma deployments return real arrays rather than JSON strings."""
    market = fx.binary_market("60008")
    market["clobTokenIds"] = ["tok-yes-60008", "tok-no-60008"]
    market["outcomes"] = ["Yes", "No"]
    market["outcomePrices"] = ["0.55", "0.45"]

    normalized = normalize(fx.event(markets=[market]), settings, stats).markets[0]
    assert normalized.yes_token_id == "tok-yes-60008"
    assert normalized.raw_yes_prob == Decimal("0.55")


def test_missing_prices_default_to_even_odds(settings, stats):
    market = fx.binary_market("60009")
    del market["outcomePrices"]
    assert normalize(fx.event(markets=[market]), settings, stats).markets[
        0
    ].raw_yes_prob == Decimal("0.5")


def test_stats_report_every_rejection_by_reason(settings, stats):
    events = [
        fx.event("1"),
        fx.event("2", tags=fx.SPORTS_TAGS),
        fx.event("3", markets=[fx.CATEGORICAL_MARKET]),
    ]
    kept = list(gamma.normalize_events(events, settings=settings, stats=stats))

    assert len(kept) == 1
    assert stats.events_seen == 3
    assert stats.events_kept == 1
    assert stats.skips["event_category_not_wanted"] == 1
    assert stats.skips["market_not_binary"] == 1


def test_naive_timestamps_are_treated_as_utc(settings, stats):
    market = fx.binary_market("60010")
    market["endDate"] = (datetime.now(UTC) + timedelta(days=5)).replace(tzinfo=None).isoformat()
    normalized = normalize(fx.event(markets=[market]), settings, stats).markets[0]
    assert normalized.end_date.tzinfo is not None


def test_politics_is_excluded_by_default(settings, stats):
    """General politics is high-volume noise for this feed, not a category it
    wants — Iran already has its own category and its own priority tag pass,
    independently of this one, so dropping Politics does not touch it.

    Kept as an explicit test rather than left implicit in the parametrised
    cases above: those pass a settings fixture that could be widened without
    anyone noticing the default had changed underneath it.
    """
    assert "Politics" not in settings.discovery_categories

    event = fx.event("p1", tags=[{"label": "US Politics", "slug": "us-politics"}])
    assert normalize(event, settings, stats) is None
    assert stats.skips["event_category_not_wanted"] == 1


def test_a_deployment_can_drop_a_category(stats):
    """DISCOVERY_CATEGORIES is the lever for keeping a topic out of the feed.

    Not a UI filter: an event whose only category is excluded is never
    ingested, so it cannot be reached by a player editing a query string.
    """
    narrowed = Settings(telegram_bot_token="x", jwt_secret="y", discovery_categories="Macro,Crypto")
    assert narrowed.discovery_categories == ["Macro", "Crypto"]

    political = fx.event("p2", tags=[{"label": "Politics", "slug": "politics"}])
    assert normalize(political, narrowed, stats) is None
    assert stats.skips["event_category_not_wanted"] == 1
