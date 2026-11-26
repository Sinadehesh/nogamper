"""Write down how each job's last run went.

This exists because of a pattern rather than a bug. Four times now the app has
gone quiet, and four times the evidence that would have named the cause in one
look was a line in a worker log — while the person who needed it was holding a
phone with Telegram open. The diagnostics endpoint could say *which layer* was
at fault, because it reads live state. It could not say why, because "why" is
the failure census from the last pass, and that lived only in the log.

So every scheduled run records its own report. The wrapper is applied in the
scheduler rather than inside each job, so a job cannot be added later and
quietly not be covered, and so a job that raises is recorded too — the run that
raises is the one most worth having a record of.

**Recording never fails a job.** A diagnostics write that breaks the thing it
is observing would be worse than no diagnostics: the pass has already done its
real work by the time this runs, and losing that to a bookkeeping error would
be an own goal.

**A skipped run is not recorded.** Every replica ticks and all but one return
immediately without the lease; writing those would overwrite the last real run
with "another container is doing it", which is exactly the information nobody
needs.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import Any

from .. import db
from .locks import instance_note

logger = logging.getLogger(__name__)

_UPSERT = """
INSERT INTO job_runs (job_name, started_at, finished_at, duration_seconds,
                      outcome, detail, holder_note)
VALUES ($1, $2, NOW(), $3, $4, $5::jsonb, $6)
ON CONFLICT (job_name) DO UPDATE SET
    started_at       = EXCLUDED.started_at,
    finished_at      = EXCLUDED.finished_at,
    duration_seconds = EXCLUDED.duration_seconds,
    outcome          = EXCLUDED.outcome,
    detail           = EXCLUDED.detail,
    holder_note      = EXCLUDED.holder_note
"""


def _detail(report: object) -> dict[str, Any]:
    if is_dataclass(report) and not isinstance(report, type):
        return asdict(report)
    if isinstance(report, dict):
        return report
    return {"result": str(report)}


async def record(
    job_name: str, *, started_at: datetime, seconds: float, outcome: str, detail: dict[str, Any]
) -> None:
    try:
        async with db.transaction() as conn:
            await conn.execute(
                _UPSERT,
                job_name,
                started_at,
                round(seconds, 3),
                outcome,
                json.dumps(detail, default=str),
                instance_note(),
            )
    except Exception:
        logger.warning("could not record the run of %s", job_name, exc_info=True)


def recorded(job_name: str, func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Wrap a scheduled job so its outcome is written down either way."""

    async def run(*args: object, **kwargs: object) -> Any:
        started_at = datetime.now(UTC)
        clock = time.monotonic()
        try:
            report = await func(*args, **kwargs)
        except TimeoutError as exc:
            await record(
                job_name,
                started_at=started_at,
                seconds=time.monotonic() - clock,
                outcome="deadline",
                detail={"error": str(exc) or "the run passed its deadline"},
            )
            raise
        except Exception as exc:
            await record(
                job_name,
                started_at=started_at,
                seconds=time.monotonic() - clock,
                outcome="error",
                detail={"error": f"{type(exc).__name__}: {exc}"},
            )
            raise

        if getattr(report, "ran", True) is False:
            return report

        detail = _detail(report)
        await record(
            job_name,
            started_at=started_at,
            seconds=time.monotonic() - clock,
            outcome="deadline" if detail.get("error") == "deadline_exceeded" else "ok",
            detail=detail,
        )
        return report

    run.__name__ = getattr(func, "__name__", job_name)
    return run
