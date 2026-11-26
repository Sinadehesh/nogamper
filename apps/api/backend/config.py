"""Runtime configuration. Fails loudly at startup rather than at first request.

## What is deliberately not here

This service used to price a house margin, sell its currency and pay out
prizes, and every one of those had a setting. They are gone rather than set to
zero: there is no `vig_rate`, no boost schedule, no insurance load, no package
list. A product that says it takes nothing should not be one environment
variable away from taking something.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated

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
    """Opening balance: 1,000 points. Nothing is ever sold, so this and the
    daily top-up are the only two ways points come into existence."""

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

    # ----- the forecasting game -------------------------------------------

    min_prob: float = 0.01
    max_prob: float = 0.99
    """Probabilities are clamped into this band before a price is made.

    The band is what bounds the odds: at 1% the fair price is 100 to one, and
    nothing here pays more than that on a single question. It also keeps the
    arithmetic away from a division by something indistinguishable from zero.
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
    and nobody is ever sold anything, and it does that job at any cadence.
    """

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

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
