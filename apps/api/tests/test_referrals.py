"""Invite a friend, get paid when they actually play.

`users.referred_by` has existed since the very first migration, unused. This
is what wires it up: a Mini App deep link carries the inviter's own
player_code as Telegram's `start_param`, the new account attaches to it once
at creation, and the referrer is credited the moment — and only the moment —
the person they brought in places a bet.

The two halves are tested separately because they answer different
questions. Attaching the referrer is about the signup path and must never
apply to a returning player. Paying the referrer is about the ledger and
must fire exactly once no matter how many bets follow, which is also the
reason the two are simulated on different timelines: growth (referred_count)
is visible before a single bet is placed; earnings never are.
"""

from __future__ import annotations

import uuid

from conftest import make_init_data
from test_predictions import body, seed_markets

from backend import db

SESSION = "/v1/auth/session"
ME = "/v1/me"


async def sign_up(client, telegram_id: int, **extra) -> dict:
    response = await client.post(SESSION, json={"initData": make_init_data(telegram_id, **extra)})
    response.raise_for_status()
    return response.json()


async def auth_header(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['access_token']}"}


async def referred_by(telegram_id: int) -> uuid.UUID | None:
    async with db.acquire() as conn:
        return await conn.fetchval(
            "SELECT referred_by FROM users WHERE telegram_id = $1", telegram_id
        )


def _with_referral_cap(monkeypatch, value: int):
    from backend.config import get_settings

    monkeypatch.setenv("REFERRAL_BONUS_MAX_PER_WINDOW", str(value))
    get_settings.cache_clear()
    return get_settings


def _with_bot_config(monkeypatch, *, username="ExampleBot", short_name="app"):
    from backend.config import get_settings

    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", username)
    monkeypatch.setenv("TELEGRAM_MINI_APP_SHORT_NAME", short_name)
    get_settings.cache_clear()
    return get_settings


async def test_a_new_player_attaches_to_the_code_that_brought_them(app_client):
    inviter = await sign_up(app_client, 900001)
    code = inviter["user"]["player_code"]

    invitee = await sign_up(app_client, 900002, start_param=code)

    assert invitee["is_new_user"] is True
    assert await referred_by(900002) == uuid.UUID(inviter["user"]["id"])


async def test_the_code_is_not_case_sensitive(app_client):
    """A code shared as text, retyped by hand, should not fail on case alone —
    player_code is stored upper and fn_new_player_code's own alphabet has no
    case distinction to preserve."""
    inviter = await sign_up(app_client, 900101)
    code = inviter["user"]["player_code"].lower()

    await sign_up(app_client, 900102, start_param=code)

    assert await referred_by(900102) == uuid.UUID(inviter["user"]["id"])


async def test_an_unknown_code_is_a_quiet_no_op(app_client):
    """A mistyped or stale invite link must never be a reason the signin
    itself fails — the player just ends up with no referrer, same as if they
    had never followed a link."""
    session = await sign_up(app_client, 900201, start_param="ZZZZZZ")

    assert session["is_new_user"] is True
    assert await referred_by(900201) is None


async def test_a_returning_player_is_never_attached_retroactively(app_client):
    """The guard that matters most: `was_created` in open_session. Without
    it, anyone could backfill a referrer onto an existing account just by
    relaunching through someone else's link."""
    inviter = await sign_up(app_client, 900301)
    await sign_up(app_client, 900302)
    assert await referred_by(900302) is None

    await sign_up(app_client, 900302, start_param=inviter["user"]["player_code"])

    assert await referred_by(900302) is None


async def test_growth_is_visible_before_any_bet_is_placed(app_client):
    """referred_count answers "how many people did I bring in", which is
    true the instant they sign up. Earnings answer a different question and
    must stay at zero until one of them actually plays — conflating the two
    would show a number the inviter has not actually been paid."""
    inviter = await sign_up(app_client, 900401)
    await sign_up(app_client, 900402, start_param=inviter["user"]["player_code"])

    profile = (await app_client.get(ME, headers=await auth_header(inviter))).json()

    assert profile["referred_count"] == 1
    assert profile["referral_earned"]["minor"] == 0


async def test_the_bonus_is_paid_the_moment_the_referred_player_bets(app_client):
    inviter = await sign_up(app_client, 900501)
    invitee = await sign_up(app_client, 900502, start_param=inviter["user"]["player_code"])

    markets = await seed_markets(3)
    placed = await app_client.post(
        "/v1/predictions",
        json=body(markets, stake=50_000),
        headers={**await auth_header(invitee), "Idempotency-Key": "referral-first-bet"},
    )
    assert placed.status_code == 201, placed.text

    from backend.config import get_settings

    profile = (await app_client.get(ME, headers=await auth_header(inviter))).json()
    assert profile["referral_earned"]["minor"] == get_settings().referral_bonus_minor
    assert profile["referred_count"] == 1


async def test_a_second_bet_from_the_same_player_does_not_pay_twice(app_client):
    inviter = await sign_up(app_client, 900601)
    invitee = await sign_up(app_client, 900602, start_param=inviter["user"]["player_code"])

    markets = await seed_markets(6)
    for i, key in enumerate(["bet-a", "bet-b"]):
        await app_client.post(
            "/v1/predictions",
            json=body(markets[i * 3 : i * 3 + 3], stake=50_000),
            headers={**await auth_header(invitee), "Idempotency-Key": key},
        )

    from backend.config import get_settings

    profile = (await app_client.get(ME, headers=await auth_header(inviter))).json()
    assert profile["referral_earned"]["minor"] == get_settings().referral_bonus_minor

    async with db.acquire() as conn:
        count = await conn.fetchval(
            "SELECT count(*) FROM ledger_entries "
            "WHERE entry_type = 'REFERRAL_BONUS_CREDIT' AND user_id = $1",
            uuid.UUID(inviter["user"]["id"]),
        )
    assert count == 1


async def test_a_player_with_no_referrer_credits_nobody(app_client):
    """The common case, and the one that must not accidentally credit the
    house or crash: most players arrive with no start_param at all."""
    player = await sign_up(app_client, 900701)
    markets = await seed_markets(1)

    response = await app_client.post(
        "/v1/predictions",
        json=body(markets, stake=50_000),
        headers={**await auth_header(player), "Idempotency-Key": "no-referrer"},
    )
    assert response.status_code == 201

    async with db.acquire() as conn:
        count = await conn.fetchval(
            "SELECT count(*) FROM ledger_entries WHERE entry_type = 'REFERRAL_BONUS_CREDIT'"
        )
    assert count == 0


async def test_the_rate_cap_stops_a_referrer_earning_past_the_window(app_client, monkeypatch):
    """The only defence against one operator farming Telegram accounts to
    refer themselves. A cap of two lets the third referred bettor's own bet
    still succeed — the cap bounds the reward, never the play."""
    get_settings = _with_referral_cap(monkeypatch, 2)
    try:
        inviter = await sign_up(app_client, 900801)
        code = inviter["user"]["player_code"]
        markets = await seed_markets(9)

        for i in range(3):
            invitee = await sign_up(app_client, 900810 + i, start_param=code)
            placed = await app_client.post(
                "/v1/predictions",
                json=body(markets[i * 3 : i * 3 + 3], stake=50_000),
                headers={**await auth_header(invitee), "Idempotency-Key": f"farm-{i}"},
            )
            assert placed.status_code == 201

        profile = (await app_client.get(ME, headers=await auth_header(inviter))).json()
        assert profile["referred_count"] == 3
        assert profile["referral_earned"]["minor"] == 2 * get_settings().referral_bonus_minor
    finally:
        get_settings.cache_clear()


async def test_the_invite_link_is_absent_without_bot_configuration(app_client):
    """Nothing on the server can discover the bot's own @username or its Mini
    App's short name — both come from @BotFather. Omitted rather than built
    wrong is the only safe default."""
    session = await sign_up(app_client, 900901)
    assert session["user"]["invite_link"] is None


async def test_the_invite_link_carries_the_players_own_code(app_client, monkeypatch):
    get_settings = _with_bot_config(monkeypatch)
    try:
        session = await sign_up(app_client, 901001)
        code = session["user"]["player_code"]
        assert session["user"]["invite_link"] == f"https://t.me/ExampleBot/app?startapp={code}"
    finally:
        get_settings.cache_clear()
