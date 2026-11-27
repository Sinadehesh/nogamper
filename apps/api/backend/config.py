"""Runtime configuration. Fails loudly at startup rather than at first request.

## What is deliberately not here

This service used to price a house margin and pay out prizes, and each of those
had a setting. They are gone rather than set to zero: there is no `vig_rate`,
no boost schedule, no insurance load, no prize table. A product that says every
price is fair should not be one environment variable away from shading one.

## What is here, and is not the same thing

Points can be bought (the `shop_*` settings, below), because a site with no
advertising has to be paid for by somebody. That is the only place money
enters, and there is no setting anywhere that lets it leave: nothing converts
points into anything.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

logger = logging.getLogger(__name__)

PLAYER_CODE_ALPHABET = frozenset("ABCDEFGHJKMNPQRSTUVWXYZ23456789")
"""Mirror of fn_new_player_code() in the schema. Used only to recognise an
allowlist entry that cannot be a code, so the mistake is named in the log."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql://postgres@localhost:5432/appdb"
    db_pool_min: int = 2
    db_pool_max: int = 10

    # ----- accounts and sessions ------------------------------------------

    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"

    session_ttl_seconds: int = 60 * 60 * 24 * 30
    """How long a sign-in lasts. Thirty days, fixed rather than sliding.

    This was twelve hours while Telegram was the front door, because Telegram
    re-authenticated silently every time the app opened. A website has no
    equivalent: a short session is a password prompt, and for a guest — whose
    cookie is the *only* key to their account — it is the account itself.
    """

    internal_api_key: str = ""
    """Shared secret between the web tier and this API.

    The browser never talks to this service; the Next.js server does, on the
    visitor's behalf. That leaves the three routes that create a session —
    register, sign in, play as a guest — as the only unauthenticated writes,
    and they are exactly the ones worth throttling per visitor. A per-visitor
    throttle needs the visitor's address, which only the web tier can see.

    So the web tier sends this key, and only a request carrying it may (a) use
    those routes at all and (b) say whose address it is acting for. Without
    it the `X-Client-IP` header would be a field anyone could fill in.

    Empty in development, where everything runs on one machine and the socket
    address is already the truth. Required in production.
    """

    signup_bonus_minor: int = 100_000
    """Opening balance: 1,000 points. With the daily top-up, this is enough to
    play indefinitely without paying anything."""

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    admin_player_codes: Annotated[list[str], NoDecode] = Field(default_factory=list)
    """Player codes that may read /v1/admin/*. Empty denies everyone.

    A player code and not an email address, deliberately. Addresses here are
    unverified — nothing sends mail — so an allowlist of emails would hand the
    admin pages to whoever registered the operator's address first. A code
    only exists once its account does, and nobody can choose one.
    """

    password_min_length: int = 10
    password_max_length: int = 128

    password_hash_time_cost: int = 2
    password_hash_memory_kib: int = 19_456
    password_hash_parallelism: int = 1
    """Argon2id parameters — OWASP's minimum profile (19 MiB, 2 passes, 1 lane).

    Sized for the container rather than for a benchmark: each hash in flight
    holds its memory for the duration, and a 512 MB instance that allowed
    64 MiB a hash would be one burst of sign-ins away from the OOM killer.
    `password_hash_concurrency` bounds how many run at once for the same
    reason. Raise the memory cost alongside the instance size; stored hashes
    carry their own parameters and are upgraded at the next sign-in.
    """
    password_hash_concurrency: int = 2

    login_rate_max: int = 10
    login_rate_window_seconds: int = 900
    """Sign-in attempts allowed against one email in the window.

    Counted per address rather than per caller, because a distributed guess at
    one account arrives from many callers and looks like nothing from any one
    of them. The cost is that somebody can lock a stranger out for the window;
    it is short for that reason, and nothing of value sits behind the lock.
    """

    auth_ip_rate_max: int = 30
    auth_ip_rate_window_seconds: int = 900

    signup_ip_rate_max: int = 10
    signup_ip_rate_window_seconds: int = 3600
    """New accounts — registered or guest — one visitor may open per window."""

    message_rate_window_seconds: int = 3600
    message_rate_max: int = 5

    # ----- articles --------------------------------------------------------

    article_max_open: int = 20
    """Unfinished articles one account may hold at a time."""

    article_submit_rate_max: int = 3
    article_submit_rate_window_seconds: int = 86_400
    """Different articles one account may put in front of a reviewer per
    window. Protects the person who reads the queue, like the message limit
    protects the person who reads the inbox."""

    # ----- safer play ------------------------------------------------------

    limit_loosen_delay_seconds: int = 86_400
    """How long a daily limit must stand before it can be raised or removed.

    Tightening is immediate. Loosening waits, because the moment somebody most
    wants a limit gone is the moment it is doing its job.
    """

    break_options_hours: Annotated[list[int], NoDecode] = Field(
        default_factory=lambda: [24, 72, 168, 720]
    )
    """The lengths of break on offer: a day, three days, a week, a month."""

    reference_margin: float = 0.05
    """The bookmaker margin the reality check illustrates with, per pick.

    This product charges no margin, so it has no figure of its own to show.
    The reality check instead answers "what would this same record have cost
    somewhere that does" — and it needs a number to do that with. Five percent
    a pick is an illustration the page labels as one, not a claim about any
    particular operator.
    """

    # ----- infrastructure --------------------------------------------------

    redis_url: str = "redis://localhost:6379/0"

    gamma_api_url: str = "https://gamma-api.polymarket.com"
    clob_api_url: str = "https://clob.polymarket.com"
    http_timeout_seconds: float = 10.0
    http_max_retries: int = 3
    http_user_agent: str = "api-client/1.0"

    # ----- ingestion workers ----------------------------------------------

    workers_enabled: bool = False
    run_discovery_on_startup: bool = True

    catch_up_on_startup: bool = True
    """Run the price sync, settlement and the standings once, in that order,
    as the process starts — instead of leaving each to its first tick.

    A process that has been running all along gains nothing from this. One
    that has not — a host that puts an idle server to sleep and wakes it for
    the next visitor, or a restart after an outage — would otherwise show
    prices older than the staleness window for its first minute, hold finished
    forecasts unsettled for five, and leave the standings alone until the hour
    next turns. On a host that sleeps, the hour may never turn while the
    process is awake to see it.
    """

    discovery_interval_minutes: int = 60
    discovery_categories: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["Politics", "Macro", "Crypto"]
    )

    discovery_priority_category: str = ""
    """A category the feed should be built around, or empty for none.

    A priority category gets three things the others do not: its own pass over
    Gamma, so it is never missed because its events trade below the volume
    cut; first claim on the ingest budget; and immunity from the surplus trim.
    Without all three a niche category is technically enabled and practically
    absent — every one of its markets loses a volume ranking to Bitcoin and
    the Fed, which is the ordering every other stage in the pipeline uses.

    Empty by default: a general audience is served by the volume ordering.
    Set it, with the tag slugs below, for a deployment built around one topic.
    """

    discovery_priority_tag_slugs: Annotated[list[str], NoDecode] = Field(default_factory=list)
    """Gamma tag slugs fetched directly, ahead of the volume-ordered pages.

    Gamma's taxonomy is not ours and it moves. If these stop matching, the
    priority pass returns nothing and the run degrades to the ordinary paged
    fetch rather than failing — check the discovery logs for the tags it saw
    but could not place.
    """
    discovery_page_size: int = 100
    discovery_max_pages: int = 20

    discovery_deadline_seconds: float = 900.0
    """How long one discovery pass may take before it is abandoned.

    Generous on purpose. A healthy pass — fetch Gamma, write a few hundred
    rows — is well under a minute, so this never paces one; it bounds a
    runaway. It stays inside RUNAWAY_AFTER_SECONDS so that a run which trips
    "this job is hung" has actually hung, or the alarm is noise.
    """

    discovery_order: str = "volume24hr"
    discovery_order_ascending: bool = False

    price_sync_interval_seconds: int = 60

    price_sync_deadline_seconds: float = 45.0

    price_fetch_retries: int = 1
    price_fetch_timeout_seconds: float = 5.0

    price_sync_max_markets: int = 400

    resolution_interval_minutes: int = 5
    resolution_concurrency: int = 20
    resolution_batch_size: int = 200
    resolution_settle_batch_size: int = 500
    resolution_overdue_hours: int = 48
    price_sync_concurrency: int = 50

    price_source: str = "midpoint"

    price_cache_ttl_seconds: int = 300
    price_staleness_seconds: int = 90

    snapshot_min_delta: float = 0.005
    snapshot_heartbeat_seconds: int = 900

    market_lock_buffer_seconds: int = 300

    # ----- what moved -------------------------------------------------------

    moves_day_threshold: float = 0.05
    moves_week_threshold: float = 0.10
    """How far a question's chance must have changed to be reported as having
    moved: five points in a day, ten in a week.

    Below that is the ordinary noise of a market — a price ticking between a
    bid and an ask — and a page of it would be a page of nothing, presented as
    news.
    """

    moves_min_hours_to_close: int = 24
    moves_decided_margin: float = 0.03
    """What keeps a result from being reported as a move.

    A question about to close does not drift, it collapses: "above $66,000 on
    the 27th?" goes from 40% to 1% on the 27th because the day arrived, not
    because anybody learned anything. So a question closing within
    `moves_min_hours_to_close` is left out, and so is one that is already all
    but decided — within `moves_decided_margin` of 0 or of 100%, now or at
    the start of the window. What is left is questions that were open then
    and are open still.
    """

    moves_max_age_hours: int = 6
    """How old the source's change figures may be and still be called "the
    last day". They are refreshed with the question list, hourly; a server
    that has been asleep refreshes them when it wakes. Older than this they
    describe some earlier day: the list of moves is then not sent at all (503,
    so the site keeps the page it last built), and a question's own page
    leaves its change figures out."""

    moves_price_max_age_seconds: int = 600
    """How old a question's price may be and still be called "now" in the
    list of moves. Prices are read every minute while the server runs, so ten
    minutes forgives a few missed passes; a server that has just woken has the
    prices it went to sleep with, hours old, until its first pass finishes,
    and until then there is no list to send."""

    history_cache_seconds: int = 600
    history_timeout_seconds: float = 3.0
    """A question's page draws a week of hourly prices, read from the source
    when the page is asked for and kept for ten minutes. The timeout is short
    on purpose: the page is worth having without its chart, and not worth
    waiting on."""

    # ----- the forecasting game -------------------------------------------

    min_prob: float = 0.01
    max_prob: float = 0.99
    """The band of probabilities a question can be forecast at.

    Outside it a question is closed to forecasts rather than priced at the
    edge. Clamping is the obvious thing to do and it is an exploit: a market
    at 99.9% clamped to 99% pays 1.0101 on something all but certain, which
    is free points for whoever notices. Refusing costs nothing — a question
    that close to settled is not a forecast.

    The band is also what bounds the odds: at 1% the fair price is 100 to one,
    and nothing here pays more than that on a single question.
    """

    max_legs: int = 5

    max_combined_odds: float = 1_000.0
    """The longest price a slip may carry, across all of its picks.

    Fair odds on five long shots multiply into numbers with nine digits, and a
    feed where the fastest way up the table is a lottery ticket is a lottery.
    A ceiling keeps the game about being right more often than the crowd, not
    about being lucky once.
    """

    min_stake_minor: int = 1_000
    max_stake_minor: int = 500_000
    payout_cap_minor: int = 10_000_000

    odds_drift_tolerance: float = 0.01

    economy_timezone: str = "UTC"

    daily_topup_minor: int = 20_000
    """The free daily top-up: 200 points, the same every day.

    Flat on purpose. It used to grow with a streak, and a streak is a reason
    to come back that has nothing to do with wanting to — miss a day and
    something is taken away. The top-up exists so that nobody is ever stuck
    and nobody ever *has* to buy anything, and it does that job at any cadence.
    """

    # ----- the shop --------------------------------------------------------

    stripe_secret_key: str = ""
    """Stripe's secret key. **Empty means the shop is closed**: no route sells
    anything, the site says points cannot be bought, and nothing below matters.
    Setting it is the act of opening the shop."""

    stripe_webhook_secret: str = ""
    """The signing secret of the Stripe webhook endpoint that points at
    `/v1/payments/stripe/webhook`. Points are credited only by a webhook whose
    signature this verifies — never by the browser coming back from checkout,
    which proves nothing. Required whenever `stripe_secret_key` is set."""

    stripe_api_base: str = "https://api.stripe.com"

    site_url: str = ""
    """The public address of the website, e.g. https://example.org. Where
    Stripe sends somebody after they pay or change their mind. Falls back to
    the first of `cors_origins`."""

    shop_currency: str = "usd"

    shop_price_per_thousand_cents: int = 200
    """What 1,000 points cost. **One price, whatever the size of the pack**:
    there is deliberately no setting for a volume discount, because a discount
    for buying more is a reason to buy more than somebody came for."""

    shop_pack_points: Annotated[list[int], NoDecode] = Field(
        default_factory=lambda: [1_000, 2_500, 5_000]
    )
    """The pack sizes on offer, in whole points."""

    shop_monthly_cap_cents: int = 2_000
    """The most one account can spend in a calendar month, in cents. A ceiling
    nobody can lift for themselves: a player's own limit may be lower, never
    higher. This is what stops running out of points from turning into the
    thing this site exists to get people away from."""

    shop_checkout_minutes: int = 30
    """How long a started checkout stays open — Stripe's minimum. An unfinished
    one counts towards the monthly cap until it lapses, so that several cannot
    be opened side by side to step over it."""

    shop_min_age: int = 18

    leaderboard_min_volume_minor: int = 10_000
    leaderboard_full_credit_volume_minor: int = 500_000
    leaderboard_profit_weight: float = 1.0
    leaderboard_roi_weight: float = 0.5

    @field_validator(
        "cors_origins", "discovery_categories", "discovery_priority_tag_slugs", mode="before"
    )
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("shop_pack_points", mode="before")
    @classmethod
    def _split_packs(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.split(",") if part.strip()]
        return value

    @field_validator("shop_pack_points")
    @classmethod
    def _sensible_packs(cls, value: list[int]) -> list[int]:
        if any(size <= 0 for size in value):
            raise ValueError("shop_pack_points must all be positive")
        return sorted(set(value))

    @field_validator("shop_currency")
    @classmethod
    def _currency_code(cls, value: str) -> str:
        code = value.strip().lower()
        if len(code) != 3 or not code.isalpha():
            raise ValueError("shop_currency must be a three-letter currency code, e.g. usd")
        return code

    @field_validator("site_url", "stripe_api_base")
    @classmethod
    def _no_trailing_slash(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @field_validator("break_options_hours", mode="before")
    @classmethod
    def _split_hours(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part.strip()) for part in value.split(",") if part.strip()]
        return value

    @field_validator("break_options_hours")
    @classmethod
    def _sane_breaks(cls, value: list[int]) -> list[int]:
        if not value or any(hours <= 0 for hours in value):
            raise ValueError("break_options_hours needs at least one positive duration")
        return sorted(set(value))

    @field_validator("admin_player_codes", mode="before")
    @classmethod
    def _split_admin_codes(cls, value: object) -> object:
        """Parse the allowlist, discarding anything that cannot be a player code.

        Dropped rather than raised on, and that is a decision with a history.
        The allowlist used to hold numeric Telegram ids and its validator used
        to raise — and an operator who pasted a player code where an id
        belonged took the whole API down at import time, over a typo in an
        admin convenience.

        Loud startup failure is right for a missing JWT_SECRET, because
        serving without one is worse than not serving. It is wrong here. This
        list decides who may read the admin pages, and the failure direction
        that matters is *granting* access, not withholding it. A junk entry
        grants nothing — the same outcome as the variable being unset, which
        is already a supported state.

        The entry is named in the log so the mistake is fixable, and named
        rather than counted because "1 invalid entry" in a comma-separated
        list is not enough to find it.
        """
        if isinstance(value, str):
            value = value.split(",")
        if not isinstance(value, list):
            return value

        codes: list[str] = []
        rejected: list[str] = []
        for typed in (str(p).strip() for p in value):
            if not typed:
                continue
            code = typed.upper()
            if len(code) == 6 and set(code) <= PLAYER_CODE_ALPHABET:
                codes.append(code)
            else:
                # As typed, not upper-cased: this goes in a log line somebody
                # will search their environment for.
                rejected.append(typed)
        if rejected:
            logger.warning(
                "ADMIN_PLAYER_CODES: ignoring %d entry/entries that are not player codes: "
                "%s. These grant no admin access. A player code is the six-character "
                "handle on the account page — not an email address. %d valid code(s) remain.",
                len(rejected),
                ", ".join(repr(r) for r in rejected),
                len(codes),
            )
        return codes

    @field_validator("price_source")
    @classmethod
    def _known_price_source(cls, value: str) -> str:
        if value not in {"midpoint", "ask"}:
            raise ValueError("price_source must be 'midpoint' or 'ask'")
        return value

    @field_validator("reference_margin")
    @classmethod
    def _plausible_margin(cls, value: float) -> float:
        if not 0 < value < 0.5:
            raise ValueError("reference_margin must be between 0 and 0.5")
        return value

    @field_validator("economy_timezone", mode="before")
    @classmethod
    def _known_timezone(cls, value: object) -> object:
        """Blank means UTC; anything else has to be a zone this machine knows.

        A deployment form that prompts for this and is left empty sets the
        variable to "", and a zone name is easy to misspell. Unchecked, either
        one surfaces at the first request that needs a date — a 500 on the
        profile page — instead of here, at startup, where the cause is named.
        """
        if not isinstance(value, str):
            return value
        zone = value.strip() or "UTC"
        try:
            ZoneInfo(zone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(
                f"economy_timezone {zone!r} is not a known IANA time zone "
                "(expected a name like 'UTC' or 'Europe/London')"
            ) from exc
        return zone

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def shop_open(self) -> bool:
        """Whether anything is for sale. One switch: the Stripe key."""
        return bool(self.stripe_secret_key)

    @property
    def public_site_url(self) -> str:
        if self.site_url:
            return self.site_url
        return self.cors_origins[0].rstrip("/") if self.cors_origins else ""

    def pack_price_cents(self, points: int) -> int:
        """The price of a pack of `points` whole points. Linear, by design."""
        return round(points * self.shop_price_per_thousand_cents / 1000)

    def require_secrets(self) -> None:
        """Refuse to serve production traffic with development placeholders."""
        if not self.jwt_secret:
            raise RuntimeError("Missing required configuration: JWT_SECRET")
        if self.is_production and len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be at least 32 characters in production.")
        if self.is_production and len(self.internal_api_key) < 32:
            # Without it the sign-up and sign-in routes are open to anyone who
            # finds this service's address, and the per-visitor throttle is
            # keyed on the web tier's own address — one bucket for everybody.
            raise RuntimeError("INTERNAL_API_KEY must be at least 32 characters in production.")
        if self.is_production and "*" in self.cors_origins:
            # CORSMiddleware is mounted with allow_credentials=True, and
            # starlette's answer to "*" under credentials is not the literal
            # string — it reflects whatever Origin the request sent, which is
            # "allow any site to make authenticated requests" with extra
            # steps. There is no reading of a wildcard that is safe here.
            raise RuntimeError('CORS_ORIGINS must not be "*" in production.')
        if self.min_stake_minor <= 0 or self.max_stake_minor < self.min_stake_minor:
            raise RuntimeError("Stake limits are inconsistent: need 0 < MIN_STAKE <= MAX_STAKE.")
        if not (
            0 < self.moves_day_threshold < 1
            and 0 < self.moves_week_threshold < 1
            and 0 <= self.moves_decided_margin < 0.5
            and self.moves_min_hours_to_close >= 0
            and self.moves_max_age_hours > 0
            and self.moves_price_max_age_seconds > 0
        ):
            # A threshold of zero would report every question as having moved,
            # every day, and call it news.
            raise RuntimeError(
                "The MOVES_* settings are inconsistent: thresholds must be between 0 and 1, "
                "MOVES_DECIDED_MARGIN below 0.5, and the age settings positive."
            )
        if self.shop_open:
            self._require_a_safe_shop()

    def _require_a_safe_shop(self) -> None:
        """Refuse to sell anything on a half-configured shop.

        Each of these would take somebody's money and then fail to do the
        other half of the bargain, or would quietly remove a limit. Better
        that the service does not start.
        """
        if not self.stripe_webhook_secret:
            # Without it nothing can confirm a payment, so every purchase
            # would be paid for and never credited.
            raise RuntimeError(
                "STRIPE_WEBHOOK_SECRET is required when STRIPE_SECRET_KEY is set: "
                "points are credited only by a verified webhook."
            )
        if self.is_production and not self.stripe_secret_key.startswith(("sk_live_", "rk_live_")):
            raise RuntimeError(
                "STRIPE_SECRET_KEY is not a live key. Production would send real visitors "
                "to a test checkout."
            )
        if not self.public_site_url.startswith(("https://", "http://localhost")):
            raise RuntimeError(
                "SITE_URL must be the site's https address when the shop is open: "
                "it is where Stripe returns people after checkout."
            )
        if self.shop_monthly_cap_cents <= 0:
            raise RuntimeError(
                "SHOP_MONTHLY_CAP_CENTS must be positive. To stop selling, unset "
                "STRIPE_SECRET_KEY; a shop with no cap is not an option."
            )
        if self.shop_price_per_thousand_cents <= 0 or not self.shop_pack_points:
            raise RuntimeError("The shop has nothing to sell: set a price and at least one pack.")
        if not 30 <= self.shop_checkout_minutes <= 24 * 60:
            raise RuntimeError(
                "SHOP_CHECKOUT_MINUTES must be between 30 and 1440 (Stripe's limits)."
            )
        cheapest = self.pack_price_cents(self.shop_pack_points[0])
        if cheapest < 50:
            raise RuntimeError(
                "The smallest pack costs less than Stripe's minimum charge (50 cents)."
            )
        if cheapest > self.shop_monthly_cap_cents:
            raise RuntimeError("The smallest pack costs more than the monthly cap allows.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
