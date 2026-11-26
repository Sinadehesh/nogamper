"""The operator's view: who is here, what they wrote, and whether it is working.

Hidden behind an allowlist of player codes and answering 404 to everyone else
— see security/dependencies.current_admin for why 404 rather than 403.

There is no revenue report here because there is no revenue. What the operator
can do is deliberately small: read the roster, correct a balance, suspend an
account that is abusing the place, and answer a message.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from .. import db
from ..cache import prices as price_cache
from ..config import Settings, get_settings
from ..repositories import analytics, diagnostics
from ..repositories import messages as messages_repo
from ..repositories import players as players_repo
from ..schemas import (
    AdjustRequest,
    AdjustResult,
    DiagnosticsOut,
    InboxItemOut,
    InboxOut,
    JobLeaseOut,
    JobRunOut,
    LedgerFlowOut,
    MessageOut,
    Money,
    OverviewDay,
    OverviewForecasts,
    OverviewOut,
    OverviewPlayers,
    OverviewPoints,
    OverviewSaferPlay,
    PlayerList,
    PlayerOut,
    ReplyRequest,
    ReplyResult,
    ResolveRequest,
    StatusRequest,
    StatusResult,
)
from ..security.dependencies import CurrentAdmin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/admin", tags=["admin"])

_GRANTED = frozenset(
    {
        "SIGNUP_BONUS_CREDIT",
        "DAILY_DRIP_CREDIT",
        # Kept in the sum so a window that reaches back before the website
        # still adds up. Nothing posts any of these any more.
        "STREAK_BONUS_CREDIT",
        "SEASON_PRIZE_CREDIT",
        "PROMO_CREDIT",
        "REFERRAL_BONUS_CREDIT",
    }
)

_STAKED = frozenset({"STAKE_DEBIT", "INSURANCE_PREMIUM_DEBIT"})
_RETURNED = frozenset({"PAYOUT_CREDIT", "INSURANCE_CREDIT", "VOID_REFUND_CREDIT"})


def _sum_of(ledger: list[analytics.LedgerFlow], types: frozenset[str] | str) -> int:
    wanted = {types} if isinstance(types, str) else types
    return sum(row.net for row in ledger if row.entry_type in wanted)


@router.get(
    "/overview",
    response_model=OverviewOut,
    summary="Who is here, what they forecast, and where points went",
)
async def read_overview(
    _: CurrentAdmin,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> OverviewOut:
    since = datetime.now(UTC) - timedelta(days=days)

    async with db.acquire() as conn:
        report = await analytics.load_overview(conn, since=since, window_days=days)

    return OverviewOut(
        window_days=days,
        since=since,
        generated_at=datetime.now(UTC),
        players=OverviewPlayers(
            total=report.players.total,
            registered=report.players.registered,
            guests=report.players.guests,
            new_in_window=report.players.new_in_window,
            forecast_in_window=report.players.forecast_in_window,
            claimed_in_window=report.players.claimed_in_window,
        ),
        forecasts=OverviewForecasts(
            placed=report.forecasts.placed,
            settled=report.forecasts.settled,
            won=report.forecasts.won,
            lost=report.forecasts.lost,
            open=report.forecasts.open,
        ),
        points=OverviewPoints(
            granted=Money.of(_sum_of(report.ledger, _GRANTED)),
            staked=Money.of(-_sum_of(report.ledger, _STAKED)),
            returned=Money.of(_sum_of(report.ledger, _RETURNED)),
            adjusted=Money.of(_sum_of(report.ledger, "ADMIN_ADJUSTMENT")),
            net_change=Money.of(sum(row.net for row in report.ledger)),
        ),
        safer_play=OverviewSaferPlay(
            with_daily_limit=report.safer_play.with_daily_limit,
            on_break=report.safer_play.on_break,
            erased=report.safer_play.erased,
        ),
        daily=[
            OverviewDay(
                day=d.day,
                new_players=d.new_players,
                forecasts=d.forecasts,
                forecasters=d.forecasters,
            )
            for d in report.daily
        ],
        ledger=[
            LedgerFlowOut(
                entry_type=row.entry_type,
                net=Money.of(row.net),
                entries=row.entries,
                players=row.players,
            )
            for row in report.ledger
        ],
    )


@router.get("/players", response_model=PlayerList, summary="Every player, and how they are doing")
async def read_players(
    _: CurrentAdmin,
    search: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PlayerList:
    async with db.acquire() as conn:
        rows, total = await players_repo.list_players(
            conn, search=search or None, limit=limit, offset=offset
        )

    return PlayerList(
        players=[
            PlayerOut(
                id=str(p.id),
                player_code=p.player_code,
                display_name=p.display_name,
                email=p.email,
                is_guest=p.is_guest,
                status=p.status,
                balance=Money.of(p.balance),
                staked=Money.of(p.staked),
                returned=Money.of(p.returned),
                net=Money.of(p.net),
                granted=Money.of(p.granted),
                adjusted=Money.of(p.adjusted),
                slips=p.slips,
                won=p.won,
                lost=p.lost,
                open_slips=p.open_slips,
                daily_limit=Money.of(p.daily_limit) if p.daily_limit is not None else None,
                break_until=p.break_until,
                created_at=p.created_at,
                last_seen_at=p.last_seen_at,
            )
            for p in rows
        ],
        total=total,
    )


@router.post("/players/adjust", response_model=AdjustResult, summary="Credit or debit a player")
async def adjust_player(payload: AdjustRequest, _: CurrentAdmin) -> AdjustResult:
    """Posted as an ADMIN_ADJUSTMENT ledger entry, never as an UPDATE to
    users.coin_balance — that column is a cache the ledger trigger owns, and
    writing it directly puts the cache and the ledger permanently out of step.

    A debit past zero is refused rather than clamped. The operator cannot take
    points that are not there; the alternative is a negative balance nothing
    in the schema is prepared for.
    """
    async with db.transaction() as conn:
        code, balance = await players_repo.adjust_balance(
            conn,
            player_code=payload.player_code,
            amount_minor=payload.amount_minor,
            reason=payload.reason,
            reference=payload.reference,
        )
    return AdjustResult(player_code=code, balance=Money.of(balance))


@router.post("/players/status", response_model=StatusResult, summary="Ban or reinstate a player")
async def set_player_status(payload: StatusRequest, _: CurrentAdmin) -> StatusResult:
    """Banning revokes live sessions as well as setting the status.

    current_user re-reads the row on every request, so the status alone would
    take effect — revoking is what makes it immediate rather than "as soon as
    they happen to reload".
    """
    async with db.transaction() as conn:
        status = await players_repo.set_status(
            conn, player_code=payload.player_code, status=payload.status
        )
    return StatusResult(player_code=payload.player_code.upper(), status=status)


@router.get("/messages", response_model=InboxOut, summary="What players have written")
async def read_inbox(
    _: CurrentAdmin,
    status: Annotated[str | None, Query(pattern="^(NEW|SEEN|ANSWERED)$")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InboxOut:
    async with db.acquire() as conn:
        items, unread, total = await messages_repo.inbox(
            conn, status=status, limit=limit, offset=offset
        )

    return InboxOut(
        messages=[
            InboxItemOut(
                id=str(m.id),
                kind=m.kind,
                status=m.status,
                body=m.body,
                created_at=m.created_at,
                answered_at=m.answered_at,
                reply_body=m.reply_body,
                replied_at=m.replied_at,
                admin_note=m.admin_note,
                player_code=m.player_code,
                display_name=m.first_name,
                is_guest=m.is_guest,
                balance=Money.of(m.balance),
                player_status=m.player_status,
            )
            for m in items
        ],
        unread=unread,
        total=total,
    )


@router.post("/messages/{message_id}", response_model=MessageOut, summary="Triage one message")
async def resolve_message(
    message_id: uuid.UUID, payload: ResolveRequest, _: CurrentAdmin
) -> MessageOut:
    async with db.transaction() as conn:
        await messages_repo.resolve(
            conn, message_id=message_id, status=payload.status, note=payload.note
        )
        rows = await conn.fetchrow(
            "SELECT id, kind::text AS kind, status::text AS status, body, created_at, "
            "answered_at, reply_body, replied_at FROM player_messages WHERE id = $1",
            message_id,
        )

    return MessageOut(
        id=str(rows["id"]),
        kind=rows["kind"],
        status=rows["status"],
        body=rows["body"],
        created_at=rows["created_at"],
        answered_at=rows["answered_at"],
        reply_body=rows["reply_body"],
        replied_at=rows["replied_at"],
    )


@router.post(
    "/messages/{message_id}/reply",
    response_model=ReplyResult,
    summary="Answer a player",
)
async def reply_to_message(
    message_id: uuid.UUID,
    payload: ReplyRequest,
    _: CurrentAdmin,
) -> ReplyResult:
    """Write the operator's answer. The player reads it in the app.

    Nothing is pushed anywhere. The reply used to go out through a chat bot;
    the website has no channel like that and deliberately does not invent one
    out of email — an address here is whatever somebody typed, and mailing an
    answer to it is how a support box becomes a way to write to strangers.
    """
    async with db.transaction() as conn:
        message = await messages_repo.record_reply(conn, message_id=message_id, body=payload.body)

    return ReplyResult(
        id=str(message.id),
        status=message.status,
        reply_body=message.reply_body or "",
        replied_at=message.replied_at or datetime.now(UTC),
    )


@router.get(
    "/diagnostics",
    response_model=DiagnosticsOut,
    summary="Whether the database, the worker, the upstream or the cache is at fault",
)
async def read_diagnostics(
    _: CurrentAdmin,
    settings: Annotated[Settings, Depends(get_settings)],
) -> DiagnosticsOut:
    """The endpoint that exists so the next outage takes one request.

    Every previous occurrence of "this price is updating" presented
    identically and had a different cause — a stranded advisory lock, then a
    job that ran for minutes while its heartbeat held the lease shut. The app
    told players it was updating and told the operator nothing, so each one
    was diagnosed by reading code.

    The evidence that separates those cases is small and cheap: how long since
    a price landed, whether a job holds its lease and for how long, and whether
    Redis agrees with Postgres.
    """
    async with db.acquire() as conn:
        health, sampled = await diagnostics.read_price_health(
            conn, staleness_seconds=settings.price_staleness_seconds
        )

    cache_reachable, cache_hits = True, 0
    try:
        cached = await price_cache.read_many(sampled) if sampled else {}
        cache_hits = len(cached)
    except Exception:
        cache_reachable = False

    health = replace(
        health, cache_reachable=cache_reachable, cache_hits=cache_hits, cache_sampled=len(sampled)
    )
    layer, advice = diagnostics.explain(
        health,
        staleness_seconds=settings.price_staleness_seconds,
        max_markets=settings.price_sync_max_markets,
    )

    return DiagnosticsOut(
        layer=layer,
        advice=advice,
        staleness_threshold_seconds=settings.price_staleness_seconds,
        markets_budget=settings.price_sync_max_markets,
        markets_total=health.markets_total,
        markets_active=health.markets_active,
        markets_locked=health.markets_locked,
        markets_fresh=health.markets_fresh,
        markets_stale=health.markets_stale,
        newest_price_at=health.newest_price_at,
        oldest_price_at=health.oldest_price_at,
        seconds_since_newest=health.seconds_since_newest,
        cache_reachable=health.cache_reachable,
        cache_sampled=health.cache_sampled,
        cache_hits=health.cache_hits,
        leases=[
            JobLeaseOut(
                job_name=job.job_name,
                holder=job.holder_note,
                held_for_seconds=round(job.held_for_seconds, 1),
                expires_in_seconds=round(job.expires_in_seconds, 1),
            )
            for job in health.leases
        ],
        runs=[
            JobRunOut(
                job_name=run.job_name,
                outcome=run.outcome,
                duration_seconds=round(run.duration_seconds, 1),
                finished_ago_seconds=round(run.finished_ago_seconds, 1),
                holder=run.holder_note,
                detail=run.detail,
            )
            for run in health.runs
        ],
        generated_at=datetime.now(UTC),
    )
