"""GET /v1/rules — the game's rules, as numbers.

Public and unauthenticated on purpose. These are the figures the site explains
itself with — the opening balance, the daily top-up, how long a slip may be —
and a page that states them from a copy would drift the first time one was
retuned. Rendered from here, the explanation cannot disagree with the game.

Nothing in it is private: every value is either printed on the page already
or discoverable by placing a forecast.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ..config import Settings, get_settings
from ..schemas import GameRules, Money

router = APIRouter(prefix="/v1", tags=["rules"])


@router.get("/rules", response_model=GameRules, summary="The rules of the game, as configured")
async def read_rules(settings: Annotated[Settings, Depends(get_settings)]) -> GameRules:
    return GameRules(
        signup_bonus=Money.of(settings.signup_bonus_minor),
        daily_topup=Money.of(settings.daily_topup_minor),
        min_stake=Money.of(settings.min_stake_minor),
        max_stake=Money.of(settings.max_stake_minor),
        payout_cap=Money.of(settings.payout_cap_minor),
        max_legs=settings.max_legs,
        max_combined_odds=str(settings.max_combined_odds),
        min_prob=str(settings.min_prob),
        max_prob=str(settings.max_prob),
        margin="0",
        reference_margin=str(settings.reference_margin),
        limit_loosen_delay_hours=round(settings.limit_loosen_delay_seconds / 3600),
        break_options_hours=settings.break_options_hours,
        password_min_length=settings.password_min_length,
    )
