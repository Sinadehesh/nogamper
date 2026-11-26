"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AccountPanel } from "@/components/AccountPanel";
import { ForecastHistory } from "@/components/ForecastHistory";
import { LeaderboardPanel } from "@/components/LeaderboardPanel";
import { MarketFeed } from "@/components/MarketFeed";
import { usePlayer } from "@/components/PlayerProvider";
import { SaferPlayPanel } from "@/components/SaferPlayPanel";
import { SessionReminder } from "@/components/SessionReminder";
import { Wordmark } from "@/components/SiteChrome";
import { SlipProvider, useSlip } from "@/components/SlipProvider";
import { SlipSheet } from "@/components/SlipSheet";
import { claimTopUp, getShop } from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { dateTime, points, timeUntil } from "@/lib/format";
import { TABS, type Tab } from "@/lib/tabs";
import type { MarketRules } from "@/lib/types";


const TAB_LABEL: Record<Tab, string> = {
  markets: t.tabMarkets,
  history: t.tabHistory,
  leaderboard: t.tabLeaderboard,
  safer: t.tabSafer,
  account: t.tabAccount,
};

/** Until the feed has answered, a slip may hold this many picks. */
const FALLBACK_MAX_LEGS = 5;

/** How somebody arrived back from Stripe's payment page, if they did. */
export type PurchaseReturn = "done" | "cancelled" | null;

export function Dashboard({
  initialTab,
  purchase = null,
}: {
  initialTab: Tab;
  purchase?: PurchaseReturn;
}) {
  const [rules, setRules] = useState<MarketRules | null>(null);

  return (
    <SlipProvider maxLegs={rules?.max_legs ?? FALLBACK_MAX_LEGS}>
      <Screen initialTab={initialTab} purchase={purchase} rules={rules} onRules={setRules} />
    </SlipProvider>
  );
}

/** A checkout stays open for half an hour, so a purchase paid just now was
 *  started no longer ago than this. */
const JUST_NOW_MS = 35 * 60 * 1000;

/**
 * The word from Stripe's payment page, and the wait for the points.
 *
 * Arriving at the "done" address proves nothing and credits nothing — anyone
 * can type it. The points are added when Stripe's own signed message reaches
 * the server, which may be a moment before this page loads or a few seconds
 * after. So this says thank you, then asks the server whether a purchase has
 * actually been paid, and only then says the points have arrived.
 */
function PurchaseNotice({ outcome }: { outcome: Exclude<PurchaseReturn, null> }) {
  const { refresh } = usePlayer();
  const [arrived, setArrived] = useState(false);

  useEffect(() => {
    if (outcome !== "done") return;
    let cancelled = false;
    let tries = 0;
    let timer: number | undefined;

    const look = async () => {
      const result = await getShop();
      if (cancelled) return;
      const paid =
        result.ok &&
        (result.data.mine?.purchases ?? []).some(
          (purchase) =>
            purchase.status === "PAID" &&
            Date.now() - new Date(purchase.at).getTime() < JUST_NOW_MS,
        );
      if (paid) {
        setArrived(true);
        void refresh();
        return;
      }
      tries += 1;
      if (tries < 10) timer = window.setTimeout(() => void look(), 3000);
    };
    void look();

    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [outcome, refresh]);

  if (outcome === "cancelled") {
    return (
      <p role="status" className="notice">
        {t.shopCancelled}
      </p>
    );
  }
  return (
    <p role="status" className="notice notice-ok">
      {arrived ? t.shopArrived : t.shopThanks}
    </p>
  );
}

function Screen({
  initialTab,
  purchase,
  rules,
  onRules,
}: {
  initialTab: Tab;
  purchase: PurchaseReturn;
  rules: MarketRules | null;
  onRules: (rules: MarketRules) => void;
}) {
  const slip = useSlip();
  const [tab, setTab] = useState<Tab>(initialTab);
  const [historyToken, setHistoryToken] = useState(0);
  const [placedFlash, setPlacedFlash] = useState(false);
  const [shopOpen, setShopOpen] = useState(false);

  useEffect(() => {
    // Only to know whether to offer the link at all. The card on the account
    // tab asks again for the detail; this must not hold up the screen.
    void getShop().then((result) => setShopOpen(result.ok && result.data.open));
    // Take the outcome out of the address, so a reload does not thank
    // somebody a second time for one purchase.
    if (purchase) window.history.replaceState(null, "", "/play");
  }, [purchase]);

  const select = useCallback((next: Tab) => {
    setTab(next);
    setPlacedFlash(false);
    // Keep the address in step so a reload, or a link from the help page,
    // lands on the same tab — without a navigation, which would refetch the
    // whole page for what is a change of view.
    window.history.replaceState(null, "", next === "markets" ? "/play" : `/play?tab=${next}`);
  }, []);

  return (
    <>
      <header className="border-b border-line bg-surface">
        <div className="container-page flex items-center justify-between gap-3 py-3">
          <Wordmark href="/play" />
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/articles" className="hidden text-muted hover:text-ink sm:inline">
              {t.navArticles}
            </Link>
            <Link href="/about" className="hidden text-muted hover:text-ink sm:inline">
              {t.navAbout}
            </Link>
            <Link href="/help" className="text-muted hover:text-ink">
              {t.navHelp}
            </Link>
          </nav>
        </div>
      </header>

      <main id="main" className="container-page flex-1 space-y-5 pb-28 pt-5">
        {purchase ? <PurchaseNotice outcome={purchase} /> : null}

        <Summary
          onOpenSafer={() => select("safer")}
          onOpenShop={shopOpen ? () => select("account") : null}
        />

        {/* Five tabs do not fit across a phone. They wrap onto two rows of
            three and two rather than scroll sideways: a tab that has scrolled
            out of sight is a tab nobody finds, and the one that fell off the
            edge was "Safer play". */}
        <div
          role="tablist"
          aria-label={t.appName}
          className="grid grid-cols-6 gap-1 rounded-xl border border-line bg-surface p-1 sm:flex"
        >
          {TABS.map((entry, index) => (
            <button
              key={entry}
              type="button"
              role="tab"
              id={`tab-${entry}`}
              aria-selected={tab === entry}
              aria-controls="tab-panel"
              onClick={() => select(entry)}
              className={`rounded-lg px-1 py-2 text-[0.8125rem] font-semibold sm:grow sm:px-3 sm:text-sm ${
                index < 3 ? "col-span-2" : "col-span-3"
              } ${tab === entry ? "bg-accent text-on-accent" : "text-muted hover:text-ink"}`}
            >
              {TAB_LABEL[entry]}
            </button>
          ))}
        </div>

        <div id="tab-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
          {placedFlash && tab === "history" ? (
            <p role="status" className="notice notice-ok mb-4">
              {t.placed}
            </p>
          ) : null}

          {tab === "markets" ? (
            <MarketFeed onRules={onRules} />
          ) : tab === "history" ? (
            <ForecastHistory refreshToken={historyToken} />
          ) : tab === "leaderboard" ? (
            <LeaderboardPanel />
          ) : tab === "safer" ? (
            <SaferPlayPanel />
          ) : (
            <AccountPanel onOpenSafer={() => select("safer")} />
          )}
        </div>
      </main>

      {slip.legs.length > 0 && !slip.isOpen ? (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 backdrop-blur">
          <div className="container-page flex items-center justify-between gap-3 py-3">
            <p className="font-semibold">{t.slipOpenBar(slip.legs.length)}</p>
            <button type="button" className="btn btn-primary" onClick={slip.open}>
              {t.slipReview}
            </button>
          </div>
        </div>
      ) : null}

      {rules ? (
        <SlipSheet
          rules={rules}
          onPlaced={() => {
            setHistoryToken((token) => token + 1);
            select("history");
            setPlacedFlash(true);
          }}
        />
      ) : null}

      <SessionReminder onTakeBreak={() => select("safer")} />
    </>
  );
}

function Summary({
  onOpenSafer,
  onOpenShop,
}: {
  onOpenSafer: () => void;
  /** Null when nothing is for sale, and then no link is shown. */
  onOpenShop: (() => void) | null;
}) {
  const { player, refresh, onBreak, limitReached } = usePlayer();
  const [claiming, setClaiming] = useState(false);
  const [flash, setFlash] = useState<{ ok: boolean; text: string } | null>(null);

  async function claim() {
    setClaiming(true);
    const result = await claimTopUp();
    setClaiming(false);
    if (result.ok) {
      setFlash({ ok: true, text: t.topUpClaimed(result.data.amount.display) });
    } else {
      setFlash({ ok: false, text: errorMessage(result.code) });
    }
    await refresh();
    // A confirmation, not a fixture: it has said its piece after a few
    // seconds, and this card already carries enough standing notices.
    window.setTimeout(() => setFlash(null), 5000);
  }

  const { limits } = player;

  return (
    <section className="card p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted">{t.greeting(player.display_name)}</p>
          <p className="mt-1 flex items-baseline gap-2">
            <span className="text-4xl font-black tracking-tight tabular-nums">
              {points(player.balance.minor)}
            </span>
            <span className="text-sm text-muted">{t.pointsUnit}</span>
          </p>
        </div>

        <div className="text-sm">
          {player.can_claim_daily ? (
            <div className="flex items-center gap-3">
              <span className="text-muted">{t.topUpReady(player.daily_topup.display)}</span>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => void claim()}
                disabled={claiming}
              >
                {claiming ? t.topUpClaiming : t.topUpClaim}
              </button>
            </div>
          ) : player.next_claim_at ? (
            <p className="text-muted">{t.topUpNext(timeUntil(player.next_claim_at))}</p>
          ) : null}
          {/* After the free top-up, never instead of it, and in the same
              place whatever the balance: it does not appear when somebody
              runs out, because that is the moment not to be sold to. */}
          {onOpenShop ? (
            <p className="mt-1 text-right">
              <button
                type="button"
                className="text-muted underline underline-offset-2 hover:text-ink"
                onClick={onOpenShop}
              >
                {t.shopLink}
              </button>
            </p>
          ) : null}
        </div>
      </div>

      {flash ? (
        <p
          role={flash.ok ? "status" : "alert"}
          className={`notice mt-4 ${flash.ok ? "notice-ok" : "notice-error"}`}
        >
          {flash.text}
        </p>
      ) : null}

      {onBreak && limits.break_until ? (
        <p className="notice notice-warn mt-4">{t.breakBanner(dateTime(limits.break_until))}</p>
      ) : null}

      {limits.daily_limit ? (
        <p className="mt-4 text-sm text-muted">
          {limitReached
            ? t.limitReachedBanner(limits.daily_limit.display)
            : t.limitBanner(limits.daily_spent.display, limits.daily_limit.display)}{" "}
          <button
            type="button"
            className="font-semibold text-accent underline underline-offset-2"
            onClick={onOpenSafer}
          >
            {t.tabSafer}
          </button>
        </p>
      ) : null}

      {player.is_guest ? (
        <p className="notice mt-4">
          {t.guestBanner}{" "}
          <Link href="/signup" className="font-semibold text-accent underline underline-offset-2">
            {t.guestBannerAction}
          </Link>
        </p>
      ) : null}

      {player.is_admin ? (
        <p className="mt-4 text-sm">
          <Link href="/admin" className="font-semibold text-accent underline underline-offset-2">
            {t.navAdmin}
          </Link>
        </p>
      ) : null}
    </section>
  );
}
