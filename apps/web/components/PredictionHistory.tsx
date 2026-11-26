"use client";


import { useCallback, useEffect, useState } from "react";

import { coins, count, odds, timeAgo, toPersianDigits } from "@/lib/format";
import { fa, translateError } from "@/lib/i18n";
import { getSlips } from "@/lib/api";
import type { LegStatus, Slip, SlipStatus } from "@/lib/types";

const FILTERS: { label: string; status?: SlipStatus }[] = [
  { label: fa.historyAll },
  { label: fa.historyOpen, status: "PENDING" },
  { label: fa.historyWon, status: "WON" },
  { label: fa.historyLost, status: "LOST" },
];

export function PredictionHistory({ refreshToken }: { refreshToken: number }) {
  const [filter, setFilter] = useState<SlipStatus | undefined>(undefined);
  const [slips, setSlips] = useState<Slip[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const result = await getSlips({ status: filter, limit: 25 });
    if (result.ok) {
      setSlips(result.data.slips);
      setError(null);
    } else {
      setError(translateError(result.code, result.detail));
    }
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load, refreshToken]);

  return (
    <section className="space-y-3">
      <div className="flex gap-2 overflow-x-auto pb-1">
        {FILTERS.map((entry) => (
          <button
            key={entry.label}
            onClick={() => setFilter(entry.status)}
            aria-pressed={filter === entry.status}
            className={`shrink-0 rounded-full px-3.5 py-1.5 text-xs font-semibold ring-1 ${
              filter === entry.status
                ? "bg-tg-button text-tg-button-text ring-tg-button"
                : "text-tg-hint ring-tg-hint/25"
            }`}
          >
            {entry.label}
          </button>
        ))}
      </div>

      {error ? (
        <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</p>
      ) : null}

      {slips === null ? (
        <p className="py-8 text-center text-sm text-tg-hint">{fa.loading}</p>
      ) : slips.length === 0 ? (
        <p className="py-8 text-center text-sm text-tg-hint">{fa.historyEmpty}</p>
      ) : (
        <ul className="space-y-3">
          {slips.map((slip) => (
            <li key={slip.id}>
              <SlipCard slip={slip} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const STATUS_STYLES: Record<SlipStatus, { label: string; chip: string }> = {
  PENDING: { label: fa.statusPending, chip: "bg-tg-hint/15 text-tg-hint" },
  WON: { label: fa.statusWon, chip: "bg-emerald-500/15 text-emerald-300" },
  LOST: { label: fa.statusLost, chip: "bg-rose-500/15 text-rose-300" },
  INSURED: { label: fa.statusInsured, chip: "bg-sky-500/15 text-sky-300" },
  VOID: { label: fa.statusVoid, chip: "bg-tg-hint/15 text-tg-hint" },
};

function SlipCard({ slip }: { slip: Slip }) {
  const won = slip.legs.filter((leg) => leg.status === "WON").length;
  const lost = slip.legs.filter((leg) => leg.status === "LOST").length;
  const style = STATUS_STYLES[slip.status];

  return (
    <article className="rounded-2xl bg-tg-secondary-bg p-3.5">
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold">
            {slip.legs.length === 1 ? fa.slipSingle : fa.slipParlay(count(slip.legs.length))}
          </p>
          <p className="mt-0.5 text-xs text-tg-hint">
            {fa.slipStakeAtOdds(coins(slip.stake.minor), odds(slip.combined_odds))} ·{" "}
            {timeAgo(slip.settled_at ?? slip.placed_at)}
          </p>
        </div>
        <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${style.chip}`}>
          {style.label}
        </span>
      </header>

      <ul className="mt-3 space-y-1.5">
        {slip.legs.map((leg) => (
          <LegRow key={leg.leg_index} question={leg.question} side={leg.side}
                  lockedOdds={leg.locked_odds} status={leg.status} />
        ))}
      </ul>

      <Outcome slip={slip} won={won} lost={lost} />
    </article>
  );
}

const LEG_MARK: Record<LegStatus, { mark: string; className: string }> = {
  WON: { mark: "✓", className: "text-emerald-400" },
  LOST: { mark: "✕", className: "text-rose-400" },
  VOID: { mark: "–", className: "text-tg-hint" },
  PENDING: { mark: "•", className: "text-tg-hint/60" },
};

function LegRow({
  question,
  side,
  lockedOdds,
  status,
}: {
  question: string;
  side: string;
  lockedOdds: string;
  status: LegStatus;
}) {
  const mark = LEG_MARK[status];
  return (
    <li className="flex items-start gap-2.5 text-xs">
      <span className={`mt-px w-3 shrink-0 text-center font-bold ${mark.className}`} aria-hidden>
        {mark.mark}
      </span>
      <span className={`min-w-0 flex-1 ${status === "LOST" ? "text-tg-hint" : ""}`}>
        <span className="line-clamp-2">{question}</span>
        <span className="mt-0.5 block text-tg-hint">
          {side === "YES" ? fa.sideYes : fa.sideNo} · {odds(lockedOdds)}
          <span className="sr-only"> — {STATUS_STYLES[status as SlipStatus]?.label ?? status}</span>
        </span>
      </span>
    </li>
  );
}

function Outcome({ slip, won, lost }: { slip: Slip; won: number; lost: number }) {
  if (slip.status === "PENDING") {
    return (
      <p className="mt-3 border-t border-tg-hint/15 pt-2.5 text-xs text-tg-hint">
        {fa.pendingProgress(
          count(won),
          count(slip.legs.length),
          coins(slip.potential_payout.minor),
        )}
      </p>
    );
  }

  if (slip.status === "WON") {
    return (
      <p className="mt-3 flex items-baseline justify-between border-t border-tg-hint/15 pt-2.5">
        <span className="text-xs text-tg-hint">{fa.paidOut}</span>
        <span className="text-base font-bold tabular-nums text-emerald-400">
          {coins(slip.settled_payout.minor)}
        </span>
      </p>
    );
  }

  if (slip.status === "INSURED") {
    return (
      <div className="mt-3 border-t border-tg-hint/15 pt-2.5">
        <p className="flex items-baseline justify-between">
          <span className="text-xs text-tg-hint">{fa.insuredHeadline}</span>
          <span className="text-base font-bold tabular-nums text-sky-300">
            {coins(slip.settled_payout.minor)}
          </span>
        </p>
        <p className="mt-1 text-[11px] text-tg-hint">
          {fa.insuredDetail(count(lost), coins(slip.insurance_premium.minor))}
        </p>
      </div>
    );
  }

  if (slip.status === "VOID") {
    return (
      <p className="mt-3 border-t border-tg-hint/15 pt-2.5 text-xs text-tg-hint">
        {slip.settlement_note ? toPersianDigits(slip.settlement_note) : fa.voidFallback}
      </p>
    );
  }

  return (
    <div className="mt-3 border-t border-tg-hint/15 pt-2.5">
      <p className="text-xs leading-relaxed text-tg-hint">
        {fa.lostSummary(count(won), count(slip.legs.length))}{" "}
        {slip.has_insurance
          ? lost === 1
            ? fa.lostInsuranceOne
            : fa.lostInsuranceMany
          : ""}
      </p>
      <p className="mt-1 flex items-baseline justify-between">
        <span className="text-xs text-tg-hint">{fa.stakeLost}</span>
        <span className="text-sm font-semibold tabular-nums text-tg-hint">
          {coins(slip.total_cost.minor)}
        </span>
      </p>
    </div>
  );
}
