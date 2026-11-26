"""Logging setup.

Without this the workers' reports vanish: `logging.lastResort` only emits
WARNING and above, so every "discovery complete" line — the one number that
tells you whether ingestion is healthy — is dropped. A background worker whose
successes are invisible is a worker you find out about only when it has been
broken for a week.
"""

from __future__ import annotations

import logging
import sys

from .config import Settings

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(message)s"


def configure_logging(settings: Settings) -> None:
    root = logging.getLogger()
    if any(getattr(h, "_app_handler", False) for h in root.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler._app_handler = True  # type: ignore[attr-defined]

    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
