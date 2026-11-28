"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { usePlayer } from "@/components/PlayerProvider";
import { useSlip } from "@/components/SlipProvider";
import { Wording } from "@/components/game/Pick";
import { useFocusTrap } from "@/components/game/trap";
import { SlipFigures } from "@/components/viz";
import { Figure } from "@/components/viz/Figure";
import { placeSlip, quoteSlip, type SlipBody } from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { chance, parsePoints, points } from "@/lib/format";
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
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panel.current?.focus({ preventScroll: true });
    return () => opener?.focus({ preventScroll: true });
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
  const stakeNoteId = useId();
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

  const [stake, setStake] = useState(() => defaultStake(rules, available));
  const [draft, setDraft] = useState(() => points(stake));
  const [quote, setQuote] = useState<SlipQuote | null>(null);
  const [quoting, setQuoting] = useState(false);
  const [placing, setPlacing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const discardBox = useRef<HTMLDivElement>(null);
  const clearButton = useRef<HTMLButtonElement>(null);
  useFocusTrap(discardBox, confirmClear);

  // Keeping the slip puts the question away and the focus back where it was.
  const keepSlip = useCallback(() => {
    setConfirmClear(false);
    window.requestAnimationFrame(() => clearButton.current?.focus());
  }, []);

  const legCount = slip.legs.length;

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

  // A stake outside the rules is said under the field, and the server would
  // only refuse it, so it is not sent.
  const inBounds = stake >= rules.min_stake.minor && stake <= rules.max_stake.minor;

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

  // The cards follow the quote on screen, and let go of it when it goes.
  useEffect(() => {
    onQuote?.(quote);
  }, [quote, onQuote]);
  useEffect(() => () => onQuote?.(null), [onQuote]);

  // Each pick's own side and chance: the server's quote once it is in, the
  // price the card showed until then. The two agree unless the price moved.
  const priced: (SlipLegInput & { question: string; marketId: string })[] = slip.legs.map((leg) => {
    const quoted = quote?.legs.find((entry) => entry.market_id === leg.marketId);
    const market = prices.get(leg.marketId);
    const probability =
      quoted?.probability ??
      (market ? (leg.side === "YES" ? market.probability.yes : market.probability.no) : "");
    return { side: leg.side, probability, question: leg.question, marketId: leg.marketId };
  });
  const allPriced = priced.every((leg) => leg.probability !== "");

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
            chance: quoted ? chance(quoted.probability) : "",
          };
        }),
        stake: points(result.data.stake.minor),
        payout: points(result.data.potential_payout.minor),
      };
      slip.clear();
      setQuote(null);
      await refresh();
      onPlaced(receipt);
      return;
    }

    if (result.code === "odds_moved") {
      // Show the new price and make them press the button again. Taking a
      // worse price on somebody's behalf is the one thing this must not do.
      const refreshed = await quoteSlip(body);
      if (refreshed.ok) setQuote(refreshed.data);
    }
    if (result.code === "on_break" || result.status === 401) void refresh();
    setError(errorMessage(result.code));
  }, [body, quote, placing, slip, refresh, onPlaced]);

  if (legCount === 0) return null;

  const short = stake - balance;
  const overLimit = allowance !== null && stake > allowance;
  // Said under the field, in the order a player would fix them.
  const fieldError =
    stake > 0 && stake < rules.min_stake.minor
      ? t.stakeTooSmall(rules.min_stake.display)
      : stake > rules.max_stake.minor
        ? t.stakeTooLarge(rules.max_stake.display)
        : short > 0
          ? t.notEnough(points(short))
          : overLimit
            ? allowance
              ? t.overLimit(points(allowance))
              : t.overLimitNone
            : null;

  const single = legCount === 1;
  const payout = quote ? points(quote.potential_payout.minor) : null;
  const chanceRight = quote ? chance(quote.win_probability) : null;

  return (
    <section className="gm-slip relative" aria-labelledby={headingId}>
      <header className="gm-slip__head">
        <h2 id={headingId} className="gm-h">
          {t.slipTitle}
        </h2>
        <span className="gm-slip__count">{t.slipLegCount(legCount, slip.maxLegs)}</span>
      </header>

      <ul className="gm-legs">
        {priced.map((leg) => (
          <li key={leg.marketId} className="gm-leg">
            <div className="min-w-0">
              <p className="gm-leg__q">
                <Wording text={leg.question} />
              </p>
              <p className="gm-leg__pick">
                <span className="gm-side" data-side={leg.side === "YES" ? "yes" : "no"} aria-hidden />
                {leg.probability !== "" ? (
                  <Figure text={t.slipPick(sideWord(leg.side), chance(leg.probability))} />
                ) : (
                  sideWord(leg.side)
                )}
              </p>
            </div>
            <button
              type="button"
              className="gm-x"
              onClick={() => slip.remove(leg.marketId)}
              aria-label={t.removeLegOf(leg.question)}
            >
              <svg viewBox="0 0 14 14" aria-hidden="true">
                <path d="M3 3l8 8M11 3l-8 8" />
              </svg>
            </button>
          </li>
        ))}
      </ul>

      {/* Two picks or more: the chance shrinking pick by pick. Its return line
          is the receipt's below, in the front page's words. */}
      {!single && allPriced ? (
        <SlipFigures legs={priced} stakeMinor={stake} rules={rules} className="gm-slip__steps" />
      ) : null}

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
            aria-describedby={stakeNoteId}
            onChange={(event) => {
              setDraft(event.target.value);
              setStake(parsePoints(event.target.value));
            }}
            onBlur={() => setDraft(points(stake))}
          />
          <span className="gm-stake__unit" aria-hidden>
            {t.stakeUnit}
          </span>
        </div>
        <div id={stakeNoteId}>
          {fieldError ? (
            <p role="alert" className="gm-error">
              {fieldError}
            </p>
          ) : null}
          <p className="gm-stake__hint">
            {t.stakeHint(rules.min_stake.display, rules.max_stake.display)}{" "}
            {t.stakeHave(points(balance))}
            {allowance !== null ? ` ${t.limitLeft(points(allowance))}` : null}
          </p>
        </div>
        <div className="gm-chips" role="group" aria-label={t.quickStakes}>
          {quickStakes(rules, available).map((amount) => (
            <button
              key={amount}
              type="button"
              className="gm-chip"
              aria-pressed={stake === amount}
              onClick={() => {
                setStake(amount);
                setDraft(points(amount));
              }}
            >
              <Figure text={points(amount)} />
            </button>
          ))}
        </div>
      </div>

      {/* What the slip comes to, anything the game refuses, and the button:
          kept in view at the foot of the rail or the sheet however long the
          slip grows, so what a stake returns is never out of sight of the
          button that places it. */}
      <div className="gm-slip__actions">
        <div className="gm-receipt" aria-live="polite" aria-atomic="true">
          <p className="gm-receipt__line">
            <Figure text={t.slipStakeLine(points(stake))} />
          </p>
          <p className="gm-receipt__big">
            {payout ? <Figure text={t.slipPaysLine(payout)} /> : quoting ? t.quoting : "—"}
          </p>
          {single && chanceRight ? (
            <p className="gm-receipt__big">
              <Figure text={t.slipChanceLine(chanceRight)} />
            </p>
          ) : null}
          {quote?.capped ? (
            <p className="gm-receipt__note">{t.cappedAt(quote.payout_cap.display)}</p>
          ) : null}
          {!single && quote ? <p className="gm-receipt__note">{t.slipAllMustWin(legCount)}</p> : null}
        </div>

        {error && !fieldError ? (
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
          {placing ? t.placing : t.placeForecast(points(stake))}
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
      <h2 id="gm-slip-empty" className="gm-h">
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
