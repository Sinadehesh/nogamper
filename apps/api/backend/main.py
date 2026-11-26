from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .cache import prices as price_cache
from .clients.http import build_client
from .config import get_settings
from .errors import install_error_handlers
from .logging_config import configure_logging
from .routers import (
    admin,
    auth,
    economy,
    health,
    markets,
    me,
    messages,
    predictions,
)
from .workers.scheduler import build_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bring up shared clients, then the scheduler; tear down in reverse.

    The scheduler starts last and stops first, so the workers never run
    against a pool or a Redis connection that is already closing. Jobs are
    coroutines on the same event loop as the API — AsyncIOScheduler does not
    spawn threads for them — so nothing here blocks request handling, and any
    job that needs CPU rather than I/O must be moved off this loop.
    """
    settings = get_settings()
    configure_logging(settings)
    settings.require_secrets()

    await db.connect(settings)
    await price_cache.connect(settings)
    app.state.http = build_client(settings)

    if not settings.internal_api_key:
        logger.warning(
            "INTERNAL_API_KEY is not set: sign-up and sign-in are open to any caller and "
            "throttled by socket address. Fine on one machine; not for a deployment."
        )
    if not settings.admin_player_codes:
        logger.info("ADMIN_PLAYER_CODES is empty: the admin pages answer 404 to everyone")

    app.state.scheduler = None
    if settings.workers_enabled:
        app.state.scheduler = build_scheduler(app.state.http, settings)
        app.state.scheduler.start()
        logger.info(
            "workers enabled: discovery every %sm, price sync every %ss",
            settings.discovery_interval_minutes,
            settings.price_sync_interval_seconds,
        )

    try:
        yield
    finally:
        if app.state.scheduler is not None:
            app.state.scheduler.shutdown(wait=True)
        await app.state.http.aclose()
        await price_cache.disconnect()
        await db.disconnect()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )

    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(me.router)
    app.include_router(markets.router)
    app.include_router(predictions.router)
    app.include_router(economy.router)
    app.include_router(messages.router)
    app.include_router(admin.router)
    return app


app = create_app()
