"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { usePlayer } from "@/components/PlayerProvider";
import { useSlip } from "@/components/SlipProvider";
import { placeSlip, quoteSlip, type SlipBody } from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { chance, odds, parsePoints, points } from "@/lib/format";
import type { MarketRules, SlipQuote } from "@/lib/types";

/**
 * The slip: review the picks, choose a stake, confirm.
 *
 * Three things here are deliberate omissions rather than oversights. There is
 * no "max" button, because staking everything should take typing it. There is
 * no nudge to add another pick. And the chance of the slip coming in sits
 * directly above what it would pay, at the same size — a big number and how
 * unlikely it is belong in the same glance.
 */

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

export function SlipSheet({
  rules,
  onPlaced,
}: {
  rules: MarketRules;
  onPlaced: () => void;
}) {
  const slip = useSlip();
  const { player, refresh } = usePlayer();
  const balance = player.balance.minor;
  const titleId = useId();
  const stakeId = useId();

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

  useEffect(() => {
    if (!slip.isOpen || legCount === 0 || stake <= 0) {
      setQuote(null);
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
  }, [body, legCount, stake, slip.isOpen, refresh]);

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
      slip.clear();
      setQuote(null);
      await refresh();
      onPlaced();
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

  // Escape closes, as it does for every dialog.
  useEffect(() => {
    if (!slip.isOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") slip.close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [slip]);

  if (!slip.isOpen) return null;

  const short = stake - balance;
  const overLimit = allowance !== null && stake > allowance;
  const profit = quote ? quote.potential_payout.minor - quote.stake.minor : 0;

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center sm:items-center sm:p-4">
      <div className="absolute inset-0 bg-black/50" onClick={slip.close} aria-hidden />

      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-10 flex max-h-[92dvh] w-full max-w-lg flex-col overflow-hidden
                   rounded-t-2xl border border-line bg-surface shadow-2xl sm:rounded-2xl"
      >
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <div>
            <h2 id={titleId} className="text-lg font-bold">
              {t.slipTitle}
            </h2>
            <p className="text-xs text-muted">{t.slipLegCount(legCount, slip.maxLegs)}</p>
          </div>
          <button type="button" className="btn btn-quiet btn-sm" onClick={slip.close}>
            {t.close}
          </button>
        </header>

        <div className="space-y-4 overflow-y-auto px-4 py-4">
          <ul className="space-y-2">
            {slip.legs.map((leg) => {
              const priced = quote?.legs.find((entry) => entry.market_id === leg.marketId);
              return (
                <li key={leg.marketId} className="flex items-start gap-3 rounded-xl bg-sunken p-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium leading-snug">{leg.question}</p>
                    <p className="mt-1 text-xs text-muted">
                      <span
                        className={`font-bold ${leg.side === "YES" ? "text-yes" : "text-no"}`}
                      >
                        {leg.side === "YES" ? t.yes : t.no}
                      </span>
                      {priced ? (
                        <span className="tabular-nums">
                          {" · "}
                          {chance(priced.probability)} · {odds(priced.locked_odds)}
                        </span>
                      ) : null}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="btn btn-quiet btn-sm !min-h-8 !px-2"
                    onClick={() => slip.remove(leg.marketId)}
                    aria-label={t.removeLeg}
                  >
                    ×
                  </button>
                </li>
              );
            })}
          </ul>

          <div>
            <div className="flex items-baseline justify-between">
              <label htmlFor={stakeId} className="label">
                {t.stake}
              </label>
              <span className="text-xs text-muted tabular-nums">
                {t.balance}: {points(balance)}
              </span>
            </div>
            <input
              id={stakeId}
              className="field text-xl font-bold tabular-nums"
              inputMode="numeric"
              value={draft}
              aria-invalid={short > 0 || overLimit ? true : undefined}
              onChange={(event) => {
                setDraft(event.target.value);
                setStake(parsePoints(event.target.value));
              }}
              onBlur={() => setDraft(points(stake))}
            />
            <div className="mt-2 flex flex-wrap gap-2">
              {quickStakes(rules, available).map((amount) => (
                <button
                  key={amount}
                  type="button"
                  className="btn btn-secondary btn-sm tabular-nums"
                  onClick={() => {
                    setStake(amount);
                    setDraft(points(amount));
                  }}
                >
                  {points(amount)}
                </button>
              ))}
            </div>
            <p className="hint">
              {t.stakeHint(rules.min_stake.display, rules.max_stake.display)}
              {allowance !== null ? ` ${t.limitLeft(points(allowance))}` : null}
            </p>
          </div>

          <dl className="space-y-2 rounded-xl border border-line p-3 text-sm">
            <Row
              label={t.combinedOdds}
              value={quote ? odds(quote.combined_odds) : quoting ? t.quoting : "—"}
            />
            <div className="border-t border-line pt-2">
              <dt className="text-muted">{t.winChance}</dt>
              <dd className="text-2xl font-black tabular-nums">
                {quote ? chance(quote.win_probability) : "—"}
              </dd>
            </div>
            <div className="border-t border-line pt-2">
              <dt className="text-muted">{t.toWin}</dt>
              <dd className="text-2xl font-black tabular-nums">
                {quote ? `${points(quote.potential_payout.minor)} ${t.pts}` : "—"}
              </dd>
              {quote ? <p className="text-xs text-muted">{t.profit(points(profit))}</p> : null}
              {quote?.capped ? (
                <p className="mt-1 text-xs text-warn">{t.cappedAt(quote.payout_cap.display)}</p>
              ) : null}
            </div>
          </dl>

          {quote ? (
            <p className="text-xs text-muted">
              {t.winChanceNote(chance(quote.win_probability))}{" "}
              {legCount > 1 ? t.slipAllMustWin(legCount) : null}
            </p>
          ) : null}

          {short > 0 ? (
            <p role="alert" className="notice notice-warn">
              {t.notEnough(points(short))}
            </p>
          ) : overLimit ? (
            <p role="alert" className="notice notice-warn">
              {allowance ? t.overLimit(points(allowance)) : t.overLimitNone}
            </p>
          ) : error ? (
            <p role="alert" className="notice notice-error">
              {error}
            </p>
          ) : null}
        </div>

        <footer className="space-y-2 border-t border-line px-4 py-3">
          <button
            type="button"
            className="btn btn-primary w-full"
            disabled={!quote || quoting || placing || short > 0 || overLimit}
            onClick={() => void place()}
          >
            {placing ? t.placing : t.placeForecast(points(stake))}
          </button>
          <div className="flex items-center justify-between gap-2">
            <button type="button" className="btn btn-quiet btn-sm" onClick={slip.close}>
              {t.keepBrowsing}
            </button>
            <button
              type="button"
              className="btn btn-quiet btn-sm"
              onClick={() => setConfirmClear(true)}
            >
              {t.discardOpen}
            </button>
          </div>
          <p className="text-center text-[0.7rem] text-muted">{t.noMargin}</p>
        </footer>

        {confirmClear ? (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/40 p-4">
            <div
              role="alertdialog"
              aria-modal="true"
              aria-labelledby="discard-title"
              aria-describedby="discard-body"
              className="card w-full max-w-xs p-4"
            >
              <p id="discard-title" className="font-bold">
                {t.discardTitle}
              </p>
              <p id="discard-body" className="mt-1 text-sm text-muted">
                {t.discardBody(legCount)}
              </p>
              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setConfirmClear(false)}
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
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted">{label}</dt>
      <dd className="font-semibold tabular-nums">{value}</dd>
    </div>
  );
}
