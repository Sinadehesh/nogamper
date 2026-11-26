"""Telegram Stars: invoicing, the webhook handshake, settlement, refunds.

This is the only path by which value enters the system, so the tests lean
hard on the failure modes: spoofed webhooks, redelivered payments, tampered
payloads, amounts that do not match, and refunds after the coins are gone.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from conftest import TEST_BOT_TOKEN, TEST_WEBHOOK_SECRET, authorise

from backend import db

WEBHOOK = "/v1/payments/webhook"
SECRET_HEADER = {"X-Telegram-Bot-Api-Secret-Token": TEST_WEBHOOK_SECRET}


async def pack_coins(code: str = "TIER_1") -> int:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT coins, bonus_coins FROM coin_packages WHERE code = $1", code
        )
    return int(row["coins"]) + int(row["bonus_coins"])


class FakeBotApi:
    """Stands in for api.telegram.org, and records what we sent it."""

    def __init__(self, *, invoice_link: str = "https://t.me/$FakeInvoiceLink") -> None:
        self.invoice_link = invoice_link
        self.calls: list[tuple[str, dict]] = []
        self.urls: list[str] = []
        self.fail_method: str | None = None
        self.failure = {"ok": False, "error_code": 400, "description": "BAD_REQUEST"}

    def handler(self, request: httpx.Request) -> httpx.Response:
        import json

        method = str(request.url).rsplit("/", 1)[-1]
        body = json.loads(request.content or b"{}")
        self.calls.append((method, body))
        self.urls.append(str(request.url))

        if self.fail_method == method:
            return httpx.Response(200, json=self.failure)
        if method == "createInvoiceLink":
            return httpx.Response(200, json={"ok": True, "result": self.invoice_link})
        return httpx.Response(200, json={"ok": True, "result": True})

    def sent(self, method: str) -> list[dict]:
        return [body for name, body in self.calls if name == method]


@pytest.fixture
def bot_api(app_client) -> FakeBotApi:
    """Point the app's shared HTTP client at a fake Bot API."""
    fake = FakeBotApi()
    app = app_client._transport.app  # type: ignore[attr-defined]
    app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    return fake


async def buy(app_client, auth, package="TIER_1"):
    return await app_client.post(
        "/v1/payments/invoices", json={"package_code": package}, headers=auth
    )


async def purchase_row(payload_or_id=None):
    async with db.acquire() as conn:
        if payload_or_id is None:
            return dict(await conn.fetchrow("SELECT * FROM star_purchases LIMIT 1"))
        return dict(
            await conn.fetchrow(
                "SELECT * FROM star_purchases WHERE invoice_payload = $1", payload_or_id
            )
        )


async def balance(telegram_id: int = 5000) -> int:
    async with db.acquire() as conn:
        return await conn.fetchval(
            "SELECT coin_balance FROM users WHERE telegram_id = $1", telegram_id
        )


def payment_update(
    payload: str,
    *,
    update_id: int = 1,
    charge: str = "tg_charge_1",
    amount: int = 50,
    currency: str = "XTR",
    telegram_id: int = 5000,
) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 10,
            "from": {"id": telegram_id, "first_name": "Ada"},
            "chat": {"id": telegram_id, "type": "private"},
            "date": 1787500000,
            "successful_payment": {
                "currency": currency,
                "total_amount": amount,
                "invoice_payload": payload,
                "telegram_payment_charge_id": charge,
                "provider_payment_charge_id": "pp_1",
            },
        },
    }


def pre_checkout_update(
    payload: str,
    *,
    update_id: int = 2,
    amount: int = 50,
    currency: str = "XTR",
    query_id: str = "pcq_1",
) -> dict:
    return {
        "update_id": update_id,
        "pre_checkout_query": {
            "id": query_id,
            "from": {"id": 5000, "first_name": "Ada"},
            "currency": currency,
            "total_amount": amount,
            "invoice_payload": payload,
        },
    }


async def test_an_invoice_is_created_in_stars_against_a_pending_purchase(app_client, bot_api):
    auth = await authorise(app_client)
    response = await buy(app_client, auth)

    assert response.status_code == 201
    body = response.json()
    assert body["invoice_link"] == bot_api.invoice_link
    assert body["stars"] == 50

    async with db.acquire() as conn:
        pack = await conn.fetchrow(
            "SELECT title, coins, bonus_coins FROM coin_packages WHERE code = 'TIER_1'"
        )
    coins = int(pack["coins"]) + int(pack["bonus_coins"])
    assert body["coins"]["minor"] == coins

    sent = bot_api.sent("createInvoiceLink")[0]
    assert sent["currency"] == "XTR"
    assert sent["prices"] == [{"label": pack["title"], "amount": 50}]
    assert sent["provider_token"] == ""

    row = await purchase_row()
    assert row["status"] == "PENDING"
    assert row["stars_amount"] == 50
    assert row["coins_amount"] == coins


async def test_the_payload_is_a_nonce_and_never_the_user_id(app_client, bot_api):
    """Telegram hands the payload back on the webhook. Anything that arrives
    from outside is input, not identity."""
    auth = await authorise(app_client, telegram_id=7777)
    await buy(app_client, auth)

    payload = bot_api.sent("createInvoiceLink")[0]["payload"]
    row = await purchase_row()

    assert payload == row["invoice_payload"]
    assert len(payload) >= 40
    assert "7777" not in payload
    assert str(row["user_id"]) not in payload


async def test_bonus_coins_are_included_in_what_is_credited(app_client, bot_api):
    auth = await authorise(app_client)
    body = (await buy(app_client, auth, package="TIER_2")).json()

    assert body["coins"]["minor"] == await pack_coins("TIER_2")


async def test_an_unknown_package_is_refused(app_client, bot_api):
    auth = await authorise(app_client)
    response = await buy(app_client, auth, package="TIER_NOPE")

    assert response.status_code == 404
    assert response.json()["code"] == "unknown_package"


async def test_a_telegram_refusal_leaves_no_orphan_purchase_row(app_client, bot_api):
    """The row and the Bot API call share a transaction: no invoice, no row
    eating the player's open-invoice allowance."""
    bot_api.fail_method = "createInvoiceLink"
    auth = await authorise(app_client)

    response = await buy(app_client, auth)
    assert response.status_code == 502
    assert response.json()["code"] == "invoice_unavailable"

    async with db.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM star_purchases") == 0


async def test_the_bot_token_never_reaches_a_client_facing_error(app_client, bot_api):
    bot_api.fail_method = "createInvoiceLink"
    auth = await authorise(app_client)

    raw = (await buy(app_client, auth)).text
    assert TEST_BOT_TOKEN not in raw
    assert "api.telegram.org" not in raw


async def test_open_invoices_are_capped_per_player(app_client, bot_api):
    auth = await authorise(app_client)
    for _ in range(5):
        assert (await buy(app_client, auth)).status_code == 201

    sixth = await buy(app_client, auth)
    assert sixth.status_code == 429
    assert sixth.json()["code"] == "too_many_open_invoices"


async def test_creating_an_invoice_requires_authentication(app_client):
    assert (
        await app_client.post("/v1/payments/invoices", json={"package_code": "TIER_1"})
    ).status_code == 401


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Telegram-Bot-Api-Secret-Token": ""},
        {"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        {"X-Telegram-Bot-Api-Secret-Token": TEST_WEBHOOK_SECRET + "x"},
    ],
)
async def test_a_webhook_without_the_right_secret_is_refused(app_client, headers):
    response = await app_client.post(WEBHOOK, json={"update_id": 1}, headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "bad_secret"


async def test_a_spoofed_payment_credits_nothing(app_client, bot_api):
    """The whole point of the secret: anyone who finds this URL must not be
    able to mint coins."""
    auth = await authorise(app_client)
    await buy(app_client, auth)
    row = await purchase_row()

    spoof = await app_client.post(WEBHOOK, json=payment_update(row["invoice_payload"]))

    assert spoof.status_code == 403
    assert await balance() == 100_000
    assert (await purchase_row())["status"] == "PENDING"


async def test_malformed_bodies_are_rejected_without_crashing(app_client):
    assert (
        await app_client.post(WEBHOOK, content=b"not json", headers=SECRET_HEADER)
    ).status_code == 400
    assert (
        await app_client.post(WEBHOOK, json={"no": "update_id"}, headers=SECRET_HEADER)
    ).status_code == 400


async def test_an_update_type_we_do_not_handle_is_acknowledged_and_ignored(app_client):
    """Anything but a 2xx makes Telegram redeliver forever."""
    response = await app_client.post(
        WEBHOOK,
        json={"update_id": 99, "message": {"message_id": 1, "text": "hello"}},
        headers=SECRET_HEADER,
    )
    assert response.status_code == 200

    async with db.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM telegram_updates WHERE update_id = 99")
    assert row["update_type"] == "ignored"
    assert row["processed_at"] is not None


async def test_a_valid_pre_checkout_is_accepted(app_client, bot_api):
    auth = await authorise(app_client)
    await buy(app_client, auth)
    row = await purchase_row()

    response = await app_client.post(
        WEBHOOK, json=pre_checkout_update(row["invoice_payload"]), headers=SECRET_HEADER
    )

    assert response.status_code == 200
    answer = bot_api.sent("answerPreCheckoutQuery")[0]
    assert answer["ok"] is True
    assert answer["pre_checkout_query_id"] == "pcq_1"


@pytest.mark.parametrize(
    ("mutate", "expect_in_message"),
    [
        ({"payload": "not-a-real-nonce"}, "could not be found"),
        ({"amount": 999}, "price"),
        ({"currency": "USD"}, "Stars"),
    ],
)
async def test_pre_checkout_declines_and_tells_the_player_why(
    app_client, bot_api, mutate, expect_in_message
):
    auth = await authorise(app_client)
    await buy(app_client, auth)
    row = await purchase_row()

    payload = mutate.pop("payload", row["invoice_payload"])
    response = await app_client.post(
        WEBHOOK, json=pre_checkout_update(payload, **mutate), headers=SECRET_HEADER
    )

    assert response.status_code == 200
    answer = bot_api.sent("answerPreCheckoutQuery")[0]
    assert answer["ok"] is False
    assert expect_in_message in answer["error_message"]


async def test_an_expired_invoice_is_declined(app_client, bot_api):
    auth = await authorise(app_client)
    await buy(app_client, auth)
    row = await purchase_row()

    async with db.transaction() as conn:
        await conn.execute("UPDATE star_purchases SET expires_at = NOW() - INTERVAL '1 minute'")

    await app_client.post(
        WEBHOOK, json=pre_checkout_update(row["invoice_payload"]), headers=SECRET_HEADER
    )
    answer = bot_api.sent("answerPreCheckoutQuery")[0]
    assert answer["ok"] is False
    assert "expired" in answer["error_message"]


async def test_a_restricted_account_cannot_complete_a_purchase(app_client, bot_api):
    auth = await authorise(app_client)
    await buy(app_client, auth)
    row = await purchase_row()

    async with db.transaction() as conn:
        await conn.execute("UPDATE users SET status = 'RESTRICTED'")

    await app_client.post(
        WEBHOOK, json=pre_checkout_update(row["invoice_payload"]), headers=SECRET_HEADER
    )
    assert bot_api.sent("answerPreCheckoutQuery")[0]["ok"] is False


async def test_a_successful_payment_mints_coins_through_the_ledger(app_client, bot_api):
    auth = await authorise(app_client)
    await buy(app_client, auth)
    row = await purchase_row()

    response = await app_client.post(
        WEBHOOK, json=payment_update(row["invoice_payload"]), headers=SECRET_HEADER
    )
    assert response.status_code == 200

    settled = await purchase_row(row["invoice_payload"])
    assert settled["status"] == "PAID"
    assert settled["telegram_payment_charge_id"] == "tg_charge_1"
    assert settled["paid_at"] is not None

    assert await balance() == 100_000 + await pack_coins()

    async with db.acquire() as conn:
        entry = await conn.fetchrow(
            "SELECT * FROM ledger_entries WHERE entry_type = 'STAR_PURCHASE_CREDIT'"
        )
        user = await conn.fetchrow("SELECT lifetime_stars FROM users WHERE telegram_id = 5000")
        drift = await conn.fetch("SELECT * FROM v_balance_reconciliation")

    assert entry["amount"] == await pack_coins()
    assert entry["idempotency_key"] == "tg_charge_1"
    assert user["lifetime_stars"] == 50
    assert drift == []


async def test_a_redelivered_payment_credits_once(app_client, bot_api):
    auth = await authorise(app_client)
    await buy(app_client, auth)
    row = await purchase_row()
    update = payment_update(row["invoice_payload"])

    first = await app_client.post(WEBHOOK, json=update, headers=SECRET_HEADER)
    second = await app_client.post(WEBHOOK, json=update, headers=SECRET_HEADER)

    assert first.status_code == second.status_code == 200
    assert second.json()["deduplicated"] is True
    assert await balance() == 100_000 + await pack_coins()


async def test_the_ledger_key_stops_a_double_credit_even_past_the_dedupe(app_client, bot_api):
    """Same charge, a *different* update_id — the delivery-level guard misses
    it, and the ledger's idempotency key is what actually protects the
    balance."""
    auth = await authorise(app_client)
    await buy(app_client, auth)
    row = await purchase_row()

    await app_client.post(
        WEBHOOK, json=payment_update(row["invoice_payload"], update_id=1), headers=SECRET_HEADER
    )
    replay = await app_client.post(
        WEBHOOK, json=payment_update(row["invoice_payload"], update_id=2), headers=SECRET_HEADER
    )

    assert replay.status_code == 200
    assert await balance() == 100_000 + await pack_coins()

    async with db.acquire() as conn:
        credits = await conn.fetchval(
            "SELECT count(*) FROM ledger_entries WHERE entry_type = 'STAR_PURCHASE_CREDIT'"
        )
    assert credits == 1


async def test_concurrent_deliveries_of_one_payment_credit_once(app_client, bot_api):
    auth = await authorise(app_client)
    await buy(app_client, auth)
    row = await purchase_row()

    await asyncio.gather(
        *(
            app_client.post(
                WEBHOOK,
                json=payment_update(row["invoice_payload"], update_id=i),
                headers=SECRET_HEADER,
            )
            for i in range(1, 4)
        )
    )

    assert await balance() == 100_000 + await pack_coins()


@pytest.mark.parametrize("mutate", [{"amount": 5}, {"amount": 5000}, {"currency": "USD"}])
async def test_a_payment_that_does_not_match_the_invoice_credits_nothing(
    app_client, bot_api, mutate
):
    """Credit what was invoiced, never what the webhook claims."""
    auth = await authorise(app_client)
    await buy(app_client, auth)
    row = await purchase_row()

    response = await app_client.post(
        WEBHOOK, json=payment_update(row["invoice_payload"], **mutate), headers=SECRET_HEADER
    )

    assert response.status_code == 200
    assert await balance() == 100_000
    assert (await purchase_row(row["invoice_payload"]))["status"] == "PENDING"


async def test_a_payment_for_an_unknown_payload_is_acknowledged_and_logged(app_client, caplog):
    """Stars were taken with no matching invoice. Retrying cannot help, so
    acknowledge it and leave a record loud enough to reconcile by hand."""
    response = await app_client.post(
        WEBHOOK, json=payment_update("a-payload-we-never-issued"), headers=SECRET_HEADER
    )

    assert response.status_code == 200
    assert "PAYMENT WITHOUT A MATCHING INVOICE" in caplog.text
    assert "tg_charge_1" in caplog.text


async def test_a_second_distinct_charge_against_one_purchase_is_refused(app_client, bot_api):
    auth = await authorise(app_client)
    await buy(app_client, auth)
    row = await purchase_row()

    await app_client.post(
        WEBHOOK,
        json=payment_update(row["invoice_payload"], update_id=1, charge="tg_charge_1"),
        headers=SECRET_HEADER,
    )
    await app_client.post(
        WEBHOOK,
        json=payment_update(row["invoice_payload"], update_id=2, charge="tg_charge_2"),
        headers=SECRET_HEADER,
    )

    assert await balance() == 100_000 + await pack_coins()


async def test_a_failure_mid_settlement_leaves_the_update_for_redelivery(
    app_client, bot_api, monkeypatch
):
    auth = await authorise(app_client)
    await buy(app_client, auth)
    row = await purchase_row()

    from backend.services import payment_service

    async def boom(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(payment_service, "settle_payment", boom)

    response = await app_client.post(
        WEBHOOK, json=payment_update(row["invoice_payload"]), headers=SECRET_HEADER
    )

    assert response.status_code == 500
    assert await balance() == 100_000

    async with db.acquire() as conn:
        recorded = await conn.fetchrow("SELECT * FROM telegram_updates WHERE update_id = 1")
    assert recorded["processed_at"] is None

    monkeypatch.undo()
    retry = await app_client.post(
        WEBHOOK, json=payment_update(row["invoice_payload"]), headers=SECRET_HEADER
    )
    assert retry.status_code == 200
    assert await balance() == 100_000 + await pack_coins()


async def test_repricing_a_package_does_not_change_an_outstanding_invoice(app_client, bot_api):
    auth = await authorise(app_client)
    await buy(app_client, auth)
    row = await purchase_row()

    quoted = await pack_coins()

    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE coin_packages SET stars_price = 999, coins = 1 WHERE code = 'TIER_1'"
        )

    await app_client.post(
        WEBHOOK, json=payment_update(row["invoice_payload"]), headers=SECRET_HEADER
    )

    assert await balance() == 100_000 + quoted


def refund_update(charge: str = "tg_charge_1", *, update_id: int = 50) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 11,
            "from": {"id": 5000, "first_name": "Ada"},
            "chat": {"id": 5000, "type": "private"},
            "date": 1787500100,
            "refunded_payment": {
                "currency": "XTR",
                "total_amount": 50,
                "invoice_payload": "irrelevant",
                "telegram_payment_charge_id": charge,
                "provider_payment_charge_id": "pp_1",
            },
        },
    }


async def settle_a_purchase(app_client, bot_api, telegram_id: int = 5000):
    auth = await authorise(app_client, telegram_id=telegram_id)
    await buy(app_client, auth)
    row = await purchase_row()
    await app_client.post(
        WEBHOOK,
        json=payment_update(row["invoice_payload"], telegram_id=telegram_id),
        headers=SECRET_HEADER,
    )
    return auth, row


async def test_a_refund_claws_the_coins_back(app_client, bot_api):
    await settle_a_purchase(app_client, bot_api)
    assert await balance() == 100_000 + await pack_coins()

    response = await app_client.post(WEBHOOK, json=refund_update(), headers=SECRET_HEADER)

    assert response.status_code == 200
    assert await balance() == 100_000

    row = await purchase_row()
    assert row["status"] == "REFUNDED"
    assert row["refunded_at"] is not None

    async with db.acquire() as conn:
        debit = await conn.fetchrow(
            "SELECT * FROM ledger_entries WHERE entry_type = 'STAR_REFUND_DEBIT'"
        )
        drift = await conn.fetch("SELECT * FROM v_balance_reconciliation")
    assert debit["amount"] == -(await pack_coins())
    assert drift == []


async def test_a_refund_after_the_coins_are_spent_recovers_what_it_can_and_restricts(
    app_client, bot_api
):
    """The obvious attack on a virtual economy: buy coins, stake them, refund
    the Stars, keep the winnings. The ledger cannot go negative, so take back
    what is there and flag the rest."""
    await settle_a_purchase(app_client, bot_api)

    leftover = 2_000_000
    spend = await balance() - leftover
    async with db.transaction() as conn:
        await conn.execute(
            """
            INSERT INTO ledger_entries (user_id, entry_type, amount, idempotency_key)
            SELECT id, 'STAKE_DEBIT', $1, 'spent-it' FROM users WHERE telegram_id = 5000
            """,
            -spend,
        )
    assert await balance() == leftover

    response = await app_client.post(WEBHOOK, json=refund_update(), headers=SECRET_HEADER)
    assert response.status_code == 200

    assert await balance() == 0

    async with db.acquire() as conn:
        user = await conn.fetchrow("SELECT status FROM users WHERE telegram_id = 5000")
        entry = await conn.fetchrow(
            "SELECT amount, metadata FROM ledger_entries WHERE entry_type = 'STAR_REFUND_DEBIT'"
        )
        drift = await conn.fetch("SELECT * FROM v_balance_reconciliation")

    assert entry["amount"] == -leftover
    credited = await pack_coins()
    assert json.loads(entry["metadata"]) == {
        "credited": credited,
        "recovered": leftover,
        "shortfall": credited - leftover,
    }
    assert user["status"] == "RESTRICTED"
    assert drift == []


async def test_a_redelivered_refund_claws_back_once(app_client, bot_api):
    await settle_a_purchase(app_client, bot_api)

    await app_client.post(WEBHOOK, json=refund_update(update_id=50), headers=SECRET_HEADER)
    await app_client.post(WEBHOOK, json=refund_update(update_id=51), headers=SECRET_HEADER)

    assert await balance() == 100_000

    async with db.acquire() as conn:
        debits = await conn.fetchval(
            "SELECT count(*) FROM ledger_entries WHERE entry_type = 'STAR_REFUND_DEBIT'"
        )
    assert debits == 1


async def test_a_refund_for_an_unknown_charge_is_acknowledged(app_client, caplog):
    response = await app_client.post(
        WEBHOOK, json=refund_update(charge="never-seen"), headers=SECRET_HEADER
    )
    assert response.status_code == 200
    assert "unknown charge" in caplog.text


async def test_abandoned_invoices_are_swept_so_the_cap_stays_usable(app_client, bot_api):
    from backend.config import get_settings
    from backend.workers import invoice_sweeper

    auth = await authorise(app_client)
    for _ in range(5):
        await buy(app_client, auth)

    assert (await buy(app_client, auth)).status_code == 429

    async with db.transaction() as conn:
        await conn.execute("UPDATE star_purchases SET expires_at = NOW() - INTERVAL '1 minute'")

    app = app_client._transport.app  # type: ignore[attr-defined]
    report = await invoice_sweeper.sweep_invoices(app.state.http, get_settings())
    assert report.expired == 5
    assert (await buy(app_client, auth)).status_code == 201


async def test_a_payment_against_an_expired_invoice_is_still_honoured(app_client, bot_api):
    """Expiry is our own bookkeeping — Telegram does not treat a retired row
    as cancelled. answerPreCheckoutQuery is the gate that declines an expired
    invoice; if a charge got past it the money moved, and the player is owed
    the coins whatever state we had the row in."""
    auth = await authorise(app_client)
    await buy(app_client, auth)
    row = await purchase_row()

    async with db.transaction() as conn:
        await conn.execute("UPDATE star_purchases SET status = 'EXPIRED'")

    response = await app_client.post(
        WEBHOOK, json=payment_update(row["invoice_payload"]), headers=SECRET_HEADER
    )

    assert response.status_code == 200
    assert await balance() == 100_000 + await pack_coins()
    assert (await purchase_row(row["invoice_payload"]))["status"] == "PAID"


async def test_pre_checkout_is_the_gate_that_stops_an_expired_purchase(app_client, bot_api):
    """The layer that should refuse, refuses — so the case above stays rare."""
    auth = await authorise(app_client)
    await buy(app_client, auth)
    row = await purchase_row()

    async with db.transaction() as conn:
        await conn.execute("UPDATE star_purchases SET status = 'EXPIRED'")

    await app_client.post(
        WEBHOOK, json=pre_checkout_update(row["invoice_payload"]), headers=SECRET_HEADER
    )
    assert bot_api.sent("answerPreCheckoutQuery")[0]["ok"] is False


async def test_the_configured_bot_api_host_is_actually_used(app_client, bot_api):
    """A mock transport answers whatever URL it is given, so nothing else in
    this file would notice if `telegram_api_url` were ignored — which is
    exactly the bug a live run turned up."""
    from backend.config import get_settings

    auth = await authorise(app_client)
    await buy(app_client, auth)

    expected_host = httpx.URL(get_settings().telegram_api_url).host
    assert bot_api.urls, "no Bot API call was made"
    for url in bot_api.urls:
        assert httpx.URL(url).host == expected_host
        assert url.endswith("/createInvoiceLink")
        assert f"/bot{TEST_BOT_TOKEN}/" in url
