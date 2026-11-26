"""Buying points, and the limits on buying them.

The game is free and stays free: a thousand points to start and a top-up every
day, for ever. This module is the other way points arrive — somebody pays for
them — and it exists because a site with no advertising and no gambling money
is paid for by its author or by its players, and "by its author" has an end.

What is being sold is a larger balance to forecast with, and nothing else. It
cannot be withdrawn, sent to anybody or exchanged for anything, here or
anywhere. That is not a policy that could be relaxed: no table, column or
route exists that moves value out.

## Why it is hedged about the way it is

People come to this site to get away from betting. "You have run out — pay to
carry on" is the mechanism they are getting away from, and selling points to
them without limits would be building it again with worse odds. So:

  * **A monthly cap nobody can lift for themselves.** Site-wide, small, and
    counted in real money per calendar month.
  * **A limit of their own beneath it**, down to zero, which closes the shop
    for that player. It follows the same rule as the daily forecast limit:
    lowered at once, raised only after it has stood for a day.
  * **A break closes the shop** as well as the game.
  * **One price per point.** No pack is cheaper per point than another, so
    nothing rewards buying more than somebody came for.
  * **An open checkout counts as spent** until it lapses, so the cap cannot be
    stepped over by starting several at once.

## Why a purchase is believed

Only because Stripe said so, in a message whose signature was checked
(see `clients/stripe.py`). The ledger's own unique index on
`(ref_type, ref_id, entry_type)` then makes "credited" something that can
happen once per purchase however many times that message arrives.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import asyncpg

from ..config import Settings

logger = logging.getLogger(__name__)

__all__ = [
    "Pack",
    "PurchaseRow",
    "ShopError",
    "Spending",
    "abandon",
    "attach_session",
    "expire",
    "mark_paid",
    "mark_refunded",
    "open_purchase",
    "packs",
    "recent",
    "set_spend_limit",
    "spending",
]

MINOR_PER_POINT = 100


class ShopError(Exception):
    def __init__(
        self, code: str, detail: str, *, status: int = 400, until: datetime | None = None
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status
        self.until = until


@dataclass(frozen=True, slots=True)
class Pack:
    points: int
    """Whole points, as a person would say it."""
    price_cents: int

    @property
    def points_minor(self) -> int:
        return self.points * MINOR_PER_POINT


def packs(settings: Settings) -> list[Pack]:
    """What is on sale. Empty when the shop is closed."""
    if not settings.shop_open:
        return []
    return [
        Pack(points=size, price_cents=settings.pack_price_cents(size))
        for size in settings.shop_pack_points
    ]


def month_bounds(settings: Settings, now: datetime | None = None) -> tuple[datetime, datetime]:
    """The calendar month `now` falls in, in the economy's timezone.

    The same clock the top-up and the daily limit use, so "this month" on the
    shop page begins when "today" on every other page does.
    """
    tz = ZoneInfo(settings.economy_timezone)
    local = (now or datetime.now(UTC)).astimezone(tz)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    following = (start + timedelta(days=32)).replace(day=1)
    return start, following


@dataclass(frozen=True, slots=True)
class Spending:
    """Where one player stands against the limits, in cents."""

    paid_month: int
    pending: int
    paid_all: int
    personal_limit: int | None
    limit_loosen_at: datetime | None
    resets_at: datetime
    ceiling: int
    """The lower of the site's cap and the player's own limit."""
    blocked: str | None
    """Why nothing can be bought right now, or None. A code, not a sentence."""
    blocked_until: datetime | None

    @property
    def remaining(self) -> int:
        return max(0, self.ceiling - self.paid_month - self.pending)


_BUYER = """
SELECT id, status, is_guest, cooloff_until, coin_balance,
       monthly_spend_limit_cents, spend_limit_set_at
  FROM users
 WHERE id = $1
"""

_SPENT = """
SELECT COALESCE(SUM(amount_cents)
                FILTER (WHERE status = 'PAID' AND paid_at >= $2), 0)::bigint AS paid_month,
       COALESCE(SUM(amount_cents)
                FILTER (WHERE status = 'PENDING' AND expires_at > NOW()), 0)::bigint AS pending,
       COALESCE(SUM(amount_cents)
                FILTER (WHERE status = 'PAID'), 0)::bigint AS paid_all
  FROM point_purchases
 WHERE user_id = $1
"""


def _loosen_at(limit: int | None, set_at: datetime | None, settings: Settings) -> datetime | None:
    if limit is None or set_at is None:
        return None
    available = set_at + timedelta(seconds=settings.limit_loosen_delay_seconds)
    return available if available > datetime.now(UTC) else None


async def _spending(
    conn: asyncpg.Connection, buyer: asyncpg.Record, settings: Settings
) -> Spending:
    start, following = month_bounds(settings)
    spent = await conn.fetchrow(_SPENT, buyer["id"], start)

    personal: int | None = buyer["monthly_spend_limit_cents"]
    ceiling = settings.shop_monthly_cap_cents
    if personal is not None:
        ceiling = min(ceiling, personal)

    now = datetime.now(UTC)
    on_break = buyer["cooloff_until"] is not None and buyer["cooloff_until"] > now
    remaining = max(0, ceiling - spent["paid_month"] - spent["pending"])
    cheapest = min((p.price_cents for p in packs(settings)), default=None)

    blocked: str | None = None
    until: datetime | None = None
    if not settings.shop_open:
        blocked = "shop_closed"
    elif buyer["is_guest"]:
        blocked = "account_required"
    elif buyer["status"] != "ACTIVE":
        blocked = "account_restricted"
    elif on_break:
        blocked, until = "on_break", buyer["cooloff_until"]
    elif personal == 0:
        blocked = "shop_closed_by_you"
    elif cheapest is None or remaining < cheapest:
        blocked, until = "spend_limit_reached", following

    return Spending(
        paid_month=spent["paid_month"],
        pending=spent["pending"],
        paid_all=spent["paid_all"],
        personal_limit=personal,
        limit_loosen_at=_loosen_at(personal, buyer["spend_limit_set_at"], settings),
        resets_at=following,
        ceiling=ceiling,
        blocked=blocked,
        blocked_until=until,
    )


async def spending(conn: asyncpg.Connection, *, user_id: uuid.UUID, settings: Settings) -> Spending:
    buyer = await conn.fetchrow(_BUYER, user_id)
    if buyer is None:
        raise ShopError("user_not_found", "No such player.", status=404)
    return await _spending(conn, buyer, settings)


_REFUSALS = {
    "shop_closed": ("Nothing is for sale here.", 404),
    "account_required": (
        "Create an account first. A guest is only a cookie, and a purchase "
        "should not depend on one.",
        403,
    ),
    "account_restricted": ("This account cannot buy points.", 403),
    "on_break": ("You are on a break. The shop is closed until it ends.", 409),
    "shop_closed_by_you": (
        "You have set your spending limit to zero, which closes the shop for you.",
        409,
    ),
    "spend_limit_reached": ("You have reached this month's spending limit.", 409),
}


def _refuse(code: str, until: datetime | None = None) -> ShopError:
    detail, status = _REFUSALS[code]
    return ShopError(code, detail, status=status, until=until)


# ----- the player's own limit ------------------------------------------------


async def set_spend_limit(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    new_limit: int | None,
    settings: Settings,
) -> None:
    """Change the monthly spending limit; refuse to loosen one that is fresh.

    The rule, and the reasoning, are `safer_play.set_daily_limit`'s: a limit
    that can be lifted in the moment it bites is not a limit. Must run inside
    a transaction.
    """
    if new_limit is not None and not 0 <= new_limit <= settings.shop_monthly_cap_cents:
        raise ShopError(
            "limit_out_of_range",
            "A spending limit must be between zero and the site's monthly cap.",
            status=422,
        )

    row = await conn.fetchrow(
        "SELECT monthly_spend_limit_cents, spend_limit_set_at FROM users WHERE id = $1 FOR UPDATE",
        user_id,
    )
    if row is None:
        raise ShopError("user_not_found", "No such player.", status=404)

    current: int | None = row["monthly_spend_limit_cents"]
    if new_limit == current:
        return  # not a change, so it must not restart the clock

    loosening = current is not None and (new_limit is None or new_limit > current)
    if loosening:
        available = _loosen_at(current, row["spend_limit_set_at"], settings)
        if available is not None:
            raise ShopError(
                "limit_locked",
                "A spending limit can be lowered at any time, but raised or removed "
                "only after it has been in place for a day.",
                status=409,
                until=available,
            )

    await conn.execute(
        """
        UPDATE users
           SET monthly_spend_limit_cents = $2,
               spend_limit_set_at = CASE WHEN $2::integer IS NULL THEN NULL ELSE NOW() END
         WHERE id = $1
        """,
        user_id,
        new_limit,
    )


# ----- a purchase, from asking to paid ---------------------------------------


@dataclass(frozen=True, slots=True)
class PurchaseRow:
    id: uuid.UUID
    points_minor: int
    amount_cents: int
    currency: str
    status: str
    created_at: datetime
    expires_at: datetime


def _to_purchase(row: asyncpg.Record) -> PurchaseRow:
    return PurchaseRow(
        id=row["id"],
        points_minor=row["points"],
        amount_cents=row["amount_cents"],
        currency=row["currency"],
        status=row["status"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


_INSERT = """
INSERT INTO point_purchases (user_id, points, amount_cents, currency, expires_at)
VALUES ($1, $2, $3, $4, NOW() + make_interval(mins => $5))
RETURNING id, points, amount_cents, currency, status, created_at, expires_at
"""

_RECENT = """
SELECT id, points, amount_cents, currency, status, created_at, expires_at
  FROM point_purchases
 WHERE user_id = $1 AND status IN ('PAID', 'REFUNDED')
 ORDER BY created_at DESC
 LIMIT $2
"""


async def open_purchase(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    points: int,
    adult: bool,
    settings: Settings,
) -> PurchaseRow:
    """Record the intention to buy one pack, if every limit allows it.

    Must run inside a transaction. The player's row is locked first, which is
    what makes the cap a cap: two checkouts started in the same instant are
    decided one after the other, and the second sees the first.
    """
    if not settings.shop_open:
        raise _refuse("shop_closed")

    pack = next((p for p in packs(settings) if p.points == points), None)
    if pack is None:
        raise ShopError("unknown_pack", "That pack is not on sale.", status=422)

    if not adult:
        raise ShopError(
            "age_required",
            f"You must be {settings.shop_min_age} or over to buy points.",
            status=422,
        )

    buyer = await conn.fetchrow(_BUYER + " FOR UPDATE", user_id)
    if buyer is None:
        raise ShopError("user_not_found", "No such player.", status=404)

    state = await _spending(conn, buyer, settings)
    if state.blocked is not None:
        raise _refuse(state.blocked, state.blocked_until)
    if pack.price_cents > state.remaining:
        raise ShopError(
            "spend_limit_reached",
            "That pack would take you over this month's spending limit.",
            status=409,
            until=state.resets_at,
        )

    row = await conn.fetchrow(
        _INSERT,
        user_id,
        pack.points_minor,
        pack.price_cents,
        settings.shop_currency,
        settings.shop_checkout_minutes,
    )
    return _to_purchase(row)


async def attach_session(
    conn: asyncpg.Connection, *, purchase_id: uuid.UUID, session_id: str
) -> None:
    await conn.execute(
        "UPDATE point_purchases SET stripe_session_id = $2 "
        "WHERE id = $1 AND stripe_session_id IS NULL",
        purchase_id,
        session_id,
    )


async def abandon(conn: asyncpg.Connection, *, purchase_id: uuid.UUID) -> None:
    """Stripe never opened a page for this one, so it must not count as spent."""
    await conn.execute(
        "UPDATE point_purchases SET status = 'EXPIRED' WHERE id = $1 AND status = 'PENDING'",
        purchase_id,
    )


async def expire(conn: asyncpg.Connection, *, purchase_id: uuid.UUID) -> bool:
    """The checkout lapsed unpaid. True if that changed anything."""
    result = await conn.execute(
        "UPDATE point_purchases SET status = 'EXPIRED' WHERE id = $1 AND status = 'PENDING'",
        purchase_id,
    )
    return result.endswith(" 1")


async def mark_paid(
    conn: asyncpg.Connection,
    *,
    purchase_id: uuid.UUID,
    session_id: str | None,
    payment_intent: str | None,
    amount_cents: int | None,
    currency: str | None,
) -> str:
    """Credit a purchase Stripe has confirmed. Returns what happened.

    `credited`, `already_credited`, `unknown` or `mismatch`. Must run inside a
    transaction.

    A lapsed purchase is still credited if the money arrived: "expired" is
    this service's bookkeeping, and somebody who has paid is owed their points
    whatever the bookkeeping says. What is *not* credited is a payment for a
    different amount or currency than the row records — that is not a delay
    or a retry, it is something this code does not understand, and it stops
    for a person to look at rather than guessing in either direction.
    """
    row = await conn.fetchrow(
        "SELECT id, user_id, points, amount_cents, currency, status "
        "FROM point_purchases WHERE id = $1 FOR UPDATE",
        purchase_id,
    )
    if row is None:
        return "unknown"
    if row["status"] in ("PAID", "REFUNDED"):
        return "already_credited"

    if amount_cents != row["amount_cents"] or (currency or "").lower() != row["currency"]:
        logger.error(
            "purchase %s: Stripe reports %s %s, the row records %s %s. Not credited.",
            purchase_id,
            amount_cents,
            currency,
            row["amount_cents"],
            row["currency"],
        )
        return "mismatch"

    await conn.execute(
        """
        UPDATE point_purchases
           SET status = 'PAID',
               paid_at = NOW(),
               stripe_session_id = COALESCE(stripe_session_id, $2),
               stripe_payment_intent = $3
         WHERE id = $1
        """,
        purchase_id,
        session_id,
        payment_intent,
    )
    await conn.execute(
        """
        INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id,
                                    idempotency_key, metadata)
        VALUES ($1, 'POINTS_PURCHASE_CREDIT', $2, 'POINT_PURCHASE', $3, $4,
                jsonb_build_object('amount_cents', $5::integer, 'currency', $6::text))
        """,
        row["user_id"],
        row["points"],
        purchase_id,
        f"purchase:{purchase_id}",
        row["amount_cents"],
        row["currency"],
    )
    return "credited"


async def mark_refunded(conn: asyncpg.Connection, *, payment_intent: str) -> str:
    """Take the points back for a payment that was refunded or disputed.

    `refunded`, `already_refunded` or `unknown`. Must run inside a transaction.

    Any refund takes back the whole pack, including a partial one: the ledger
    allows one reversal per purchase, and "half a pack" is not a thing an
    operator should be issuing in the first place.

    Points already used cannot be taken back — a balance does not go below
    zero — so this takes what is there and records how much that was.
    """
    row = await conn.fetchrow(
        "SELECT id, user_id, points, status FROM point_purchases "
        "WHERE stripe_payment_intent = $1 FOR UPDATE",
        payment_intent,
    )
    if row is None:
        return "unknown"
    if row["status"] != "PAID":
        return "already_refunded" if row["status"] == "REFUNDED" else "unknown"

    balance = await conn.fetchval(
        "SELECT coin_balance FROM users WHERE id = $1 FOR UPDATE", row["user_id"]
    )
    take = min(row["points"], balance)
    if take > 0:
        await conn.execute(
            """
            INSERT INTO ledger_entries (user_id, entry_type, amount, ref_type, ref_id,
                                        idempotency_key, metadata)
            VALUES ($1, 'POINTS_REFUND_DEBIT', $2, 'POINT_PURCHASE', $3, $4,
                    jsonb_build_object('purchased', $5::bigint))
            """,
            row["user_id"],
            -take,
            row["id"],
            f"purchase-refund:{row['id']}",
            row["points"],
        )
    await conn.execute(
        "UPDATE point_purchases SET status = 'REFUNDED', refunded_at = NOW(), clawed_back = $2 "
        "WHERE id = $1",
        row["id"],
        take,
    )
    return "refunded"


async def recent(
    conn: asyncpg.Connection, *, user_id: uuid.UUID, limit: int = 10
) -> list[PurchaseRow]:
    """A player's own purchases, newest first. Unfinished checkouts are left
    out: they are not purchases, and a list padded with them reads as debt."""
    rows = await conn.fetch(_RECENT, user_id, limit)
    return [_to_purchase(row) for row in rows]
