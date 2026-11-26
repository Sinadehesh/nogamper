"""Scheduled economy jobs: decay, boost generation, leaderboard rollup.

The daily drip is not here — it is player-triggered, at
`POST /v1/economy/claim`. A gift that arrives without being opened is not a
retention loop; the tap is the point.

Each job takes the same Postgres advisory lock the other workers use, so N API
replicas ticking at the same moment produce one run. Each is also wrapped so a
failure is logged and contained: an economy job that throws must not take the
scheduler's thread with it, and the next tick should find the world in a state
it can still work with. Every write is idempotent per (user, day), so a
half-finished run is safe to repeat.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass

from .. import db
from ..config import Settings
from ..services import economy
from .locks import single_flight

logger = logging.getLogger(__name__)

DAILY_JOB_NAME = "economy_daily"
BOOST_JOB_NAME = "economy_boosts"


@dataclass
class DailyEconomyReport:
    ran: bool
    duration_seconds: float = 0.0
    decay: dict | None = None
    leaderboard: dict | None = None
    errors: list[str] | None = None


async def run_daily_economy(settings: Settings) -> DailyEconomyReport:
    """Inactivity decay, then the leaderboard rollup.

    Separate transactions on purpose: a rollup that fails must not roll back
    decay charges that already committed, and the two have nothing to do with
    each other beyond sharing a schedule.
    """
    async with single_flight(DAILY_JOB_NAME) as owner:
        if not owner:
            return DailyEconomyReport(ran=False)

        started = time.monotonic()
        report = DailyEconomyReport(ran=True, errors=[])

        try:
            async with db.transaction() as conn:
                decay = await economy.run_inactivity_decay(conn, settings)
            report.decay = asdict(decay)
        except Exception as exc:  # noqa: BLE001 - one job must not sink the other
            logger.exception("inactivity decay failed")
            report.errors.append(f"decay: {exc}")

        try:
            async with db.transaction() as conn:
                board = await economy.roll_up_leaderboard(conn, settings)
            report.leaderboard = asdict(board)
        except Exception as exc:  # noqa: BLE001
            logger.exception("leaderboard rollup failed")
            report.errors.append(f"leaderboard: {exc}")

        report.duration_seconds = round(time.monotonic() - started, 3)

        if report.errors:
            logger.error("daily economy completed with failures: %s", asdict(report))
        else:
            logger.info("daily economy complete: %s", asdict(report))
        return report


@dataclass
class BoostJobReport:
    ran: bool
    duration_seconds: float = 0.0
    boosts: dict | None = None
    error: str | None = None


async def run_boost_generation(settings: Settings) -> BoostJobReport:
    async with single_flight(BOOST_JOB_NAME) as owner:
        if not owner:
            return BoostJobReport(ran=False)

        started = time.monotonic()
        try:
            async with db.transaction() as conn:
                boosts = await economy.generate_boosts(conn, settings)
        except Exception as exc:  # noqa: BLE001
            logger.exception("boost generation failed")
            return BoostJobReport(
                ran=True, duration_seconds=round(time.monotonic() - started, 3), error=str(exc)
            )

        report = BoostJobReport(
            ran=True,
            duration_seconds=round(time.monotonic() - started, 3),
            boosts=asdict(boosts),
        )
        if boosts.created:
            logger.info("boost generation complete: %s", asdict(report))
        return report
