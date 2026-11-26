"use client";


import { useEffect, useRef, useState } from "react";

import {
  closesIn,
  isClosingSoon,
  odds,
  oddsValue,
  percent,
  percentValue,
} from "@/lib/format";
import { categoryLabel, fa } from "@/lib/i18n";
import { useBetSlip } from "@/components/BetSlipProvider";
import { lockedOdds } from "@/lib/parlay";
import type { MarketSummary, Side } from "@/lib/types";

const FALLBACK_VIG = 0.05;

export function MarketCard({
  market,
  vigRate = FALLBACK_VIG,
}: {
  market: MarketSummary;
  vigRate?: number;
}) {
  const slip = useBetSlip();
  const blocked = slip.blockedBecause(market);
  const boosted = market.boosts.length > 0;
  const remaining = closesIn(market.lock_at);
  const urgent = isClosingSoon(market.lock_at);

  return (
    <article
      className={`relative rounded-2xl bg-tg-secondary-bg p-3.5 ring-1 transition-shadow ${
        boosted ? "ring-boost/35" : "ring-white/5"
      }`}
    >
      {boosted ? <BoostRibbon /> : null}

      <header>
        <p className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-tg-hint">
          <span className="font-semibold text-tg-text/70">
            {categoryLabel(market.category)}
          </span>
          <span aria-hidden>·</span>
          <span className="min-w-0 truncate">{market.event.title}</span>
        </p>

        <h3 className="mt-1 text-sm font-semibold leading-snug">
          {market.question}
        </h3>

        <p
          className={`mt-1.5 flex items-center gap-1.5 text-[11px] ${
            urgent ? "font-semibold text-urgent" : "text-tg-hint"
          }`}
        >
          {urgent ? (
            <span className="animate-urgent inline-block size-1.5 rounded-full bg-urgent" />
          ) : null}
          <span>{remaining ? fa.closesIn(remaining) : fa.closed}</span>
          {market.probability.stale ? (
            <span className="text-tg-hint">· {fa.priceUpdating}</span>
          ) : null}
        </p>
      </header>

      <ChanceBar market={market} />

      <div className="mt-2.5 grid grid-cols-2 gap-2">
        {(["YES", "NO"] as const).map((side) => (
          <SideButton
            key={side}
            market={market}
            side={side}
            selected={slip.has(market.id, side)}
            disabled={Boolean(blocked) && !slip.has(market.id, side)}
            vigRate={vigRate}
            onPick={() => slip.add(market, side)}
          />
        ))}
      </div>

      {blocked ? (
        <p className="mt-2 text-[11px] text-amber-300">{blocked}</p>
      ) : null}
    </article>
  );
}

function ChanceBar({ market }: { market: MarketSummary }) {
  const yes = percentValue(market.probability.yes);
  const no = percentValue(market.probability.no, 100 - yes);

  return (
    <div className="mt-3">
      <div className="mb-1 flex items-center justify-between text-[10px] text-tg-hint">
        <span className="font-medium uppercase tracking-wide">
          {fa.marketSays}
        </span>
      </div>

      <div
        className="flex h-2 gap-1"
        role="img"
        aria-label={fa.chanceSplit(
          percent(market.probability.yes),
          percent(market.probability.no),
        )}
      >
        <span
          className="animate-fill-in block h-full rounded-full bg-yes"
          style={{ width: `${yes}%` }}
        />
        <span
          className="animate-fill-in block h-full rounded-full bg-no"
          style={{ width: `${no}%` }}
        />
      </div>
    </div>
  );
}

function SideButton({
  market,
  side,
  selected,
  disabled,
  vigRate,
  onPick,
}: {
  market: MarketSummary;
  side: Side;
  selected: boolean;
  disabled: boolean;
  vigRate: number;
  onPick: () => void;
}) {
  const boost = market.boosts.find((entry) => entry.side === side);
  const base = lockedOdds(market, side, vigRate, { withBoost: false }).toFixed(
    6,
  );
  const boostedOdds = boost
    ? lockedOdds(market, side, vigRate).toFixed(6)
    : null;
  const probability =
    side === "YES" ? market.probability.yes : market.probability.no;
  const yes = side === "YES";

  const pop = usePickFeedback(selected);

  return (
    <button
      onClick={onPick}
      disabled={disabled}
      aria-pressed={selected}
      className={`${pop} rounded-xl px-3 py-2.5 text-start ring-1 transition
                  duration-150 active:scale-[0.97] disabled:opacity-35 disabled:active:scale-100 ${
                    selected
                      ? yes
                        ? "bg-yes/20 ring-2 ring-yes"
                        : "bg-no/20 ring-2 ring-no"
                      : yes
                        ? "bg-yes/[0.07] ring-yes/25"
                        : "bg-no/[0.07] ring-no/25"
                  }`}
    >
      <span className="flex items-center justify-between">
        <span className={`text-xs font-bold ${yes ? "text-yes" : "text-no"}`}>
          {yes ? fa.sideYes : fa.sideNo}
        </span>
        {selected ? (
          <span
            className={`text-[13px] leading-none ${yes ? "text-yes" : "text-no"}`}
          >
            ✓
          </span>
        ) : null}
      </span>

      {/* The number the whole card exists to show. */}
      <span
        className={`mt-0.5 block text-2xl font-black leading-tight tabular-nums ${
          yes ? "text-yes" : "text-no"
        }`}
      >
        {percent(probability)}
      </span>
      <span className="block text-[10px] leading-none text-tg-hint">
        {fa.chance}
      </span>

      {/* Boosted: the promoted number leads, the ordinary one follows struck
          through. Both are real — the struck figure is what this market pays
          without the promotion — so leading with the boost is emphasis, not
          a reference price invented to flatter the offer. */}
      <span className="mt-2 flex items-baseline gap-1 border-t border-white/5 pt-1.5">
        <span className="text-[10px] text-tg-hint">{fa.oddsLabel}</span>
        {boostedOdds ? (
          <>
            <span className="text-sm font-bold text-boost">
              {odds(boostedOdds)}
            </span>
            <span className="text-[11px] text-tg-hint/70 line-through">
              {oddsValue(base)}
            </span>
          </>
        ) : (
          <span className="text-sm font-bold">{odds(base)}</span>
        )}
      </span>

      {boost ? (
        <span className="mt-1 block text-[10px] font-semibold text-boost">
          ⚡ {fa.boosted} · {fa.boostEndsIn(closesIn(boost.ends_at))}
        </span>
      ) : null}
    </button>
  );
}

function usePickFeedback(selected: boolean): string {
  const [key, setKey] = useState(0);
  const previous = useRef(selected);

  useEffect(() => {
    if (selected && !previous.current) setKey((value) => value + 1);
    previous.current = selected;
  }, [selected]);

  return key > 0 && selected ? "animate-pick" : "";
}

function BoostRibbon() {
  return (
    <span
      className="absolute -top-2 start-3 flex items-center gap-1 rounded-full bg-boost
                 px-2 py-0.5 text-[10px] font-bold text-black shadow-sm"
    >
      <span className="animate-boost" aria-hidden>
        ⚡
      </span>
      {fa.boosted}
    </span>
  );
}
