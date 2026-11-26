"""Wire formats.

Coin amounts cross the wire twice: `*_minor` as an integer (authoritative,
safe to compute with) and a preformatted display string. A float never
appears — JSON numbers are IEEE 754 doubles in most clients, which is the
wrong container for a balance.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

MINOR_UNITS_PER_COIN = 100


def format_coins(minor: int) -> str:
    """Minor units as whole toman: 12345678 -> "123,456".

    Two decimals were right while the unit was an invented "coin". A toman is
    not divided in practice, so a trailing ".78" reads as rial — the wrong
    currency by a factor of ten to the audience this is written for.

    Floored rather than rounded, and for the same reason the client floors:
    this renders balances, and showing a player one toman more than they hold
    produces a stake the server then refuses on exact minor-unit arithmetic.
    The minor value travels alongside and stays authoritative; this string is
    only ever for reading.
    """
    sign = "-" if minor < 0 else ""
    whole = abs(minor) // MINOR_UNITS_PER_COIN
    return f"{sign}{whole:,}"


class Money(BaseModel):
    minor: int
    display: str

    @classmethod
    def of(cls, minor: int) -> Money:
        return cls(minor=minor, display=format_coins(minor))


class SessionRequest(BaseModel):
    init_data: str = Field(min_length=1, max_length=8192, alias="initData")

    model_config = {"populate_by_name": True}


class UserProfile(BaseModel):
    id: str
    telegram_id: int
    player_code: str
    first_name: str
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    balance: Money
    streak_count: int
    lifetime_staked: Money
    lifetime_returned: Money
    can_claim_daily: bool
    member_since: datetime
    is_admin: bool = False

    invite_link: str | None = None
    referred_count: int = 0
    referral_earned: Money = Field(default_factory=lambda: Money.of(0))


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"  # noqa: S105
    expires_at: datetime
    is_new_user: bool
    user: UserProfile


class ErrorResponse(BaseModel):
    code: str
    detail: str


class Probability(BaseModel):
    """A market's current YES/NO probabilities.

    Sent as decimal strings, not floats: these feed payout arithmetic, and a
    JSON number is a double in most clients. `stale` is the flag the odds
    engine will refuse to price on in Phase 3 — it means the number is older
    than the configured tolerance and should be shown, not traded on.
    """

    yes: str
    no: str
    source: str
    age_seconds: float
    stale: bool


class MarketBoost(BaseModel):
    id: str
    side: str
    multiplier: str
    ends_at: datetime
    remaining_stake: Money
    max_stake_per_user: Money


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
    boosts: list[MarketBoost] = Field(default_factory=list)


class MarketPage(BaseModel):
    markets: list[MarketSummary]
    next_cursor: str | None = None
    min_legs: int = 1
    max_legs: int = 5
    vig_rate: str = "0.05"
    parlay_bonus_by_legs: list[str] = Field(default_factory=list)
    example_stake: Money
    signup_bonus: Money
    referral_bonus: Money


class LegRequestBody(BaseModel):
    market_id: str
    side: Literal["YES", "NO"]


class SlipRequest(BaseModel):
    legs: list[LegRequestBody] = Field(min_length=1, max_length=5)
    stake: int = Field(gt=0, description="Stake in minor units (100 = 1 coin).")
    insurance: bool = False
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
    fair_odds: str
    locked_odds: str
    boosted: bool
    boost_multiplier: str
    lock_at: datetime


class InsuranceOffer(BaseModel):
    available: bool
    selected: bool
    rate: str
    premium: Money
    covers_failed_legs: int
    min_legs: int
    unavailable_reason: str | None = None


class SlipQuoteResponse(BaseModel):
    legs: list[QuotedLeg]
    stake: Money
    combined_odds: str
    potential_payout: Money
    gross_potential_payout: Money
    payout_cap: Money
    capped: bool
    uncapped: bool = False
    parlay_bonus: str = "1.0"
    insurance: InsuranceOffer
    total_cost: Money


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
    has_insurance: bool
    insurance_premium: Money
    total_cost: Money
    settled_payout: Money
    settlement_note: str | None = None
    placed_at: datetime
    settled_at: datetime | None = None


class SlipPage(BaseModel):
    slips: list[Slip]
    next_cursor: str | None = None


class InvoiceRequest(BaseModel):
    package_code: str = Field(min_length=1, max_length=64)


class InvoiceResponse(BaseModel):
    purchase_id: str
    invoice_link: str
    """A t.me/$... link. The client passes it to WebApp.openInvoice()."""
    stars: int
    coins: Money


class CoinPackage(BaseModel):
    code: str
    title: str
    description: str
    stars: int
    coins: Money
    bonus_coins: Money


class ActivityEntry(BaseModel):
    id: str
    player: str
    status: str
    leg_count: int
    stake: Money
    payout: Money
    combined_odds: str
    settled_at: datetime


class ActivityFeed(BaseModel):
    entries: list[ActivityEntry] = Field(default_factory=list)


class PackageList(BaseModel):
    packages: list[CoinPackage] = Field(default_factory=list)


class ClaimResponse(BaseModel):
    claim_date: str
    base: Money
    streak_bonus: Money
    total: Money
    streak: int
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


class RewardItem(BaseModel):
    """One catalogue entry, already told whether *this* player can take it.

    `claimable` and `blocked_reason` are computed server-side rather than left
    to the client. The rules that gate a redemption — balance, lifetime volume,
    remaining supply, per-player limit — are enforced in the redeem
    transaction, and a client re-deriving them from raw fields would drift out
    of agreement with the server the first time one of them changed.
    """

    code: str
    title: str
    description: str
    kind: str
    image_url: str | None = None
    cost: Money
    min_lifetime_staked: Money
    remaining: int | None = None
    """Units left, or null when the reward is unlimited."""
    held_by_user: int = 0
    claimable: bool = False
    blocked_reason: str | None = None
    """A stable code — insufficient_funds, not_enough_play, already_claimed,
    reward_exhausted — not prose. The client owns the wording."""


class RewardCatalogue(BaseModel):
    rewards: list[RewardItem] = Field(default_factory=list)
    balance: Money


class RewardClaimItem(BaseModel):
    id: str
    reward_code: str
    title: str
    kind: str
    image_url: str | None = None
    cost: Money
    status: Literal["RESERVED", "FULFILLED", "FAILED", "REFUNDED"]
    created_at: datetime
    fulfilled_at: datetime | None = None
    fulfilment: dict = Field(default_factory=dict)


class RewardClaimList(BaseModel):
    claims: list[RewardClaimItem] = Field(default_factory=list)


class RedeemRequest(BaseModel):
    reward_code: str = Field(min_length=1, max_length=64)


class RedeemResponse(BaseModel):
    claim_id: str
    reward_code: str
    title: str
    cost: Money
    balance: Money
    status: Literal["RESERVED"]


class RevenueBlock(BaseModel):
    stars_gross: int
    stars_refunded: int
    stars_net: int
    purchases: int
    refunds: int
    paying_players: int
    coins_sold: Money


class RevenueDay(BaseModel):
    day: date
    stars: int
    stars_refunded: int
    purchases: int
    payers: int


class PackageSalesOut(BaseModel):
    code: str
    title: str
    stars_price: int
    coins: Money
    coins_per_star: float
    purchases: int
    stars: int
    share_of_stars: float


class LedgerFlowOut(BaseModel):
    entry_type: str
    net: Money
    entries: int
    players: int


class EconomyBalance(BaseModel):
    """Where coins come from and where they go, netted.

    `house_edge` is the only one of these that is not a direct sum: the vig is
    priced into the odds rather than posted as its own ledger entry, so it only
    exists as the gap between what players staked and what they were paid back.
    """

    minted_free: Money
    minted_purchased: Money
    house_edge: Money
    decayed: Money
    burned_on_rewards: Money
    net_change: Money


class BreakEvenBucketOut(BaseModel):
    bucket: str
    players: int
    daily_stake: Money


class PlayerBlock(BaseModel):
    total: int
    new_in_window: int
    staked_in_window: int
    claimed_in_window: int
    conversion_rate: float


class EconomyReportOut(BaseModel):
    """One screen's worth of "is this a business yet".

    Star amounts stay in Stars rather than being converted to a currency here.
    The developer payout rate is set by Telegram and Fragment, changes without
    notice, and differs by platform — baking a guess at it into the API would
    turn a rate change into a silently wrong revenue figure. The dashboard
    applies a rate the operator can see and edit.
    """

    window_days: int
    since: datetime
    generated_at: datetime

    revenue: RevenueBlock
    lifetime: RevenueBlock
    stars_per_day: float
    stars_per_paying_player: float

    daily: list[RevenueDay]
    packages: list[PackageSalesOut]
    players: PlayerBlock

    ledger: list[LedgerFlowOut]
    balance: EconomyBalance

    break_even_daily_stake: Money
    break_even_buckets: list[BreakEvenBucketOut]
    free_players_share: float


class MessageRequest(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    kind: Literal["MESSAGE", "PRIZE_CLAIM"] = "MESSAGE"


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


class PlayerOut(BaseModel):
    """One row of the roster.

    `net` is what betting has cost or made this player — returned minus
    staked. Open slips count their stake but not their outcome, so somebody
    mid-parlay reads slightly negative until it settles.
    """

    id: str
    player_code: str
    telegram_id: int
    username: str | None
    display_name: str
    status: str
    balance: Money
    lifetime_stars: int
    staked: Money
    returned: Money
    net: Money
    bought: Money
    granted: Money
    adjusted: Money
    slips: int
    won: int
    lost: int
    open_slips: int
    created_at: datetime
    last_seen_at: datetime


class PlayerList(BaseModel):
    players: list[PlayerOut]
    total: int


class AdjustRequest(BaseModel):
    """Credit or debit a player, identified by whichever handle is to hand.

    Both identifiers are optional and exactly one must be given. The operator
    has the player code when working from the roster or from a message, and the
    Telegram id when somebody has reached them outside the app; making them
    translate one into the other by hand is asking for a mistake with money.
    """

    player_code: str | None = Field(default=None, min_length=1, max_length=16)
    telegram_id: int | None = None
    amount_minor: int
    reason: str = Field(min_length=1, max_length=200)
    reference: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _exactly_one_handle(self) -> AdjustRequest:
        if (self.player_code is None) == (self.telegram_id is None):
            raise ValueError("Give either player_code or telegram_id, not both.")
        return self


class AdjustResult(BaseModel):
    player_code: str
    balance: Money


class ReplyRequest(BaseModel):
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ReplyResult(BaseModel):
    """What happened to the reply, told apart from whether it was written.

    `delivered` false does not mean the reply failed: it means Telegram would
    not carry it, because a bot cannot open a conversation the player has not
    opened first. The answer is saved and the player reads it in the app. The
    operator needs that distinction to know whether to expect a response.
    """

    id: str
    status: str
    reply_body: str
    replied_at: datetime
    delivered: bool
    delivery_detail: str | None = None


class StatusRequest(BaseModel):
    player_code: str = Field(min_length=1, max_length=16)
    status: Literal["ACTIVE", "RESTRICTED", "BANNED"]


class StatusResult(BaseModel):
    player_code: str
    status: str


class InboxItemOut(MessageOut):
    admin_note: str | None = None
    reply_delivered: bool = False
    player_code: str
    username: str | None = None
    display_name: str
    telegram_id: int
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
