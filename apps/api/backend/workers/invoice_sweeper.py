"""Reconcile dropped Stars payments, then retire abandoned invoices.

## The gap this closes

A player pays. Telegram takes the Stars. The `successful_payment` webhook
never arrives — dropped delivery, our process restarting mid-request, a
network partition. The `star_purchases` row stays PENDING and the player is
out of pocket with nothing to show for it. Nothing else in the system notices,
because every other guard is about not crediting *twice*; none of them catch
not crediting *at all*.

Every fifteen minutes this asks Telegram what it actually charged, and settles
anything we missed.

## Why this cannot double-credit

`StarTransaction.id` is documented as coinciding with
`SuccessfulPayment.telegram_payment_charge_id` for an incoming payment. Both
paths therefore compute the *same* ledger idempotency key, and
`ledger_entries (user_id, idempotency_key)` refuses the second one. A webhook
that arrives late, while this sweep is mid-flight, is a no-op rather than a
race — which is why settlement is not reimplemented here but handed to the
same `payment_service.settle_payment` the webhook uses, Farsi notes and all.

## Order matters

Reconcile first, expire second. An invoice expires after an hour but stays
reconcilable for a day; expiring first would retire a row moments before
discovering it had in fact been paid.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field

import httpx

from .. import db
from ..clients import telegram
from ..config import Settings
from ..services import payment_service
from .locks import single_flight

logger = logging.getLogger(__name__)

JOB_NAME = "invoice_sweeper"


@dataclass
class SweepReport:
    ran: bool
    duration_seconds: float = 0.0
    orphans_found: int = 0
    transactions_scanned: int = 0
    pages_fetched: int = 0
    settled: int = 0
    already_settled: int = 0
    unmatched: int = 0
    expired: int = 0
    reasons: dict[str, int] = field(default_factory=dict)
    error: str | None = None


_ORPHANS = """
SELECT sp.id, sp.invoice_payload, sp.stars_amount, sp.created_at, sp.status
  FROM star_purchases sp
 WHERE sp.status IN ('PENDING', 'EXPIRED')
   -- A grace period, so this never races the ordinary webhook path.
   AND sp.created_at <  NOW() - make_interval(mins => $1)
   AND sp.created_at >= NOW() - make_interval(hours => $2)
 ORDER BY sp.created_at
 LIMIT $3
"""


async def _find_orphans(settings: Settings) -> list[dict]:
    async with db.acquire() as conn:
        rows = await conn.fetch(
            _ORPHANS,
            settings.reconciliation_grace_minutes,
            settings.reconciliation_window_hours,
            settings.reconciliation_batch_size,
        )
    return [dict(row) for row in rows]


async def _collect_transactions(
    client: httpx.AsyncClient, settings: Settings, oldest_orphan_at
) -> tuple[dict[str, telegram.StarTransaction], int, int]:
    """Page the bot's Stars ledger back as far as the oldest orphan.

    Telegram returns newest first, so a page whose entries all predate the
    oldest thing we are looking for means nothing further back can match —
    stop rather than walking the bot's entire history every fifteen minutes.
    """
    by_payload: dict[str, telegram.StarTransaction] = {}
    scanned = 0
    pages = 0

    for page in range(settings.reconciliation_max_pages):
        transactions = await telegram.get_star_transactions(
            client,
            settings.telegram_bot_token,
            offset=page * telegram.MAX_TRANSACTIONS_PER_PAGE,
            limit=telegram.MAX_TRANSACTIONS_PER_PAGE,
            api_url=settings.telegram_api_url,
        )
        pages += 1
        scanned += len(transactions)

        for transaction in transactions:
            if transaction.is_incoming and transaction.invoice_payload:
                by_payload.setdefault(transaction.invoice_payload, transaction)

        if len(transactions) < telegram.MAX_TRANSACTIONS_PER_PAGE:
            break
        if transactions and transactions[-1].at < oldest_orphan_at:
            break
    else:
        logger.warning(
            "reconciliation stopped at its page ceiling (%s); some history unread",
            settings.reconciliation_max_pages,
        )

    return by_payload, scanned, pages


async def reconcile_dropped_payments(
    client: httpx.AsyncClient, settings: Settings, report: SweepReport
) -> None:
    orphans = await _find_orphans(settings)
    report.orphans_found = len(orphans)
    if not orphans:
        return

    logger.info("reconciling %s outstanding purchase(s) against Telegram", len(orphans))

    by_payload, report.transactions_scanned, report.pages_fetched = await _collect_transactions(
        client, settings, orphans[0]["created_at"]
    )

    for orphan in orphans:
        transaction = by_payload.get(orphan["invoice_payload"])
        if transaction is None:
            report.unmatched += 1
            continue

        async with db.transaction() as conn:
            outcome = await payment_service.settle_payment(
                conn,
                invoice_payload=orphan["invoice_payload"],
                telegram_payment_charge_id=transaction.charge_id,
                provider_payment_charge_id=None,
                total_amount=transaction.stars,
                currency=telegram.STARS_CURRENCY,
            )

        if outcome.already_settled:
            report.already_settled += 1
        elif outcome.credited_minor > 0:
            report.settled += 1
            logger.error(
                "RECOVERED A DROPPED PAYMENT: purchase=%s charge=%s stars=%s coins=%s",
                orphan["id"],
                transaction.charge_id,
                transaction.stars,
                outcome.credited_minor,
            )
        else:
            reason = outcome.reason or "unknown"
            report.reasons[reason] = report.reasons.get(reason, 0) + 1


async def sweep_invoices(client: httpx.AsyncClient, settings: Settings) -> SweepReport:
    """Recover dropped payments, then dead-letter what nobody paid.

    Reconciliation failing must not stop expiry: they are independent, and
    abandoned rows otherwise accumulate against the per-player open-invoice
    allowance until a player who changed their mind a few times cannot buy at
    all.
    """
    async with single_flight(JOB_NAME) as owner:
        if not owner:
            return SweepReport(ran=False)

        started = time.monotonic()
        report = SweepReport(ran=True)

        try:
            await reconcile_dropped_payments(client, settings, report)
        except telegram.TelegramApiError as exc:
            logger.error("getStarTransactions failed: %s", exc.description)
            report.error = exc.description
        except Exception as exc:  # noqa: BLE001 - expiry must still run
            logger.exception("reconciliation failed")
            report.error = str(exc)

        try:
            async with db.transaction() as conn:
                report.expired = await payment_service.expire_stale_invoices(conn)
        except Exception:
            logger.exception("expiring stale invoices failed")

        report.duration_seconds = round(time.monotonic() - started, 3)

        if report.settled or report.error or report.reasons:
            logger.warning("invoice sweep: %s", asdict(report))
        elif report.expired:
            logger.info("expired %s abandoned Stars invoice(s)", report.expired)

        return report
