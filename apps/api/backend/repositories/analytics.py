"""The operator's overview: is anyone here, and is the game healthy.

This file used to answer a different question — whether the economy was tuned
to turn free players into paying ones — with a break-even stake, a conversion
rate and a revenue series. There is no revenue now and nothing to convert
anybody to, so the questions left are the plain ones:

  * **Are people using it?** New accounts, people who forecast, forecasts.
  * **Where do points go?** Granted, staked, returned. At fair odds the gap
    between staked and returned is nobody's income; it is reported so that a
    gap which *stops* averaging out is noticed, because that would mean the
    pricing is wrong.
  * **Are the brakes being used?** How many players have set a limit or are on
    a break. Not a target to push in either direction — a number to know.

## A note on windows

Every query takes an explicit window rather than reading "all time", because
the questions worth asking are rate questions. Totals that are not windowed
say so in their names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import asyncpg

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
    (SELECT count(*) FROM users WHERE deleted_at IS NULL)                     AS total,
    (SELECT count(*) FROM users WHERE deleted_at IS NULL AND email IS NOT NULL) AS registered,
    (SELECT count(*) FROM users WHERE deleted_at IS NULL AND is_guest)        AS guests,
    (SELECT count(*) FROM users WHERE created_at >= $1)                       AS new_in_window,
    (SELECT count(DISTINCT user_id) FROM predictions WHERE placed_at >= $1)   AS forecast_in_window,
    (SELECT count(DISTINCT user_id) FROM daily_claims WHERE claimed_at >= $1) AS claimed_in_window
"""

_FORECASTS = """
SELECT count(*)                                      AS placed,
       count(*) FILTER (WHERE status <> 'PENDING')   AS settled,
       count(*) FILTER (WHERE status = 'WON')        AS won,
       count(*) FILTER (WHERE status = 'LOST')       AS lost,
       (SELECT count(*) FROM predictions WHERE status = 'PENDING') AS open
  FROM predictions
 WHERE placed_at >= $1
"""

_SAFER_PLAY = """
SELECT count(*) FILTER (WHERE deleted_at IS NULL AND daily_stake_limit IS NOT NULL) AS with_limit,
       count(*) FILTER (WHERE deleted_at IS NULL AND cooloff_until > NOW())         AS on_break,
       count(*) FILTER (WHERE deleted_at IS NOT NULL)                               AS erased
  FROM users
"""

_DAILY = """
SELECT d::date AS day,
       (SELECT count(*) FROM users u
         WHERE u.created_at >= d AND u.created_at < d + INTERVAL '1 day')      AS new_players,
       (SELECT count(*) FROM predictions p
         WHERE p.placed_at >= d AND p.placed_at < d + INTERVAL '1 day')        AS forecasts,
       (SELECT count(DISTINCT p.user_id) FROM predictions p
         WHERE p.placed_at >= d AND p.placed_at < d + INTERVAL '1 day')        AS forecasters
  FROM generate_series($1::date, CURRENT_DATE, INTERVAL '1 day') AS d
 ORDER BY d
"""


@dataclass(frozen=True, slots=True)
class LedgerFlow:
    entry_type: str
    net: int
    entries: int
    players: int


@dataclass(frozen=True, slots=True)
class Players:
    total: int
    registered: int
    guests: int
    new_in_window: int
    forecast_in_window: int
    claimed_in_window: int


@dataclass(frozen=True, slots=True)
class Forecasts:
    placed: int
    settled: int
    won: int
    lost: int
    open: int


@dataclass(frozen=True, slots=True)
class SaferPlay:
    with_daily_limit: int
    on_break: int
    erased: int


@dataclass(frozen=True, slots=True)
class DayPoint:
    day: date
    new_players: int
    forecasts: int
    forecasters: int


@dataclass(frozen=True, slots=True)
class Overview:
    window_days: int
    since: datetime
    players: Players
    forecasts: Forecasts
    safer_play: SaferPlay
    daily: list[DayPoint] = field(default_factory=list)
    ledger: list[LedgerFlow] = field(default_factory=list)


async def load_overview(conn: asyncpg.Connection, *, since: datetime, window_days: int) -> Overview:
    players = await conn.fetchrow(_PLAYERS, since)
    forecasts = await conn.fetchrow(_FORECASTS, since)
    safer = await conn.fetchrow(_SAFER_PLAY)

    return Overview(
        window_days=window_days,
        since=since,
        players=Players(
            total=int(players["total"]),
            registered=int(players["registered"]),
            guests=int(players["guests"]),
            new_in_window=int(players["new_in_window"]),
            forecast_in_window=int(players["forecast_in_window"]),
            claimed_in_window=int(players["claimed_in_window"]),
        ),
        forecasts=Forecasts(
            placed=int(forecasts["placed"]),
            settled=int(forecasts["settled"]),
            won=int(forecasts["won"]),
            lost=int(forecasts["lost"]),
            open=int(forecasts["open"]),
        ),
        safer_play=SaferPlay(
            with_daily_limit=int(safer["with_limit"]),
            on_break=int(safer["on_break"]),
            erased=int(safer["erased"]),
        ),
        daily=[
            DayPoint(
                day=r["day"],
                new_players=int(r["new_players"]),
                forecasts=int(r["forecasts"]),
                forecasters=int(r["forecasters"]),
            )
            for r in await conn.fetch(_DAILY, since.date())
        ],
        ledger=[
            LedgerFlow(
                entry_type=r["entry_type"],
                net=int(r["net"]),
                entries=int(r["entries"]),
                players=int(r["players"]),
            )
            for r in await conn.fetch(_LEDGER_FLOW, since)
        ],
    )
