"""A bet too unlikely to be exposure is paid in full.

The payout cap exists so one slip cannot put the house on the hook for an
unbounded amount, and that reasoning holds for outcomes that might happen. It
stops holding somewhere. A payout arriving once in ten thousand attempts is not
exposure — it is a lottery ticket the house is selling — and capping it makes
the ticket worse without making the house safer, because the expected cost of
the bet is stake x (1 - vig)^legs whichever way the notional lands.

Two things are under test: that the waiver keys off the *probability* and not
the odds, and that the liability guard agrees with it. Either one alone leaves
the feature broken — a waived cap whose payout is then refused as "market at
capacity" is not a waiver.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.engine import odds

VIG = Decimal("0.05")
CAP = 20_000_000_000
LOTTERY = Decimal("0.0001")

NO_INSURANCE = odds.InsuranceQuote(
    available=False,
    rate=Decimal(0),
    premium_minor=0,
    covers_failed_legs=0,
    min_legs=4,
    fair_rate=Decimal(0),
)


def leg(prob: str, *, boost: str = "1.0") -> odds.PricedLeg:
    return odds.price_leg(
        market_id="m",
        side="YES",
        raw_yes_prob=Decimal(prob),
        vig_rate=VIG,
        min_prob=Decimal("0.01"),
        max_prob=Decimal("0.99"),
        boost_multiplier=Decimal(boost),
    )


def price(legs, *, stake=100_000, threshold=LOTTERY) -> odds.PricedSlip:
    return odds.price_slip(
        tuple(legs),
        stake_minor=stake,
        payout_cap_minor=CAP,
        max_combined_odds=Decimal(50_000_000),
        insurance=NO_INSURANCE,
        uncapped_below_probability=threshold,
    )


def test_a_one_in_ten_thousand_slip_is_paid_in_full():
    """Five legs at 15%: about one slip in 125,000 wins. The cap would pay a
    fraction of what the odds promised, on a bet that will not land."""
    slip = price([leg("0.15") for _ in range(5)], stake=100_000_000)

    assert slip.true_probability < LOTTERY
    assert slip.uncapped is True
    assert slip.capped is False
    assert slip.potential_payout_minor == slip.gross_payout_minor
    assert slip.potential_payout_minor > CAP


def test_a_likely_slip_is_still_capped():
    """The waiver must not become a way around the cap for bets that can
    actually land."""
    slip = price([leg("0.9") for _ in range(3)], stake=20_000_000_000)

    assert slip.uncapped is False
    assert slip.capped is True
    assert slip.potential_payout_minor == CAP


def test_the_waiver_reads_probability_and_not_odds():
    """The two look interchangeable and are not.

    Odds carry the vig and any boost, so an odds threshold would waive the cap
    on a slip made expensive by a promotion rather than by being unlikely — the
    house handing out an uncapped payout on a bet it expects to lose money on.
    """
    plain = price([leg("0.5") for _ in range(3)])
    boosted = price([leg("0.5", boost="3.0") for _ in range(3)])

    assert boosted.combined_odds > plain.combined_odds * 20
    assert boosted.true_probability == plain.true_probability
    assert boosted.uncapped is False


@pytest.mark.parametrize(
    ("legs", "waived"),
    [
        (["0.15"] * 5, True),
        (["0.4"] * 5, False),
    ],
)
def test_the_band_is_decided_by_the_product_of_the_legs(legs, waived):
    assert price([leg(p) for p in legs], stake=100_000_000).uncapped is waived


def test_a_threshold_of_zero_disables_the_waiver_entirely():
    """So a deployment that does not want this gets the old behaviour rather
    than a waiver that fires on a probability of zero."""
    slip = price([leg("0.05") for _ in range(5)], stake=100_000_000, threshold=Decimal(0))
    assert slip.uncapped is False
    assert slip.potential_payout_minor == min(slip.gross_payout_minor, CAP)


async def test_a_longshot_is_actually_placeable_end_to_end(app_client):
    """The half that would otherwise be silently broken.

    Waiving the cap raises the payout far above `house_seed_minor`, and the
    liability guard refuses anything past that as "market at capacity". A
    waived cap whose payout is then refused is not a waiver — the player still
    cannot make the bet, and the failure arrives as an unrelated message.
    """
    from conftest import authorise
    from test_predictions import body, seed_markets

    markets = await seed_markets(5, probability="0.15")
    headers = await authorise(app_client, telegram_id=606060)

    quote = await app_client.post(
        "/v1/predictions/quote", json=body(markets, stake=100_000), headers=headers
    )
    assert quote.status_code == 200, quote.text
    assert quote.json()["capped"] is False

    placed = await app_client.post(
        "/v1/predictions",
        json=body(markets, stake=100_000),
        headers={**headers, "Idempotency-Key": "longshot-1"},
    )
    assert placed.status_code == 201, placed.text
    assert (
        placed.json()["potential_payout"]["minor"]
        == quote.json()["gross_potential_payout"]["minor"]
    )


async def test_a_realistic_slip_is_still_refused_when_the_market_is_full(app_client):
    """The guard is waived for lottery tickets, not switched off. A bet that
    can actually land is still bounded by what the house will lose on one
    market."""
    from conftest import authorise
    from test_predictions import body, seed_markets

    markets = await seed_markets(3, probability="0.90")
    headers = await authorise(app_client, telegram_id=616161)

    placed = await app_client.post(
        "/v1/predictions",
        json=body(markets, stake=100_000_000),
        headers={**headers, "Idempotency-Key": "fat-1"},
    )
    assert placed.status_code in (400, 402, 409)
    assert placed.json()["code"] in {"market_at_capacity", "insufficient_funds", "stake_too_large"}


async def test_five_legs_at_the_minimum_probability_can_be_placed(app_client):
    """The bet the app used to refuse.

    Five legs at 1% compound to 95^5 = 7.7e9, and the refusal said "combined
    odds exceed the maximum" — which reads as the house declining a bet it
    does not like. It was a column width: combined_odds was NUMERIC(14,6), so
    the value could not be stored and the ceiling existed to fail politely
    rather than at insert.
    """
    from conftest import authorise
    from test_predictions import body, seed_markets

    markets = await seed_markets(5, probability="0.01")
    headers = await authorise(app_client, telegram_id=626262)

    quote = await app_client.post(
        "/v1/predictions/quote", json=body(markets, stake=100_000), headers=headers
    )
    assert quote.status_code == 200, quote.text

    odds = Decimal(quote.json()["combined_odds"])
    assert odds > Decimal(7_000_000_000)
    assert quote.json()["uncapped"] is True

    placed = await app_client.post(
        "/v1/predictions",
        json=body(markets, stake=100_000),
        headers={**headers, "Idempotency-Key": "five-longshots"},
    )
    assert placed.status_code == 201, placed.text
    assert Decimal(placed.json()["combined_odds"]) == odds


def test_the_odds_ceiling_stays_inside_what_a_payout_can_hold():
    """The ceiling is arithmetic safety, not squeamishness.

    gross_potential_payout is BIGINT. Above stake x odds = 9.22e18 a winning
    slip cannot be written down at all, so the ceiling has to sit below that
    at the largest stake the app will take.
    """
    from backend.config import Settings

    shipped = Settings(telegram_bot_token="t", jwt_secret="j" * 40)
    assert shipped.max_stake_minor * shipped.max_combined_odds < 9.22e18

    longest = ((1 - shipped.vig_rate) / shipped.min_prob) ** shipped.max_legs
    assert longest * shipped.parlay_bonus(shipped.max_legs) < shipped.max_combined_odds
