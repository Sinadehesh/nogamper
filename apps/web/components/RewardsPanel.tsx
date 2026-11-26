"use client";


import { useCallback, useEffect, useState } from "react";

import { coins, count } from "@/lib/format";
import { fa, translateError } from "@/lib/i18n";
import { getRewardClaims, getRewards, redeemReward } from "@/lib/api";
import type {
  RewardBlockedReason,
  RewardCatalogue,
  RewardClaim,
  RewardClaimStatus,
  RewardItem,
} from "@/lib/types";

const BLOCKED_LABEL: Record<RewardBlockedReason, string> = {
  insufficient_funds: fa.rewardBlockedFunds,
  not_enough_play: fa.rewardBlockedPlay,
  already_claimed: fa.rewardBlockedClaimed,
  reward_exhausted: fa.rewardBlockedGone,
};

const STATUS_LABEL: Record<RewardClaimStatus, string> = {
  RESERVED: fa.rewardStatusReserved,
  FULFILLED: fa.rewardStatusFulfilled,
  FAILED: fa.rewardStatusFailed,
  REFUNDED: fa.rewardStatusRefunded,
};

const STATUS_TONE: Record<RewardClaimStatus, string> = {
  RESERVED: "bg-boost/15 text-boost",
  FULFILLED: "bg-yes/15 text-yes",
  FAILED: "bg-no/15 text-no",
  REFUNDED: "bg-tg-hint/15 text-tg-hint",
};

const KIND_GLYPH: Record<string, string> = {
  NFT: "🎴",
  TELEGRAM_GIFT: "🎁",
  BADGE: "🏅",
  MERCH: "📦",
};

export function RewardsPanel({ onBalanceChanged }: { onBalanceChanged: () => void }) {
  const [catalogue, setCatalogue] = useState<RewardCatalogue | null>(null);
  const [claims, setClaims] = useState<RewardClaim[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<RewardItem | null>(null);
  const [claimed, setClaimed] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [cat, mine] = await Promise.all([getRewards(), getRewardClaims()]);
    if (cat.ok) {
      setCatalogue(cat.data);
      setError(null);
    } else {
      setError(translateError(cat.code, cat.detail));
    }
    if (mine.ok) setClaims(mine.data.claims);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onRedeemed = useCallback(async () => {
    setConfirming(null);
    await load();
    onBalanceChanged();
  }, [load, onBalanceChanged]);

  return (
    <section className="space-y-3">
      <header>
        <h2 className="text-sm font-bold">{fa.rewardsTitle}</h2>
        <p className="mt-0.5 text-[11px] leading-relaxed text-tg-hint">{fa.rewardsIntro}</p>
      </header>

      {error ? (
        <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</p>
      ) : null}

      {claimed ? (
        <div className="rounded-xl bg-yes/10 px-3 py-2.5 ring-1 ring-yes/30">
          <p className="text-xs font-bold text-yes">{fa.rewardClaimedTitle}</p>
          <p className="mt-0.5 text-[11px] text-tg-hint">{fa.rewardClaimedBody}</p>
          <p className="mt-1 text-[11px] font-semibold">{claimed}</p>
        </div>
      ) : null}

      {catalogue === null ? (
        <p className="py-8 text-center text-sm text-tg-hint">{fa.rewardsLoading}</p>
      ) : catalogue.rewards.length === 0 ? (
        <p className="py-8 text-center text-sm text-tg-hint">{fa.rewardsEmpty}</p>
      ) : (
        <ul className="space-y-2.5">
          {catalogue.rewards.map((reward) => (
            <li key={reward.code}>
              <RewardCard reward={reward} onPick={() => setConfirming(reward)} />
            </li>
          ))}
        </ul>
      )}

      {claims.length > 0 ? (
        <div className="pt-2">
          <h3 className="text-xs font-bold text-tg-hint">{fa.myRewards}</h3>
          <ul className="mt-2 space-y-1.5">
            {claims.map((claim) => (
              <li
                key={claim.id}
                className="flex items-center justify-between gap-2 rounded-xl
                           bg-tg-secondary-bg px-3 py-2"
              >
                <span className="flex min-w-0 items-center gap-2">
                  <span aria-hidden>{KIND_GLYPH[claim.kind] ?? "🎁"}</span>
                  <span className="truncate text-xs font-semibold">{claim.title}</span>
                </span>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold
                              ${STATUS_TONE[claim.status]}`}
                >
                  {STATUS_LABEL[claim.status]}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {confirming ? (
        <ConfirmRedeem
          reward={confirming}
          balanceMinor={catalogue?.balance.minor ?? 0}
          onCancel={() => setConfirming(null)}
          onDone={(title) => {
            setClaimed(title);
            void onRedeemed();
          }}
          onError={setError}
        />
      ) : null}
    </section>
  );
}

function RewardCard({ reward, onPick }: { reward: RewardItem; onPick: () => void }) {
  const blocked = reward.blocked_reason;

  return (
    <article
      className={`rounded-2xl bg-tg-secondary-bg p-3.5 ring-1 ${
        reward.claimable ? "ring-boost/40" : "ring-white/5"
      }`}
    >
      <div className="flex items-start gap-3">
        <span className="text-2xl leading-none" aria-hidden>
          {KIND_GLYPH[reward.kind] ?? "🎁"}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-bold">{reward.title}</h3>
          <p className="mt-0.5 text-[11px] leading-relaxed text-tg-hint">{reward.description}</p>

          <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-tg-hint">
            <span className="font-bold text-boost">
              {fa.rewardCost(coins(reward.cost.minor))}
            </span>
            <span aria-hidden>·</span>
            <span>
              {reward.remaining === null
                ? fa.rewardUnlimited
                : fa.rewardRemaining(count(reward.remaining))}
            </span>
            {reward.held_by_user > 0 ? (
              <>
                <span aria-hidden>·</span>
                <span className="text-yes">{fa.rewardOwned(count(reward.held_by_user))}</span>
              </>
            ) : null}
          </p>

          {/* The volume gate deserves a number, not just a refusal: "play more"
              with no target is the kind of message that reads as arbitrary. */}
          {blocked === "not_enough_play" ? (
            <p className="mt-1 text-[10px] text-tg-hint">
              {fa.rewardNeedStaked(coins(reward.min_lifetime_staked.minor))}
            </p>
          ) : null}
        </div>
      </div>

      <button
        onClick={onPick}
        disabled={!reward.claimable}
        className={`mt-3 w-full rounded-xl py-2.5 text-xs font-bold transition duration-150
                    active:scale-[0.98] disabled:active:scale-100 ${
                      reward.claimable
                        ? "bg-boost text-black"
                        : "bg-tg-bg/60 text-tg-hint ring-1 ring-tg-hint/20"
                    }`}
      >
        {reward.claimable ? fa.rewardRedeem : blocked ? BLOCKED_LABEL[blocked] : fa.rewardRedeem}
      </button>
    </article>
  );
}

function ConfirmRedeem({
  reward,
  balanceMinor,
  onCancel,
  onDone,
  onError,
}: {
  reward: RewardItem;
  balanceMinor: number;
  onCancel: () => void;
  onDone: (title: string) => void;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setBusy(true);
    const result = await redeemReward(reward.code);
    if (result.ok) {
      onDone(result.data.title);
    } else {
      onError(translateError(result.code, result.detail));
      setBusy(false);
      onCancel();
    }
  }

  return (
    <div
      className="fixed inset-0 z-40 flex items-end justify-center bg-black/60 p-3"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md rounded-2xl bg-tg-secondary-bg p-4">
        <h3 className="text-sm font-bold">{fa.rewardConfirmTitle}</h3>
        <p className="mt-1 text-xs font-semibold">{reward.title}</p>
        <p className="mt-2 text-[11px] leading-relaxed text-tg-hint">
          {fa.rewardConfirmBody(
            coins(reward.cost.minor),
            coins(Math.max(0, balanceMinor - reward.cost.minor)),
          )}
        </p>

        <div className="mt-4 flex gap-2">
          <button
            onClick={onCancel}
            disabled={busy}
            className="flex-1 rounded-xl bg-tg-bg/60 py-2.5 text-xs font-bold text-tg-hint
                       ring-1 ring-tg-hint/20"
          >
            {fa.rewardConfirmNo}
          </button>
          <button
            onClick={confirm}
            disabled={busy}
            className="flex-1 rounded-xl bg-boost py-2.5 text-xs font-bold text-black
                       transition duration-150 active:scale-[0.98] disabled:opacity-60"
          >
            {busy ? fa.rewardRedeeming : fa.rewardConfirmYes}
          </button>
        </div>
      </div>
    </div>
  );
}
