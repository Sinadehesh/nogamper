"""Wire formats.

Point amounts cross the wire twice: `minor` as an integer (authoritative, safe
to compute with) and a preformatted display string. A float never appears —
JSON numbers are IEEE 754 doubles in most clients, which is the wrong
container for a balance, even one with no cash value.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

MINOR_UNITS_PER_POINT = 100


def format_points(minor: int) -> str:
    """Minor units as whole points: 12345678 -> "123,456".

    Floored rather than rounded, and for the same reason the client floors:
    this renders balances, and showing a player one point more than they hold
    produces a stake the server then refuses on exact minor-unit arithmetic.
    The minor value travels alongside and stays authoritative; this string is
    only ever for reading.
    """
    sign = "-" if minor < 0 else ""
    whole = abs(minor) // MINOR_UNITS_PER_POINT
    return f"{sign}{whole:,}"


class Money(BaseModel):
    """An amount of points. Named for its shape, not for what it is worth:
    points cannot be bought, sold, transferred or redeemed."""

    minor: int
    display: str

    @classmethod
    def of(cls, minor: int) -> Money:
        return cls(minor=minor, display=format_points(minor))


class ErrorResponse(BaseModel):
    code: str
    detail: str


# ----- accounts -------------------------------------------------------------


class RegisterRequest(BaseModel):
    """Lengths are bounded here so an oversized body is refused before any
    work is done on it; what makes a *good* password or name is decided in
    security/passwords.py and repositories/auth.py, which can say why."""

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)
    display_name: str = Field(min_length=1, max_length=64)


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)


class EraseRequest(BaseModel):
    """Erasing a registered account asks for the password again. A guest has
    none, and confirms by having the session at all."""

    password: str | None = Field(default=None, max_length=1024)


class Limits(BaseModel):
    """The player's own brakes, and how much room is left under them."""

    daily_limit: Money | None = None
    """The most they have chosen to stake in a day, or null for no limit."""
    daily_spent: Money
    daily_limit_loosen_at: datetime | None = None
    """When the limit may next be raised or removed. Null means now — either
    there is no limit, or it has stood long enough."""
    break_until: datetime | None = None
    """Set while a break is running. Forecasting is refused until it passes."""
    break_options_hours: list[int] = Field(default_factory=list)


class UserProfile(BaseModel):
    id: str
    player_code: str
    display_name: str
    email: str | None = None
    is_guest: bool
    balance: Money
    lifetime_staked: Money
    lifetime_returned: Money
    can_claim_daily: bool
    daily_topup: Money
    next_claim_at: datetime | None = None
    member_since: datetime
    is_admin: bool = False
    limits: Limits
    session_expires_at: datetime


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"  # noqa: S105
    expires_at: datetime
    is_new_user: bool
    user: UserProfile


class LimitRequest(BaseModel):
    daily_limit_minor: int | None = Field(
        default=None,
        gt=0,
        description="Most to stake per day, in minor units. Null removes the limit.",
    )


class BreakRequest(BaseModel):
    hours: int = Field(gt=0, le=24 * 366)


# ----- markets --------------------------------------------------------------


class Probability(BaseModel):
    """A market's current YES/NO probabilities.

    Sent as decimal strings, not floats: these feed payout arithmetic, and a
    JSON number is a double in most clients. `stale` means the number is older
    than the configured tolerance — it should be shown, and the server will
    refuse to make a price from it.
    """

    yes: str
    no: str
    source: str
    age_seconds: float
    stale: bool


class MarketEventSummary(BaseModel):
    id: str
    title: str
    slug: str | None = None


class MarketSummary(BaseModel):
    id: str
    question: str
    description: str | None = None
    category: str
    image_url: str | None = None
    event: MarketEventSummary
    probability: Probability
    liquidity_usd: str
    volume_usd: str
    lock_at: datetime
    end_date: datetime


class MarketPage(BaseModel):
    """The feed, and the rules a slip built from it has to satisfy.

    The rules ride along so the client can say "this one is all but settled"
    before a round trip rather than after one. They are advisory there: the
    server re-checks every one of them at quote and at placement.
    """

    markets: list[MarketSummary]
    next_cursor: str | None = None
    categories: list[str] = Field(default_factory=list)
    """Every category with something open in it — not just those on this
    page — so a filter built from it does not lose options as you page."""
    max_legs: int
    min_prob: str
    max_prob: str
    max_combined_odds: str
    min_stake: Money
    max_stake: Money
    payout_cap: Money


class GameRules(BaseModel):
    """The configured rules, for the pages that explain the game.

    `margin` is a constant and is here anyway. It is the one number the whole
    product is a claim about, and stating it in the same response as the
    figures that *can* be tuned makes the point that this one cannot.
    """

    signup_bonus: Money
    daily_topup: Money
    min_stake: Money
    max_stake: Money
    payout_cap: Money
    max_legs: int
    max_combined_odds: str
    min_prob: str
    max_prob: str
    margin: Literal["0"] = "0"
    reference_margin: str
    limit_loosen_delay_hours: int
    break_options_hours: list[int]
    password_min_length: int


# ----- forecasts ------------------------------------------------------------


class LegRequestBody(BaseModel):
    market_id: str
    side: Literal["YES", "NO"]


class SlipRequest(BaseModel):
    legs: list[LegRequestBody] = Field(min_length=1, max_length=5)
    stake: int = Field(gt=0, description="Stake in minor units (100 = 1 point).")
    accepted_odds: str | None = Field(
        default=None,
        description=(
            "The combined odds the client displayed. If the market has moved "
            "against the player by more than the tolerance since then, the "
            "placement is refused and a fresh quote returned."
        ),
    )


class QuotedLeg(BaseModel):
    market_id: str
    question: str
    category: str
    side: str
    probability: str
    locked_odds: str
    lock_at: datetime


class SlipQuoteResponse(BaseModel):
    legs: list[QuotedLeg]
    stake: Money
    combined_odds: str
    win_probability: str
    """The chance every pick comes in, as the market prices it. Shown beside
    the payout on purpose: a big number and how unlikely it is belong in the
    same glance."""
    potential_payout: Money
    gross_potential_payout: Money
    payout_cap: Money
    capped: bool


class SettledLeg(BaseModel):
    leg_index: int
    market_id: str
    question: str
    side: str
    locked_odds: str
    status: str
    resolution: str | None = None
    lock_at: datetime


class Slip(BaseModel):
    id: str
    type: str
    status: str
    legs: list[SettledLeg]
    stake: Money
    combined_odds: str
    potential_payout: Money
    capped: bool
    total_cost: Money
    """What actually left the balance. Equal to `stake` for anything placed on
    the website; slips from before it may include a premium on top."""
    settled_payout: Money
    placed_at: datetime
    settled_at: datetime | None = None


class SlipPage(BaseModel):
    slips: list[Slip]
    next_cursor: str | None = None


# ----- economy --------------------------------------------------------------


class ClaimResponse(BaseModel):
    claim_date: str
    amount: Money
    balance: Money
    next_claim_at: datetime


class LeaderboardRow(BaseModel):
    rank: int | None
    player: str
    slips_settled: int
    slips_won: int
    total_staked: Money
    net_profit: Money
    best_odds: str | None = None
    is_me: bool = False


class LeaderboardPage(BaseModel):
    season: str
    ends_at: datetime
    min_volume_to_rank: Money
    rows: list[LeaderboardRow] = Field(default_factory=list)
    my_rank: int | None = None
    my_net_profit: Money
    my_total_staked: Money


# ----- reality check --------------------------------------------------------


class CalibrationBucket(BaseModel):
    """How often picks in one probability band actually came in.

    A well-calibrated forecaster is right about 70% of the time on things
    priced at 70%. `expected` is the average price paid in the band, so the
    two can be compared without the client redoing the arithmetic.
    """

    low: str
    high: str
    picks: int
    correct: int
    expected: str | None = None


class RealityCheck(BaseModel):
    """A player's own record, stated plainly — and what it would have cost.

    The first half is theirs: how often they were right, and where the points
    went. The second half is the reason this product exists. It reprices the
    same winning slips at a bookmaker's margin and shows the difference, so
    the cost of that margin is a number about *their* forecasts rather than a
    warning about gambling in general.
    """

    member_since: datetime
    slips_placed: int
    slips_open: int
    slips_settled: int
    slips_won: int
    slips_lost: int
    picks_settled: int
    picks_correct: int

    staked: Money
    returned: Money
    net: Money

    reference_margin: str
    margin_cost: Money
    """What a margin of `reference_margin` per pick would have removed from
    the winning slips' payouts."""
    net_with_margin: Money

    active_days_30d: int
    slips_30d: int
    calibration: list[CalibrationBucket] = Field(default_factory=list)


# ----- messages -------------------------------------------------------------


class MessageRequest(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    id: str
    kind: str
    status: str
    body: str
    created_at: datetime
    answered_at: datetime | None = None
    reply_body: str | None = None
    replied_at: datetime | None = None


class MessageList(BaseModel):
    messages: list[MessageOut]


# ----- operator -------------------------------------------------------------


class LedgerFlowOut(BaseModel):
    entry_type: str
    net: Money
    entries: int
    players: int


class OverviewPlayers(BaseModel):
    total: int
    registered: int
    guests: int
    new_in_window: int
    forecast_in_window: int
    claimed_in_window: int


class OverviewForecasts(BaseModel):
    placed: int
    settled: int
    won: int
    lost: int
    open: int


class OverviewPoints(BaseModel):
    """Where points came from and where they went, in the window.

    There is no line for takings because there are none: `granted` is the
    only source, and the gap between `staked` and `returned` is what forecasts
    cost the players who made them — at fair odds that gap is luck and skill,
    and it sums to nobody's income.
    """

    granted: Money
    staked: Money
    returned: Money
    adjusted: Money
    net_change: Money


class OverviewSaferPlay(BaseModel):
    with_daily_limit: int
    on_break: int
    erased: int


class OverviewDay(BaseModel):
    day: date
    new_players: int
    forecasts: int
    forecasters: int


class OverviewOut(BaseModel):
    window_days: int
    since: datetime
    generated_at: datetime
    players: OverviewPlayers
    forecasts: OverviewForecasts
    points: OverviewPoints
    safer_play: OverviewSaferPlay
    daily: list[OverviewDay]
    ledger: list[LedgerFlowOut]


class PlayerOut(BaseModel):
    """One row of the roster.

    `net` is what forecasting has cost or made this player — returned minus
    staked. Open slips count their stake but not their outcome, so somebody
    mid-slip reads slightly negative until it settles.
    """

    id: str
    player_code: str
    display_name: str
    email: str | None
    is_guest: bool
    status: str
    balance: Money
    staked: Money
    returned: Money
    net: Money
    granted: Money
    adjusted: Money
    slips: int
    won: int
    lost: int
    open_slips: int
    daily_limit: Money | None = None
    break_until: datetime | None = None
    created_at: datetime
    last_seen_at: datetime


class PlayerList(BaseModel):
    players: list[PlayerOut]
    total: int


class AdjustRequest(BaseModel):
    """Credit or debit a player, identified by their code."""

    player_code: str = Field(min_length=1, max_length=16)
    amount_minor: int
    reason: str = Field(min_length=1, max_length=200)
    reference: str = Field(min_length=1, max_length=64)


class AdjustResult(BaseModel):
    player_code: str
    balance: Money


class ReplyRequest(BaseModel):
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ReplyResult(BaseModel):
    id: str
    status: str
    reply_body: str
    replied_at: datetime


class StatusRequest(BaseModel):
    player_code: str = Field(min_length=1, max_length=16)
    status: Literal["ACTIVE", "RESTRICTED", "BANNED"]


class StatusResult(BaseModel):
    player_code: str
    status: str


class InboxItemOut(MessageOut):
    admin_note: str | None = None
    player_code: str
    display_name: str
    is_guest: bool
    balance: Money
    player_status: str


class InboxOut(BaseModel):
    messages: list[InboxItemOut]
    unread: int
    total: int


class ResolveRequest(BaseModel):
    status: Literal["NEW", "SEEN", "ANSWERED"]
    note: str | None = Field(default=None, max_length=2000)


class JobLeaseOut(BaseModel):
    job_name: str
    holder: str | None = None
    held_for_seconds: float
    expires_in_seconds: float


class JobRunOut(BaseModel):
    """How a job's last run went.

    Carried alongside the verdict because the verdict names a layer and this
    says why. Every time this app has gone quiet, that "why" existed only in a
    worker log, and the person who needed it was reading from a phone.
    """

    job_name: str
    outcome: Literal["ok", "error", "deadline"]
    duration_seconds: float
    finished_ago_seconds: float
    holder: str | None = None
    detail: dict


class DiagnosticsOut(BaseModel):
    """One request that answers "is it the database, the app, or upstream".

    `layer` names where to look and `advice` says what to do about it. Both are
    derived from the numbers below, so an operator can check the reasoning
    rather than take it on trust.
    """

    layer: Literal["healthy", "degraded", "discovery", "worker", "upstream", "cache", "capacity"]
    advice: str

    staleness_threshold_seconds: int
    markets_budget: int
    markets_total: int
    markets_active: int
    markets_locked: int
    markets_fresh: int
    markets_stale: int
    newest_price_at: datetime | None
    oldest_price_at: datetime | None
    seconds_since_newest: float | None

    cache_reachable: bool
    cache_sampled: int
    cache_hits: int

    leases: list[JobLeaseOut]
    runs: list[JobRunOut] = []
    generated_at: datetime
