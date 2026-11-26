"use client";


import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { BuyCoinsModal } from "@/components/BuyCoinsModal";
import { MAX_LEGS, useBetSlip } from "@/components/BetSlipProvider";
import {
  coins,
  count,
  odds,
  oddsValue,
  parseAmount,
  percent,
  priceAnchor,
  shortCoins,
} from "@/lib/format";
import { fa, translateError } from "@/lib/i18n";
import { placeSlip, quoteSlip, type PlacementResult } from "@/lib/api";
import type { Slip, SlipQuote, UserProfile } from "@/lib/types";

type Props = {
  profile: UserProfile;
  onPlaced: (slip: Slip) => void;
  onBalanceChanged: () => void;
  bonuses: string[];
};

function defaultStake(balanceMinor: number): number {
  const tenth = Math.round(balanceMinor / 10 / 100) * 100;
  return Math.max(1000, Math.min(tenth, 5_000_000, balanceMinor));
}

export function BetSlip({
  profile,
  onPlaced,
  onBalanceChanged,
  bonuses,
}: Props) {
  const slip = useBetSlip();
  const balance = profile.balance.minor;

  const [stake, setStake] = useState(() => defaultStake(balance));
  const [insurance, setInsurance] = useState(false);
  const [quote, setQuote] = useState<SlipQuote | null>(null);
  const [quoteError, setQuoteError] = useState<string | null>(null);
  const [requiredLegs, setRequiredLegs] = useState<number | null>(null);
  const [quoting, setQuoting] = useState(false);
  const [placing, setPlacing] = useState(false);
  const [result, setResult] = useState<PlacementResult | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [shortfall, setShortfall] = useState<number | null>(null);

  const idempotencyKey = useRef<string>(crypto.randomUUID());
  const legCount = slip.legs.length;

  useEffect(() => {
    if (quote && !quote.insurance.available && insurance) setInsurance(false);
  }, [quote, insurance]);

  const body = useMemo(
    () => ({
      legs: slip.legs.map((leg) => ({
        market_id: leg.marketId,
        side: leg.side,
      })),
      stake,
      insurance,
    }),
    [slip.legs, stake, insurance],
  );

  useEffect(() => {
    if (legCount === 0 || stake <= 0) {
      setQuote(null);
      return;
    }

    let cancelled = false;
    setQuoting(true);
    const timer = setTimeout(async () => {
      const response = await quoteSlip(body);
      if (cancelled) return;
      setQuoting(false);
      if (response.ok) {
        setQuote(response.data);
        setQuoteError(null);
        setRequiredLegs(null);
      } else if (response.code === "too_few_legs") {
        setQuote(null);
        setQuoteError(null);
        setRequiredLegs(response.requiredLegs ?? null);
      } else {
        setQuote(null);
        setQuoteError(translateError(response.code, response.detail));
        setRequiredLegs(null);
      }
    }, 250);

    return () => {
      cancelled = true;
      clearTimeout(timer);
      setQuoting(false);
    };
  }, [body, legCount, stake]);

  const handlePlace = useCallback(async () => {
    if (!quote) return;
    setPlacing(true);
    setResult(null);

    const outcome = await placeSlip(
      { ...body, accepted_odds: quote.combined_odds },
      idempotencyKey.current,
      quote.total_cost.minor,
      balance,
    );
    setPlacing(false);

    if (outcome.kind === "placed") {
      idempotencyKey.current = crypto.randomUUID();
      slip.clear();
      setQuote(null);
      onPlaced(outcome.slip);
      onBalanceChanged();
      return;
    }

    if (outcome.kind === "insufficient_funds") {
      setShortfall(outcome.shortfallMinor);
      return;
    }

    if (outcome.kind === "odds_moved") {
      idempotencyKey.current = crypto.randomUUID();
      const refreshed = await quoteSlip(body);
      if (refreshed.ok) setQuote(refreshed.data);
    }

    setResult(outcome);
  }, [body, quote, balance, slip, onPlaced, onBalanceChanged]);

  const requestClose = () => {
    if (legCount > 0) setConfirmDiscard(true);
    else slip.close();
  };

  if (!slip.isOpen) return null;

  const total = quote?.total_cost.minor ?? stake;
  const overBalance = total > balance;

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/50"
        onClick={requestClose}
        aria-hidden
      />

      <section
        role="dialog"
        aria-label={fa.slipTitle}
        className="fixed inset-x-0 bottom-0 z-50 max-h-[88dvh] overflow-y-auto rounded-t-3xl
                   bg-tg-secondary-bg pb-[env(safe-area-inset-bottom)] shadow-2xl"
      >
        <header
          className="sticky top-0 flex items-center justify-between gap-3
                           border-b border-tg-hint/15 bg-tg-secondary-bg px-4 py-3"
        >
          <div>
            <h2 className="text-base font-bold">{fa.slipTitle}</h2>
            <p className="text-xs text-tg-hint">
              {fa.slipLegCount(count(legCount), count(MAX_LEGS))}
            </p>
          </div>
          <button
            onClick={requestClose}
            className="rounded-full px-3 py-1.5 text-sm text-tg-hint active:bg-tg-hint/10"
          >
            {fa.close}
          </button>
        </header>

        <div className="space-y-4 px-4 py-4">
          <LegList quote={quote} onRemove={slip.remove} legs={slip.legs} />

          <ParlayProgress legCount={legCount} quote={quote} />

          <StakeField
            stake={stake}
            balance={balance}
            onChange={setStake}
            overBalance={overBalance}
          />

          {quote?.insurance.available ? (
            <InsuranceToggle
              quote={quote}
              selected={insurance}
              onToggle={() => setInsurance((on) => !on)}
            />
          ) : null}

          <PayoutSummary
            quote={quote}
            quoting={quoting}
            stake={stake}
            legCount={legCount}
            bonuses={bonuses}
          />

          {requiredLegs !== null && legCount < requiredLegs ? (
            <p className="rounded-xl bg-tg-secondary-bg px-3 py-2 text-sm text-tg-text">
              <span className="font-bold text-[var(--color-boost)]">
                {fa.unlockMultiplier(count(requiredLegs - legCount))}
              </span>
              <span className="mt-0.5 block text-xs text-tg-hint">
                {fa.parlayOnlyHint(count(requiredLegs))}
              </span>
            </p>
          ) : null}

          {quoteError ? (
            <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-300">
              {quoteError}
            </p>
          ) : null}

          {result &&
          result.kind !== "placed" &&
          result.kind !== "insufficient_funds" ? (
            <p className="rounded-xl bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
              {translateError(result.code, result.detail)}
            </p>
          ) : null}

          {/* Back to the markets, named for what it leads to.
           *
           * The only way out of this sheet was "Close", and a close button
           * does not read as "carry on betting" — so a player who had picked
           * one selection had no visible route to a second. Gold, because it
           * leads to the bonus; below the payout, because the decision to
           * place comes first. */}
          {legCount < MAX_LEGS ? (
            <button
              type="button"
              onClick={slip.close}
              className="w-full rounded-2xl border border-[#e8b73a]/45 bg-[#e8b73a]/10 px-4
                         py-3 text-sm font-bold text-[#e8b73a] transition duration-150
                         active:scale-[0.98]"
            >
              {fa.keepPicking}
            </button>
          ) : null}

          <button
            disabled={!quote || placing || quoting}
            onClick={handlePlace}
            className="w-full rounded-2xl bg-tg-button px-4 py-3.5 text-base font-bold
                       text-tg-button-text disabled:opacity-40"
          >
            {placing
              ? fa.placing
              : overBalance
                ? fa.placeAndTopUp(coins(total))
                : fa.placePrediction(coins(total))}
          </button>

          {/* "All N must win" stays; the no-cash-value line does not.
           *
           * It is not lost — the fuller version sits in the top-up sheet,
           * which is where real money is actually spent and the only place it
           * has to be. Repeating it at the moment of the bet was the app
           * arguing with the thing the player is doing, and it said nothing
           * the top-up sheet had not already said before their money moved. */}
          {legCount > 1 ? (
            <p className="text-center text-[11px] leading-relaxed text-tg-hint">
              {fa.allLegsMustWin(count(legCount))}
            </p>
          ) : null}
        </div>
      </section>

      {confirmDiscard ? (
        <ConfirmDiscard
          legCount={legCount}
          onKeep={() => setConfirmDiscard(false)}
          onDiscard={() => {
            setConfirmDiscard(false);
            slip.clear();
          }}
          onHide={() => {
            setConfirmDiscard(false);
            slip.close();
          }}
        />
      ) : null}

      {shortfall !== null ? (
        <BuyCoinsModal
          shortfallMinor={shortfall}
          onClose={() => setShortfall(null)}
          onFunded={() => {
            setShortfall(null);
            onBalanceChanged();
          }}
        />
      ) : null}
    </>
  );
}

function LegList({
  legs,
  quote,
  onRemove,
}: {
  legs: { marketId: string; side: string; question: string }[];
  quote: SlipQuote | null;
  onRemove: (marketId: string) => void;
}) {
  return (
    <ul className="space-y-2">
      {legs.map((leg) => {
        const priced = quote?.legs.find((q) => q.market_id === leg.marketId);
        return (
          <li
            key={leg.marketId}
            className="flex items-start gap-3 rounded-xl bg-tg-bg/60 px-3 py-2.5"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{leg.question}</p>
              <p className="mt-0.5 text-xs text-tg-hint">
                <span
                  className={
                    leg.side === "YES"
                      ? "font-semibold text-emerald-400"
                      : "font-semibold text-rose-400"
                  }
                >
                  {leg.side === "YES" ? fa.sideYes : fa.sideNo}
                </span>
                {priced ? (
                  <>
                    {" · "}
                    {priced.boosted ? (
                      <>
                        {/* The struck-through number is the real unboosted
                            price this market would have paid. */}
                        <span className="text-tg-hint/60 line-through">
                          {oddsValue(
                            String(
                              Number(priced.locked_odds) /
                                Number(priced.boost_multiplier),
                            ),
                          )}
                        </span>{" "}
                        <span className="font-semibold text-emerald-400">
                          {odds(priced.locked_odds)}
                        </span>
                      </>
                    ) : (
                      <span className="font-semibold">
                        {odds(priced.locked_odds)}
                      </span>
                    )}
                  </>
                ) : null}
              </p>
            </div>
            <button
              onClick={() => onRemove(leg.marketId)}
              aria-label={fa.removeLeg}
              className="shrink-0 rounded-full px-2 py-1 text-lg leading-none text-tg-hint active:bg-tg-hint/10"
            >
              ×
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function ParlayProgress({
  legCount,
  quote,
}: {
  legCount: number;
  quote: SlipQuote | null;
}) {
  if (legCount >= MAX_LEGS) {
    return (
      <p className="rounded-xl bg-tg-bg/60 px-3 py-2 text-xs text-tg-hint">
        {fa.slipFull(count(MAX_LEGS))}
      </p>
    );
  }

  return (
    <div className="rounded-xl bg-tg-bg/60 px-3 py-2.5">
      {/* Stacked rather than a two-column row: Farsi runs longer than the
          English it replaced, and a flex row orphaned the last word. */}
      <div className="space-y-1 text-xs text-tg-hint">
        <p className="font-medium">
          {fa.slipLegCount(count(legCount), count(MAX_LEGS))}
          {quote ? ` · ${odds(quote.combined_odds)}` : ""}
        </p>
        <p className="leading-relaxed">{fa.slipTradeoff}</p>
      </div>
      <div className="mt-2 flex gap-1" aria-hidden>
        {Array.from({ length: MAX_LEGS }, (_, index) => (
          <span
            key={index}
            className={`h-1 flex-1 rounded-full ${
              index < legCount ? "bg-tg-button" : "bg-tg-hint/20"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

function StakeField({
  stake,
  balance,
  onChange,
  overBalance,
}: {
  stake: number;
  balance: number;
  onChange: (minor: number) => void;
  overBalance: boolean;
}) {
  const [draft, setDraft] = useState(() => coins(stake));
  useEffect(() => setDraft(coins(stake)), [stake]);

  const chips: [string, number][] = [
    [fa.stakePercent(count(10)), Math.round(balance / 10)],
    [fa.stakePercent(count(25)), Math.round(balance / 4)],
    [fa.stakeMax, balance],
  ];

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <label
          htmlFor="stake"
          className="text-xs font-medium uppercase tracking-wide text-tg-hint"
        >
          {fa.stake}
        </label>
        <span className="text-xs text-tg-hint">
          {fa.balance} {coins(balance)}
        </span>
      </div>

      <input
        id="stake"
        inputMode="decimal"
        value={draft}
        onChange={(event) => {
          setDraft(event.target.value);
          onChange(parseAmount(event.target.value));
        }}
        onBlur={() => setDraft(coins(stake))}
        className={`mt-1.5 w-full rounded-xl bg-tg-bg px-3 py-3 text-2xl font-bold tabular-nums
                    outline-none ring-1 ${
                      overBalance ? "ring-red-500/60" : "ring-tg-hint/20"
                    }`}
      />

      <div className="mt-2 flex gap-2">
        {chips.map(([label, value]) => (
          <button
            key={label}
            onClick={() => onChange(Math.round(value / 100) * 100)}
            className="flex-1 rounded-lg bg-tg-bg py-2 text-xs font-semibold text-tg-hint
                       ring-1 ring-tg-hint/15 active:bg-tg-hint/10"
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

function InsuranceToggle({
  quote,
  selected,
  onToggle,
}: {
  quote: SlipQuote;
  selected: boolean;
  onToggle: () => void;
}) {
  const { insurance, stake } = quote;
  const covered = insurance.covers_failed_legs;

  const premium = insurance.selected
    ? insurance.premium.minor
    : Math.round(Number(insurance.rate) * stake.minor);

  return (
    <button
      onClick={onToggle}
      aria-pressed={selected}
      className={`flex w-full items-start gap-3 rounded-xl px-3 py-3 text-start ring-1 ${
        selected
          ? "bg-tg-button/10 ring-tg-button/50"
          : "bg-tg-bg/60 ring-tg-hint/15"
      }`}
    >
      <span
        className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md ring-1 ${
          selected
            ? "bg-tg-button text-tg-button-text ring-tg-button"
            : "ring-tg-hint/40"
        }`}
        aria-hidden
      >
        {selected ? "✓" : ""}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold">
          {covered === 1
            ? fa.insuranceTitleOne(coins(stake.minor))
            : fa.insuranceTitleMany(count(covered), coins(stake.minor))}
        </span>
        <span className="mt-0.5 block text-xs leading-relaxed text-tg-hint">
          {fa.insuranceBody(coins(premium))}
        </span>
      </span>
    </button>
  );
}

function PayoutSummary({
  quote,
  quoting,
  stake,
  legCount,
  bonuses,
}: {
  quote: SlipQuote | null;
  quoting: boolean;
  stake: number;
  legCount: number;
  bonuses: string[];
}) {
  return (
    <dl className="space-y-1.5 rounded-xl bg-tg-bg/60 px-3 py-3 text-sm">
      <Row label={fa.stake} value={coins(stake)} />
      {quote?.insurance.selected ? (
        <Row label={fa.cover} value={coins(quote.insurance.premium.minor)} />
      ) : null}
      <Row
        label={fa.combinedOdds}
        value={quote ? odds(quote.combined_odds) : quoting ? "…" : "—"}
      />
      {/* The payout is the hero.
       *
       * It was a row in a list the same size as "stake" and "combined odds",
       * which is the arrangement of a receipt. The number a player is deciding
       * on is what they stand to win, so it gets the size, and the line
       * underneath restates it in their own figures — "your 1,000,000 becomes
       * 100,000,000" lands where a bare multiplier does not. */}
      <div className="border-t border-tg-hint/15 pt-2">
        <dt className="text-sm font-semibold">{fa.toWin}</dt>
        {/* Short form is the headline once the digits stop being readable, and
         *  keyed on the value so React remounts it and the animation replays.
         *
         *  A figure that changes silently is read as a label; one that moves
         *  is read as a consequence of the tap that caused it. That is the
         *  reason to animate it — feedback, not decoration.
         *
         * Past a few million nobody reads the figure — they count the groups
         * — so the scale word carries it, and the exact number moves to the
         * line below where it is still there for anyone who wants it. */}
        <dd
          key={quote?.potential_payout.minor ?? "none"}
          className="animate-payout text-3xl font-black leading-tight tabular-nums text-emerald-400"
        >
          {quote
            ? shortCoins(quote.potential_payout.minor)
            : quoting
              ? "…"
              : "—"}
        </dd>
        {quote ? (
          <p className="pt-0.5 text-[11px] text-tg-hint">
            {fa.stakeBecomes(coins(stake), coins(quote.potential_payout.minor))}
          </p>
        ) : null}
        {/* A price the reader already knows, doing the work the digits
         *  cannot. Phrased as a comparison and never as a thing being handed
         *  over — and the "not real money" line sits in this same panel. */}
        {quote && priceAnchor(quote.potential_payout.minor) ? (
          <p className="pt-1 text-xs font-bold text-emerald-300/90">
            {priceAnchor(quote.potential_payout.minor)}
          </p>
        ) : null}
      </div>
      {/* The golden key: a real extra multiplier for a longer slip.
       *
       * Rendered from the quote's own number rather than a table in the app,
       * so retuning the bonus server-side cannot leave this advertising a
       * percentage the payout does not contain. */}
      <GoldenKey
        bonus={quote?.parlay_bonus}
        legCount={legCount}
        bonuses={bonuses}
      />

      {quote?.uncapped ? (
        <p className="text-[11px] font-bold text-emerald-300">{fa.noCeiling}</p>
      ) : null}
      {quote?.capped ? (
        <p className="text-[11px] text-amber-300">
          {fa.cappedAt(coins(quote.payout_cap.minor))}
        </p>
      ) : null}
    </dl>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between">
      <dt className="text-tg-hint">{label}</dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  );
}

function ConfirmDiscard({
  legCount,
  onKeep,
  onDiscard,
  onHide,
}: {
  legCount: number;
  onKeep: () => void;
  onDiscard: () => void;
  onHide: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/60 px-4 pb-8">
      <div className="w-full max-w-sm rounded-2xl bg-tg-secondary-bg p-4">
        <p className="text-base font-semibold">{fa.discardTitle}</p>
        <p className="mt-1 text-sm text-tg-hint">
          {fa.discardBody(count(legCount))}
        </p>
        <div className="mt-4 space-y-2">
          <button
            onClick={onHide}
            className="w-full rounded-xl bg-tg-button py-3 text-sm font-semibold text-tg-button-text"
          >
            {fa.discardKeep}
          </button>
          <button
            onClick={onKeep}
            className="w-full rounded-xl py-2.5 text-sm text-tg-hint"
          >
            {fa.discardBack}
          </button>
          <button
            onClick={onDiscard}
            className="w-full rounded-xl py-2.5 text-sm text-red-400"
          >
            {fa.discardConfirm}
          </button>
        </div>
      </div>
    </div>
  );
}

function GoldenKey({
  bonus,
  legCount,
  bonuses,
}: {
  bonus: string | undefined;
  legCount: number;
  bonuses: string[];
}) {
  const value = Number(bonus ?? "1");
  const earned = Number.isFinite(value) && value > 1;
  const next = Number(bonuses[legCount] ?? "1");
  const nextIsBetter = legCount < MAX_LEGS && next > Math.max(value, 1);
  const nextLine = nextIsBetter ? (
    <span className="golden-key-next">
      {fa.goldenKeyNext(count(Math.round((next - 1) * 100)))}
    </span>
  ) : null;

  if (earned) {
    return (
      <p className="golden-key is-on">
        🔑 {fa.goldenKeyOn(count(Math.round((value - 1) * 100)))}
        {nextLine}
      </p>
    );
  }
  if (legCount > 0 && legCount < MAX_LEGS) {
    return (
      <p className="golden-key">
        🔑 {fa.goldenKeyLocked}
        {nextLine}
      </p>
    );
  }
  return null;
}
