"""Resolution worker — grade settled markets, then let the database pay.

Runs every five minutes. For each market whose upstream event has passed, it
asks Gamma what happened, grades the open legs, and calls
`fn_settle_prediction` for every slip that was touched.

## The division of labour

This module decides **what happened**. Postgres decides **what it pays**.

All the parlay arithmetic — compounding, void legs collapsing to a factor of
one, the insurance near-miss window, the payout cap, the ledger keys that make
a payout exactly-once — lives in `fn_settle_prediction`. Re-implementing any of
it here would create a second source of truth for what a slip is worth, and the
two would drift. The worker's entire settlement step is one `SELECT`.

## Failure policy

Everything here is written so that a bad Gamma response costs nothing:

* **An ambiguous outcome is not graded.** `read_resolution` returns None for a
  market that is closed but still in dispute, and the market simply waits for
  the next tick. A stuck market is a monitoring problem; a wrongly graded one
  is a refund exercise across every slip that touched it, against an
  append-only ledger.
* **One market's failure is one market's failure.** Fetches run under a
  semaphore and are collected individually.
* **Grading and settlement are separate transactions.** A crash between them
  leaves a fully-graded slip nobody paid, which the settleable-slip sweep picks
  up on the next tick.
* **Settlement is per slip.** One slip that cannot settle must not roll back
  the payouts of the others in the batch.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field

import httpx

from .. import db
from ..clients.http import get_json
from ..clients.resolution import ResolutionReading, read_resolution
from ..config import Settings
from ..repositories import markets as markets_repo
from ..repositories.markets import ResolvableMarket
from .locks import single_flight

logger = logging.getLogger(__name__)

JOB_NAME = "polymarket_resolution"


@dataclass
class ResolutionReport:
    ran: bool
    duration_seconds: float = 0.0
    markets_checked: int = 0
    markets_resolved: int = 0
    markets_pending: int = 0
    fetch_failures: int = 0
    slips_settled: int = 0
    slips_still_open: int = 0
    settlement_failures: int = 0
    outcomes: dict[str, int] = field(default_factory=dict)
    overdue_markets: int = 0


@dataclass(frozen=True, slots=True)
class _Checked:
    market: ResolvableMarket
    reading: ResolutionReading


async def _check_one(
    client: httpx.AsyncClient,
    settings: Settings,
    market: ResolvableMarket,
    semaphore: asyncio.Semaphore,
) -> _Checked | Exception:
    async with semaphore:
        try:
            payload = await get_json(
                client,
                f"{settings.gamma_api_url}/markets/{market.polymarket_market_id}",
                max_retries=settings.http_max_retries,
            )
        except Exception as exc:  # noqa: BLE001 - one market must not fail the batch
            return exc
        return _Checked(
            market=market, reading=read_resolution(payload, yes_token_id=market.yes_token_id)
        )


async def run_resolution(client: httpx.AsyncClient, settings: Settings) -> ResolutionReport:
    async with single_flight(JOB_NAME) as owner:
        if not owner:
            return ResolutionReport(ran=False)

        started = time.monotonic()

        async with db.acquire() as conn:
            due = await markets_repo.list_markets_awaiting_resolution(
                conn, limit=settings.resolution_batch_size
            )

        report = ResolutionReport(ran=True, markets_checked=len(due))
        touched: set[uuid.UUID] = set()

        if due:
            semaphore = asyncio.Semaphore(settings.resolution_concurrency)
            results = await asyncio.gather(
                *(_check_one(client, settings, market, semaphore) for market in due)
            )

            for outcome in results:
                if isinstance(outcome, Exception):
                    report.fetch_failures += 1
                    logger.warning("could not reach Gamma for a market: %s", outcome)
                    continue

                reading = outcome.reading
                if reading.resolution is None:
                    report.markets_pending += 1
                    logger.debug(
                        "market %s not gradeable: %s",
                        outcome.market.polymarket_market_id,
                        reading.reason,
                    )
                    continue

                try:
                    async with db.transaction() as conn:
                        slips = await markets_repo.resolve_market(
                            conn,
                            outcome.market.id,
                            reading.resolution,
                            source="polymarket_gamma",
                        )
                except Exception:
                    report.fetch_failures += 1
                    logger.exception(
                        "failed to record resolution for market %s",
                        outcome.market.polymarket_market_id,
                    )
                    continue

                report.markets_resolved += 1
                report.outcomes[reading.resolution] = report.outcomes.get(reading.resolution, 0) + 1
                touched.update(slips)
                logger.info(
                    "resolved %s as %s (%s); %s slip(s) touched",
                    outcome.market.polymarket_market_id,
                    reading.resolution,
                    reading.reason,
                    len(slips),
                )

        async with db.acquire() as conn:
            orphans = await markets_repo.list_settleable_slips(
                conn, limit=settings.resolution_settle_batch_size
            )
        pending_settlement = touched.union(orphans)

        for prediction_id in pending_settlement:
            try:
                async with db.transaction() as conn:
                    status = await markets_repo.settle_slip(conn, prediction_id)
            except Exception:
                report.settlement_failures += 1
                logger.exception("failed to settle slip %s", prediction_id)
                continue

            if status == "PENDING":
                report.slips_still_open += 1
            else:
                report.slips_settled += 1

        async with db.acquire() as conn:
            report.overdue_markets = await markets_repo.count_overdue_markets(
                conn, older_than_hours=settings.resolution_overdue_hours
            )

        report.duration_seconds = round(time.monotonic() - started, 3)

        if report.settlement_failures or report.fetch_failures:
            logger.error("resolution completed with failures: %s", asdict(report))
        elif report.markets_resolved or report.slips_settled:
            logger.info("resolution complete: %s", asdict(report))

        if report.overdue_markets:
            logger.warning(
                "%s market(s) have been awaiting resolution for over %sh",
                report.overdue_markets,
                settings.resolution_overdue_hours,
            )

        return report
