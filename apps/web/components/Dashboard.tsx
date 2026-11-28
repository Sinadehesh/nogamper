"use client";

import "@/components/game/game.css";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";

import { AccountPanel } from "@/components/AccountPanel";
import { ForecastHistory } from "@/components/ForecastHistory";
import {
  QuestionLinks,
  QuotedPrices,
  quotedPrices,
  ReviewSlip,
  useWide,
} from "@/components/game/context";
import { useFocusTrap } from "@/components/game/trap";
import { GameBar, TabBar, VIEW_LABEL, viewHref } from "@/components/game/views";
import { LeaderboardPanel } from "@/components/LeaderboardPanel";
import { MarketFeed } from "@/components/MarketFeed";
import { usePlayer } from "@/components/PlayerProvider";
import { SaferPlayPanel } from "@/components/SaferPlayPanel";
import { SessionReminder } from "@/components/SessionReminder";
import { SlipProvider, useSlip } from "@/components/SlipProvider";
import { SlipEmpty, SlipPlaced, SlipRail, SlipSheet, type Receipt } from "@/components/SlipSheet";
import { Figure } from "@/components/viz/Figure";
import { claimTopUp, getShop } from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { dateTimeUtc, points } from "@/lib/format";
import type { Tab } from "@/lib/tabs";
import type { MarketRules, MarketSummary, SlipQuote } from "@/lib/types";

/** Until the feed has answered, a slip may hold this many picks. */
const FALLBACK_MAX_LEGS = 5;

/** How somebody arrived back from Stripe's payment page, if they did. */
export type PurchaseReturn = "done" | "cancelled" | null;

export function Dashboard({
  initialTab,
  purchase = null,
  links = {},
}: {
  initialTab: Tab;
  purchase?: PurchaseReturn;
  /** Each open question's public page, by its wording (see QuestionLinks). */
  links?: Readonly<Record<string, string>>;
}) {
  const [rules, setRules] = useState<MarketRules | null>(null);

  return (
    <QuestionLinks links={links}>
      <SlipProvider maxLegs={rules?.max_legs ?? FALLBACK_MAX_LEGS}>
        <Screen initialTab={initialTab} purchase={purchase} rules={rules} onRules={setRules} />
      </SlipProvider>
    </QuestionLinks>
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
      <p role="status" className="gm-note">
        {t.shopCancelled}
      </p>
    );
  }
  return (
    <p role="status" className="gm-note gm-note--line">
      {arrived ? t.shopArrived : t.shopThanks}
    </p>
  );
}

const VIEW_LEDE: Record<Exclude<Tab, "markets">, string> = {
  history: t.historyLede,
  leaderboard: t.leaderboardIntro,
  safer: t.saferLede,
  account: t.accountLede,
};

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
  const wide = useWide();
  const { onBreak, limitReached } = usePlayer();
  const [tab, setTab] = useState<Tab>(initialTab);
  const [historyToken, setHistoryToken] = useState(0);
  const [shopOpen, setShopOpen] = useState(false);
  // Every question the feed has shown this visit, by id, at its latest price.
  const [prices, setPrices] = useState<ReadonlyMap<string, MarketSummary>>(() => new Map());
  const [placed, setPlaced] = useState<Receipt | null>(null);
  // The slip's quote on screen: the cards of the questions on it show its prices.
  const [quote, setQuote] = useState<SlipQuote | null>(null);
  const quoted = useMemo(() => quotedPrices(quote), [quote]);
  const heading = useRef<HTMLHeadingElement>(null);
  const placedTitleId = useId();

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
    // Keep the address in step so a reload, or a link from the help page,
    // lands on the same view — without a navigation, which would refetch the
    // whole page for what is a change of view.
    window.history.replaceState(null, "", viewHref(next));
    // A new view starts at its top, and says so to a screen reader.
    window.scrollTo(0, 0);
    window.requestAnimationFrame(() => heading.current?.focus({ preventScroll: true }));
  }, []);

  const seen = useCallback((markets: MarketSummary[]) => {
    setPrices((current) => {
      const next = new Map(current);
      for (const market of markets) next.set(market.id, market);
      return next;
    });
  }, []);

  // A new pick puts the last confirmation away.
  const hasPicks = slip.legs.length > 0;
  useEffect(() => {
    if (hasPicks) setPlaced(null);
  }, [hasPicks]);

  const onPlaced = useCallback((receipt: Receipt) => {
    setHistoryToken((token) => token + 1);
    setPlaced(receipt);
  }, []);

  const seeForecasts = useCallback(() => {
    setPlaced(null);
    select("history");
  }, [select]);

  // The confirmation's button has gone with it: the focus goes to the
  // view's heading, as it does on a change of view, not to the page's end.
  const donePlacing = useCallback(() => {
    setPlaced(null);
    window.requestAnimationFrame(() => heading.current?.focus({ preventScroll: true }));
  }, []);

  // From a card to the slip: its stake on a wide screen, the sheet on a phone.
  const { open: openSlip } = slip;
  const reviewSlip = useCallback(() => {
    if (wide) document.querySelector<HTMLElement>(".gm-rail .gm-stake input")?.focus();
    else openSlip();
  }, [wide, openSlip]);

  const maxLegs = rules?.max_legs ?? slip.maxLegs;
  // The folded slip at the foot: on a phone whenever the sheet is shut, on a
  // wide screen only away from the questions, where the rail is not.
  const showBar = hasPicks && !slip.isOpen && (!wide || tab !== "markets");

  return (
    <>
      <GameBar view={tab} onView={select} />

      <main id="main" className="gm flex-1">
        <div className="wrap gm-page">
          {purchase ? <PurchaseNotice outcome={purchase} /> : null}

          <Strip
            onOpenSafer={() => select("safer")}
            onOpenShop={shopOpen ? () => select("account") : null}
          />

          <header className="gm-head">
            <h1 ref={heading} id="gm-view-title" tabIndex={-1} className="gm-title">
              {tab === "account" ? t.accountTitle : VIEW_LABEL[tab]}
            </h1>
            <p className="gm-lede">
              {tab === "markets" ? t.marketsLede(maxLegs) : VIEW_LEDE[tab]}
            </p>
          </header>

          {tab === "markets" ? (
            <div className="gm-market">
              <QuotedPrices prices={quoted}>
                <ReviewSlip onReview={reviewSlip}>
                  <MarketFeed onRules={onRules} onMarkets={seen} />
                </ReviewSlip>
              </QuotedPrices>
              <aside className="gm-rail" aria-label={t.slipTitle}>
                <div className="gm-panel">
                  {wide && hasPicks && rules ? (
                    <SlipRail rules={rules} prices={prices} onPlaced={onPlaced} onQuote={setQuote} />
                  ) : wide && placed ? (
                    <SlipPlaced receipt={placed} onSee={seeForecasts} onDone={donePlacing} />
                  ) : (
                    <SlipEmpty
                      maxLegs={maxLegs}
                      paused={onBreak ? t.onBreakNoPicks : limitReached ? t.limitReachedNoPicks : null}
                    />
                  )}
                </div>
              </aside>
            </div>
          ) : tab === "history" ? (
            <ForecastHistory refreshToken={historyToken} prices={prices} />
          ) : tab === "leaderboard" ? (
            <LeaderboardPanel />
          ) : tab === "safer" ? (
            <SaferPlayPanel />
          ) : (
            <AccountPanel onOpenSafer={() => select("safer")} />
          )}
        </div>
      </main>

      <TabBar view={tab} onView={select} />

      {showBar ? (
        <SlipBar onReview={wide ? () => select("markets") : slip.open} prices={prices} />
      ) : null}

      {!wide && rules ? (
        <SlipSheet rules={rules} prices={prices} onPlaced={onPlaced} onQuote={setQuote} />
      ) : null}

      {!wide && placed && !hasPicks ? (
        <PlacedSheet titleId={placedTitleId} onClose={donePlacing}>
          <SlipPlaced
            receipt={placed}
            titleId={placedTitleId}
            onSee={seeForecasts}
            onDone={donePlacing}
          />
        </PlacedSheet>
      ) : null}

      <SessionReminder onTakeBreak={() => select("safer")} onSettings={() => select("account")} />
    </>
  );
}

/** The slip, folded to one line at the foot of the screen. */
function SlipBar({
  onReview,
  prices,
}: {
  onReview: () => void;
  prices: ReadonlyMap<string, MarketSummary>;
}) {
  const slip = useSlip();
  const last = slip.legs[slip.legs.length - 1];
  const market = last ? prices.get(last.marketId) : undefined;

  return (
    <div className="gm-slipbar gm">
      <div className="wrap gm-slipbar__in">
        <p className="gm-slipbar__text" aria-live="polite">
          <b>{t.slipOpenBar(slip.legs.length)}</b>
          {last ? (
            <span>
              {last.side === "YES" ? t.yes : t.no}
              {market ? ` · ${market.question}` : ` · ${last.question}`}
            </span>
          ) : null}
        </p>
        <button type="button" className="btn btn--primary" onClick={onReview}>
          {t.slipReview}
        </button>
      </div>
    </div>
  );
}

/** The confirmation, on a phone, in the sheet the slip was in. */
function PlacedSheet({
  titleId,
  onClose,
  children,
}: {
  titleId: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);
  useFocusTrap(panel, true);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="gm-sheet gm">
      <div className="gm-sheet__scrim" onClick={onClose} aria-hidden />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="gm-sheet__panel"
      >
        <span className="gm-sheet__grip" aria-hidden />
        {children}
      </div>
    </div>
  );
}

/**
 * The strip at the top of every view: the balance first and largest, the
 * free daily points beside it, and the player's own limit or break when one
 * applies. Nothing in it is for sale and nothing in it counts down.
 */
function Strip({
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
    // seconds, and this strip already carries enough standing lines.
    window.setTimeout(() => setFlash(null), 5000);
  }

  const { limits } = player;
  const limit = limits.daily_limit;
  const used = limit && limit.minor > 0 ? Math.min(100, (limits.daily_spent.minor / limit.minor) * 100) : 0;
  const foot = player.is_guest || onOpenShop || player.is_admin;

  return (
    <section className="gm-panel gm-strip" aria-label={t.balanceLabel}>
      <div className="gm-strip__cells">
        <div className="gm-stat">
          <p className="gm-label">{t.balanceLabel}</p>
          {/* "Your points" and the figure, as the front page draws it: the
              label already says what the number counts. */}
          <p className="gm-balance">
            <Figure className="gm-balance__figure" text={points(player.balance.minor)} />
          </p>
        </div>

        <div className="gm-stat">
          <p className="gm-label">{t.dailyLabel}</p>
          <p className="gm-stat__figure">
            <Figure text={t.dailyAmount(player.daily_topup.display)} />
          </p>
          {player.can_claim_daily ? (
            <button
              type="button"
              className="btn btn-secondary btn-sm gm-stat__action"
              onClick={() => void claim()}
              disabled={claiming}
            >
              {claiming ? t.topUpClaiming : t.dailyAdd(player.daily_topup.display)}
            </button>
          ) : player.next_claim_at ? (
            <p className="gm-stat__line">{t.dailyDone(dateTimeUtc(player.next_claim_at))}</p>
          ) : null}
        </div>

        {/* A break outranks a limit: it lasts longer. */}
        {onBreak && limits.break_until ? (
          <div className="gm-stat">
            <p className="gm-label">{t.breakLabel}</p>
            <p className="gm-stat__line text-ink">{t.breakUntil(dateTimeUtc(limits.break_until))}</p>
            <p className="gm-stat__line">{t.breakPaused}</p>
            <button type="button" className="gm-link gm-stat__action text-sm" onClick={onOpenSafer}>
              {t.saferLink}
            </button>
          </div>
        ) : limit ? (
          <div className="gm-stat">
            <p className="gm-label">{t.limitLabel}</p>
            <p className="gm-stat__figure">
              <Figure text={t.limitOf(limits.daily_spent.display, limit.display)} />
            </p>
            <div
              className="gm-meter"
              role="img"
              aria-label={t.limitMeter(limits.daily_spent.display, limit.display)}
              style={{ "--gm-used": `${used}%` } as CSSProperties}
            >
              <span />
            </div>
            <p className="gm-stat__line">{limitReached ? t.limitReachedShort : t.limitTodayLine}</p>
            <button type="button" className="gm-link gm-stat__action text-sm" onClick={onOpenSafer}>
              {t.saferLink}
            </button>
          </div>
        ) : null}
      </div>

      {flash ? (
        <p role={flash.ok ? "status" : "alert"} className={flash.ok ? "gm-note" : "gm-note gm-error"}>
          {flash.text}
        </p>
      ) : null}

      {foot ? (
        <div className="gm-strip__foot">
          {player.is_guest ? (
            <p>
              {t.guestBanner}{" "}
              <Link href="/signup" prefetch={false} className="gm-link">
                {t.guestBannerAction}
              </Link>
            </p>
          ) : (
            <span />
          )}
          <div className="gm-strip__links">
            {/* After the free top-up, never instead of it, and in the same
                place whatever the balance: it does not appear when somebody
                runs out, because that is the moment not to be sold to. */}
            {onOpenShop ? (
              <button type="button" className="gm-link" onClick={onOpenShop}>
                {t.shopLink}
              </button>
            ) : null}
            {player.is_admin ? (
              <Link href="/admin" prefetch={false} className="gm-link">
                {t.navAdmin}
              </Link>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
