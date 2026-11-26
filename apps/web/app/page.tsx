"use client";


import { useCallback, useEffect, useMemo, useState } from "react";

import { ActivityTicker } from "@/components/ActivityTicker";
import { BetSlip } from "@/components/BetSlip";
import {
  BetSlipProvider,
  MAX_LEGS,
  useBetSlip,
} from "@/components/BetSlipProvider";
import { BuyCoinsModal } from "@/components/BuyCoinsModal";
import { MarketCard } from "@/components/MarketCard";
import { PredictionHistory } from "@/components/PredictionHistory";
import { PrizePanel } from "@/components/PrizePanel";
import { RewardsPanel } from "@/components/RewardsPanel";
import { TelegramGate, useProfile } from "@/components/TelegramGate";
import { coins, count, priceAnchor, shortCoins } from "@/lib/format";
import { CATEGORIES, DEFAULT_CATEGORY, categoryLabel, fa, translateError } from "@/lib/i18n";
import { getMarkets } from "@/lib/api";
import { combinedOdds, longestOddsSlip } from "@/lib/parlay";
import { shareInviteLink } from "@/lib/share";
import type { MarketSummary, Money } from "@/lib/types";

export default function HomePage() {
  return (
    <TelegramGate>
      <BetSlipProvider>
        <Dashboard />
      </BetSlipProvider>
    </TelegramGate>
  );
}

type Tab = "markets" | "history" | "rewards" | "prize";

const TAB_LABEL: Record<Tab, string> = {
  markets: fa.tabMarkets,
  history: fa.tabHistory,
  rewards: fa.tabRewards,
  prize: fa.tabPrize,
};

const FEED_VIEWS = [
  {
    id: "closing",
    label: fa.viewClosing,
    hint: fa.viewClosingHint,
    apply: (markets: MarketSummary[]) => markets,
  },
  {
    id: "favourites",
    label: fa.viewFavourites,
    hint: fa.viewFavouritesHint,
    apply: (markets: MarketSummary[]) =>
      [...markets].sort(
        (a, b) =>
          Math.max(Number(b.probability.yes), Number(b.probability.no)) -
          Math.max(Number(a.probability.yes), Number(a.probability.no)),
      ),
  },
  {
    id: "longshots",
    label: fa.viewLongshots,
    hint: fa.viewLongshotsHint,
    apply: (markets: MarketSummary[]) =>
      [...markets].sort(
        (a, b) =>
          Math.min(Number(a.probability.yes), Number(a.probability.no)) -
          Math.min(Number(b.probability.yes), Number(b.probability.no)),
      ),
  },
  {
    id: "boosted",
    label: fa.viewBoosted,
    hint: fa.viewBoostedHint,
    apply: (markets: MarketSummary[]) =>
      markets.filter((market) => market.boosts.length > 0),
  },
  {
    id: "busiest",
    label: fa.viewBusiest,
    hint: fa.viewBusiestHint,
    apply: (markets: MarketSummary[]) =>
      [...markets].sort((a, b) => Number(b.volume_usd) - Number(a.volume_usd)),
  },
] as const;

function Dashboard() {
  const { user, refresh } = useProfile();
  const slip = useBetSlip();

  const [tab, setTab] = useState<Tab>("markets");
  const [view, setView] =
    useState<(typeof FEED_VIEWS)[number]["id"]>("closing");
  // Opens on the priority category rather than on everything: it is the
  // reason the feed exists, and it is the one tab the volume ordering would
  // otherwise bury. Set DEFAULT_CATEGORY to undefined in lib/i18n to open on
  // all markets again.
  const [category, setCategory] = useState<string | undefined>(DEFAULT_CATEGORY);
  const [markets, setMarkets] = useState<MarketSummary[] | null>(null);
  const [minLegs, setMinLegs] = useState(1);
  const [vigRate, setVigRate] = useState(0.05);
  const [bonuses, setBonuses] = useState<string[]>([]);
  const [exampleStake, setExampleStake] = useState<Money | null>(null);
  const [signupBonus, setSignupBonus] = useState<Money | null>(null);
  const [referralBonus, setReferralBonus] = useState<Money | null>(null);
  const [feedError, setFeedError] = useState<string | null>(null);
  const [historyToken, setHistoryToken] = useState(0);
  const [topUpOpen, setTopUpOpen] = useState(false);

  const loadMarkets = useCallback(async () => {
    const result = await getMarkets({ category, limit: 50 });
    if (result.ok) {
      setMarkets(result.data.markets);
      setMinLegs(result.data.min_legs);
      setVigRate(Number(result.data.vig_rate));
      setBonuses(result.data.parlay_bonus_by_legs);
      setExampleStake(result.data.example_stake);
      setSignupBonus(result.data.signup_bonus);
      setReferralBonus(result.data.referral_bonus);
      setFeedError(null);
    } else {
      setFeedError(translateError(result.code, result.detail));
    }
  }, [category]);

  const preview = useMemo(() => {
    if (!exampleStake) return null;
    const multiplier = combinedOdds(slip.legs, markets ?? [], vigRate, bonuses);
    return multiplier === null
      ? null
      : Math.round(exampleStake.minor * multiplier);
  }, [slip.legs, markets, vigRate, bonuses, exampleStake]);

  const biggest = useMemo(() => {
    if (!markets || !exampleStake) return null;
    const candidates = longestOddsSlip(markets, vigRate, MAX_LEGS);
    if (candidates.length === 0) return null;

    const seen = new Set<string>();
    const legs: {
      marketId: string;
      side: (typeof candidates)[number]["side"];
    }[] = [];
    const picks: typeof candidates = [];
    for (const candidate of candidates) {
      if (legs.length >= MAX_LEGS) break;
      if (seen.has(candidate.market.event.id)) continue;
      seen.add(candidate.market.event.id);
      picks.push(candidate);
      legs.push({ marketId: candidate.market.id, side: candidate.side });
    }

    const multiplier = combinedOdds(legs, markets, vigRate, bonuses);
    if (multiplier === null) return null;
    return { picks, payout: Math.round(exampleStake.minor * multiplier) };
  }, [markets, vigRate, bonuses, exampleStake]);

  useEffect(() => {
    void loadMarkets();
  }, [loadMarkets]);

  const active = FEED_VIEWS.find((entry) => entry.id === view) ?? FEED_VIEWS[0];
  const visible = markets ? active.apply(markets) : null;

  return (
    <>
      <main className="mx-auto w-full max-w-md px-4 pb-40 pt-4">
        <Header
          name={user.first_name}
          balance={user.balance.minor}
          streak={user.streak_count}
          isAdmin={user.is_admin ?? false}
          onTopUp={() => setTopUpOpen(true)}
        />

        <div className="mt-4">
          <ActivityTicker />
        </div>

        <nav
          className="mt-4 flex gap-1 rounded-xl bg-tg-secondary-bg p-1"
          role="tablist"
        >
          {(["markets", "history", "rewards", "prize"] as const).map(
            (entry) => (
              <button
                key={entry}
                role="tab"
                aria-selected={tab === entry}
                onClick={() => setTab(entry)}
                className={`flex-1 rounded-lg py-2 text-xs font-semibold ${
                  tab === entry
                    ? "bg-tg-button text-tg-button-text"
                    : "text-tg-hint"
                }`}
              >
                {TAB_LABEL[entry]}
              </button>
            ),
          )}
        </nav>

        {tab === "markets" ? (
          <section className="mt-4 space-y-3">
            <FeedControls
              view={view}
              onView={setView}
              category={category}
              onCategory={setCategory}
              hint={active.hint}
            />

            {feedError ? (
              <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-300">
                {feedError}
              </p>
            ) : null}

            {visible === null ? (
              <p className="py-8 text-center text-sm text-tg-hint">
                {fa.marketsLoading}
              </p>
            ) : visible.length === 0 ? (
              <p className="py-8 text-center text-sm text-tg-hint">
                {fa.marketsEmpty}
              </p>
            ) : (
              <>
                {/* Growth, not a bet — deliberately a different colour from
                 *  the button below so the two are never confused at a
                 *  glance. Absent when the operator has not configured the
                 *  bot username / Mini App short name, same as the invite
                 *  card on "my prize". */}
                {user.invite_link && signupBonus && referralBonus ? (
                  <button
                    type="button"
                    onClick={() =>
                      void shareInviteLink(
                        user.invite_link!,
                        fa.inviteShareText(
                          signupBonus.display,
                          referralBonus.display,
                        ),
                      )
                    }
                    className="mb-3 flex w-full flex-col gap-0.5 rounded-2xl border
                               border-sky-400/40 bg-sky-400/10 px-4 py-3 text-start
                               transition duration-150 active:scale-[0.98]"
                  >
                    <span className="text-sm font-bold text-sky-300">
                      {fa.inviteBannerHeadline(signupBonus.display)}
                    </span>
                    <span className="text-[11px] font-semibold text-sky-300/80">
                      {fa.inviteBannerSub(referralBonus.display)}
                    </span>
                  </button>
                ) : null}

                {/* One tap to the longest-odds slip the feed can produce.
                 *
                 * Real markets at real prices, and each leg keeps its own
                 * percentage on its card — the number is big because the
                 * outcomes are unlikely, and both halves stay on screen. */}
                {biggest && exampleStake ? (
                  <button
                    type="button"
                    onClick={() => {
                      slip.fill(biggest.picks);
                      slip.open();
                    }}
                    className="mb-3 flex w-full items-center justify-between gap-3 rounded-2xl
                               border border-[#e8b73a]/45 bg-[#e8b73a]/10 px-4 py-3
                               text-start transition duration-150 active:scale-[0.98]"
                  >
                    <span className="text-sm font-bold text-[#e8b73a]">
                      {fa.biggestMultiplier}
                    </span>
                    <span className="flex shrink-0 flex-col items-end">
                      <span className="text-[11px] font-semibold tabular-nums text-[#e8b73a]/85">
                        {fa.biggestMultiplierWin(
                          coins(exampleStake.minor),
                          shortCoins(biggest.payout),
                        )}
                      </span>
                      {priceAnchor(biggest.payout) ? (
                        <span className="text-[11px] text-[#e8b73a]/70">
                          {priceAnchor(biggest.payout)}
                        </span>
                      ) : null}
                    </span>
                  </button>
                ) : null}

                <ul className="space-y-3">
                  {visible.map((market) => (
                    <li key={market.id}>
                      <MarketCard market={market} vigRate={vigRate} />
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>
        ) : tab === "history" ? (
          <div className="mt-4">
            <PredictionHistory refreshToken={historyToken} />
          </div>
        ) : tab === "rewards" ? (
          <div className="mt-4">
            <RewardsPanel onBalanceChanged={() => void refresh()} />
          </div>
        ) : (
          <div className="mt-4">
            <PrizePanel
              profile={user}
              referralBonus={referralBonus}
              signupBonus={signupBonus}
            />
          </div>
        )}
      </main>

      {slip.legs.length > 0 && !slip.isOpen ? (
        <button
          onClick={slip.open}
          className="fixed inset-x-3 bottom-[calc(0.75rem+env(safe-area-inset-bottom))] z-30
                     flex items-center justify-between gap-3 rounded-2xl bg-tg-button px-4 py-3
                     text-tg-button-text shadow-lg shadow-black/30 transition duration-150
                     active:scale-[0.98]"
        >
          <span className="flex items-center gap-2">
            <span
              className="flex size-6 items-center justify-center rounded-full
                             bg-tg-button-text/20 text-xs font-bold tabular-nums"
            >
              {count(slip.legs.length)}
            </span>
            {/* Below the minimum the bar names what is one tap away rather
             *  than counting what is already there. Same fact, and the second
             *  reading is an invitation instead of a receipt. */}
            {/* What this slip pays, the moment a selection is tapped.
             *
             * Worked out in the app from the margin and bonus the feed sends,
             * because the point is that it lands on the first tap and grows
             * on every one after — a round trip per tap would make the number
             * arrive after the decision it exists to inform. The server
             * re-prices everything at quote and at placement regardless. */}
            <span className="flex flex-col text-start">
              <span className="text-sm font-bold">
                {slip.legs.length < minLegs
                  ? fa.slipBarUnlock(count(minLegs - slip.legs.length))
                  : fa.slipOpenBar(count(slip.legs.length))}
              </span>
              {preview && exampleStake ? (
                <span className="text-[11px] font-semibold opacity-90">
                  {fa.exampleWin(
                    coins(exampleStake.minor),
                    shortCoins(preview),
                  )}
                </span>
              ) : null}
            </span>
          </span>
          <span className="text-xs font-semibold opacity-80">
            {fa.slipReview} ←
          </span>
        </button>
      ) : null}

      <BetSlip
        profile={user}
        bonuses={bonuses}
        onPlaced={() => {
          setHistoryToken((token) => token + 1);
          setTab("history");
        }}
        onBalanceChanged={() => {
          void refresh();
          void loadMarkets();
        }}
      />

      {topUpOpen ? (
        <BuyCoinsModal
          onClose={() => setTopUpOpen(false)}
          onFunded={() => {
            setTopUpOpen(false);
            void refresh();
          }}
        />
      ) : null}
    </>
  );
}

function Header({
  name,
  balance,
  streak,
  isAdmin,
  onTopUp,
}: {
  name: string;
  balance: number;
  streak: number;
  isAdmin: boolean;
  onTopUp: () => void;
}) {
  return (
    <header
      className="relative overflow-hidden rounded-2xl bg-tg-secondary-bg p-4
                 ring-1 ring-white/5"
    >
      {/* A single warm highlight behind the balance. Coins are the reward
          currency, so the one gradient in the app belongs here and nowhere
          else — spread across every surface it would stop meaning anything. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-16 -end-10 size-40 rounded-full
                   bg-boost/15 blur-2xl"
      />

      <div className="relative flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-xs text-tg-hint">{fa.greeting(name)}</p>
          <p className="mt-0.5 flex items-baseline gap-1.5">
            <span className="text-4xl font-black tabular-nums tracking-tight">
              {coins(balance)}
            </span>
            <span className="text-xs font-medium text-tg-hint">
              {fa.coinsUnit}
            </span>
          </p>
          {streak > 0 ? (
            <p
              className="mt-1.5 inline-flex items-center gap-1 rounded-full bg-boost/15
                         px-2 py-0.5 text-[11px] font-semibold text-boost"
            >
              <span aria-hidden>🔥</span>
              {fa.streak(count(streak))}
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {/* Only door into the admin pages from inside Telegram, where there
              is no address bar to type one. Shown on a flag from /me and
              gated for real on the server: every admin route re-checks the
              allowlist, so a forged flag reaches a page that 404s. */}
          {isAdmin ? (
            <a
              href="/admin"
              aria-label={fa.adminLink}
              title={fa.adminLink}
              className="flex size-9 items-center justify-center rounded-xl
                         bg-tg-bg/60 text-base ring-1 ring-white/10
                         transition duration-150 active:scale-95"
            >
              <span aria-hidden>⚙️</span>
            </a>
          ) : null}
          <button
            onClick={onTopUp}
            className="shrink-0 rounded-xl bg-tg-button px-3.5 py-2 text-xs font-bold
                       text-tg-button-text transition duration-150 active:scale-95"
          >
            {fa.topUp}
          </button>
        </div>
      </div>
    </header>
  );
}

function FeedControls({
  view,
  onView,
  category,
  onCategory,
  hint,
}: {
  view: string;
  onView: (id: (typeof FEED_VIEWS)[number]["id"]) => void;
  category: string | undefined;
  onCategory: (value: string | undefined) => void;
  hint: string;
}) {
  return (
    <div className="space-y-2">
      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 [scrollbar-width:none]">
        {FEED_VIEWS.map((entry) => (
          <button
            key={entry.id}
            onClick={() => onView(entry.id)}
            aria-pressed={view === entry.id}
            className={`shrink-0 rounded-full px-3.5 py-1.5 text-xs font-semibold ring-1
                        transition duration-150 active:scale-95 ${
                          view === entry.id
                            ? "bg-tg-button text-tg-button-text ring-tg-button"
                            : entry.id === "boosted"
                              ? "text-boost ring-boost/40"
                              : "text-tg-hint ring-tg-hint/25"
                        }`}
          >
            {entry.id === "boosted" && view !== entry.id ? (
              <span aria-hidden>⚡ </span>
            ) : null}
            {entry.label}
          </button>
        ))}
      </div>

      <div className="flex items-center justify-between">
        <p className="text-[11px] text-tg-hint">{hint}</p>
        <div className="flex gap-1.5">
          {/* Driven by lib/i18n's CATEGORIES so adding one is a single edit.
              This used to be a hardcoded array beside a chain of ternaries
              picking the label, which is two places to forget. */}
          {[undefined, ...CATEGORIES].map((entry) => (
            <button
              key={entry ?? "all"}
              onClick={() => onCategory(entry)}
              aria-pressed={category === entry}
              className={`rounded-md px-2 py-1 text-[11px] font-medium transition
                          duration-150 active:scale-95 ${
                            category === entry
                              ? "bg-tg-hint/20 font-semibold text-tg-text"
                              : "text-tg-hint"
                          }`}
            >
              {entry === undefined ? fa.categoryAll : categoryLabel(entry)}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
