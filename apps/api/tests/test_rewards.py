"""Redeeming a balance for a reward, and the burn that makes it mean something.

The point of the feature is that the coins leave. A redemption that returns a
reward while the balance stays put is claimable again the same second, so most
of what is worth testing here is about money not existing afterwards, and
about the item still being owed when delivery has not happened yet.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from conftest import authorise

from backend import db
from backend.services import rewards

GOLD = "gold_badge"
NFT = "founders_nft"


async def activate(code: str, **columns) -> None:
    """Seeded rewards ship inactive on purpose; a test that wants one says so."""
    sets = ", ".join(f"{name} = ${i + 2}" for i, name in enumerate(columns))
    clause = f", {sets}" if columns else ""
    async with db.acquire() as conn:
        # noqa justified: only column *names* are interpolated, and they are
        await conn.execute(
            f"UPDATE rewards SET is_active = TRUE{clause} WHERE code = $1",  # noqa: S608
            code,
            *columns.values(),
        )


async def fund(
    headers: dict[str, str], client, *, coins: int, staked: int | None = None
) -> uuid.UUID:
    """Give the player a balance without going through a purchase flow.

    Written straight to `users` rather than through the ledger: this is
    arranging a precondition, and posting a fake STAR_PURCHASE_CREDIT to do it
    would put a transaction in the history that never happened.
    """
    profile = (await client.get("/v1/me", headers=headers)).json()
    user_id = uuid.UUID(profile["id"])
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE users SET coin_balance = $2, lifetime_staked = $3 WHERE id = $1",
            user_id,
            coins,
            staked if staked is not None else coins,
        )
    return user_id


async def balance_of(user_id: uuid.UUID) -> int:
    async with db.acquire() as conn:
        return await conn.fetchval("SELECT coin_balance FROM users WHERE id = $1", user_id)


async def reward_row(code: str) -> dict:
    async with db.acquire() as conn:
        return dict(await conn.fetchrow("SELECT * FROM rewards WHERE code = $1", code))


async def test_inactive_rewards_are_not_offered(app_client):
    """Everything seeds inactive, because a reward nobody can deliver is a trap."""
    headers = await authorise(app_client)
    body = (await app_client.get("/v1/rewards", headers=headers)).json()
    assert body["rewards"] == []


async def test_the_catalogue_says_why_a_reward_is_out_of_reach(app_client):
    headers = await authorise(app_client)
    await activate(GOLD)
    await fund(headers, app_client, coins=1, staked=0)

    item = (await app_client.get("/v1/rewards", headers=headers)).json()["rewards"][0]

    assert item["code"] == GOLD
    assert item["claimable"] is False
    assert item["blocked_reason"] == "not_enough_play"


async def test_a_player_who_qualifies_is_told_so(app_client):
    headers = await authorise(app_client)
    await activate(GOLD)
    reward = await reward_row(GOLD)
    await fund(headers, app_client, coins=reward["cost"], staked=reward["min_lifetime_staked"])

    item = (await app_client.get("/v1/rewards", headers=headers)).json()["rewards"][0]
    assert item["claimable"] is True
    assert item["blocked_reason"] is None


async def test_remaining_supply_is_reported_and_unlimited_is_null(app_client):
    headers = await authorise(app_client)
    await activate(GOLD)
    await activate(NFT)

    body = (await app_client.get("/v1/rewards", headers=headers)).json()
    items = {i["code"]: i for i in body["rewards"]}
    assert items[GOLD]["remaining"] is None
    assert items[NFT]["remaining"] == 100


async def test_redeeming_burns_the_coins(app_client):
    headers = await authorise(app_client)
    await activate(GOLD)
    reward = await reward_row(GOLD)
    user_id = await fund(headers, app_client, coins=reward["cost"] + 500, staked=reward["cost"])

    response = await app_client.post(
        "/v1/rewards/redeem", json={"reward_code": GOLD}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["balance"]["minor"] == 500
    assert await balance_of(user_id) == 500


async def test_the_burn_is_a_ledger_entry_like_any_other(app_client):
    """Not a bare UPDATE to coin_balance. The ledger is the only way money moves."""
    headers = await authorise(app_client)
    await activate(GOLD)
    reward = await reward_row(GOLD)
    user_id = await fund(headers, app_client, coins=reward["cost"], staked=reward["cost"])

    await app_client.post("/v1/rewards/redeem", json={"reward_code": GOLD}, headers=headers)

    async with db.acquire() as conn:
        entry = await conn.fetchrow(
            "SELECT * FROM ledger_entries WHERE user_id = $1"
            "   AND entry_type = 'REWARD_REDEEM_DEBIT'",
            user_id,
        )
    assert entry is not None
    assert entry["amount"] == -reward["cost"]
    assert entry["balance_after"] == 0
    assert entry["ref_type"] == "REWARD_CLAIM"


async def test_redeeming_twice_needs_the_coins_twice(app_client):
    """The whole mechanic: the second attempt fails because the first spent it."""
    headers = await authorise(app_client)
    await activate(GOLD, per_user_limit=None)
    reward = await reward_row(GOLD)
    await fund(headers, app_client, coins=reward["cost"], staked=reward["cost"])

    first = await app_client.post("/v1/rewards/redeem", json={"reward_code": GOLD}, headers=headers)
    second = await app_client.post(
        "/v1/rewards/redeem", json={"reward_code": GOLD}, headers=headers
    )

    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json()["code"] == "insufficient_funds"


async def test_a_reward_that_is_one_per_player_stays_that_way(app_client):
    headers = await authorise(app_client)
    await activate(GOLD, per_user_limit=1)
    reward = await reward_row(GOLD)
    await fund(headers, app_client, coins=reward["cost"] * 3, staked=reward["cost"] * 3)

    await app_client.post("/v1/rewards/redeem", json={"reward_code": GOLD}, headers=headers)
    again = await app_client.post("/v1/rewards/redeem", json={"reward_code": GOLD}, headers=headers)

    assert again.status_code == 409
    assert again.json()["code"] == "already_claimed"


async def test_playing_is_required_not_only_paying(app_client):
    """A reward with resale value must not be purchasable outright with Stars."""
    headers = await authorise(app_client)
    await activate(GOLD)
    reward = await reward_row(GOLD)
    await fund(headers, app_client, coins=reward["cost"] * 10, staked=0)

    response = await app_client.post(
        "/v1/rewards/redeem", json={"reward_code": GOLD}, headers=headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "not_enough_play"


async def test_an_inactive_reward_cannot_be_redeemed_by_code(app_client):
    """The catalogue hides it; the endpoint must refuse it too."""
    headers = await authorise(app_client)
    reward = await reward_row(NFT)
    await fund(headers, app_client, coins=reward["cost"], staked=reward["cost"])

    response = await app_client.post(
        "/v1/rewards/redeem", json={"reward_code": NFT}, headers=headers
    )
    assert response.status_code == 404


async def test_supply_cannot_be_oversubscribed_by_concurrent_claims(app_client):
    """Two players, one unit left. Exactly one wins.

    The row lock in redeem() is what makes this deterministic; without it both
    read claimed_count = 0 and both take the last one.
    """
    await activate(NFT, total_supply=1, per_user_limit=1)
    reward = await reward_row(NFT)

    people = []
    for telegram_id in (7001, 7002):
        headers = await authorise(app_client, telegram_id=telegram_id)
        user_id = await fund(
            headers, app_client, coins=reward["cost"], staked=reward["min_lifetime_staked"]
        )
        people.append((headers, user_id))

    results = await asyncio.gather(
        *(
            app_client.post("/v1/rewards/redeem", json={"reward_code": NFT}, headers=h)
            for h, _ in people
        )
    )

    codes = sorted(r.status_code for r in results)
    assert codes == [200, 409]

    row = await reward_row(NFT)
    assert row["claimed_count"] == 1

    balances = sorted([await balance_of(user_id) for _, user_id in people])
    assert balances == [0, reward["cost"]]


async def test_a_fresh_claim_is_owed_not_delivered(app_client):
    headers = await authorise(app_client)
    await activate(GOLD)
    reward = await reward_row(GOLD)
    await fund(headers, app_client, coins=reward["cost"], staked=reward["cost"])

    await app_client.post("/v1/rewards/redeem", json={"reward_code": GOLD}, headers=headers)
    claim = (await app_client.get("/v1/rewards/claims", headers=headers)).json()["claims"][0]

    assert claim["status"] == "RESERVED"
    assert claim["fulfilled_at"] is None
    assert claim["fulfilment"] == {}


async def test_delivery_records_its_proof(app_client):
    headers = await authorise(app_client)
    await activate(GOLD)
    reward = await reward_row(GOLD)
    await fund(headers, app_client, coins=reward["cost"], staked=reward["cost"])

    body = (
        await app_client.post("/v1/rewards/redeem", json={"reward_code": GOLD}, headers=headers)
    ).json()

    async with db.transaction() as conn:
        await rewards.fulfil_claim(
            conn, claim_id=uuid.UUID(body["claim_id"]), fulfilment={"chain": "ton", "tx": "0xabc"}
        )

    claim = (await app_client.get("/v1/rewards/claims", headers=headers)).json()["claims"][0]
    assert claim["status"] == "FULFILLED"
    assert claim["fulfilment"] == {"chain": "ton", "tx": "0xabc"}
    assert claim["fulfilled_at"] is not None


async def test_a_mint_that_lands_after_timing_out_still_counts(app_client):
    """FAILED is not terminal. A delivered item is delivered."""
    headers = await authorise(app_client)
    await activate(GOLD)
    reward = await reward_row(GOLD)
    await fund(headers, app_client, coins=reward["cost"], staked=reward["cost"])
    body = (
        await app_client.post("/v1/rewards/redeem", json={"reward_code": GOLD}, headers=headers)
    ).json()
    claim_id = uuid.UUID(body["claim_id"])

    async with db.transaction() as conn:
        await rewards.fail_claim(conn, claim_id=claim_id, reason="mint timed out")
    async with db.transaction() as conn:
        await rewards.fulfil_claim(conn, claim_id=claim_id, fulfilment={"tx": "0xlate"})

    claim = (await app_client.get("/v1/rewards/claims", headers=headers)).json()["claims"][0]
    assert claim["status"] == "FULFILLED"


async def test_an_undeliverable_reward_gives_the_coins_back(app_client):
    headers = await authorise(app_client)
    await activate(NFT, total_supply=5)
    reward = await reward_row(NFT)
    user_id = await fund(
        headers, app_client, coins=reward["cost"], staked=reward["min_lifetime_staked"]
    )
    body = (
        await app_client.post("/v1/rewards/redeem", json={"reward_code": NFT}, headers=headers)
    ).json()
    claim_id = uuid.UUID(body["claim_id"])

    assert await balance_of(user_id) == 0

    async with db.transaction() as conn:
        await rewards.fail_claim(conn, claim_id=claim_id, reason="chain unreachable")
    async with db.transaction() as conn:
        restored = await rewards.refund_claim(conn, claim_id=claim_id)

    assert restored == reward["cost"]
    assert await balance_of(user_id) == reward["cost"]
    assert (await reward_row(NFT))["claimed_count"] == 0


async def test_a_refund_is_a_new_entry_not_an_edit(app_client):
    """ledger_entries is append-only; the debit stays in the history."""
    headers = await authorise(app_client)
    await activate(GOLD)
    reward = await reward_row(GOLD)
    user_id = await fund(headers, app_client, coins=reward["cost"], staked=reward["cost"])
    body = (
        await app_client.post("/v1/rewards/redeem", json={"reward_code": GOLD}, headers=headers)
    ).json()

    async with db.transaction() as conn:
        await rewards.refund_claim(conn, claim_id=uuid.UUID(body["claim_id"]))

    async with db.acquire() as conn:
        types = [
            r["entry_type"]
            for r in await conn.fetch(
                "SELECT entry_type FROM ledger_entries WHERE user_id = $1 ORDER BY id", user_id
            )
        ]
    assert "REWARD_REDEEM_DEBIT" in types
    assert "REWARD_REFUND_CREDIT" in types


async def test_a_claim_cannot_be_refunded_twice(app_client):
    headers = await authorise(app_client)
    await activate(GOLD)
    reward = await reward_row(GOLD)
    user_id = await fund(headers, app_client, coins=reward["cost"], staked=reward["cost"])
    body = (
        await app_client.post("/v1/rewards/redeem", json={"reward_code": GOLD}, headers=headers)
    ).json()
    claim_id = uuid.UUID(body["claim_id"])

    async with db.transaction() as conn:
        await rewards.refund_claim(conn, claim_id=claim_id)

    with pytest.raises(rewards.RewardError) as exc:
        async with db.transaction() as conn:
            await rewards.refund_claim(conn, claim_id=claim_id)

    assert exc.value.code == "already_refunded"
    assert await balance_of(user_id) == reward["cost"]


async def test_a_delivered_reward_is_not_refundable(app_client):
    """Otherwise the item and the coins both end up with the player."""
    headers = await authorise(app_client)
    await activate(GOLD)
    reward = await reward_row(GOLD)
    await fund(headers, app_client, coins=reward["cost"], staked=reward["cost"])
    body = (
        await app_client.post("/v1/rewards/redeem", json={"reward_code": GOLD}, headers=headers)
    ).json()
    claim_id = uuid.UUID(body["claim_id"])

    async with db.transaction() as conn:
        await rewards.fulfil_claim(conn, claim_id=claim_id, fulfilment={"tx": "0x1"})

    with pytest.raises(rewards.RewardError) as exc:
        async with db.transaction() as conn:
            await rewards.refund_claim(conn, claim_id=claim_id)
    assert exc.value.code == "claim_fulfilled"


async def test_a_refunded_claim_frees_the_per_player_limit(app_client):
    """They gave it back, so they have not 'already claimed' it."""
    headers = await authorise(app_client)
    await activate(GOLD, per_user_limit=1)
    reward = await reward_row(GOLD)
    await fund(headers, app_client, coins=reward["cost"], staked=reward["cost"])
    body = (
        await app_client.post("/v1/rewards/redeem", json={"reward_code": GOLD}, headers=headers)
    ).json()

    async with db.transaction() as conn:
        await rewards.refund_claim(conn, claim_id=uuid.UUID(body["claim_id"]))

    again = await app_client.post("/v1/rewards/redeem", json={"reward_code": GOLD}, headers=headers)
    assert again.status_code == 200
