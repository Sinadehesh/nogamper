"use client";

import { useSlip } from "@/components/SlipProvider";
import { categoryLabel, t } from "@/lib/copy";
import { chancePair, odds, percentValue, timeUntil } from "@/lib/format";
import { fairOdds, isPriceable, probabilityOf } from "@/lib/odds";
import type { MarketRules, MarketSummary, Side } from "@/lib/types";

/**
 * One question.
 *
 * The percentage leads and the payout follows, in that order and at those
 * sizes on purpose. On a betting slip the big number is what you could win;
 * here it is how likely the thing is, which is the number that is actually
 * true.
 */
export function MarketCard({
  market,
  rules,
  paused,
}: {
  market: MarketSummary;
  rules: MarketRules;
  /** The player is on a break: show everything, offer nothing. */
  paused: boolean;
}) {
  const slip = useSlip();
  const blocked = slip.blockedBecause(market);
  const remaining = timeUntil(market.lock_at);
  const settled =
    !isPriceable(market, "YES", rules) || !isPriceable(market, "NO", rules);

  return (
    <article className="card flex h-full flex-col p-4">
      <header>
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
          <span className="chip">{categoryLabel(market.category)}</span>
          <span>{remaining ? t.closesIn(remaining) : t.closed}</span>
          {market.probability.stale ? <span>· {t.priceUpdating}</span> : null}
        </p>
        <h3 className="mt-2 text-base font-semibold leading-snug">{market.question}</h3>
        {market.event.title && market.event.title !== market.question ? (
          <p className="mt-1 line-clamp-1 text-xs text-muted">{market.event.title}</p>
        ) : null}
      </header>

      <ChanceBar market={market} />

      <div className="mt-auto grid grid-cols-2 gap-2 pt-3">
        {(["YES", "NO"] as const).map((side) => (
          <SideButton
            key={side}
            market={market}
            side={side}
            selected={slip.has(market.id, side)}
            priceable={isPriceable(market, side, rules)}
            disabled={
              paused || market.probability.stale || (Boolean(blocked) && !slip.has(market.id, side))
            }
            onPick={() => slip.toggle(market, side)}
          />
        ))}
      </div>

      {settled ? (
        <p className="mt-2 text-xs text-muted">{t.settledAlreadyHint}</p>
      ) : blocked ? (
        <p className="mt-2 text-xs text-warn">{blocked}</p>
      ) : null}
    </article>
  );
}

function ChanceBar({ market }: { market: MarketSummary }) {
  const yes = percentValue(market.probability.yes);

  return (
    <div className="mt-3">
      <p className="mb-1 text-[0.7rem] font-semibold uppercase tracking-wide text-muted">
        {t.marketSays}
      </p>
      <div
        className="flex h-2 overflow-hidden rounded-full bg-no/25"
        role="img"
        aria-label={t.chanceSplit(
          chancePair(market.probability.yes).yes,
          chancePair(market.probability.yes).no,
        )}
      >
        <span className="animate-bar-in block h-full bg-yes" style={{ width: `${yes}%` }} />
      </div>
    </div>
  );
}

function SideButton({
  market,
  side,
  selected,
  priceable,
  disabled,
  onPick,
}: {
  market: MarketSummary;
  side: Side;
  selected: boolean;
  priceable: boolean;
  disabled: boolean;
  onPick: () => void;
}) {
  const yes = side === "YES";
  const probability = probabilityOf(market, side);
  const shown = chancePair(market.probability.yes)[yes ? "yes" : "no"];
  const label = yes ? t.yes : t.no;
  const tone = yes ? "text-yes" : "text-no";

  return (
    <button
      type="button"
      onClick={onPick}
      disabled={disabled || !priceable}
      aria-pressed={selected}
      aria-label={selected ? t.pickRemove : t.pickAdd(label)}
      className={`rounded-xl border px-3 py-2.5 text-left transition-colors
                  disabled:cursor-not-allowed disabled:opacity-45 ${
                    selected
                      ? yes
                        ? "border-yes bg-yes/12"
                        : "border-no bg-no/12"
                      : "border-line bg-bg hover:border-muted"
                  }`}
    >
      <span className="flex items-center justify-between text-xs font-bold">
        <span className={tone}>{label}</span>
        {selected ? (
          <span className={tone} aria-hidden>
            ✓
          </span>
        ) : null}
      </span>
      <span className={`mt-0.5 block text-2xl font-black leading-tight tabular-nums ${tone}`}>
        {shown}
      </span>
      <span className="mt-0.5 block text-xs text-muted">
        {priceable ? t.pays(odds(fairOdds(probability))) : t.settledAlready}
      </span>
    </button>
  );
}
