"""Recovering payments whose webhook never arrived.

Every other guard in the payments path is about not crediting twice. This is
the one that catches not crediting at all — a player charged Stars who got
nothing back.
"""

from __future__ import annotations

import time
import uuid

import httpx
import pytest
from conftest import TEST_WEBHOOK_SECRET, authorise

from backend import db
from backend.clients import telegram
from backend.config import get_settings
from backend.workers import invoice_sweeper

SECRET_HEADER = {"X-Telegram-Bot-Api-Secret-Token": TEST_WEBHOOK_SECRET}


async def pack_coins(code: str = "TIER_1") -> int:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT coins, bonus_coins FROM coin_packages WHERE code = $1", code
        )
    return int(row["coins"]) + int(row["bonus_coins"])


class FakeStarsLedger:
    """Stands in for the Bot API, serving createInvoiceLink and
    getStarTransactions from an in-memory list."""

    def __init__(self) -> None:
        self.transactions: list[dict] = []
        self.calls: list[str] = []
        self.fail_get = False
        self.pages_served = 0

    def charge(
        self,
        payload: str,
        *,
        charge_id: str,
        stars: int = 50,
        age_seconds: int = 600,
        incoming: bool = True,
    ) -> None:
        entry: dict = {
            "id": charge_id,
            "amount": stars,
            "date": int(time.time()) - age_seconds,
        }
        if incoming:
            entry["source"] = {"type": "user", "user": {"id": 5000}, "invoice_payload": payload}
        else:
            entry["receiver"] = {"type": "user", "user": {"id": 5000}}
            entry["source"] = {"type": "user", "invoice_payload": payload}
        self.transactions.insert(0, entry)

    def handler(self, request: httpx.Request) -> httpx.Response:
        import json as jsonlib

        method = str(request.url).rsplit("/", 1)[-1]
        self.calls.append(method)
        body = jsonlib.loads(request.content or b"{}")

        if method == "createInvoiceLink":
            return httpx.Response(200, json={"ok": True, "result": "https://t.me/$Fake"})
        if method == "getStarTransactions":
            if self.fail_get:
                return httpx.Response(
                    200, json={"ok": False, "error_code": 429, "description": "Too Many Requests"}
                )
            self.pages_served += 1
            offset = int(body.get("offset", 0))
            limit = int(body.get("limit", 100))
            page = self.transactions[offset : offset + limit]
            return httpx.Response(200, json={"ok": True, "result": {"transactions": page}})
        return httpx.Response(200, json={"ok": True, "result": True})

    @property
    def get_calls(self) -> int:
        return sum(1 for c in self.calls if c == "getStarTransactions")


@pytest.fixture
def stars(app_client) -> FakeStarsLedger:
    fake = FakeStarsLedger()
    app = app_client._transport.app  # type: ignore[attr-defined]
    app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    return fake


async def buy(app_client, auth, package="TIER_1") -> dict:
    response = await app_client.post(
        "/v1/payments/invoices", json={"package_code": package}, headers=auth
    )
    assert response.status_code == 201
    async with db.acquire() as conn:
        return dict(
            await conn.fetchrow(
                "SELECT * FROM star_purchases WHERE id = $1",
                uuid.UUID(response.json()["purchase_id"]),
            )
        )


async def age_purchase(purchase_id, *, minutes: int) -> None:
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE star_purchases SET created_at = NOW() - make_interval(mins => $2)"
            " WHERE id = $1",
            purchase_id,
            minutes,
        )


async def sweep(app_client, settings=None):
    app = app_client._transport.app  # type: ignore[attr-defined]
    return await invoice_sweeper.sweep_invoices(app.state.http, settings or get_settings())


async def balance(telegram_id: int = 5000) -> int:
    async with db.acquire() as conn:
        return await conn.fetchval(
            "SELECT coin_balance FROM users WHERE telegram_id = $1", telegram_id
        )


async def purchase(purchase_id) -> dict:
    async with db.acquire() as conn:
        return dict(await conn.fetchrow("SELECT * FROM star_purchases WHERE id = $1", purchase_id))


def test_the_charge_id_is_the_transaction_id():
    """The Bot API documents StarTransaction.id as coinciding with
    SuccessfulPayment.telegram_payment_charge_id. That equality is what makes
    both settlement paths compute the same ledger key."""
    parsed = telegram.parse_star_transaction(
        {
            "id": "tg_charge_abc",
            "amount": 50,
            "date": int(time.time()),
            "source": {"type": "user", "invoice_payload": "nonce-1"},
        }
    )
    assert parsed is not None
    assert parsed.charge_id == "tg_charge_abc"
    assert parsed.stars == 50
    assert parsed.invoice_payload == "nonce-1"
    assert parsed.is_incoming is True


def test_an_outgoing_transaction_is_marked_as_such():
    parsed = telegram.parse_star_transaction(
        {
            "id": "refund_1",
            "amount": 50,
            "date": int(time.time()),
            "source": {"type": "user", "invoice_payload": "nonce-1"},
            "receiver": {"type": "user"},
        }
    )
    assert parsed is not None
    assert parsed.is_incoming is False


def test_a_transaction_with_no_payload_of_ours_is_parsed_but_unmatched():
    """Gifts and paid media appear in the same ledger and carry no invoice."""
    parsed = telegram.parse_star_transaction(
        {"id": "gift_1", "amount": 10, "date": int(time.time()), "source": {"type": "user"}}
    )
    assert parsed is not None
    assert parsed.invoice_payload is None


@pytest.mark.parametrize(
    "broken",
    [
        {"amount": 50, "date": 1},
        {"id": "x", "date": 1},
        {"id": "x", "amount": "fifty", "date": 1},
        {"id": "", "amount": 50, "date": 1},
        "not an object",
    ],
)
def test_malformed_transactions_are_dropped_not_guessed_at(broken):
    assert telegram.parse_star_transaction(broken) is None


async def test_a_dropped_payment_is_recovered(app_client, stars):
    """The whole point: Telegram charged, the webhook never came, and the
    player would otherwise be out of pocket with nothing."""
    auth = await authorise(app_client)
    row = await buy(app_client, auth)
    assert await balance() == 100_000

    stars.charge(row["invoice_payload"], charge_id="tg_dropped_1", stars=50)
    await age_purchase(row["id"], minutes=30)

    report = await sweep(app_client)

    assert report.orphans_found == 1
    assert report.settled == 1
    assert await balance() == 100_000 + await pack_coins()

    settled = await purchase(row["id"])
    assert settled["status"] == "PAID"
    assert settled["telegram_payment_charge_id"] == "tg_dropped_1"

    async with db.acquire() as conn:
        entry = await conn.fetchrow(
            "SELECT amount, idempotency_key, metadata FROM ledger_entries"
            " WHERE entry_type = 'STAR_PURCHASE_CREDIT'"
        )
        drift = await conn.fetch("SELECT * FROM v_balance_reconciliation")

    assert entry["idempotency_key"] == "tg_dropped_1"
    assert entry["amount"] == await pack_coins()
    assert drift == []


async def test_a_late_webhook_after_a_sweep_credits_nothing_further(app_client, stars):
    """The two paths compute the same ledger key, so a webhook that turns up
    afterwards is a no-op rather than a race."""
    auth = await authorise(app_client)
    row = await buy(app_client, auth)
    stars.charge(row["invoice_payload"], charge_id="tg_late_1")
    await age_purchase(row["id"], minutes=30)

    await sweep(app_client)
    after_sweep = await balance()

    late = {
        "update_id": 900,
        "message": {
            "message_id": 1,
            "from": {"id": 5000, "first_name": "Ada"},
            "chat": {"id": 5000, "type": "private"},
            "date": 1787500000,
            "successful_payment": {
                "currency": "XTR",
                "total_amount": 50,
                "invoice_payload": row["invoice_payload"],
                "telegram_payment_charge_id": "tg_late_1",
                "provider_payment_charge_id": "pp_1",
            },
        },
    }
    response = await app_client.post("/v1/payments/webhook", json=late, headers=SECRET_HEADER)

    assert response.status_code == 200
    assert await balance() == after_sweep

    async with db.acquire() as conn:
        credits = await conn.fetchval(
            "SELECT count(*) FROM ledger_entries WHERE entry_type = 'STAR_PURCHASE_CREDIT'"
        )
    assert credits == 1


async def test_sweeping_twice_credits_once(app_client, stars):
    auth = await authorise(app_client)
    row = await buy(app_client, auth)
    stars.charge(row["invoice_payload"], charge_id="tg_twice_1")
    await age_purchase(row["id"], minutes=30)

    first = await sweep(app_client)
    second = await sweep(app_client)

    assert first.settled == 1
    assert second.settled == 0
    assert second.orphans_found == 0
    assert await balance() == 100_000 + await pack_coins()


async def test_a_purchase_still_inside_the_grace_period_is_left_alone(app_client, stars):
    """Five minutes for the ordinary webhook path, so this never races it."""
    auth = await authorise(app_client)
    row = await buy(app_client, auth)
    stars.charge(row["invoice_payload"], charge_id="tg_fresh_1")

    report = await sweep(app_client)

    assert report.orphans_found == 0
    assert stars.get_calls == 0
    assert await balance() == 100_000


async def test_a_purchase_older_than_the_window_is_not_reconciled(app_client, stars):
    auth = await authorise(app_client)
    row = await buy(app_client, auth)
    stars.charge(row["invoice_payload"], charge_id="tg_ancient_1")
    await age_purchase(row["id"], minutes=60 * 48)

    report = await sweep(app_client)
    assert report.orphans_found == 0


async def test_an_abandoned_invoice_matches_nothing_and_is_fine(app_client, stars):
    """The ordinary case: the player opened an invoice and never paid."""
    auth = await authorise(app_client)
    row = await buy(app_client, auth)
    await age_purchase(row["id"], minutes=30)

    report = await sweep(app_client)

    assert report.orphans_found == 1
    assert report.unmatched == 1
    assert report.settled == 0
    assert await balance() == 100_000
    assert (await purchase(row["id"]))["status"] == "PENDING"


async def test_a_refund_transaction_never_settles_a_purchase(app_client, stars):
    auth = await authorise(app_client)
    row = await buy(app_client, auth)
    stars.charge(row["invoice_payload"], charge_id="tg_refund_1", incoming=False)
    await age_purchase(row["id"], minutes=30)

    report = await sweep(app_client)

    assert report.settled == 0
    assert report.unmatched == 1
    assert await balance() == 100_000


async def test_a_charge_for_a_different_amount_is_refused(app_client, stars):
    """Credit what was invoiced, never what the ledger claims."""
    auth = await authorise(app_client)
    row = await buy(app_client, auth)
    stars.charge(row["invoice_payload"], charge_id="tg_wrong_amount", stars=5)
    await age_purchase(row["id"], minutes=30)

    report = await sweep(app_client)

    assert report.settled == 0
    assert report.reasons.get("amount_mismatch") == 1
    assert await balance() == 100_000
    assert (await purchase(row["id"]))["status"] == "PENDING"


async def test_a_payment_for_an_invoice_we_already_expired_is_still_honoured(app_client, stars):
    """Our expiry is bookkeeping, not something Telegram knows about. If the
    charge is real the player is owed the coins regardless."""
    auth = await authorise(app_client)
    row = await buy(app_client, auth)
    stars.charge(row["invoice_payload"], charge_id="tg_expired_1")
    await age_purchase(row["id"], minutes=120)

    async with db.transaction() as conn:
        await conn.execute("UPDATE star_purchases SET status = 'EXPIRED'")

    report = await sweep(app_client)

    assert report.settled == 1
    assert await balance() == 100_000 + await pack_coins()
    assert (await purchase(row["id"]))["status"] == "PAID"


async def test_a_telegram_failure_does_not_stop_expiry(app_client, stars):
    auth = await authorise(app_client)
    row = await buy(app_client, auth)
    await age_purchase(row["id"], minutes=30)
    async with db.transaction() as conn:
        await conn.execute("UPDATE star_purchases SET expires_at = NOW() - INTERVAL '1 minute'")

    stars.fail_get = True
    report = await sweep(app_client)

    assert report.error is not None
    assert report.settled == 0
    assert report.expired == 1
    assert (await purchase(row["id"]))["status"] == "EXPIRED"


async def test_reconciliation_runs_before_expiry(app_client, stars):
    """An invoice expires after an hour but stays reconcilable for a day.
    Expiring first would retire a row moments before discovering it was paid."""
    auth = await authorise(app_client)
    row = await buy(app_client, auth)
    stars.charge(row["invoice_payload"], charge_id="tg_order_1")
    await age_purchase(row["id"], minutes=90)
    async with db.transaction() as conn:
        await conn.execute("UPDATE star_purchases SET expires_at = NOW() - INTERVAL '30 minutes'")

    report = await sweep(app_client)

    assert report.settled == 1
    assert report.expired == 0
    assert (await purchase(row["id"]))["status"] == "PAID"
    assert await balance() == 100_000 + await pack_coins()


async def test_only_one_replica_sweeps(app_client, stars):
    import asyncio

    auth = await authorise(app_client)
    row = await buy(app_client, auth)
    stars.charge(row["invoice_payload"], charge_id="tg_lock_1")
    await age_purchase(row["id"], minutes=30)

    reports = await asyncio.gather(sweep(app_client), sweep(app_client), sweep(app_client))

    assert sum(1 for r in reports if r.ran) == 1
    assert await balance() == 100_000 + await pack_coins()


async def test_an_empty_sweep_asks_telegram_nothing(app_client, stars):
    report = await sweep(app_client)
    assert report.ran is True
    assert report.orphans_found == 0
    assert stars.get_calls == 0


async def test_paging_stops_once_the_history_predates_the_oldest_orphan(app_client, stars):
    """Otherwise this walks the bot's entire Stars history every fifteen
    minutes, forever."""
    auth = await authorise(app_client)
    row = await buy(app_client, auth)
    await age_purchase(row["id"], minutes=30)

    for index in range(250):
        stars.charge(f"someone-else-{index}", charge_id=f"other_{index}", age_seconds=86_400 * 30)
    stars.charge(row["invoice_payload"], charge_id="tg_paged_1", age_seconds=600)

    report = await sweep(app_client)

    assert report.settled == 1
    assert report.pages_fetched <= 2
    assert await balance() == 100_000 + await pack_coins()


async def test_a_short_page_ends_the_walk(app_client, stars):
    auth = await authorise(app_client)
    row = await buy(app_client, auth)
    await age_purchase(row["id"], minutes=30)
    stars.charge(row["invoice_payload"], charge_id="tg_short_1")

    report = await sweep(app_client)

    assert report.pages_fetched == 1
    assert report.settled == 1
