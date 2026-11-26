"""The one scheduled economy job: the leaderboard rollup.

It used to share this file with two others — a charge on accounts that had
gone quiet and a generator of short-lived better prices. Both existed to bring
people back, and both are gone; see services/economy.py.

The daily top-up is not here either: it is player-triggered, at
`POST /v1/economy/claim`.

The job takes the same lease the other workers use, so N replicas ticking at
the same moment produce one run, and it is wrapped so a failure is logged and
contained: a job that throws must not take the scheduler with it. The rollup
recomputes every row from settled slips, so a half-finished run is safe to
repeat.
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

JOB_NAME = "leaderboard_rollup"


@dataclass
class LeaderboardJobReport:
    ran: bool
    duration_seconds: float = 0.0
    leaderboard: dict | None = None
    error: str | None = None


async def run_leaderboard_rollup(settings: Settings) -> LeaderboardJobReport:
    async with single_flight(JOB_NAME) as owner:
        if not owner:
            return LeaderboardJobReport(ran=False)

        started = time.monotonic()
        report = LeaderboardJobReport(ran=True)

        try:
            async with db.transaction() as conn:
                board = await economy.roll_up_leaderboard(conn, settings)
            report.leaderboard = asdict(board)
        except Exception as exc:  # noqa: BLE001 - contain it; the next tick retries
            logger.exception("leaderboard rollup failed")
            report.error = str(exc)

        report.duration_seconds = round(time.monotonic() - started, 3)

        if report.error:
            logger.error("leaderboard rollup completed with a failure: %s", asdict(report))
        else:
            logger.info("leaderboard rollup complete: %s", asdict(report))
        return report
