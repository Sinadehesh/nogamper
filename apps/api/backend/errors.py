from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse

from .engine.quoting import QuoteError
from .repositories.articles import ArticleError
from .repositories.auth import AccountError, AccountSuspended
from .repositories.messages import MessageError
from .repositories.players import PlayerAdminError
from .repositories.predictions import PlacementError
from .repositories.safer_play import SaferPlayError
from .repositories.shop import ShopError
from .security.ratelimit import RateLimited
from .security.tokens import TokenError
from .services.economy import EconomyError


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

    @app.exception_handler(TokenError)
    async def _token(_: Request, exc: TokenError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"code": exc.code, "detail": exc.detail},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(RateLimited)
    async def _rate_limited(_: Request, exc: RateLimited) -> JSONResponse:
        """429 with the wait, in both the header and the body.

        The header is the standard place and the one a generic client reads;
        the body repeats it because the web tier forwards bodies and not
        headers, and the form needs the number to say something more useful
        than "try again later".
        """
        return JSONResponse(
            status_code=429,
            content={
                "code": "rate_limited",
                "detail": "Too many attempts. Wait a little and try again.",
                "retry_after": exc.retry_after,
            },
            headers={"Retry-After": str(exc.retry_after)},
        )

    @app.exception_handler(AccountError)
    async def _account(_: Request, exc: AccountError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content={"code": exc.code, "detail": exc.detail}
        )

    @app.exception_handler(QuoteError)
    async def _quote(_: Request, exc: QuoteError) -> JSONResponse:
        body = {"code": exc.code, "detail": exc.detail}
        if exc.market_id:
            body["market_id"] = exc.market_id
        return JSONResponse(status_code=409 if exc.code == "odds_moved" else 400, content=body)

    _PLACEMENT_STATUS = {
        "insufficient_funds": 402,
        "idempotency_key_reused": 409,
        "account_restricted": 403,
        "daily_limit_reached": 403,
        "on_break": 403,
    }

    @app.exception_handler(PlacementError)
    async def _placement(_: Request, exc: PlacementError) -> JSONResponse:
        body = {"code": exc.code, "detail": exc.detail}
        if exc.market_id:
            body["market_id"] = exc.market_id
        if exc.until is not None:
            body["until"] = exc.until.isoformat()
        return JSONResponse(status_code=_PLACEMENT_STATUS.get(exc.code, 400), content=body)

    @app.exception_handler(SaferPlayError)
    async def _safer_play(_: Request, exc: SaferPlayError) -> JSONResponse:
        body = {"code": exc.code, "detail": exc.detail}
        if exc.until is not None:
            body["until"] = exc.until.isoformat()
        return JSONResponse(status_code=exc.status, content=body)

    @app.exception_handler(ShopError)
    async def _shop(_: Request, exc: ShopError) -> JSONResponse:
        body = {"code": exc.code, "detail": exc.detail}
        if exc.until is not None:
            body["until"] = exc.until.isoformat()
        return JSONResponse(status_code=exc.status, content=body)

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

    @app.exception_handler(ArticleError)
    async def _article(_: Request, exc: ArticleError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content={"code": exc.code, "detail": exc.detail}
        )

    @app.exception_handler(EconomyError)
    async def _economy(_: Request, exc: EconomyError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content={"code": exc.code, "detail": exc.detail}
        )

    @app.exception_handler(AccountSuspended)
    async def _suspended(_: Request, exc: AccountSuspended) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"code": "account_suspended", "detail": str(exc)},
        )
