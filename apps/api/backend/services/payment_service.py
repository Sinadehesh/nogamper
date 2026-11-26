"""Telegram Stars: invoices in, coins out.

This is the only path by which value enters the system, so it is written to
fail closed at every step.

## The nonce

We never put a user id in the invoice payload. Telegram hands the payload
back on the webhook, and anything that arrives from outside is input, not
identity. Instead we mint a random nonce, persist it against the purchase
*before* the invoice exists, and resolve the webhook by looking that nonce up.
A tampered payload matches nothing and settles nothing.

## Where idempotency actually lives

Telegram redelivers webhooks. Three independent guards catch that, in order:

1. `telegram_updates.update_id` — the same delivery, seen twice.
2. `star_purchases.telegram_payment_charge_id UNIQUE` — the same charge
   against a second purchase row.
3. `ledger_entries (user_id, idempotency_key)` — the charge id as the key, so
   a second credit for one payment cannot be written even if the two guards
   above are somehow bypassed.

The third is the one that actually protects the balance. The others just make
the common case cheap.

## Refunds

Telegram lets a player refund Stars. That is the obvious attack on a virtual
economy: buy coins, stake them, refund the Stars, keep the winnings. The
clawback below takes back what is still there and restricts the account for
whatever is not, because the ledger cannot go negative and pretending the
shortfall did not happen is how the exploit pays.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg
import httpx

from ..clients import telegram
from ..config import Settings

logger = logging.getLogger(__name__)

__all__ = [
    "InvoiceIssued",
    "PaymentError",
    "SettlementOutcome",
    "expire_stale_invoices",
    "issue_invoice",
    "resolve_pre_checkout",
    "settle_payment",
    "settle_refund",
]


class PaymentError(Exception):
    def __init__(self, code: str, detail: str, *, status: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


@dataclass(frozen=True, slots=True)
class InvoiceIssued:
    purchase_id: uuid.UUID
    invoice_link: str
    stars: int
    coins_minor: int


@dataclass(frozen=True, slots=True)
class SettlementOutcome:
    handled: bool
    """False only when there is nothing this system can do with the update."""
    credited_minor: int = 0
    already_settled: bool = False
    reason: str | None = None


_LOAD_PACKAGE = """
SELECT code, title, description, stars_price, coins, bonus_coins
  FROM coin_packages
 WHERE code = $1 AND is_active
"""

_OPEN_INVOICES = """
SELECT count(*) FROM star_purchases
 WHERE user_id = $1 AND status = 'PENDING' AND expires_at > NOW()
"""

_CREATE_PURCHASE = """
INSERT INTO star_purchases (user_id, package_code, invoice_payload, stars_amount,
                            coins_amount, expires_at)
VALUES ($1, $2, $3, $4, $5, NOW() + make_interval(secs => $6))
RETURNING id
"""


async def issue_invoice(
    conn: asyncpg.Connection,
    http: httpx.AsyncClient,
    settings: Settings,
    *,
    user_id: uuid.UUID,
    package_code: str,
) -> InvoiceIssued:
    package = await conn.fetchrow(_LOAD_PACKAGE, package_code)
    if package is None:
        raise PaymentError("unknown_package", "No such coin package.", status=404)

    open_invoices = await conn.fetchval(_OPEN_INVOICES, user_id)
    if open_invoices >= settings.max_open_invoices_per_user:
        raise PaymentError(
            "too_many_open_invoices",
            "Finish or abandon your open purchases before starting another.",
            status=429,
        )

    nonce = secrets.token_urlsafe(32)

    coins_minor = package["coins"] + package["bonus_coins"]

    purchase_id = await conn.fetchval(
        _CREATE_PURCHASE,
        user_id,
        package["code"],
        nonce,
        package["stars_price"],
        coins_minor,
        settings.invoice_ttl_seconds,
    )

    try:
        link = await telegram.create_invoice_link(
            http,
            settings.telegram_bot_token,
            title=package["title"],
            description=package["description"],
            payload=nonce,
            prices=[telegram.LabeledPrice(label=package["title"], amount=package["stars_price"])],
            api_url=settings.telegram_api_url,
        )
    except telegram.TelegramApiError as exc:
        logger.error(
            "createInvoiceLink refused for package %s: %s (%s)",
            package_code,
            exc.description,
            exc.error_code,
        )
        raise PaymentError(
            "invoice_unavailable",
            "Telegram could not create this invoice. Try again shortly.",
            status=502,
        ) from exc

    logger.info(
        "invoice issued: purchase=%s package=%s stars=%s",
        purchase_id,
        package_code,
        package["stars_price"],
    )
    return InvoiceIssued(
        purchase_id=purchase_id,
        invoice_link=link,
        stars=package["stars_price"],
        coins_minor=coins_minor,
    )


_FIND_BY_PAYLOAD = """
SELECT sp.id, sp.user_id, sp.status, sp.stars_amount, sp.coins_amount,
       sp.expires_at, sp.telegram_payment_charge_id, u.telegram_id, u.status AS user_status
  FROM star_purchases sp
  JOIN users u ON u.id = sp.user_id
 WHERE sp.invoice_payload = $1
"""


async def resolve_pre_checkout(
    conn: asyncpg.Connection, *, invoice_payload: str, total_amount: int, currency: str
) -> tuple[bool, str | None]:
    """Decide whether to accept a payment. Returns (ok, message_for_the_player).

    One indexed lookup and nothing else: Telegram cancels the payment if this
    is not answered within ten seconds.
    """
    if currency != telegram.STARS_CURRENCY:
        return False, "This bot only accepts Telegram Stars."

    purchase = await conn.fetchrow(_FIND_BY_PAYLOAD, invoice_payload)
    if purchase is None:
        return False, "This purchase could not be found."

    if purchase["status"] == "PAID":
        return False, "This purchase has already been completed."
    if purchase["status"] != "PENDING":
        return False, "This purchase is no longer available."
    if purchase["expires_at"] <= datetime.now(UTC):
        return False, "This invoice has expired. Please start a new purchase."
    if purchase["user_status"] != "ACTIVE":
        return False, "This account cannot make purchases right now."

    if total_amount != purchase["stars_amount"]:
        logger.error(
            "pre-checkout amount mismatch on purchase %s: expected %s stars, got %s",
            purchase["id"],
            purchase["stars_amount"],
            total_amount,
        )
        return False, "The price of this purchase has changed. Please start again."

    return True, None


_LOCK_BY_PAYLOAD = """
SELECT sp.id, sp.user_id, sp.status, sp.stars_amount, sp.coins_amount,
       sp.telegram_payment_charge_id, u.telegram_id
  FROM star_purchases sp
  JOIN users u ON u.id = sp.user_id
 WHERE sp.invoice_payload = $1
   FOR UPDATE OF sp
"""

_SETTLEABLE = ("PENDING", "EXPIRED")

_MARK_PAID = """
UPDATE star_purchases
   SET status = 'PAID',
       telegram_payment_charge_id = $2,
       provider_payment_charge_id = $3,
       paid_at = NOW()
 WHERE id = $1 AND status = ANY($4::star_purchase_status[])
RETURNING id
"""


async def settle_payment(
    conn: asyncpg.Connection,
    *,
    invoice_payload: str,
    telegram_payment_charge_id: str,
    provider_payment_charge_id: str | None,
    total_amount: int,
    currency: str,
) -> SettlementOutcome:
    """Credit a completed Stars payment, exactly once.

    Runs inside the caller's transaction so the purchase row, the ledger entry
    and the balance move together or not at all.
    """
    purchase = await conn.fetchrow(_LOCK_BY_PAYLOAD, invoice_payload)

    if purchase is None:
        logger.error(
            "PAYMENT WITHOUT A MATCHING INVOICE: charge=%s amount=%s %s payload=%s",
            telegram_payment_charge_id,
            total_amount,
            currency,
            invoice_payload[:16] + "...",
        )
        return SettlementOutcome(handled=True, reason="unknown_payload")

    if purchase["status"] in {"PAID", "REFUNDED"}:
        if purchase["telegram_payment_charge_id"] != telegram_payment_charge_id:
            logger.error(
                "second distinct charge %s against purchase %s (already %s under %s)",
                telegram_payment_charge_id,
                purchase["id"],
                purchase["status"],
                purchase["telegram_payment_charge_id"],
            )
            return SettlementOutcome(handled=True, reason="charge_conflict")
        return SettlementOutcome(handled=True, already_settled=True)

    if purchase["status"] not in _SETTLEABLE:
        logger.warning(
            "payment for purchase %s in unexpected state %s", purchase["id"], purchase["status"]
        )
        return SettlementOutcome(handled=True, reason="not_settleable")

    if purchase["status"] == "EXPIRED":
        logger.warning(
            "settling purchase %s that we had already expired — the charge is real",
            purchase["id"],
        )

    if currency != telegram.STARS_CURRENCY or total_amount != purchase["stars_amount"]:
        logger.error(
            "settlement mismatch on purchase %s: invoiced %s XTR, webhook says %s %s",
            purchase["id"],
            purchase["stars_amount"],
            total_amount,
            currency,
        )
        return SettlementOutcome(handled=True, reason="amount_mismatch")

    updated = await conn.fetchval(
        _MARK_PAID,
        purchase["id"],
        telegram_payment_charge_id,
        provider_payment_charge_id or "",
        list(_SETTLEABLE),
    )
    if updated is None:  # pragma: no cover - the row lock above makes this dead
        return SettlementOutcome(handled=True, already_settled=True)

    await conn.execute(
        """
        INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id,
                                    idempotency_key, metadata)
        VALUES ($1, 'STAR_PURCHASE_CREDIT', $2, 'STAR_PURCHASE', $3, $4, $5::jsonb)
        """,
        purchase["user_id"],
        purchase["coins_amount"],
        purchase["id"],
        telegram_payment_charge_id,
        f'{{"stars":{purchase["stars_amount"]},"charge":"{telegram_payment_charge_id}"}}',
    )

    logger.info(
        "settled purchase %s: %s stars -> %s minor coins for user %s",
        purchase["id"],
        purchase["stars_amount"],
        purchase["coins_amount"],
        purchase["user_id"],
    )
    return SettlementOutcome(handled=True, credited_minor=purchase["coins_amount"])


_LOCK_BY_CHARGE = """
SELECT sp.id, sp.user_id, sp.status, sp.stars_amount, sp.coins_amount,
       u.coin_balance, u.telegram_id
  FROM star_purchases sp
  JOIN users u ON u.id = sp.user_id
 WHERE sp.telegram_payment_charge_id = $1
   FOR UPDATE OF sp
"""


async def settle_refund(
    conn: asyncpg.Connection, *, telegram_payment_charge_id: str
) -> SettlementOutcome:
    """Claw back coins for a refunded Stars payment.

    The player may already have staked them. `coin_balance` has a
    non-negative CHECK and the ledger is append-only, so we take back what is
    there and restrict the account for the rest. Leaving a shortfall unmarked
    is what makes buy-stake-refund profitable.
    """
    purchase = await conn.fetchrow(_LOCK_BY_CHARGE, telegram_payment_charge_id)

    if purchase is None:
        logger.error(
            "refund for an unknown charge %s — nothing to claw back",
            telegram_payment_charge_id,
        )
        return SettlementOutcome(handled=True, reason="unknown_charge")

    if purchase["status"] == "REFUNDED":
        return SettlementOutcome(handled=True, already_settled=True)
    if purchase["status"] != "PAID":
        logger.warning(
            "refund for purchase %s which is %s, not PAID", purchase["id"], purchase["status"]
        )
        return SettlementOutcome(handled=True, reason="not_paid")

    credited = purchase["coins_amount"]
    recoverable = min(credited, purchase["coin_balance"])
    shortfall = credited - recoverable

    await conn.execute(
        """
        UPDATE star_purchases
           SET status = 'REFUNDED', refunded_at = NOW(), refund_reason = $2
         WHERE id = $1
        """,
        purchase["id"],
        f"clawed back {recoverable} of {credited} minor coins",
    )

    if recoverable > 0:
        await conn.execute(
            """
            INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id,
                                        idempotency_key, metadata)
            VALUES ($1, 'STAR_REFUND_DEBIT', $2, 'STAR_PURCHASE', $3, $4, $5::jsonb)
            """,
            purchase["user_id"],
            -recoverable,
            purchase["id"],
            f"refund:{telegram_payment_charge_id}",
            f'{{"credited":{credited},"recovered":{recoverable},"shortfall":{shortfall}}}',
        )

    if shortfall > 0:
        await conn.execute(
            "UPDATE users SET status = 'RESTRICTED' WHERE id = $1 AND status = 'ACTIVE'",
            purchase["user_id"],
        )
        logger.error(
            "refund shortfall on purchase %s: %s of %s minor coins unrecoverable; "
            "user %s restricted",
            purchase["id"],
            shortfall,
            credited,
            purchase["user_id"],
        )

    return SettlementOutcome(handled=True, credited_minor=-recoverable)


async def expire_stale_invoices(conn: asyncpg.Connection) -> int:
    """Retire invoices nobody paid, so the open-invoice cap stays meaningful."""
    result = await conn.execute(
        "UPDATE star_purchases SET status = 'EXPIRED' "
        " WHERE status = 'PENDING' AND expires_at <= NOW()"
    )
    return int(result.rsplit(" ", 1)[-1])
