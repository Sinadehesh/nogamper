"""Questions, for pages anybody can read.

    GET /v1/questions/moves    the questions whose chance changed most
    GET /v1/questions          every question with a page, for the sitemap
    GET /v1/questions/{slug}   one question: what is asked, what the market
                               says, how that has changed, how it ended

Public and unauthenticated, like the rules and the published articles. Every
figure here is the market's own and can be read at its source; nothing about a
player is in it.

**A move is reported, not explained.** These routes say that a chance went
from one number to another, and when. They do not say why, and they do not say
what happens next, because nothing here knows either. The page built on them
is held to the same rule.

**A result is not a move.** A question about to close does not drift, it
collapses, and a list of the biggest changes would otherwise be a list of
questions that had just been decided. See `config.py` for how those are kept
out.

**No list is better than an old one.** A server that has been asleep wakes
with the figures it went to sleep with. Until they have been read again the
list of moves is not sent at all (503), so the site goes on showing the list
it last built, with its date, rather than building a new page out of a day
that is over.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .. import db
from ..cache import history as history_cache
from ..cache import prices as price_cache
from ..clients import clob
from ..config import Settings, get_settings
from ..repositories import questions as questions_repo
from ..schemas import (
    HistoryPoint,
    Move,
    MovesOut,
    QuestionChanges,
    QuestionIndex,
    QuestionIndexItem,
    QuestionOut,
    QuestionState,
)
from ..services.probabilities import PROB_PLACES, current_probability

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/questions", tags=["questions"])

_ADDRESS = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_MAX_ADDRESS = 200
_HISTORY_DAYS = 7
_NOT_READY_RETRY_SECONDS = 60
"""What a caller is told to wait when the figures are being read again. A
fresh read of the question list takes about that long on the smallest server."""
_FAILED_HISTORY_SECONDS = 60
"""How long a failed fetch of a question's history is remembered. Long enough
that an outage at the source is not retried on every page view, short enough
that the chart comes back soon after the source does."""

_STATES: dict[str, QuestionState] = {
    "ACTIVE": "open",
    "LOCKED": "closed",
    "SETTLING": "closed",
    "RESOLVED": "resolved",
    "VOID": "void",
    "DRAFT": "unfollowed",
}


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404, detail={"code": "not_found", "detail": "No such question."}
    )


def _state(row: asyncpg.Record) -> QuestionState:
    # A question its source cancelled is recorded as RESOLVED with a VOID
    # resolution; it has no outcome, and the page should not imply one.
    if row["resolution"] == "VOID":
        return "void"
    return _STATES[row["status"]]


def _places(value: Decimal) -> str:
    return str(value.quantize(PROB_PLACES))


def _change(value: Decimal | None) -> str | None:
    return None if value is None else _places(value)


# ----- what moved -------------------------------------------------------------


async def _moves(
    conn: asyncpg.Connection,
    *,
    window: questions_repo.Window,
    threshold: Decimal,
    settings: Settings,
    now: datetime,
    limit: int,
) -> list[Move]:
    column = "change_24h" if window == "day" else "change_7d"
    rows = await questions_repo.move_candidates(
        conn,
        window=window,
        min_change=threshold,
        closes_after=now + timedelta(hours=settings.moves_min_hours_to_close),
        measured_after=now - timedelta(hours=settings.moves_max_age_hours),
        # More than asked for: some will have come back since they were
        # measured, and some were never open questions to begin with.
        limit=limit * 3,
    )
    cached = await price_cache.read_many([row["id"] for row in rows])

    low = Decimal(str(settings.moves_decided_margin))
    high = Decimal(1) - low
    read_since = now - timedelta(seconds=settings.moves_price_max_age_seconds)

    found: list[tuple[Decimal, Move]] = []
    listed: set[str] = set()
    for row in rows:
        # An address is the source's and need not be unique. One address is
        # one page, so it is listed once: by its largest reported change.
        if row["slug"] in listed:
            continue
        # Where it stood at the start of the window, by the source's own
        # arithmetic; and where it stands now, by the price the game runs on.
        was = min(max(row["change_ref_prob"] - row[column], Decimal(0)), Decimal(1))
        price = cached.get(row["id"])
        if price is not None:
            current, read_at = price.probability, price.captured_at
        else:
            current, read_at = row["raw_yes_prob"], row["price_updated_at"]
        if read_at < read_since:
            continue  # a price nobody has read lately is not where it stands "now"

        if not (low <= was <= high and low <= current <= high):
            continue  # decided, then or now: a result arriving, not a move
        change = current - was
        if abs(change) < threshold:
            continue  # it moved, and has since come most of the way back

        listed.add(row["slug"])
        found.append(
            (
                abs(change),
                Move(
                    slug=row["slug"],
                    question=row["question"],
                    category=row["category"],
                    event_title=row["event_title"],
                    closes_at=row["lock_at"],
                    was=_places(was),
                    now=_places(current),
                    change=_places(change),
                    measured_at=row["changes_at"],
                ),
            )
        )

    found.sort(key=lambda item: item[0], reverse=True)
    return [move for _, move in found[:limit]]


@router.get(
    "/moves",
    response_model=MovesOut,
    responses={503: {"description": "The figures are out of date and being read again."}},
    summary="The questions whose chance changed most",
)
async def read_moves(
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
) -> MovesOut:
    now = datetime.now(UTC)
    day_threshold = Decimal(str(settings.moves_day_threshold))
    week_threshold = Decimal(str(settings.moves_week_threshold))

    async with db.acquire() as conn:
        measured_at, price_at = await questions_repo.newest_readings(conn)
        figures_since = now - timedelta(hours=settings.moves_max_age_hours)
        prices_since = now - timedelta(seconds=settings.moves_price_max_age_seconds)
        # Both halves of "from X to Y" have to be current: where the market
        # says the question stood, and where it stands. A server just woken
        # has neither until it has read them again.
        #
        # Not an empty list: "nothing moved" is a finding, and this is not one.
        # A failure is also something the site's cache does not keep, so the
        # next request asks again instead of being handed this answer back.
        if (
            measured_at is None
            or measured_at < figures_since
            or price_at is None
            or price_at < prices_since
        ):
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "figures_not_current",
                    "detail": "The market's figures are being read again. Try again shortly.",
                    "retry_after": _NOT_READY_RETRY_SECONDS,
                },
                headers={"Retry-After": str(_NOT_READY_RETRY_SECONDS)},
            )
        day = await _moves(
            conn, window="day", threshold=day_threshold, settings=settings, now=now, limit=limit
        )
        week = await _moves(
            conn, window="week", threshold=week_threshold, settings=settings, now=now, limit=limit
        )

    return MovesOut(
        day=day,
        week=week,
        measured_at=measured_at,
        day_threshold=_places(day_threshold),
        week_threshold=_places(week_threshold),
        min_hours_to_close=settings.moves_min_hours_to_close,
        decided_margin=_places(Decimal(str(settings.moves_decided_margin))),
        as_of=now,
    )


# ----- the list, for the sitemap ------------------------------------------------


@router.get("", response_model=QuestionIndex, summary="Every question that has a page")
async def list_questions(
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> QuestionIndex:
    async with db.acquire() as conn:
        rows, total = await questions_repo.index(conn, limit=limit, offset=offset)
    return QuestionIndex(
        questions=[
            QuestionIndexItem(
                slug=row["slug"],
                question=row["question"],
                category=row["category"],
                state=_state(row),
                updated_at=row["updated_at"],
            )
            for row in rows
        ],
        total=total,
    )


# ----- one question ---------------------------------------------------------------


async def _history(
    request: Request, row: asyncpg.Record, settings: Settings, now: datetime
) -> tuple[list[HistoryPoint], str]:
    """A week of prices for the chart, from the best place that has one.

    The source's own hourly history first, through a short-lived cache. If the
    source cannot be reached, or has nothing, this site's own record of the
    prices it saw. If there is neither, no chart: an empty list, said plainly.
    """
    points = await history_cache.read(row["id"])
    if points is None:
        try:
            points = await clob.fetch_price_history(
                request.app.state.http, row["yes_token_id"], settings
            )
            ttl = settings.history_cache_seconds
        except Exception as exc:  # noqa: BLE001 - the page is worth having without its chart
            logger.warning("no price history for %s: %s", row["slug"], type(exc).__name__)
            points, ttl = [], _FAILED_HISTORY_SECONDS
        await history_cache.write(row["id"], points, ttl_seconds=ttl)

    if points:
        return (
            [HistoryPoint(at=point.at, yes=_places(point.probability)) for point in points],
            "source",
        )

    async with db.acquire() as conn:
        own = await questions_repo.own_history(
            conn, row["id"], since=now - timedelta(days=_HISTORY_DAYS)
        )
    if own:
        return [HistoryPoint(at=at, yes=_places(yes)) for at, yes in own], "own"
    return [], "none"


def _changes(row: asyncpg.Record, settings: Settings, now: datetime) -> QuestionChanges:
    """How the chance has changed, when the figures are recent enough to say.

    Held to the same age as the list of moves. Older than that, "over the last
    day" describes a day that is over — a question that has left the list the
    site reads keeps its last figures for ever — so they are left out, not
    shown as this one.
    """
    measured_at = row["changes_at"]
    if measured_at is None or measured_at < now - timedelta(hours=settings.moves_max_age_hours):
        return QuestionChanges()
    return QuestionChanges(
        hour=_change(row["change_1h"]),
        day=_change(row["change_24h"]),
        week=_change(row["change_7d"]),
        reference=_change(row["change_ref_prob"]),
        measured_at=measured_at,
    )


@router.get(
    "/{slug}",
    response_model=QuestionOut,
    responses={404: {"description": "No question has this address."}},
    summary="One question, and how its chance has changed",
)
async def read_question(
    slug: str,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> QuestionOut:
    # Checked before the database is asked: an address that could not be one
    # is not worth a query, and is never worth a request to the source.
    if len(slug) > _MAX_ADDRESS or not _ADDRESS.match(slug):
        raise _not_found()

    now = datetime.now(UTC)
    async with db.acquire() as conn:
        row = await questions_repo.find_by_slug(conn, slug)
    if row is None:
        raise _not_found()

    cached = await price_cache.read_many([row["id"]])
    history, history_source = await _history(request, row, settings, now)
    state = _state(row)

    return QuestionOut(
        slug=row["slug"],
        question=row["question"],
        description=row["description"],
        category=row["category"],
        event_title=row["event_title"],
        state=state,
        outcome=row["resolution"].lower() if row["resolution"] in ("YES", "NO") else None,
        closes_at=row["lock_at"],
        ends_at=row["end_date"],
        resolved_at=row["resolved_at"],
        probability=current_probability(
            row["id"],
            row["raw_yes_prob"],
            row["price_updated_at"],
            cached.get(row["id"]),
            settings,
            now,
        ),
        changes=_changes(row, settings, now),
        history=history,
        history_source=history_source,
        volume_usd=str(row["volume_usd"]),
        updated_at=row["updated_at"],
        as_of=now,
    )
