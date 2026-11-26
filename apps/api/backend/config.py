"""Runtime configuration. Fails loudly at startup rather than at first request."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql://postgres@localhost:5432/appdb"
    db_pool_min: int = 2
    db_pool_max: int = 10

    telegram_bot_token: str = ""

    telegram_api_url: str = "https://api.telegram.org"

    telegram_webhook_secret: str = ""

    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = 60 * 60 * 12

    init_data_ttl_seconds: int = 3600

    signup_bonus_minor: int = 500_000_000

    referral_bonus_minor: int = 100_000_000

    referral_bonus_window_seconds: int = 86_400
    referral_bonus_max_per_window: int = 20

    telegram_bot_username: str = ""
    telegram_mini_app_short_name: str = ""

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    admin_telegram_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    message_rate_window_seconds: int = 3600
    message_rate_max: int = 5

    redis_url: str = "redis://localhost:6379/0"

    gamma_api_url: str = "https://gamma-api.polymarket.com"
    clob_api_url: str = "https://clob.polymarket.com"
    http_timeout_seconds: float = 10.0
    http_max_retries: int = 3
    http_user_agent: str = "api-client/1.0"

    translation_provider: str = "null"
    translation_api_url: str = ""
    translation_api_key: str = ""
    translation_model: str = "gpt-4o-mini"

    translation_temperature: float | None = None
    """Sampling temperature, or None to let the provider choose.

    Omitted by default because it is the only setting valid everywhere. This
    was pinned to 0 — right for translation, and rejected outright by models
    that allow exactly one value: every request came back
    `invalid temperature: only 1 is allowed for this model`, and because the
    rejection arrived as a 400 body rather than an exception, the run reported
    an unreadable response rather than the reason. Sending nothing lets each
    provider apply its own default, which is always a value it accepts.

    Set it when a provider both accepts and rewards a fixed value.
    """
    translation_date_calendar: str = "auto"
    """Which calendar dates are rendered in: `auto`, `source` or `persian`.

    `auto` follows the target language — Persian (Jalali) for Farsi, the
    source calendar otherwise — because a reader of a Farsi market question
    dates their life by that calendar, and "31 December" is a translation
    only in the sense that the words changed.

    The conversion is the model's arithmetic, not ours, and a market question
    is a statement about when a bet resolves. `source` turns it off and keeps
    the Gregorian dates exactly as Polymarket wrote them.
    """

    translation_source_lang: str = "en"
    translation_target_lang: str = "fa"
    translation_timeout_seconds: float = 180.0
    """How long one translation request may take.

    Separate from `http_timeout_seconds`, which is 10 seconds and right for
    the price and market APIs it was written for: those answer from a cache
    and a slow one is a broken one. A reasoning model is the opposite. It
    spends most of its output budget thinking before it writes a word — a
    single sentence measured 594 reasoning tokens against 38 of prompt — so a
    batch takes minutes, and under the shared default every request was
    aborted at ten seconds, retried three times, and reported as an
    unreachable provider. The feed then ingested English on every run, which
    is indistinguishable from having no translator at all.

    It bounds a hang rather than paces a healthy call, so it is generous. The
    discovery deadline is what actually limits the pass.
    """

    translation_batch_size: int = 8
    """How many strings go into one translation request.

    This was 25, then raised to 50 in production trying to cut the number of
    round trips, and both were wrong in the same direction: a reasoning model
    spends roughly 594 reasoning tokens translating *one* short sentence, so
    50 of them in a single call is tens of thousands of reasoning tokens —
    comfortably more than translation_timeout_seconds buys, however generous
    that is set. A batch that cannot finish inside its own timeout does not
    degrade; it fails outright, on every attempt, forever, and at
    concurrency=1 it burns the run's entire budget doing so — a real
    production run spent 1800s failing to translate a single 50-item batch
    and never got to try another one.

    Smaller batches trade round trips for actually finishing: each one lands
    and is cached the moment it succeeds, so a run that cannot get through
    the whole backlog in one pass still keeps every batch that did complete,
    and the next hourly run resumes from there rather than from zero.
    """

    translation_concurrency: int = 1
    """How many translation requests may be in flight at once.

    Defaults to the strictest case rather than a throughput-friendly one.
    Kimi's moonshot.ai account — the provider this pipeline was built
    against — allows exactly one concurrent request; a second one gets HTTP
    429 ("max organization concurrency: 1") immediately, before the first has
    had time to answer. Against a reasoning model that holds its one slot for
    minutes, `post_json`'s few short retries run out long before that slot
    frees up, so every batch but the one that won the race fails outright —
    on every run, forever, because the same race repeats each time.

    Raise it only for a provider whose account is actually provisioned for
    more than one concurrent call.
    """

    workers_enabled: bool = False
    run_discovery_on_startup: bool = True

    discovery_interval_minutes: int = 60
    discovery_categories: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["Iran", "Macro", "Crypto"]
    )

    discovery_priority_category: str = "Iran"
    """The category the feed is built around.

    It gets three things the others do not: its own pass over Gamma, so it is
    never missed because its events trade below the volume cut; first claim on
    the ingest budget; and immunity from the surplus trim. Without all three a
    niche category is technically enabled and practically absent — every one
    of its markets loses a volume ranking to Bitcoin and the Fed, which is the
    ordering every other stage in the pipeline uses.

    Set to an empty string to turn the preference off and treat all categories
    equally.
    """

    discovery_priority_tag_slugs: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["iran"]
    )
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

    This was 240, and 240 was measured against a pass that did not translate.
    Once the translator started working the shape changed completely: fetching
    Gamma is under a minute, and the rest is a reasoning model answering one
    batch at a time — the provider allows a single concurrent request, and one
    batch is minutes, not seconds. Every production run died at 241 seconds
    with the batches still in flight, which reads as a hung worker and is
    really a budget written for different work.

    It bounds a runaway pass rather than paces a healthy one, so it is sized
    for the slow case and stays inside RUNAWAY_AFTER_SECONDS — a run that trips
    "this job is hung" has to actually be hung, or the alarm is noise.
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

    min_prob: float = 0.01
    max_prob: float = 0.99

    vig_rate: float = 0.07
    max_legs: int = 5

    parlay_bonus_by_legs: Annotated[list[float], NoDecode] = Field(
        default_factory=lambda: [1.0, 1.02, 1.04, 1.06, 1.08]
    )

    example_stake_minor: int = 100_000_000

    min_legs: int = 1

    min_leg_odds: float = 1.01
    max_combined_odds: float = 15_000_000_000.0

    min_stake_minor: int = 5_000_000
    max_stake_minor: int = 500_000_000
    payout_cap_minor: int = 2_500_000_000_000

    uncapped_below_probability: float = 0.0001

    house_seed_minor: int = 2_500_000_000

    max_market_liability_minor: int = 10_000_000_000_000

    odds_drift_tolerance: float = 0.01

    invoice_ttl_seconds: int = 3600
    max_open_invoices_per_user: int = 5
    invoice_sweep_interval_minutes: int = 15

    reconciliation_grace_minutes: int = 5
    reconciliation_window_hours: int = 24
    reconciliation_batch_size: int = 200
    reconciliation_max_pages: int = 10

    economy_timezone: str = "UTC"

    daily_drip_minor: int = 50_000_000
    streak_bonus_step_minor: int = 25_000_000
    streak_bonus_max_minor: int = 250_000_000

    decay_rate: float = 0.05
    decay_inactive_days: int = 3
    decay_floor_minor: int = 250_000_000
    decay_skips_open_slips: bool = True
    decay_batch_size: int = 5_000

    boost_generation_interval_minutes: int = 60
    boosts_per_run: int = 3
    boost_min_multiplier: float = 1.10
    boost_max_multiplier: float = 1.50
    boost_duration_hours: int = 4
    boost_max_total_stake_minor: int = 5_000_000_000
    boost_max_stake_per_user_minor: int = 500_000_000
    boost_max_raw_prob: float = 0.10
    boost_min_volume_usd: float = 10_000.0

    leaderboard_min_volume_minor: int = 500_000_000
    leaderboard_full_credit_volume_minor: int = 10_000_000_000
    leaderboard_profit_weight: float = 1.0
    leaderboard_roi_weight: float = 0.5

    insurance_load: float = 0.35
    insurance_min_rate: float = 0.05
    insurance_max_rate: float = 0.60
    insurance_min_legs: int = 4
    insurance_covers_failed_legs: int = 1

    @field_validator("parlay_bonus_by_legs", mode="before")
    @classmethod
    def _split_bonuses(cls, value: object) -> object:
        if isinstance(value, str):
            return [float(part.strip()) for part in value.split(",") if part.strip()]
        return value

    @field_validator(
        "cors_origins", "discovery_categories", "discovery_priority_tag_slugs", mode="before"
    )
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def _split_admin_ids(cls, value: object) -> object:
        """Parse the allowlist, discarding anything that is not a number.

        This used to raise, and taking the module docstring at its word —
        fail loudly at startup — was the wrong call for this one setting.

        It cost a production outage. The operator, following instructions,
        pasted their six-character *player code* into ADMIN_TELEGRAM_IDS
        instead of their numeric Telegram id. `int("GRDZGN")` raised inside
        Settings(), uvicorn could not import the app, and the whole API was
        down: no markets, no bets, no players, over a typo in an admin
        convenience.

        Loud startup failure is right for a missing JWT_SECRET, because
        serving without one is worse than not serving. It is wrong here.
        This list decides who may read the admin pages, and the failure
        direction that matters is *granting* access, not withholding it. A
        junk entry is dropped, so it grants nothing — the same outcome as the
        variable being unset, which is already a supported state.

        The entry is named in the log so the mistake is fixable, and named
        rather than counted because "1 invalid entry" in a comma-separated
        list is not enough to find it.
        """
        if isinstance(value, str):
            ids: list[int] = []
            rejected: list[str] = []
            for part in (p.strip() for p in value.split(",")):
                if not part:
                    continue
                try:
                    ids.append(int(part))
                except ValueError:
                    rejected.append(part)
            if rejected:
                logger.warning(
                    "ADMIN_TELEGRAM_IDS: ignoring %d entry/entries that are not numeric "
                    "Telegram ids: %s. These grant no admin access. A Telegram id is all "
                    "digits — a player code (letters) is a different thing. %d valid id(s) "
                    "remain.",
                    len(rejected),
                    ", ".join(repr(r) for r in rejected),
                    len(ids),
                )
            return ids
        return value

    @field_validator("translation_date_calendar")
    @classmethod
    def _known_calendar(cls, value: str) -> str:
        allowed = {"auto", "source", "persian"}
        if value not in allowed:
            raise ValueError(f"translation_date_calendar must be one of {sorted(allowed)}")
        return value

    @field_validator("translation_provider")
    @classmethod
    def _known_translation_provider(cls, value: str) -> str:
        allowed = {"null", "libretranslate", "openai"}
        if value not in allowed:
            raise ValueError(f"translation_provider must be one of {sorted(allowed)}")
        return value

    @field_validator("price_source")
    @classmethod
    def _known_price_source(cls, value: str) -> str:
        if value not in {"midpoint", "ask"}:
            raise ValueError("price_source must be 'midpoint' or 'ask'")
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def parlay_bonus(self, legs: int) -> float:
        """The bonus for a slip of this many legs, 1.0 if none is configured."""
        if legs < 1 or legs > len(self.parlay_bonus_by_legs):
            return 1.0
        return self.parlay_bonus_by_legs[legs - 1]

    def house_edge_at(self, legs: int) -> float:
        """Expected margin on a slip of this many legs, after the bonus."""
        return 1.0 - (1.0 - self.vig_rate) ** legs * self.parlay_bonus(legs)

    def require_secrets(self) -> None:
        """Refuse to serve production traffic with development placeholders."""
        missing = [
            name
            for name, value in (
                ("TELEGRAM_BOT_TOKEN", self.telegram_bot_token),
                ("JWT_SECRET", self.jwt_secret),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing required configuration: {', '.join(missing)}")
        if self.is_production and len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be at least 32 characters in production.")
        if self.is_production and len(self.telegram_webhook_secret) < 16:
            raise RuntimeError(
                "TELEGRAM_WEBHOOK_SECRET must be at least 16 characters in production."
            )
        if self.translation_provider == "libretranslate" and not self.translation_api_url:
            raise RuntimeError(
                "TRANSLATION_API_URL is required when TRANSLATION_PROVIDER=libretranslate."
            )
        if self.is_production and "*" in self.cors_origins:
            # CORSMiddleware is mounted with allow_credentials=True, and
            # starlette's answer to "*" under credentials is not the literal
            # string — it reflects whatever Origin the request sent, which is
            # "allow any site to make authenticated requests" with extra
            # steps. There is no reading of a wildcard that is safe here.
            raise RuntimeError('CORS_ORIGINS must not be "*" in production.')


@lru_cache
def get_settings() -> Settings:
    return Settings()
