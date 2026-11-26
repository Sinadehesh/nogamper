from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse

from .engine.quoting import QuoteError
from .repositories.auth import AccountSuspended
from .repositories.messages import MessageError
from .repositories.players import PlayerAdminError
from .repositories.predictions import PlacementError
from .security.telegram import InitDataError
from .security.tokens import TokenError
from .services.economy import EconomyError
from .services.payment_service import PaymentError
from .services.rewards import RewardError


def install_error_handlers(app) -> None:
    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException):
        """Keep one error envelope across the whole API.

        FastAPI nests `detail` under a "detail" key, so a route raising
        HTTPException(detail={"code": ...}) answered in a different shape
        from every handler below. Flatten it so clients can always read
        `code` off the top level.
        """
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code, content=exc.detail, headers=exc.headers
            )
        return await http_exception_handler(request, exc)

    @app.exception_handler(InitDataError)
    async def _init_data(_: Request, exc: InitDataError) -> JSONResponse:
        return JSONResponse(status_code=401, content={"code": exc.code, "detail": exc.detail})

    @app.exception_handler(TokenError)
    async def _token(_: Request, exc: TokenError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"code": exc.code, "detail": exc.detail},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(QuoteError)
    async def _quote(_: Request, exc: QuoteError) -> JSONResponse:
        body = {"code": exc.code, "detail": exc.detail}
        if exc.market_id:
            body["market_id"] = exc.market_id
        if exc.required_legs is not None:
            body["required_legs"] = exc.required_legs
        return JSONResponse(status_code=409 if exc.code == "odds_moved" else 400, content=body)

    _PLACEMENT_STATUS = {
        "insufficient_funds": 402,
        "idempotency_key_reused": 409,
        "account_restricted": 403,
        "daily_limit_reached": 403,
        "market_at_capacity": 409,
        "boost_exhausted": 409,
        "boost_limit_reached": 409,
    }

    @app.exception_handler(PlacementError)
    async def _placement(_: Request, exc: PlacementError) -> JSONResponse:
        body = {"code": exc.code, "detail": exc.detail}
        if exc.market_id:
            body["market_id"] = exc.market_id
        return JSONResponse(status_code=_PLACEMENT_STATUS.get(exc.code, 400), content=body)

    @app.exception_handler(PlayerAdminError)
    async def _player_admin(_: Request, exc: PlayerAdminError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content={"code": exc.code, "detail": exc.detail}
        )

    @app.exception_handler(MessageError)
    async def _message(_: Request, exc: MessageError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content={"code": exc.code, "detail": exc.detail}
        )

    @app.exception_handler(PaymentError)
    async def _payment(_: Request, exc: PaymentError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content={"code": exc.code, "detail": exc.detail}
        )

    @app.exception_handler(EconomyError)
    async def _economy(_: Request, exc: EconomyError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content={"code": exc.code, "detail": exc.detail}
        )

    @app.exception_handler(RewardError)
    async def _reward(_: Request, exc: RewardError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content={"code": exc.code, "detail": exc.detail}
        )

    @app.exception_handler(AccountSuspended)
    async def _suspended(_: Request, exc: AccountSuspended) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"code": "account_suspended", "detail": str(exc)},
        )
