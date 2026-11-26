"""The shop: selling points without rebuilding the thing this site is against.

Three properties carry the weight, and most of this file is spent trying to
break them.

**Points are credited because Stripe said so, once.** Not because a browser
came back from a payment page, not for a message nobody signed, not twice for
a message that was delivered twice.

**The limits are limits.** The monthly cap holds against a burst of
simultaneous checkouts and against checkouts left open on purpose. A player's
own limit can be lowered in a moment and cannot be raised in one.

**Closed means closed.** Without a Stripe key nothing is for sale, and the
price list says so rather than leaving it to a missing button.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest
from conftest import (
    TEST_PASSWORD,
    authorise,
    balance_of,
    email_for,
    make_admin,
    mock_http_client,
    user_id_for,
)

from backend import db
from backend.clients import stripe
from backend.config import Settings, get_settings
from backend.repositories import shop as shop_repo

SHOP = "/v1/shop"
CHECKOUT = "/v1/shop/checkout"
LIMIT = "/v1/shop/limit"
WEBHOOK = "/v1/payments/stripe/webhook"

SECRET = "whsec_test_secret_for_signing"
KEY = "sk_test_not_a_real_key"

THOUSAND = 100_000
"""1,000 points in minor units."""


# ----- scaffolding -----------------------------------------------------------


class FakeStripe:
    """Answers checkout-session requests the way Stripe does, and keeps them."""

    def __init__(self, *, status: int = 200) -> None:
        self.status = status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"message": "nope"}})
        number = len(self.requests)
        return httpx.Response(
            200,
            json={
                "id": f"cs_test_{number}",
                "url": f"https://checkout.stripe.com/c/pay/cs_test_{number}",
            },
        )

    def form(self, index: int = -1) -> dict[str, str]:
        parsed = parse_qs(self.requests[index].content.decode())
        return {key: values[0] for key, values in parsed.items()}


@pytest.fixture
def open_shop(app_client):
    """Open the shop for one test, with a fake Stripe behind it."""
    settings = get_settings()
    settings.stripe_secret_key = KEY
    settings.stripe_webhook_secret = SECRET
    settings.site_url = "https://site.test"
    fake = FakeStripe()
    app_client._transport.app.state.http = mock_http_client(fake)
    yield fake
    get_settings.cache_clear()


def signed(event: dict, *, secret: str = SECRET, at: float | None = None) -> tuple[bytes, dict]:
    payload = json.dumps(event).encode()
    timestamp = int(at if at is not None else time.time())
    signature = stripe.sign_payload(payload, secret, timestamp)
    return payload, {
        "Stripe-Signature": f"t={timestamp},v1={signature}",
        "Content-Type": "application/json",
    }


def completed(
    purchase_id: str,
    *,
    amount: int = 200,
    currency: str = "usd",
    payment_status: str = "paid",
    intent: str | None = None,
) -> dict:
    return {
        "id": f"evt_{uuid.uuid4().hex}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_test_{purchase_id[:8]}",
                "object": "checkout.session",
                "payment_status": payment_status,
                "payment_intent": intent or f"pi_{purchase_id[:12]}",
                "amount_total": amount,
                "currency": currency,
                "client_reference_id": purchase_id,
                "metadata": {"purchase_id": purchase_id},
            }
        },
    }


def refunded(intent: str, kind: str = "charge.refunded") -> dict:
    return {
        "id": f"evt_{uuid.uuid4().hex}",
        "type": kind,
        "data": {"object": {"id": "ch_1", "payment_intent": intent, "amount_refunded": 200}},
    }


async def deliver(client, event: dict, **kwargs) -> httpx.Response:
    payload, headers = signed(event, **kwargs)
    return await client.post(WEBHOOK, content=payload, headers=headers)


async def start(client, headers, points: int = 1000, adult: bool = True) -> httpx.Response:
    return await client.post(CHECKOUT, json={"points": points, "adult": adult}, headers=headers)


async def latest_purchase(player: int = 5000):
    async with db.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM point_purchases WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1",
            await user_id_for(player),
        )


async def buy(client, headers, points: int = 1000, player: int = 5000) -> str:
    """Go all the way: checkout, then Stripe's confirmation. Returns the id."""
    response = await start(client, headers, points)
    assert response.status_code == 200, response.text
    row = await latest_purchase(player)
    confirmation = await deliver(client, completed(str(row["id"]), amount=row["amount_cents"]))
    assert confirmation.json()["outcome"] == "credited"
    return str(row["id"])


# ----- the signature ---------------------------------------------------------


def test_a_correctly_signed_message_is_believed():
    payload, headers = signed({"type": "ping"})
    assert stripe.verify_webhook(payload, headers["Stripe-Signature"], SECRET) == {"type": "ping"}


def test_a_message_signed_with_another_secret_is_not():
    payload, headers = signed({"type": "ping"}, secret="whsec_somebody_else")
    with pytest.raises(stripe.SignatureError, match="does not match"):
        stripe.verify_webhook(payload, headers["Stripe-Signature"], SECRET)


def test_a_body_changed_after_signing_is_not():
    payload, headers = signed({"type": "ping", "amount": 200})
    tampered = payload.replace(b"200", b"900")
    with pytest.raises(stripe.SignatureError, match="does not match"):
        stripe.verify_webhook(tampered, headers["Stripe-Signature"], SECRET)


def test_an_old_message_cannot_be_replayed():
    payload, headers = signed({"type": "ping"}, at=time.time() - 3600)
    with pytest.raises(stripe.SignatureError, match="too old"):
        stripe.verify_webhook(payload, headers["Stripe-Signature"], SECRET)


def test_an_old_message_cannot_be_given_a_new_date():
    """The timestamp is inside the signature, so editing it breaks the match."""
    payload, headers = signed({"type": "ping"}, at=time.time() - 3600)
    old = headers["Stripe-Signature"]
    redated = f"t={int(time.time())},{old.split(',', 1)[1]}"
    with pytest.raises(stripe.SignatureError, match="does not match"):
        stripe.verify_webhook(payload, redated, SECRET)


@pytest.mark.parametrize("header", [None, "", "v1=abc", "t=123", "t=soon,v1=abc", "nonsense"])
def test_a_missing_or_malformed_signature_is_refused(header):
    with pytest.raises(stripe.SignatureError):
        stripe.verify_webhook(b"{}", header, SECRET)


def test_either_signature_matches_while_a_secret_is_being_rolled():
    payload = b'{"type":"ping"}'
    now = int(time.time())
    good = stripe.sign_payload(payload, SECRET, now)
    header = f"t={now},v1={'0' * 64},v1={good}"
    assert stripe.verify_webhook(payload, header, SECRET) == {"type": "ping"}


def test_nothing_verifies_against_an_empty_secret():
    """An unset secret must not become "sign with the empty string"."""
    payload, headers = signed({"type": "ping"}, secret="")
    with pytest.raises(stripe.SignatureError, match="no webhook secret"):
        stripe.verify_webhook(payload, headers["Stripe-Signature"], "")


# ----- configuration ---------------------------------------------------------


def _settings(**overrides) -> Settings:
    base = {
        "jwt_secret": "j" * 40,
        "internal_api_key": "k" * 40,
        "stripe_secret_key": KEY,
        "stripe_webhook_secret": SECRET,
        "site_url": "https://site.test",
    }
    return Settings(**{**base, **overrides})


def test_the_shop_is_closed_unless_a_key_says_otherwise():
    settings = Settings(jwt_secret="j" * 40, stripe_secret_key="")
    assert settings.shop_open is False
    assert shop_repo.packs(settings) == []
    settings.require_secrets()


def test_a_key_without_a_webhook_secret_refuses_to_start():
    """It would take money and never be able to credit it."""
    with pytest.raises(RuntimeError, match="STRIPE_WEBHOOK_SECRET"):
        _settings(stripe_webhook_secret="").require_secrets()


def test_production_refuses_a_test_key():
    with pytest.raises(RuntimeError, match="not a live key"):
        _settings(environment="production", cors_origins=["https://site.test"]).require_secrets()
    _settings(
        environment="production",
        cors_origins=["https://site.test"],
        stripe_secret_key="sk_live_" + "x" * 24,
    ).require_secrets()


def test_an_open_shop_needs_somewhere_to_send_people_back_to():
    with pytest.raises(RuntimeError, match="SITE_URL"):
        _settings(site_url="http://insecure.example").require_secrets()


@pytest.mark.parametrize("cap", [0, -5])
def test_the_cap_cannot_be_switched_off(cap):
    with pytest.raises(RuntimeError, match="SHOP_MONTHLY_CAP_CENTS"):
        _settings(shop_monthly_cap_cents=cap).require_secrets()


def test_a_pack_below_stripes_minimum_charge_is_caught_at_startup():
    with pytest.raises(RuntimeError, match="minimum charge"):
        _settings(shop_pack_points=[100]).require_secrets()


def test_a_cap_too_small_to_buy_anything_is_caught_at_startup():
    with pytest.raises(RuntimeError, match="more than the monthly cap"):
        _settings(shop_monthly_cap_cents=100).require_secrets()


def test_no_pack_is_cheaper_per_point_than_another():
    """A discount for buying more is a reason to buy more. There is none."""
    settings = _settings(shop_pack_points="5000, 1000,2500,1000")
    packs = shop_repo.packs(settings)
    assert [p.points for p in packs] == [1000, 2500, 5000]
    rates = {p.price_cents / p.points for p in packs}
    assert len(rates) == 1


# ----- closed ----------------------------------------------------------------


async def test_with_no_key_nothing_is_for_sale(app_client):
    headers = await authorise(app_client)

    listing = (await app_client.get(SHOP, headers=headers)).json()
    assert listing["open"] is False
    assert listing["packs"] == []
    assert listing["mine"]["blocked"] == "shop_closed"

    assert (await app_client.get("/v1/rules")).json()["shop"]["open"] is False

    refused = await start(app_client, headers)
    assert refused.status_code == 404
    assert refused.json()["code"] == "shop_closed"

    payload, signature = signed(completed(str(uuid.uuid4())))
    assert (await app_client.post(WEBHOOK, content=payload, headers=signature)).status_code == 404


# ----- the price list --------------------------------------------------------


async def test_the_price_list_is_public_and_says_what_the_limits_are(app_client, open_shop):
    listing = (await app_client.get(SHOP)).json()

    assert listing["open"] is True
    assert listing["currency"] == "usd"
    assert listing["mine"] is None
    assert [(p["points"]["minor"], p["price_cents"]) for p in listing["packs"]] == [
        (100_000, 200),
        (250_000, 500),
        (500_000, 1000),
    ]
    assert listing["monthly_cap_cents"] == 2000
    assert listing["min_age"] == 18
    assert (await app_client.get("/v1/rules")).json()["shop"] == {
        key: value for key, value in listing.items() if key != "mine"
    }


async def test_a_signed_in_player_sees_where_they_stand(app_client, open_shop):
    headers = await authorise(app_client)
    mine = (await app_client.get(SHOP, headers=headers)).json()["mine"]

    assert mine["spent_month_cents"] == 0
    assert mine["remaining_cents"] == 2000
    assert mine["limit_cents"] is None
    assert mine["blocked"] is None
    assert mine["purchases"] == []
    assert datetime.fromisoformat(mine["resets_at"]) > datetime.now(UTC)


# ----- checkout --------------------------------------------------------------


async def test_checkout_sends_the_buyer_to_stripe_and_credits_nothing(app_client, open_shop):
    headers = await authorise(app_client)
    before = await balance_of()

    response = await start(app_client, headers, 2500)

    assert response.status_code == 200, response.text
    assert response.json()["url"].startswith("https://checkout.stripe.com/")
    assert await balance_of() == before, "points were credited before anybody paid"

    row = await latest_purchase()
    assert (row["status"], row["points"], row["amount_cents"], row["currency"]) == (
        "PENDING",
        250_000,
        500,
        "usd",
    )
    assert row["stripe_session_id"] == "cs_test_1"
    window = row["expires_at"] - row["created_at"]
    assert timedelta(minutes=29) < window <= timedelta(minutes=31)


async def test_what_stripe_is_told(app_client, open_shop):
    headers = await authorise(app_client)
    await start(app_client, headers, 1000)
    row = await latest_purchase()

    request = open_shop.requests[0]
    form = open_shop.form()

    assert str(request.url) == "https://api.stripe.com/v1/checkout/sessions"
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert request.headers["Idempotency-Key"] == f"checkout-{row['id']}"
    assert form["mode"] == "payment"
    assert form["payment_method_types[0]"] == "card"
    assert form["line_items[0][price_data][unit_amount]"] == "200"
    assert form["line_items[0][price_data][currency]"] == "usd"
    assert form["line_items[0][quantity]"] == "1"
    assert form["success_url"] == "https://site.test/play?purchase=done"
    assert form["cancel_url"] == "https://site.test/play?purchase=cancelled"
    assert form["metadata[purchase_id]"] == str(row["id"])
    assert form["client_reference_id"] == str(row["id"])
    assert form["payment_intent_data[metadata][purchase_id]"] == str(row["id"])
    assert "no cash value" in form["line_items[0][price_data][product_data][description]"]
    assert "no cash value" in form["custom_text[submit][message]"]
    assert abs(int(form["expires_at"]) - row["expires_at"].timestamp()) < 2


async def test_nothing_about_the_player_is_sent_to_stripe(app_client, open_shop):
    """Stripe gets a random purchase id. Not who bought it."""
    headers = await authorise(app_client)
    await start(app_client, headers, 1000)

    sent = open_shop.requests[0].content.decode().lower()
    user_id = str(await user_id_for())
    async with db.acquire() as conn:
        code = await conn.fetchval("SELECT player_code FROM users WHERE id = $1", user_id)

    assert email_for(5000).split("@")[0] not in sent
    assert "example.test" not in sent
    assert user_id not in sent
    assert code.lower() not in sent
    assert "player+5000" not in sent and "player%205000" not in sent


async def test_a_guest_must_make_an_account_first(app_client, open_shop):
    guest = await app_client.post("/v1/auth/guest")
    headers = {"Authorization": f"Bearer {guest.json()['access_token']}"}

    assert (await app_client.get(SHOP, headers=headers)).json()["mine"]["blocked"] == (
        "account_required"
    )
    refused = await start(app_client, headers)
    assert refused.status_code == 403
    assert refused.json()["code"] == "account_required"
    assert open_shop.requests == []


async def test_the_buyer_must_say_they_are_an_adult(app_client, open_shop):
    headers = await authorise(app_client)

    refused = await start(app_client, headers, adult=False)
    assert refused.status_code == 422
    assert refused.json()["code"] == "age_required"

    silent = await app_client.post(CHECKOUT, json={"points": 1000}, headers=headers)
    assert silent.json()["code"] == "age_required"
    assert open_shop.requests == []


async def test_only_the_packs_on_the_list_can_be_bought(app_client, open_shop):
    headers = await authorise(app_client)

    refused = await start(app_client, headers, 999_999)
    assert refused.status_code == 422
    assert refused.json()["code"] == "unknown_pack"
    assert open_shop.requests == []


async def test_a_break_closes_the_shop_as_well_as_the_game(app_client, open_shop):
    headers = await authorise(app_client)
    await app_client.post("/v1/me/break", json={"hours": 24}, headers=headers)

    mine = (await app_client.get(SHOP, headers=headers)).json()["mine"]
    assert mine["blocked"] == "on_break"
    assert mine["blocked_until"] is not None

    refused = await start(app_client, headers)
    assert refused.status_code == 409
    assert refused.json()["code"] == "on_break"
    assert refused.json()["until"] is not None
    assert open_shop.requests == []


async def test_a_restricted_account_cannot_buy(app_client, open_shop):
    headers = await authorise(app_client)
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE users SET status = 'RESTRICTED' WHERE id = $1", await user_id_for()
        )

    refused = await start(app_client, headers)
    assert refused.status_code == 403
    assert refused.json()["code"] == "account_restricted"


async def test_if_stripe_is_down_nothing_is_charged_and_nothing_counts(app_client, open_shop):
    headers = await authorise(app_client)
    open_shop.status = 503

    failed = await start(app_client, headers)

    assert failed.status_code == 502
    assert failed.json()["code"] == "payment_unavailable"
    assert (await latest_purchase())["status"] == "EXPIRED"
    mine = (await app_client.get(SHOP, headers=headers)).json()["mine"]
    assert mine["pending_cents"] == 0
    assert mine["remaining_cents"] == 2000


async def test_the_key_never_appears_in_an_error(app_client, open_shop):
    headers = await authorise(app_client)
    open_shop.status = 401

    failed = await start(app_client, headers)

    assert KEY not in failed.text


# ----- Stripe's confirmation -------------------------------------------------


async def test_a_confirmed_payment_is_credited(app_client, open_shop):
    headers = await authorise(app_client)
    before = await balance_of()

    purchase_id = await buy(app_client, headers, 1000)

    assert await balance_of() == before + THOUSAND
    row = await latest_purchase()
    assert row["status"] == "PAID"
    assert row["paid_at"] is not None
    assert row["stripe_payment_intent"] == f"pi_{purchase_id[:12]}"
    async with db.acquire() as conn:
        entry = await conn.fetchrow(
            "SELECT entry_type, amount, ref_type, metadata FROM ledger_entries WHERE ref_id = $1",
            row["id"],
        )
    assert (entry["entry_type"], entry["amount"], entry["ref_type"]) == (
        "POINTS_PURCHASE_CREDIT",
        THOUSAND,
        "POINT_PURCHASE",
    )
    assert json.loads(entry["metadata"]) == {"amount_cents": 200, "currency": "usd"}

    mine = (await app_client.get(SHOP, headers=headers)).json()["mine"]
    assert mine["spent_month_cents"] == 200
    assert mine["spent_all_cents"] == 200
    assert mine["remaining_cents"] == 1800
    assert [(p["status"], p["amount_cents"], p["points"]["minor"]) for p in mine["purchases"]] == [
        ("PAID", 200, THOUSAND)
    ]


async def test_a_message_delivered_twice_credits_once(app_client, open_shop):
    headers = await authorise(app_client)
    await start(app_client, headers)
    row = await latest_purchase()
    event = completed(str(row["id"]))

    first = await deliver(app_client, event)
    balance = await balance_of()
    second = await deliver(app_client, event)
    third = await deliver(app_client, completed(str(row["id"])))  # a fresh event, same purchase

    assert first.json()["outcome"] == "credited"
    assert second.status_code == third.status_code == 200
    assert second.json()["outcome"] == third.json()["outcome"] == "already_credited"
    assert await balance_of() == balance


async def test_simultaneous_deliveries_credit_once(app_client, open_shop):
    headers = await authorise(app_client)
    before = await balance_of()
    await start(app_client, headers)
    row = await latest_purchase()

    answers = await asyncio.gather(
        *(deliver(app_client, completed(str(row["id"]))) for _ in range(6))
    )

    outcomes = sorted(a.json()["outcome"] for a in answers)
    assert outcomes == ["already_credited"] * 5 + ["credited"]
    assert await balance_of() == before + THOUSAND


async def test_coming_back_from_the_payment_page_credits_nothing(app_client, open_shop):
    """The success address is only an address. Anyone can open it."""
    headers = await authorise(app_client)
    before = await balance_of()
    await start(app_client, headers)

    await app_client.get(SHOP, headers=headers)
    await app_client.get("/v1/me", headers=headers)

    assert await balance_of() == before
    assert (await latest_purchase())["status"] == "PENDING"


@pytest.mark.parametrize(
    "headers_for",
    [
        lambda payload: {},
        lambda payload: {"Stripe-Signature": "t=1,v1=deadbeef"},
        lambda payload: {
            "Stripe-Signature": (
                f"t={int(time.time())},"
                f"v1={stripe.sign_payload(payload, 'whsec_wrong', int(time.time()))}"
            )
        },
    ],
    ids=["unsigned", "garbage", "wrong-secret"],
)
async def test_a_message_nobody_signed_credits_nothing(app_client, open_shop, headers_for):
    headers = await authorise(app_client)
    before = await balance_of()
    await start(app_client, headers)
    row = await latest_purchase()
    payload = json.dumps(completed(str(row["id"]))).encode()

    answer = await app_client.post(WEBHOOK, content=payload, headers=headers_for(payload))

    assert answer.status_code == 400
    assert answer.json()["code"] == "bad_signature"
    assert await balance_of() == before
    assert (await latest_purchase())["status"] == "PENDING"


async def test_a_stale_signed_message_credits_nothing(app_client, open_shop):
    headers = await authorise(app_client)
    before = await balance_of()
    await start(app_client, headers)
    row = await latest_purchase()

    answer = await deliver(app_client, completed(str(row["id"])), at=time.time() - 3600)

    assert answer.status_code == 400
    assert await balance_of() == before


@pytest.mark.parametrize(
    "overrides", [{"amount": 1}, {"amount": 20000}, {"currency": "eur"}], ids=str
)
async def test_a_payment_for_the_wrong_amount_is_not_credited(app_client, open_shop, overrides):
    headers = await authorise(app_client)
    before = await balance_of()
    await start(app_client, headers)
    row = await latest_purchase()

    answer = await deliver(app_client, completed(str(row["id"]), **overrides))

    assert answer.status_code == 200
    assert answer.json()["outcome"] == "mismatch"
    assert await balance_of() == before
    assert (await latest_purchase())["status"] == "PENDING"


async def test_a_session_that_completed_unpaid_is_not_credited(app_client, open_shop):
    headers = await authorise(app_client)
    before = await balance_of()
    await start(app_client, headers)
    row = await latest_purchase()

    answer = await deliver(app_client, completed(str(row["id"]), payment_status="unpaid"))

    assert answer.json()["outcome"] == "not_paid"
    assert await balance_of() == before


async def test_payments_that_are_not_ours_are_acknowledged_and_ignored(app_client, open_shop):
    """A donation on the same Stripe account arrives here too."""
    await authorise(app_client)
    before = await balance_of()

    donation = completed(str(uuid.uuid4()))
    donation["data"]["object"]["metadata"] = {}
    donation["data"]["object"]["client_reference_id"] = None
    stranger = completed(str(uuid.uuid4()))
    other = {"id": "evt_1", "type": "customer.created", "data": {"object": {"id": "cus_1"}}}

    for event, expected in ((donation, "ignored"), (stranger, "unknown"), (other, "ignored")):
        answer = await deliver(app_client, event)
        assert answer.status_code == 200
        assert answer.json()["outcome"] == expected
    assert await balance_of() == before


async def test_a_lapsed_checkout_stops_counting(app_client, open_shop):
    headers = await authorise(app_client)
    await start(app_client, headers, 5000)
    row = await latest_purchase()
    assert (await app_client.get(SHOP, headers=headers)).json()["mine"]["pending_cents"] == 1000

    expired = {
        "id": "evt_x",
        "type": "checkout.session.expired",
        "data": {"object": {"id": "cs_1", "metadata": {"purchase_id": str(row["id"])}}},
    }
    assert (await deliver(app_client, expired)).json()["outcome"] == "expired"

    assert (await latest_purchase())["status"] == "EXPIRED"
    mine = (await app_client.get(SHOP, headers=headers)).json()["mine"]
    assert (mine["pending_cents"], mine["remaining_cents"]) == (0, 2000)


async def test_money_that_arrives_after_a_checkout_lapsed_is_still_honoured(app_client, open_shop):
    headers = await authorise(app_client)
    before = await balance_of()
    await start(app_client, headers)
    row = await latest_purchase()
    async with db.acquire() as conn:
        await shop_repo.expire(conn, purchase_id=row["id"])

    answer = await deliver(app_client, completed(str(row["id"])))

    assert answer.json()["outcome"] == "credited"
    assert await balance_of() == before + THOUSAND


# ----- the monthly cap -------------------------------------------------------


async def test_the_cap_is_a_cap(app_client, open_shop):
    headers = await authorise(app_client)
    await buy(app_client, headers, 5000)  # 10.00
    await buy(app_client, headers, 2500)  #  5.00
    await buy(app_client, headers, 2500)  #  5.00 → 20.00, the cap

    mine = (await app_client.get(SHOP, headers=headers)).json()["mine"]
    assert mine["spent_month_cents"] == 2000
    assert mine["remaining_cents"] == 0
    assert mine["blocked"] == "spend_limit_reached"

    calls = len(open_shop.requests)
    refused = await start(app_client, headers, 1000)
    assert refused.status_code == 409
    assert refused.json()["code"] == "spend_limit_reached"
    assert datetime.fromisoformat(refused.json()["until"]) > datetime.now(UTC)
    assert len(open_shop.requests) == calls, "Stripe was asked for a checkout past the cap"


async def test_a_pack_that_would_cross_the_cap_is_refused_and_a_smaller_one_is_not(
    app_client, open_shop
):
    headers = await authorise(app_client)
    await buy(app_client, headers, 5000)
    await buy(app_client, headers, 2500)
    await buy(app_client, headers, 1000)  # 17.00 spent, 3.00 left

    too_big = await start(app_client, headers, 2500)
    assert too_big.status_code == 409
    assert too_big.json()["code"] == "spend_limit_reached"

    assert (await start(app_client, headers, 1000)).status_code == 200


async def test_open_checkouts_count_so_the_cap_cannot_be_stepped_over(app_client, open_shop):
    headers = await authorise(app_client)
    for _ in range(2):
        assert (await start(app_client, headers, 5000)).status_code == 200

    refused = await start(app_client, headers, 1000)
    assert refused.status_code == 409
    assert refused.json()["code"] == "spend_limit_reached"

    # …and stop counting once they have lapsed on their own, with no word from Stripe.
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE point_purchases SET created_at = NOW() - INTERVAL '2 hours', "
            "expires_at = NOW() - INTERVAL '1 hour'"
        )
    assert (await start(app_client, headers, 1000)).status_code == 200


async def test_a_burst_of_checkouts_cannot_race_past_the_cap(app_client, open_shop):
    headers = await authorise(app_client)

    answers = await asyncio.gather(*(start(app_client, headers, 5000) for _ in range(8)))

    assert sorted(a.status_code for a in answers) == [200, 200] + [409] * 6
    async with db.acquire() as conn:
        committed = await conn.fetchval(
            "SELECT SUM(amount_cents) FROM point_purchases WHERE status = 'PENDING'"
        )
    assert committed == 2000


async def test_the_cap_is_per_calendar_month(app_client, open_shop):
    headers = await authorise(app_client)
    for _ in range(2):
        await buy(app_client, headers, 5000)
    assert (await start(app_client, headers, 1000)).status_code == 409

    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE point_purchases SET created_at = created_at - INTERVAL '40 days', "
            "expires_at = expires_at - INTERVAL '40 days', paid_at = paid_at - INTERVAL '40 days'"
        )

    mine = (await app_client.get(SHOP, headers=headers)).json()["mine"]
    assert mine["spent_month_cents"] == 0
    assert mine["spent_all_cents"] == 2000, "last month still happened"
    assert (await start(app_client, headers, 1000)).status_code == 200


async def test_one_players_spending_is_not_anothers(app_client, open_shop):
    first = await authorise(app_client, 5000)
    second = await authorise(app_client, 5001)
    for _ in range(2):
        await buy(app_client, first, 5000, player=5000)

    assert (await start(app_client, second, 5000)).status_code == 200
    assert (await app_client.get(SHOP, headers=second)).json()["mine"]["spent_month_cents"] == 0


def test_a_month_ends_when_the_economys_calendar_says_so():
    settings = Settings(jwt_secret="j" * 40, economy_timezone="Pacific/Auckland")
    late_on_the_31st_utc = datetime(2026, 1, 31, 12, 0, tzinfo=UTC)  # already 1 Feb in Auckland

    start_of_month, following = shop_repo.month_bounds(settings, late_on_the_31st_utc)

    assert (start_of_month.month, following.month) == (2, 3)
    assert start_of_month.utcoffset() is not None

    december = shop_repo.month_bounds(
        Settings(jwt_secret="j" * 40), datetime(2026, 12, 15, tzinfo=UTC)
    )
    assert (december[0].year, december[1].year, december[1].month) == (2026, 2027, 1)


# ----- a player's own limit --------------------------------------------------


async def test_a_player_can_set_a_limit_below_the_cap(app_client, open_shop):
    headers = await authorise(app_client)

    saved = await app_client.put(LIMIT, json={"limit_cents": 500}, headers=headers)

    assert saved.status_code == 200
    mine = saved.json()["mine"]
    assert (mine["limit_cents"], mine["remaining_cents"]) == (500, 500)
    assert mine["limit_loosen_at"] is not None

    assert (await start(app_client, headers, 5000)).status_code == 409
    assert (await start(app_client, headers, 2500)).status_code == 200


async def test_a_limit_of_zero_closes_the_shop_for_that_player(app_client, open_shop):
    headers = await authorise(app_client)
    await app_client.put(LIMIT, json={"limit_cents": 0}, headers=headers)

    mine = (await app_client.get(SHOP, headers=headers)).json()["mine"]
    assert mine["blocked"] == "shop_closed_by_you"
    assert mine["remaining_cents"] == 0

    refused = await start(app_client, headers, 1000)
    assert refused.status_code == 409
    assert refused.json()["code"] == "shop_closed_by_you"
    assert open_shop.requests == []


async def test_a_limit_can_be_lowered_at_once_but_not_raised(app_client, open_shop):
    headers = await authorise(app_client)
    await app_client.put(LIMIT, json={"limit_cents": 1000}, headers=headers)

    lowered = await app_client.put(LIMIT, json={"limit_cents": 400}, headers=headers)
    assert lowered.status_code == 200
    assert lowered.json()["mine"]["limit_cents"] == 400

    for looser in (1000, 401, None):
        raised = await app_client.put(LIMIT, json={"limit_cents": looser}, headers=headers)
        assert raised.status_code == 409, f"loosened to {looser!r} at once"
        assert raised.json()["code"] == "limit_locked"
        assert datetime.fromisoformat(raised.json()["until"]) > datetime.now(UTC)

    assert (await app_client.get(SHOP, headers=headers)).json()["mine"]["limit_cents"] == 400


async def test_a_limit_can_be_raised_once_it_has_stood_for_a_day(app_client, open_shop):
    headers = await authorise(app_client)
    await app_client.put(LIMIT, json={"limit_cents": 0}, headers=headers)
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE users SET spend_limit_set_at = NOW() - INTERVAL '25 hours' WHERE id = $1",
            await user_id_for(),
        )

    raised = await app_client.put(LIMIT, json={"limit_cents": None}, headers=headers)

    assert raised.status_code == 200
    mine = raised.json()["mine"]
    assert (mine["limit_cents"], mine["blocked"], mine["remaining_cents"]) == (None, None, 2000)


async def test_saving_the_same_limit_does_not_restart_the_wait(app_client, open_shop):
    headers = await authorise(app_client)
    first = await app_client.put(LIMIT, json={"limit_cents": 300}, headers=headers)
    await asyncio.sleep(0.05)
    again = await app_client.put(LIMIT, json={"limit_cents": 300}, headers=headers)

    assert again.json()["mine"]["limit_loosen_at"] == first.json()["mine"]["limit_loosen_at"]


@pytest.mark.parametrize("limit", [2001, 1_000_000])
async def test_a_limit_above_the_cap_means_nothing_and_is_refused(app_client, open_shop, limit):
    headers = await authorise(app_client)

    refused = await app_client.put(LIMIT, json={"limit_cents": limit}, headers=headers)

    assert refused.status_code == 422
    assert refused.json()["code"] == "limit_out_of_range"


async def test_a_limit_can_be_set_before_the_shop_ever_opens(app_client):
    headers = await authorise(app_client)

    saved = await app_client.put(LIMIT, json={"limit_cents": 0}, headers=headers)

    assert saved.status_code == 200
    assert saved.json()["mine"]["limit_cents"] == 0


async def test_the_limit_needs_a_session(app_client, open_shop):
    assert (await app_client.put(LIMIT, json={"limit_cents": 0})).status_code == 401
    unsigned = await app_client.post(CHECKOUT, json={"points": 1000, "adult": True})
    assert unsigned.status_code == 401


# ----- refunds ---------------------------------------------------------------


async def test_a_refund_takes_the_points_back(app_client, open_shop):
    headers = await authorise(app_client)
    before = await balance_of()
    purchase_id = await buy(app_client, headers, 1000)
    intent = f"pi_{purchase_id[:12]}"

    answer = await deliver(app_client, refunded(intent))

    assert answer.json()["outcome"] == "refunded"
    assert await balance_of() == before
    row = await latest_purchase()
    assert (row["status"], row["clawed_back"]) == ("REFUNDED", THOUSAND)
    assert row["refunded_at"] is not None

    mine = (await app_client.get(SHOP, headers=headers)).json()["mine"]
    assert mine["spent_month_cents"] == 0, "refunded money is not money spent"
    assert mine["purchases"][0]["status"] == "REFUNDED"

    again = await deliver(app_client, refunded(intent))
    assert again.json()["outcome"] == "already_refunded"
    assert await balance_of() == before


async def test_a_dispute_is_treated_as_a_refund(app_client, open_shop):
    headers = await authorise(app_client)
    before = await balance_of()
    purchase_id = await buy(app_client, headers, 1000)

    answer = await deliver(app_client, refunded(f"pi_{purchase_id[:12]}", "charge.dispute.created"))

    assert answer.json()["outcome"] == "refunded"
    assert await balance_of() == before


async def test_a_refund_cannot_take_a_balance_below_zero(app_client, open_shop):
    headers = await authorise(app_client)
    purchase_id = await buy(app_client, headers, 1000)
    user_id = await user_id_for()
    async with db.acquire() as conn:
        balance = await conn.fetchval("SELECT coin_balance FROM users WHERE id = $1", user_id)
        await conn.execute(
            "INSERT INTO ledger_entries (user_id, entry_type, amount, idempotency_key) "
            "VALUES ($1, 'ADMIN_ADJUSTMENT', $2, 'spent-most-of-it')",
            user_id,
            -(balance - 30_000),
        )

    answer = await deliver(app_client, refunded(f"pi_{purchase_id[:12]}"))

    assert answer.json()["outcome"] == "refunded"
    assert await balance_of() == 0
    assert (await latest_purchase())["clawed_back"] == 30_000


async def test_a_refund_with_nothing_left_to_take_still_closes_the_purchase(app_client, open_shop):
    headers = await authorise(app_client)
    purchase_id = await buy(app_client, headers, 1000)
    user_id = await user_id_for()
    async with db.acquire() as conn:
        balance = await conn.fetchval("SELECT coin_balance FROM users WHERE id = $1", user_id)
        await conn.execute(
            "INSERT INTO ledger_entries (user_id, entry_type, amount, idempotency_key) "
            "VALUES ($1, 'ADMIN_ADJUSTMENT', $2, 'spent-all-of-it')",
            user_id,
            -balance,
        )

    answer = await deliver(app_client, refunded(f"pi_{purchase_id[:12]}"))

    assert answer.json()["outcome"] == "refunded"
    row = await latest_purchase()
    assert (row["status"], row["clawed_back"]) == ("REFUNDED", 0)


async def test_a_refund_for_a_payment_that_is_not_ours_is_ignored(app_client, open_shop):
    answer = await deliver(app_client, refunded("pi_somebody_elses_payment"))

    assert answer.status_code == 200
    assert answer.json()["outcome"] == "ignored"


# ----- everything else stays as it was ---------------------------------------


async def test_bought_points_do_not_lift_the_daily_limit(app_client, open_shop):
    """Paying buys a bigger balance. It does not buy a way round a brake."""
    headers = await authorise(app_client)
    await app_client.put("/v1/me/limits", json={"daily_limit_minor": 10_000}, headers=headers)

    await buy(app_client, headers, 5000)

    limits = (await app_client.get("/v1/me/limits", headers=headers)).json()
    assert limits["daily_limit"]["minor"] == 10_000


async def test_erasing_an_account_keeps_the_record_of_what_was_paid(app_client, open_shop):
    headers = await authorise(app_client)
    await buy(app_client, headers, 1000)
    user_id = await user_id_for()

    erased = await app_client.post(
        "/v1/me/erase", json={"password": TEST_PASSWORD}, headers=headers
    )

    assert erased.status_code == 204
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, amount_cents FROM point_purchases WHERE user_id = $1", user_id
        )
        email = await conn.fetchval("SELECT email FROM users WHERE id = $1", user_id)
    assert (row["status"], row["amount_cents"]) == ("PAID", 200)
    assert email is None, "the account was not actually erased"


async def test_the_operator_sees_bought_points_net_of_refunds(app_client, open_shop):
    """Points bought are their own line, so the books add up without Stripe open."""
    admin = await make_admin(app_client)
    buyer = await authorise(app_client)
    first = await buy(app_client, buyer, 1000)
    await buy(app_client, buyer, 2500)
    await deliver(app_client, refunded(f"pi_{first[:12]}"))

    overview = (await app_client.get("/v1/admin/overview", headers=admin)).json()

    assert overview["points"]["bought"]["minor"] == 250_000
    granted = overview["points"]["granted"]["minor"]
    assert granted == 2 * 100_000, "bought points were counted as granted free"
