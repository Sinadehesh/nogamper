"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { usePlayer } from "@/components/PlayerProvider";
import { useSlip } from "@/components/SlipProvider";
import { quotedPrices } from "@/components/game/context";
import { Wording } from "@/components/game/Pick";
import { useFocusTrap } from "@/components/game/trap";
import { SlipFigures } from "@/components/viz";
import { Figure } from "@/components/viz/Figure";
import { placeSlip, quoteSlip, type SlipBody } from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { chance, points, readPoints, sideChance } from "@/lib/format";
import type { MarketRules, MarketSummary, Side, SlipQuote } from "@/lib/types";
import type { SlipLegInput } from "@/lib/viz";

/**
 * The slip: review the picks, choose a stake, confirm.
 *
 * Beside the feed on a wide screen (SlipRail), in a sheet from the foot of
 * the screen on a phone or a tablet (SlipSheet). One panel either way, in the
 * order and the words of the front page's picture of it: "Your forecast",
 * then each pick ("Yes at 22%"), then the stake ("100 points"), then what it
 * pays ("pays 462 if right").
 *
 * Three things here are deliberate omissions rather than oversights. There is
 * no "max" button, because staking everything should take typing it. There is
 * no nudge to add another pick. And the chance of the slip coming in sits
 * directly beside what it would pay, at the same size: a big number and how
 * unlikely it is belong in the same glance.
 */

/** What was placed, for the confirmation, in the slip's own words. */
export type Receipt = {
  picks: { question: string; side: Side; chance: string }[];
  stake: string;
  payout: string;
};

type SlipProps = {
  rules: MarketRules;
  /** The questions the feed has shown, by id: a pick's chance before the server's quote is in. */
  prices: ReadonlyMap<string, MarketSummary>;
  onPlaced: (receipt: Receipt) => void;
  /** The quote on screen, or null: the cards of the questions on it show its prices. */
  onQuote?: (quote: SlipQuote | null) => void;
};

function defaultStake(rules: MarketRules, available: number): number {
  // A modest fixed opening stake — five times the minimum — rather than a
  // share of the balance. A default that scales with what you hold quietly
  // raises the stakes every time you do well.
  const preferred = rules.min_stake.minor * 5;
  return Math.max(rules.min_stake.minor, Math.min(preferred, available, rules.max_stake.minor));
}

function quickStakes(rules: MarketRules, available: number): number[] {
  const ceiling = Math.min(available, rules.max_stake.minor);
  return [1, 5, 10, 25]
    .map((multiple) => rules.min_stake.minor * multiple)
    .filter((amount) => amount <= ceiling);
}

const sideWord = (side: Side) => (side === "YES" ? t.yes : t.no);

/** The slip beside the feed, on a wide screen. */
export function SlipRail(props: SlipProps) {
  return <SlipPanel {...props} mode="rail" />;
}

/** The slip in a sheet from the foot of a phone's or a tablet's screen. */
export function SlipSheet(props: SlipProps) {
  const slip = useSlip();
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);

  // Escape closes, as it does for every dialog.
  useEffect(() => {
    if (!slip.isOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") slip.close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [slip]);

  // The sheet takes the focus when it opens and hands it back when it shuts,
  // and the Tab key stays inside it while it is open.
  const { isOpen } = slip;
  useFocusTrap(panel, isOpen);
  useEffect(() => {
    if (!isOpen) return;
    // The page itself is no opener: the folded bar's button has already gone
    // by now when the sheet was opened from it.
    const active = document.activeElement;
    const opener = active instanceof HTMLElement && active !== document.body ? active : null;
    panel.current?.focus({ preventScroll: true });
    return () => {
      if (opener?.isConnected) {
        opener.focus({ preventScroll: true });
        return;
      }
      // The opener has gone: the folded slip bar is not drawn while the sheet
      // is open, and a card's "Review slip" goes with its pick. Once the page
      // has drawn again, the bar's button if it is back, else the view's
      // heading, unless something has taken the focus by then.
      window.requestAnimationFrame(() => {
        if (document.activeElement && document.activeElement !== document.body) return;
        const target =
          document.querySelector<HTMLElement>(".gm-slipbar .btn") ??
          document.getElementById("gm-view-title");
        target?.focus({ preventScroll: true });
      });
    };
  }, [isOpen]);

  if (!slip.isOpen) return null;

  return (
    <div className="gm-sheet gm">
      <div className="gm-sheet__scrim" onClick={slip.close} aria-hidden />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="gm-sheet__panel"
      >
        <span className="gm-sheet__grip" aria-hidden />
        <SlipPanel {...props} mode="sheet" titleId={titleId} />
      </div>
    </div>
  );
}

function SlipPanel({
  rules,
  prices,
  onPlaced,
  onQuote,
  mode,
  titleId,
}: SlipProps & { mode: "rail" | "sheet"; titleId?: string }) {
  const slip = useSlip();
  const { player, refresh } = usePlayer();
  const balance = player.balance.minor;
  const ownTitleId = useId();
  const headingId = titleId ?? ownTitleId;
  const stakeId = useId();
  const stakeHintId = useId();
  const stakeErrorId = useId();
  const discardTitleId = useId();
  const discardBodyId = useId();
  // The rail is on screen whenever it holds a pick; the sheet when it is open.
  const active = mode === "rail" || slip.isOpen;

  // What is left of a daily limit the player set, or null when there is none.
  // The server enforces it; this is so the slip can say so before the button
  // is pressed instead of answering a confirmed stake with a refusal.
  const { daily_limit: limit, daily_spent: spent } = player.limits;
  const allowance = limit ? Math.max(0, limit.minor - spent.minor) : null;
  const available = allowance === null ? balance : Math.min(balance, allowance);

  const legCount = slip.legs.length;

  // The stake is the slip's, not this panel's (see SlipProvider): the field's
  // text, read strictly. A new slip takes the default once, so it does not
  // move with the balance while the slip is open.
  const { stakeDraft, setStakeDraft } = slip;
  const fallbackDraft = points(defaultStake(rules, available));
  const draft = stakeDraft ?? fallbackDraft;
  useEffect(() => {
    if (stakeDraft === null && legCount > 0) setStakeDraft(fallbackDraft);
  }, [stakeDraft, legCount, fallbackDraft, setStakeDraft]);
  const entry = readPoints(draft);
  const stake = entry.minor;
  const typed = entry.problem === null && stake > 0;

  const [quote, setQuote] = useState<SlipQuote | null>(null);
  // The last quote the server gave, kept while the stake is being retyped:
  // the picks' prices do not depend on the stake, so they stay put while the
  // field passes through "", "1" and "12" on the way to "120".
  const [lastQuote, setLastQuote] = useState<SlipQuote | null>(null);
  const [quoting, setQuoting] = useState(false);
  const [placing, setPlacing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const discardBox = useRef<HTMLDivElement>(null);
  const clearButton = useRef<HTMLButtonElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const actions = useRef<HTMLDivElement>(null);
  useFocusTrap(discardBox, confirmClear);

  // Keeping the slip puts the question away and the focus back where it was.
  const keepSlip = useCallback(() => {
    setConfirmClear(false);
    window.requestAnimationFrame(() => clearButton.current?.focus());
  }, []);

  const body: SlipBody = useMemo(
    () => ({
      legs: slip.legs.map((leg) => ({ market_id: leg.marketId, side: leg.side })),
      stake,
    }),
    [slip.legs, stake],
  );

  // One key per distinct slip. The same key on a retry returns the slip that
  // was already placed instead of a second one; a changed slip gets a new key,
  // so an earlier attempt can never be confused with this one.
  const idempotencyKey = useRef(crypto.randomUUID());
  const bodySignature = JSON.stringify(body);
  useEffect(() => {
    idempotencyKey.current = crypto.randomUUID();
  }, [bodySignature]);

  // The feed's own price for each pick. When a refresh of the feed moves
  // one, the slip asks for a new quote, so the slip and the cards move
  // together rather than a minute apart.
  const feedPrices = slip.legs.map((leg) => prices.get(leg.marketId)?.probability.yes ?? "").join(" ");

  // A stake outside the rules is said beside the button, and the server
  // would only refuse it, so it is not sent.
  const inBounds = typed && stake >= rules.min_stake.minor && stake <= rules.max_stake.minor;

  useEffect(() => {
    if (!active || legCount === 0 || !inBounds) {
      setQuote(null);
      setQuoting(false);
      return;
    }

    let cancelled = false;
    setQuoting(true);
    // Debounced: a stake is typed a digit at a time, and each digit is not a
    // question worth asking the server.
    const timer = window.setTimeout(async () => {
      const result = await quoteSlip(body);
      if (cancelled) return;
      setQuoting(false);
      if (result.ok) {
        setQuote(result.data);
        setLastQuote(result.data);
        setError(null);
      } else {
        setQuote(null);
        setError(errorMessage(result.code));
        if (result.status === 401) void refresh();
      }
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [body, legCount, inBounds, active, refresh, feedPrices]);

  // Each pick's own side and chance: the last quote's once there is one, the
  // price the card showed until then. The two agree unless the price moved.
  // A pick swapped to its other side since that quote reads that side from it.
  const lastPrices = useMemo(() => quotedPrices(lastQuote), [lastQuote]);
  const priced: (SlipLegInput & { question: string; marketId: string })[] = slip.legs.map((leg) => {
    const held = lastPrices.get(leg.marketId);
    const market = prices.get(leg.marketId);
    const probability = held
      ? leg.side === "YES"
        ? held.yes
        : held.no
      : market
        ? leg.side === "YES"
          ? market.probability.yes
          : market.probability.no
        : "";
    return { side: leg.side, probability, question: leg.question, marketId: leg.marketId };
  });
  const allPriced = priced.every((leg) => leg.probability !== "");

  // The cards follow the same prices, for the questions still on the slip,
  // and let go of them when the panel goes.
  const onSlip = slip.legs.map((leg) => leg.marketId).join(" ");
  const shownQuote = useMemo(() => {
    if (!lastQuote) return null;
    const ids = new Set(onSlip.split(" "));
    return { ...lastQuote, legs: lastQuote.legs.filter((leg) => ids.has(leg.market_id)) };
  }, [lastQuote, onSlip]);
  useEffect(() => {
    onQuote?.(shownQuote);
  }, [shownQuote, onQuote]);
  useEffect(() => () => onQuote?.(null), [onQuote]);

  const place = useCallback(async () => {
    if (!quote || placing) return;
    setPlacing(true);
    setError(null);

    const result = await placeSlip(
      { ...body, accepted_odds: quote.combined_odds },
      idempotencyKey.current,
    );
    setPlacing(false);

    if (result.ok) {
      // Named from the quote the player confirmed and the slip the server
      // kept: what was placed, not what the page expected to place.
      const receipt: Receipt = {
        picks: result.data.legs.map((leg) => {
          const quoted = quote.legs.find((entry) => entry.market_id === leg.market_id);
          return {
            question: leg.question,
            side: leg.side === "NO" ? "NO" : "YES",
            chance: quoted ? sideChance(quoted.probability, leg.side === "NO" ? "NO" : "YES") : "",
          };
        }),
        stake: points(result.data.stake.minor),
        payout: points(result.data.potential_payout.minor),
      };
      slip.clear();
      setQuote(null);
      setLastQuote(null);
      await refresh();
      onPlaced(receipt);
      return;
    }

    if (result.code === "odds_moved") {
      // Show the new price and make them press the button again. Taking a
      // worse price on somebody's behalf is the one thing this must not do.
      const refreshed = await quoteSlip(body);
      if (refreshed.ok) {
        setQuote(refreshed.data);
        setLastQuote(refreshed.data);
      }
    }
    if (result.code === "on_break" || result.status === 401) void refresh();
    setError(errorMessage(result.code));
  }, [body, quote, placing, slip, refresh, onPlaced]);

  // The panel scrolls under its sticky foot, whose height changes with what
  // it says. A field or a line brought into view stops above the foot, never
  // under it: the panel's scroll padding follows the foot's height.
  useEffect(() => {
    const foot = actions.current;
    const scroller = foot?.closest<HTMLElement>(".gm-sheet__panel, .gm-rail > .gm-panel");
    if (!foot || !scroller) return;
    const fit = () => scroller.style.setProperty("--gm-foot", `${Math.ceil(foot.offsetHeight)}px`);
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(foot);
    return () => observer.disconnect();
  }, [legCount]);

  // Taking a pick off hands the focus on rather than dropping it: to the
  // next pick's remove button, else the one before, else the slip's heading,
  // else the card the pick came from.
  const removePick = useCallback(
    (marketId: string, side: Side, index: number) => {
      slip.remove(marketId);
      window.requestAnimationFrame(() => {
        const buttons = Array.from(list.current?.querySelectorAll<HTMLElement>(".gm-x") ?? []);
        const pick = document.querySelector<HTMLElement>(
          `.gm-pick[data-market="${CSS.escape(marketId)}"][data-side="${side === "YES" ? "yes" : "no"}"]`,
        );
        // The first of them that can take the focus: on a phone the rail's
        // empty slip is in the page but not drawn.
        const candidates = [
          buttons[index],
          buttons[index - 1],
          heading.current,
          document.getElementById("gm-slip-empty"),
          pick,
          document.getElementById("gm-view-title"),
        ];
        for (const candidate of candidates) {
          if (!candidate?.isConnected) continue;
          candidate.focus();
          if (document.activeElement === candidate) return;
        }
      });
    },
    [slip],
  );

  if (legCount === 0) return null;

  const short = stake - balance;
  const overLimit = allowance !== null && stake > allowance;
  const { min_stake: min, max_stake: max } = rules;
  // Said beside the button it disables, in the order a player would fix them.
  const fieldError =
    entry.problem === "fraction"
      ? t.stakeWhole(min.display, max.display)
      : !typed
        ? t.stakeEnter(min.display, max.display)
        : stake < min.minor
          ? t.stakeTooSmall(min.display)
          : stake > max.minor
            ? t.stakeTooLarge(max.display)
            : short > 0
              ? t.notEnough(points(short))
              : overLimit
                ? allowance
                  ? t.overLimit(points(allowance))
                  : t.overLimitNone
                : null;

  const single = legCount === 1;
  const payout = quote && !fieldError ? points(quote.potential_payout.minor) : null;
  // How likely the slip is to come in, beside what it pays: for one pick,
  // its own chance as its line prints it; for several, the chance that all
  // of them are right, the product the steps above end on.
  const first = priced[0];
  const chanceRight = !allPriced
    ? null
    : single
      ? first
        ? sideChance(first.probability, first.side)
        : null
      : chance(priced.reduce((all, leg) => all * Number(leg.probability), 1));

  return (
    <section className="gm-slip relative" aria-labelledby={headingId}>
      <header className="gm-slip__head">
        <h2 ref={heading} id={headingId} tabIndex={-1} className="gm-h">
          {t.slipTitle}
        </h2>
        <span className="gm-slip__count">{t.slipLegCount(legCount, slip.maxLegs)}</span>
      </header>

      <ul ref={list} className="gm-legs">
        {priced.map((leg, index) => (
          <li key={leg.marketId} className="gm-leg">
            <div className="min-w-0">
              <p className="gm-leg__q">
                <Wording text={leg.question} />
              </p>
              <p className="gm-leg__pick">
                <span className="gm-side" data-side={leg.side === "YES" ? "yes" : "no"} aria-hidden />
                {leg.probability !== "" ? (
                  <Figure text={t.slipPick(sideWord(leg.side), sideChance(leg.probability, leg.side))} />
                ) : (
                  sideWord(leg.side)
                )}
              </p>
            </div>
            <button
              type="button"
              className="gm-x"
              onClick={() => removePick(leg.marketId, leg.side, index)}
              aria-label={t.removeLegOf(leg.question)}
            >
              <svg viewBox="0 0 14 14" aria-hidden="true">
                <path d="M3 3l8 8M11 3l-8 8" />
              </svg>
            </button>
          </li>
        ))}
      </ul>

      <div className="gm-stake">
        <label htmlFor={stakeId} className="label">
          {t.stake}
        </label>
        <div className="gm-stake__row">
          <input
            id={stakeId}
            className="field"
            inputMode="numeric"
            autoComplete="off"
            value={draft}
            aria-invalid={fieldError ? true : undefined}
            aria-describedby={fieldError ? `${stakeErrorId} ${stakeHintId}` : stakeHintId}
            onChange={(event) => setStakeDraft(event.target.value)}
            onBlur={() => {
              // Tidied to "1,200" once typed, but never rewritten when it is
              // not a number: the field keeps what was typed beside its error.
              if (entry.problem === null) setStakeDraft(points(stake));
            }}
          />
          <span className="gm-stake__unit" aria-hidden>
            {t.stakeUnit}
          </span>
        </div>
        <p id={stakeHintId} className="gm-stake__hint">
          {t.stakeHint(min.display, max.display)} {t.stakeHave(points(balance))}
          {allowance !== null ? ` ${t.limitLeft(points(allowance))}` : null}
        </p>
        <div className="gm-chips" role="group" aria-label={t.quickStakes}>
          {quickStakes(rules, available).map((amount) => (
            <button
              key={amount}
              type="button"
              className="gm-chip"
              aria-pressed={typed && stake === amount}
              onClick={() => setStakeDraft(points(amount))}
            >
              <Figure text={points(amount)} />
            </button>
          ))}
        </div>
      </div>

      {/* Two picks or more: the chance shrinking pick by pick, after the stake
          so the stake stays near the top of a phone's sheet. Its total and its
          return line are the receipt's below, beside the button. */}
      {!single && allPriced ? (
        <SlipFigures legs={priced} stakeMinor={stake} rules={rules} className="gm-slip__steps" />
      ) : null}

      {/* What the slip comes to, why the button is off when it is, and the
          button: kept in view at the foot of the rail or the sheet however
          long the slip grows, so what a stake returns, how likely that is,
          and any reason it cannot be placed are never out of sight of the
          button that places it. */}
      <div ref={actions} className="gm-slip__actions">
        <div className="gm-receipt" aria-live="polite" aria-atomic="true">
          {typed ? (
            <p className="gm-receipt__line">
              <Figure text={t.slipStakeLine(points(stake))} />
            </p>
          ) : null}
          <p className="gm-receipt__big">
            {payout ? <Figure text={t.slipPaysLine(payout)} /> : quoting ? t.quoting : "—"}
          </p>
          {chanceRight ? (
            <p className="gm-receipt__big">
              <Figure text={t.slipChanceLine(chanceRight)} />
            </p>
          ) : null}
          {quote?.capped && payout ? (
            <p className="gm-receipt__note">{t.cappedAt(quote.payout_cap.display)}</p>
          ) : null}
          {!single ? <p className="gm-receipt__note">{t.slipAllMustWin(legCount)}</p> : null}
        </div>

        {fieldError ? (
          <p id={stakeErrorId} role="alert" className="gm-error">
            {fieldError}
          </p>
        ) : error ? (
          <p role="alert" className="gm-error">
            {error}
          </p>
        ) : null}

        <button
          type="button"
          className="btn btn--primary"
          disabled={!quote || quoting || placing || Boolean(fieldError)}
          onClick={() => void place()}
        >
          {placing ? t.placing : typed ? t.placeForecast(points(stake)) : t.placeForecastBare}
        </button>
      </div>

      <div className="gm-slip__after">
        <div className="gm-slip__minor">
          {mode === "sheet" ? (
            <button type="button" className="gm-quiet" onClick={slip.close}>
              {t.keepBrowsing}
            </button>
          ) : (
            <span />
          )}
          <button
            ref={clearButton}
            type="button"
            className="gm-quiet"
            onClick={() => setConfirmClear(true)}
          >
            {t.discardOpen}
          </button>
        </div>
        <p className="gm-slip__foot">{t.noMargin}</p>
      </div>

      {confirmClear ? (
        <div className="gm-discard">
          <div
            ref={discardBox}
            role="alertdialog"
            aria-modal="true"
            aria-labelledby={discardTitleId}
            aria-describedby={discardBodyId}
            onKeyDown={(event) => {
              // Escape answers this question (keep), not the sheet around it.
              if (event.key === "Escape") {
                event.stopPropagation();
                keepSlip();
              }
            }}
          >
            <p id={discardTitleId} className="gm-h gm-h--sm">
              {t.discardTitle}
            </p>
            <p id={discardBodyId} className="gm-small">
              {t.discardBody(legCount)}
            </p>
            <div className="btn-row">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                autoFocus
                onClick={keepSlip}
              >
                {t.discardKeep}
              </button>
              <button
                type="button"
                className="btn btn-danger btn-sm"
                onClick={() => {
                  setConfirmClear(false);
                  slip.clear();
                }}
              >
                {t.discardConfirm}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

/**
 * Before the first pick: what the slip is for. On a break or at the day's
 * limit no pick can be made, and it says that instead of asking for one.
 */
export function SlipEmpty({ maxLegs, paused = null }: { maxLegs: number; paused?: string | null }) {
  return (
    <section className="gm-slip-empty" aria-labelledby="gm-slip-empty">
      <h2 id="gm-slip-empty" tabIndex={-1} className="gm-h">
        {t.slipTitle}
      </h2>
      {paused ? (
        <p className="gm-small">{paused}</p>
      ) : (
        <>
          <p className="gm-label">{t.slipEmptyTitle}</p>
          <p className="gm-small">{t.slipEmptyBody(maxLegs)}</p>
          <div className="gm-slip-empty__art" aria-hidden>
            <span />
            <span />
          </div>
        </>
      )}
    </section>
  );
}

/**
 * After a forecast is placed: what was placed, plainly, in the slip's words.
 * No celebration; the player decides what comes next.
 */
export function SlipPlaced({
  receipt,
  onSee,
  onDone,
  titleId,
}: {
  receipt: Receipt;
  onSee: () => void;
  onDone: () => void;
  titleId?: string;
}) {
  const ownId = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  // The button that placed it has gone; the confirmation takes the focus.
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, []);

  return (
    <section className="gm-done" aria-labelledby={titleId ?? ownId}>
      <h2 ref={heading} id={titleId ?? ownId} tabIndex={-1} className="gm-h">
        {t.placedTitle}
      </h2>
      <div className="gm-receipt">
        <p className="gm-label">{t.slipTitle}</p>
        {receipt.picks.map((pick, index) => (
          <div key={index}>
            <p className="gm-receipt__line">
              <Wording text={pick.question} />
            </p>
            <p className="gm-leg__pick">
              <span className="gm-side" data-side={pick.side === "YES" ? "yes" : "no"} aria-hidden />
              {pick.chance ? (
                <Figure text={t.slipPick(sideWord(pick.side), pick.chance)} />
              ) : (
                sideWord(pick.side)
              )}
            </p>
          </div>
        ))}
        <p className="gm-receipt__line mt-2">
          <Figure text={t.slipStakeLine(receipt.stake)} />
        </p>
        <p className="gm-receipt__big">
          <Figure text={t.slipPaysLine(receipt.payout)} />
        </p>
      </div>
      <p className="gm-small">{t.placedBody}</p>
      <div className="gm-done__actions">
        <button type="button" className="btn btn--secondary" onClick={onSee}>
          {t.placedSee}
        </button>
        <button type="button" className="gm-quiet" onClick={onDone}>
          {t.placedDone}
        </button>
      </div>
    </section>
  );
}
