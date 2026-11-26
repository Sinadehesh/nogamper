"""The operator's view: what came in, and whether the economy is tuned for it.

Hidden behind an allowlist of Telegram ids and answering 404 to everyone else
— see security/dependencies.current_admin for why 404 rather than 403.

## Why the derived numbers are computed here rather than in SQL

Break-even, house edge and conversion are all *interpretations* of the raw
sums: they depend on the current vig, the current drip, and on which ledger
entry types count as wagering. Those change. Keeping the arithmetic in Python
next to the settings that feed it means a retune shows up in the report on the
next deploy, rather than requiring somebody to remember that a constant is also
buried in a query.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from .. import db
from ..cache import prices as price_cache
from ..clients import telegram
from ..config import Settings, get_settings
from ..repositories import analytics, diagnostics
from ..repositories import messages as messages_repo
from ..repositories import players as players_repo
from ..schemas import (
    AdjustRequest,
    AdjustResult,
    BreakEvenBucketOut,
    DiagnosticsOut,
    EconomyBalance,
    EconomyReportOut,
    InboxItemOut,
    InboxOut,
    JobLeaseOut,
    JobRunOut,
    LedgerFlowOut,
    MessageOut,
    Money,
    PackageSalesOut,
    PlayerBlock,
    PlayerList,
    PlayerOut,
    ReplyRequest,
    ReplyResult,
    ResolveRequest,
    RevenueBlock,
    RevenueDay,
    StatusRequest,
    StatusResult,
)
from ..security.dependencies import CurrentAdmin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/admin", tags=["admin"])

_FREE_MINT = frozenset(
    {
        "SIGNUP_BONUS_CREDIT",
        "DAILY_DRIP_CREDIT",
        "STREAK_BONUS_CREDIT",
        "SEASON_PRIZE_CREDIT",
        "PROMO_CREDIT",
    }
)

_WAGERING = frozenset(
    {
        "STAKE_DEBIT",
        "INSURANCE_PREMIUM_DEBIT",
        "PAYOUT_CREDIT",
        "INSURANCE_CREDIT",
        "VOID_REFUND_CREDIT",
    }
)


def _house_edge(settings: Settings) -> float:
    """The house's expected share of a stake, given the shortest allowed slip.

    Not `vig_rate`. The vig is charged per *leg* and the legs multiply, so the
    house's expected share of an n-leg slip is `1 - (1 - vig)^n`:

        1 leg   5.0%      3 legs  14.3%
        2 legs  9.8%      5 legs  22.6%

    Using the raw vig here was wrong the moment MIN_LEGS stopped being 1 —
    it under-states the take by roughly three times at the shipped default,
    and everything derived from it inherits the error.
    """
    return 1.0 - (1.0 - settings.vig_rate) ** settings.min_legs


def _break_even_daily_stake(settings: Settings) -> int:
    """The stake rate at which free coins exactly cover what the house takes.

    A player earning `drip + max streak bonus` a day and losing the house edge
    on everything they stake is self-sustaining at

        (drip + streak) / house_edge

    and below it they can play forever without spending a Star. This is the
    single number the whole free-to-play model turns on, so it is derived from
    the live settings rather than written down anywhere as a constant — retune
    the drip or the leg minimum and the threshold moves with it.

    Note the denominator is the *compounded* edge, not the vig. Mandating
    three-leg slips nearly triples what the house takes per stake, which
    lowers this threshold by the same factor: far more players cross it than
    the vig alone would suggest.
    """
    free_per_day = settings.daily_drip_minor + settings.streak_bonus_max_minor
    edge = _house_edge(settings)
    if edge <= 0:
        return 0
    return round(free_per_day / edge)


def _sum_of(ledger: list[analytics.LedgerFlow], types: frozenset[str] | str) -> int:
    wanted = {types} if isinstance(types, str) else types
    return sum(row.net for row in ledger if row.entry_type in wanted)


@router.get(
    "/economy",
    response_model=EconomyReportOut,
    summary="Revenue, coin flow and whether the economy produces payers",
)
async def read_economy(
    _: CurrentAdmin,
    settings: Annotated[Settings, Depends(get_settings)],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> EconomyReportOut:
    since = datetime.now(UTC) - timedelta(days=days)
    break_even = _break_even_daily_stake(settings)

    async with db.acquire() as conn:
        report = await analytics.load_economy_report(
            conn, since=since, window_days=days, break_even_daily_stake=break_even
        )

    def block(revenue: analytics.Revenue) -> RevenueBlock:
        return RevenueBlock(
            stars_gross=revenue.stars_gross,
            stars_refunded=revenue.stars_refunded,
            stars_net=revenue.stars_net,
            purchases=revenue.purchases,
            refunds=revenue.refunds,
            paying_players=revenue.paying_players,
            coins_sold=Money.of(revenue.coins_sold),
        )

    total_pack_stars = sum(p.stars for p in report.packages)
    packages = [
        PackageSalesOut(
            code=p.code,
            title=p.title,
            stars_price=p.stars_price,
            coins=Money.of(p.coins),
            coins_per_star=p.coins_per_star,
            purchases=p.purchases,
            stars=p.stars,
            share_of_stars=round(p.stars / total_pack_stars, 4) if total_pack_stars else 0.0,
        )
        for p in report.packages
    ]

    minted_free = _sum_of(report.ledger, _FREE_MINT)
    minted_purchased = _sum_of(report.ledger, "STAR_PURCHASE_CREDIT")
    house_edge = _sum_of(report.ledger, _WAGERING)
    decayed = _sum_of(report.ledger, "INACTIVITY_DECAY_DEBIT")
    burned = _sum_of(report.ledger, "REWARD_REDEEM_DEBIT")

    balance = EconomyBalance(
        minted_free=Money.of(minted_free),
        minted_purchased=Money.of(minted_purchased),
        house_edge=Money.of(-house_edge),
        decayed=Money.of(-decayed),
        burned_on_rewards=Money.of(-burned),
        net_change=Money.of(sum(row.net for row in report.ledger)),
    )

    active = report.players.staked_in_window
    buckets = [
        BreakEvenBucketOut(
            bucket=b.bucket, players=b.players, daily_stake=Money.of(b.daily_stake_total)
        )
        for b in report.break_even_buckets
    ]
    free_players = sum(
        b.players for b in report.break_even_buckets if b.bucket in {"far_below", "below"}
    )

    return EconomyReportOut(
        window_days=days,
        since=since,
        generated_at=datetime.now(UTC),
        revenue=block(report.revenue),
        lifetime=block(report.lifetime),
        stars_per_day=round(report.revenue.stars_net / days, 2),
        stars_per_paying_player=(
            round(report.revenue.stars_net / report.revenue.paying_players, 2)
            if report.revenue.paying_players
            else 0.0
        ),
        daily=[
            RevenueDay(
                day=d.day,
                stars=d.stars,
                stars_refunded=d.stars_refunded,
                purchases=d.purchases,
                payers=d.payers,
            )
            for d in report.daily
        ],
        packages=packages,
        players=PlayerBlock(
            total=report.players.total,
            new_in_window=report.players.new_in_window,
            staked_in_window=active,
            claimed_in_window=report.players.claimed_in_window,
            conversion_rate=(round(report.revenue.paying_players / active, 4) if active else 0.0),
        ),
        ledger=[
            LedgerFlowOut(
                entry_type=row.entry_type,
                net=Money.of(row.net),
                entries=row.entries,
                players=row.players,
            )
            for row in report.ledger
        ],
        balance=balance,
        break_even_daily_stake=Money.of(break_even),
        break_even_buckets=buckets,
        free_players_share=round(free_players / active, 4) if active else 0.0,
    )


def _display_name(first: str, last: str | None) -> str:
    return f"{first} {last}".strip() if last else first


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
                telegram_id=p.telegram_id,
                username=p.username,
                display_name=_display_name(p.first_name, p.last_name),
                status=p.status,
                balance=Money.of(p.balance),
                lifetime_stars=p.lifetime_stars,
                staked=Money.of(p.staked),
                returned=Money.of(p.returned),
                net=Money.of(p.net),
                bought=Money.of(p.bought),
                granted=Money.of(p.granted),
                adjusted=Money.of(p.adjusted),
                slips=p.slips,
                won=p.won,
                lost=p.lost,
                open_slips=p.open_slips,
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
    coins that are not there; the alternative is a negative balance nothing in
    the schema is prepared for.
    """
    async with db.transaction() as conn:
        code, balance = await players_repo.adjust_balance(
            conn,
            player_code=payload.player_code,
            telegram_id=payload.telegram_id,
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
                reply_delivered=m.reply_delivered,
                player_code=m.player_code,
                username=m.username,
                display_name=m.first_name,
                telegram_id=m.telegram_id,
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
    summary="Answer a player, as the bot",
)
async def reply_to_message(
    message_id: uuid.UUID,
    payload: ReplyRequest,
    request: Request,
    _: CurrentAdmin,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReplyResult:
    """Send the operator's answer to the player, from the bot.

    **The operator's account never appears.** Answering a support message from
    a personal Telegram account hands every player who writes in a name, a
    username and a photo, permanently, in exchange for answering a question
    about a prize. The bot is already a party to this conversation and the
    player already expects to hear from it, so it carries the reply.

    **The reply is recorded whether or not Telegram takes it.** A bot may not
    open a conversation the person has not opened first, so a player who
    launched the Mini App from a link without pressing Start is unreachable —
    403, and no amount of retrying changes it. Losing their answer would be
    worse than not sending it: the operator would believe they had replied.
    So it is written down either way, the player reads it in the app where
    they wrote it, and `delivered` tells the operator which happened.

    The send is deliberately outside the transaction. It is a side effect on
    somebody else's system and cannot be rolled back, so holding a row lock
    across it would buy nothing and block the inbox on Telegram's latency.
    """
    async with db.acquire() as conn:
        target = await messages_repo.load_for_reply(conn, message_id)

    delivered, detail = True, None
    try:
        await telegram.send_message(
            request.app.state.http,
            settings.telegram_bot_token,
            chat_id=target.telegram_id,
            text=payload.body.strip(),
            api_url=settings.telegram_api_url,
        )
    except telegram.TelegramCannotReach as exc:
        delivered = False
        detail = (
            "Telegram will not deliver to this player — they have never started the bot, "
            "or have blocked it. They will see your answer in the app."
        )
        logger.info("reply to %s undeliverable: %s", message_id, exc.description)
    except telegram.TelegramApiError as exc:
        delivered = False
        detail = "Telegram did not accept the message. Your answer is saved and shown in the app."
        logger.warning("reply to %s failed to send: %s", message_id, exc.description)

    async with db.transaction() as conn:
        message = await messages_repo.record_reply(
            conn, message_id=message_id, body=payload.body, delivered=delivered
        )

    return ReplyResult(
        id=str(message.id),
        status=message.status,
        reply_body=message.reply_body or "",
        replied_at=message.replied_at or datetime.now(UTC),
        delivered=delivered,
        delivery_detail=detail,
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
