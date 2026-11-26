"""Revenue and economy reporting.

The one number this exists to answer: **is the coin economy tuned to produce
paying players, or is it giving the game away?**

Everything else here is in service of that. The model is a free-to-play
market: Stars are the only value that enters, coins are the only value that
moves, and coins never leave. So revenue happens in exactly one place — a
player whose balance hits zero decides to buy rather than wait for tomorrow's
drip — and every lever that matters either speeds that up or slows it down.

## Where the house actually earns

Not in the packs. In the vig.

The 5% vig never appears as a ledger entry; it is priced into the odds, so it
shows up only as the gap between what players stake and what they are paid
back. That makes it invisible in any per-row view and obvious in aggregate,
which is why the ledger is reported by entry type: `net_by_entry_type` is the
whole economy in one table, and the house's take is the sum of the wagering
rows.

## Why `break_even_buckets` is the interesting query

A player earns up to `daily_drip + streak_bonus` coins a day for free and
burns `vig_rate` of whatever they stake. Below

    break_even_daily_stake = (daily_drip + max_streak_bonus) / vig_rate

they can play forever without ever spending a Star. Above it, they must
eventually buy. That threshold is the business, and the distribution of
players around it says more than any revenue total: revenue is what happened
last month, the distribution is what will happen next month.

## A note on windows

Every query takes an explicit window rather than reading "all time", because
the questions worth asking are rate questions — Stars *per day*, new players
*per week*. Lifetime totals are reported separately and clearly labelled, so
nobody reads a two-year cumulative figure as a run rate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import asyncpg

_REVENUE = """
SELECT
    COALESCE(SUM(stars_amount) FILTER (WHERE status = 'PAID'), 0)      AS stars_gross,
    COALESCE(SUM(stars_amount) FILTER (WHERE status = 'REFUNDED'), 0)  AS stars_refunded,
    COALESCE(SUM(coins_amount) FILTER (WHERE status = 'PAID'), 0)      AS coins_sold,
    count(*) FILTER (WHERE status = 'PAID')                            AS purchases,
    count(*) FILTER (WHERE status = 'REFUNDED')                        AS refunds,
    count(DISTINCT user_id) FILTER (WHERE status = 'PAID')             AS paying_players
  FROM star_purchases
 WHERE paid_at >= $1
"""

_REVENUE_LIFETIME = """
SELECT
    COALESCE(SUM(stars_amount) FILTER (WHERE status = 'PAID'), 0)     AS stars_gross,
    COALESCE(SUM(stars_amount) FILTER (WHERE status = 'REFUNDED'), 0) AS stars_refunded,
    count(DISTINCT user_id) FILTER (WHERE status = 'PAID')            AS paying_players
  FROM star_purchases
"""

_DAILY_SERIES = """
SELECT d::date                                                          AS day,
       COALESCE(SUM(sp.stars_amount) FILTER (WHERE sp.status = 'PAID'), 0)     AS stars,
       COALESCE(SUM(sp.stars_amount) FILTER (WHERE sp.status = 'REFUNDED'), 0) AS stars_refunded,
       count(sp.id) FILTER (WHERE sp.status = 'PAID')                   AS purchases,
       count(DISTINCT sp.user_id) FILTER (WHERE sp.status = 'PAID')     AS payers
  FROM generate_series($1::date, CURRENT_DATE, INTERVAL '1 day') AS d
  LEFT JOIN star_purchases sp
         ON sp.paid_at >= d AND sp.paid_at < d + INTERVAL '1 day'
 GROUP BY d
 ORDER BY d
"""

_BY_PACKAGE = """
SELECT cp.code,
       cp.title,
       cp.stars_price,
       cp.coins + cp.bonus_coins                       AS coins,
       count(sp.id) FILTER (WHERE sp.status = 'PAID')  AS purchases,
       COALESCE(SUM(sp.stars_amount) FILTER (WHERE sp.status = 'PAID'), 0) AS stars
  FROM coin_packages cp
  LEFT JOIN star_purchases sp
         ON sp.package_code = cp.code AND sp.paid_at >= $1
 GROUP BY cp.code, cp.title, cp.stars_price, cp.coins, cp.bonus_coins, cp.sort_order
 ORDER BY cp.sort_order
"""


_LEDGER_FLOW = """
SELECT entry_type::text AS entry_type,
       SUM(amount)      AS net,
       count(*)         AS entries,
       count(DISTINCT user_id) AS players
  FROM ledger_entries
 WHERE created_at >= $1
 GROUP BY entry_type
 ORDER BY SUM(amount)
"""


_PLAYERS = """
SELECT
    (SELECT count(*) FROM users)                                AS total,
    (SELECT count(*) FROM users WHERE created_at >= $1)         AS new_in_window,
    (SELECT count(DISTINCT user_id) FROM ledger_entries
      WHERE created_at >= $1 AND entry_type = 'STAKE_DEBIT')    AS staked_in_window,
    (SELECT count(DISTINCT user_id) FROM ledger_entries
      WHERE created_at >= $1 AND entry_type = 'DAILY_DRIP_CREDIT') AS claimed_in_window
"""

_BREAK_EVEN = """
WITH staked AS (
    SELECT user_id, SUM(-amount)::numeric / $2 AS daily_stake
      FROM ledger_entries
     WHERE created_at >= $1 AND entry_type = 'STAKE_DEBIT'
     GROUP BY user_id
)
SELECT CASE
           WHEN daily_stake < $3 * 0.5 THEN 'far_below'
           WHEN daily_stake < $3       THEN 'below'
           WHEN daily_stake < $3 * 2   THEN 'at'
           WHEN daily_stake < $3 * 5   THEN 'above'
           ELSE 'far_above'
       END                       AS bucket,
       count(*)                  AS players,
       COALESCE(SUM(daily_stake), 0)::bigint AS daily_stake_total
  FROM staked
 GROUP BY 1
"""

_BUCKET_ORDER = ("far_below", "below", "at", "above", "far_above")


@dataclass(frozen=True, slots=True)
class Revenue:
    stars_gross: int
    stars_refunded: int
    stars_net: int
    coins_sold: int
    purchases: int
    refunds: int
    paying_players: int


@dataclass(frozen=True, slots=True)
class DayPoint:
    day: date
    stars: int
    stars_refunded: int
    purchases: int
    payers: int


@dataclass(frozen=True, slots=True)
class PackageSales:
    code: str
    title: str
    stars_price: int
    coins: int
    purchases: int
    stars: int
    coins_per_star: float


@dataclass(frozen=True, slots=True)
class LedgerFlow:
    entry_type: str
    net: int
    entries: int
    players: int


@dataclass(frozen=True, slots=True)
class Players:
    total: int
    new_in_window: int
    staked_in_window: int
    claimed_in_window: int


@dataclass(frozen=True, slots=True)
class BreakEvenBucket:
    bucket: str
    players: int
    daily_stake_total: int


@dataclass(frozen=True, slots=True)
class EconomyReport:
    window_days: int
    since: datetime
    revenue: Revenue
    lifetime: Revenue
    daily: list[DayPoint]
    packages: list[PackageSales]
    ledger: list[LedgerFlow]
    players: Players
    break_even_daily_stake: int
    break_even_buckets: list[BreakEvenBucket] = field(default_factory=list)


def _revenue(row: asyncpg.Record) -> Revenue:
    gross = int(row["stars_gross"])
    refunded = int(row["stars_refunded"])
    return Revenue(
        stars_gross=gross,
        stars_refunded=refunded,
        stars_net=gross - refunded,
        coins_sold=int(row.get("coins_sold") or 0),
        purchases=int(row.get("purchases") or 0),
        refunds=int(row.get("refunds") or 0),
        paying_players=int(row["paying_players"]),
    )


async def load_economy_report(
    conn: asyncpg.Connection,
    *,
    since: datetime,
    window_days: int,
    break_even_daily_stake: int,
) -> EconomyReport:
    revenue = _revenue(await conn.fetchrow(_REVENUE, since))
    lifetime = _revenue(await conn.fetchrow(_REVENUE_LIFETIME))

    daily = [
        DayPoint(
            day=r["day"],
            stars=int(r["stars"]),
            stars_refunded=int(r["stars_refunded"]),
            purchases=int(r["purchases"]),
            payers=int(r["payers"]),
        )
        for r in await conn.fetch(_DAILY_SERIES, since.date())
    ]

    packages = [
        PackageSales(
            code=r["code"],
            title=r["title"],
            stars_price=int(r["stars_price"]),
            coins=int(r["coins"]),
            purchases=int(r["purchases"]),
            stars=int(r["stars"]),
            coins_per_star=round(int(r["coins"]) / 100 / int(r["stars_price"]), 2),
        )
        for r in await conn.fetch(_BY_PACKAGE, since)
    ]

    ledger = [
        LedgerFlow(
            entry_type=r["entry_type"],
            net=int(r["net"]),
            entries=int(r["entries"]),
            players=int(r["players"]),
        )
        for r in await conn.fetch(_LEDGER_FLOW, since)
    ]

    player_row = await conn.fetchrow(_PLAYERS, since)
    players = Players(
        total=int(player_row["total"]),
        new_in_window=int(player_row["new_in_window"]),
        staked_in_window=int(player_row["staked_in_window"]),
        claimed_in_window=int(player_row["claimed_in_window"]),
    )

    found = {
        r["bucket"]: BreakEvenBucket(
            bucket=r["bucket"],
            players=int(r["players"]),
            daily_stake_total=int(r["daily_stake_total"]),
        )
        for r in await conn.fetch(_BREAK_EVEN, since, window_days, break_even_daily_stake)
    }
    buckets = [
        found.get(name, BreakEvenBucket(bucket=name, players=0, daily_stake_total=0))
        for name in _BUCKET_ORDER
    ]

    return EconomyReport(
        window_days=window_days,
        since=since,
        revenue=revenue,
        lifetime=lifetime,
        daily=daily,
        packages=packages,
        ledger=ledger,
        players=players,
        break_even_daily_stake=break_even_daily_stake,
        break_even_buckets=buckets,
    )
