"""Reading an outcome out of a Gamma payload.

Pure-function tests. The bias throughout is that refusing to grade is cheap
and grading wrongly is not: the ledger is append-only, so a mistaken payout
cannot be reversed, only compensated.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from backend.clients.resolution import read_resolution

YES_TOKEN = "tok-yes-1"
NO_TOKEN = "tok-no-1"


def payload(**overrides) -> dict:
    base = {
        "id": "51234",
        "closed": True,
        "clobTokenIds": json.dumps([YES_TOKEN, NO_TOKEN]),
        "outcomePrices": json.dumps(["1", "0"]),
    }
    base.update(overrides)
    return base


def read(**overrides):
    return read_resolution(payload(**overrides), yes_token_id=YES_TOKEN)


def test_a_settled_yes_is_graded_yes():
    result = read(outcomePrices=json.dumps(["1", "0"]))
    assert result.resolution == "YES"
    assert result.yes_price == Decimal("1")


def test_a_settled_no_is_graded_no():
    assert read(outcomePrices=json.dumps(["0", "1"])).resolution == "NO"


def test_a_fifty_fifty_close_is_a_void():
    """Polymarket refunds an invalid market at 50/50."""
    result = read(outcomePrices=json.dumps(["0.5", "0.5"]))
    assert result.resolution == "VOID"


@pytest.mark.parametrize("prices", [["1.0", "0.0"], ["0.995", "0.005"], ["0.99", "0.01"]])
def test_settlement_tolerates_the_forms_the_api_actually_sends(prices):
    assert read(outcomePrices=json.dumps(prices)).resolution == "YES"


def test_prices_arriving_as_a_real_array_are_read_too():
    result = read_resolution(
        payload(clobTokenIds=[YES_TOKEN, NO_TOKEN], outcomePrices=["0", "1"]),
        yes_token_id=YES_TOKEN,
    )
    assert result.resolution == "NO"


def test_a_reversed_token_order_still_grades_the_right_side():
    """`outcomePrices[i]` pairs with `clobTokenIds[i]`, and that order is not
    guaranteed. Reading index 0 as YES would pay every loser on a market whose
    tokens happen to be listed the other way round."""
    result = read_resolution(
        payload(
            clobTokenIds=json.dumps([NO_TOKEN, YES_TOKEN]),
            outcomePrices=json.dumps(["0", "1"]),
        ),
        yes_token_id=YES_TOKEN,
    )
    assert result.resolution == "YES"


def test_a_market_whose_tokens_no_longer_match_is_refused():
    result = read_resolution(
        payload(clobTokenIds=json.dumps(["someone-elses-token", NO_TOKEN])),
        yes_token_id=YES_TOKEN,
    )
    assert result.resolution is None
    assert "YES token" in result.reason


def test_an_open_market_is_not_graded():
    result = read(closed=False)
    assert result.resolution is None
    assert result.reason == "not closed upstream"


@pytest.mark.parametrize("state", ["proposed", "disputed", "challenged", "initialized"])
def test_a_market_still_being_argued_about_is_not_graded(state):
    """Closed is not resolved. A UMA outcome under dispute can still flip."""
    result = read(umaResolutionStatus=state)
    assert result.resolution is None
    assert state in result.reason


def test_an_unrecognised_upstream_state_fails_safe():
    assert read(umaResolutionStatus="something-new-they-added").resolution is None


def test_a_settled_uma_state_is_accepted():
    assert read(umaResolutionStatus="resolved").resolution == "YES"


@pytest.mark.parametrize(
    "prices", [["0.7", "0.3"], ["0.6", "0.4"], ["0.45", "0.55"], ["0.9", "0.1"]]
)
def test_prices_between_settled_and_void_are_not_graded(prices):
    result = read(outcomePrices=json.dumps(prices))
    assert result.resolution is None
    assert "inconclusive" in result.reason


@pytest.mark.parametrize(
    "broken",
    [
        {"clobTokenIds": "not json"},
        {"outcomePrices": "not json"},
        {"outcomePrices": json.dumps(["a", "b"])},
        {"clobTokenIds": json.dumps([YES_TOKEN, NO_TOKEN, "third"])},
        {"outcomePrices": json.dumps(["1"])},
    ],
)
def test_malformed_payloads_are_refused_not_guessed_at(broken):
    assert read(**broken).resolution is None


def test_a_non_object_payload_is_refused():
    assert read_resolution("not an object", yes_token_id=YES_TOKEN).resolution is None
    assert read_resolution(None, yes_token_id=YES_TOKEN).resolution is None


def test_every_refusal_explains_itself():
    """A market stuck pending is a monitoring problem, so the log has to say
    which kind of stuck it is."""
    for reading in [
        read(closed=False),
        read(umaResolutionStatus="disputed"),
        read(outcomePrices=json.dumps(["0.7", "0.3"])),
    ]:
        assert reading.reason
        assert reading.resolution is None
