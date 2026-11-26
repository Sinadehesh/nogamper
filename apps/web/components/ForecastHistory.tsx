"use client";

import { useCallback, useEffect, useState } from "react";

import { usePlayer } from "@/components/PlayerProvider";
import { getSlips } from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { odds, points, timeAgo } from "@/lib/format";
import type { LegStatus, Slip, SlipStatus } from "@/lib/types";

const FILTERS: { label: string; status?: SlipStatus }[] = [
  { label: t.historyAll },
  { label: t.historyOpen, status: "PENDING" },
  { label: t.historyWon, status: "WON" },
  { label: t.historyLost, status: "LOST" },
];

const STATUS: Record<SlipStatus, { label: string; tone: string }> = {
  PENDING: { label: t.statusPending, tone: "text-muted" },
  WON: { label: t.statusWon, tone: "text-yes" },
  LOST: { label: t.statusLost, tone: "text-no" },
  INSURED: { label: t.statusInsured, tone: "text-muted" },
  VOID: { label: t.statusVoid, tone: "text-muted" },
};

const LEG_MARK: Record<LegStatus, { mark: string; tone: string; label: string }> = {
  WON: { mark: "✓", tone: "text-yes", label: t.statusWon },
  LOST: { mark: "✕", tone: "text-no", label: t.statusLost },
  VOID: { mark: "–", tone: "text-muted", label: t.statusVoid },
  PENDING: { mark: "•", tone: "text-muted", label: t.statusPending },
};

export function ForecastHistory({ refreshToken }: { refreshToken: number }) {
  const { refresh } = usePlayer();
  const [filter, setFilter] = useState<SlipStatus | undefined>(undefined);
  const [slips, setSlips] = useState<Slip[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const result = await getSlips({ status: filter, limit: 20 });
    if (result.ok) {
      setSlips(result.data.slips);
      setCursor(result.data.next_cursor);
      setError(null);
    } else {
      if (result.status === 401) void refresh();
      setError(errorMessage(result.code));
    }
  }, [filter, refresh]);

  useEffect(() => {
    void load();
  }, [load, refreshToken]);

  const loadMore = useCallback(async () => {
    if (!cursor) return;
    const result = await getSlips({ status: filter, limit: 20, cursor });
    if (!result.ok) {
      setError(errorMessage(result.code));
      return;
    }
    setSlips((current) => [...(current ?? []), ...result.data.slips]);
    setCursor(result.data.next_cursor);
  }, [cursor, filter]);

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap gap-1.5" role="group" aria-label={t.tabHistory}>
        {FILTERS.map((entry) => (
          <button
            key={entry.label}
            type="button"
            onClick={() => setFilter(entry.status)}
            aria-pressed={filter === entry.status}
            className={`rounded-full border px-3 py-1.5 text-sm font-semibold ${
              filter === entry.status
                ? "border-accent bg-accent text-on-accent"
                : "border-line bg-surface text-muted hover:text-ink"
            }`}
          >
            {entry.label}
          </button>
        ))}
      </div>

      {error ? (
        <p role="alert" className="notice notice-error">
          {error}
        </p>
      ) : null}

      {slips === null ? (
        error ? null : <p className="py-10 text-center text-muted">{t.loading}</p>
      ) : slips.length === 0 ? (
        <p className="py-10 text-center text-muted">{t.historyEmpty}</p>
      ) : (
        <>
          <ul className="grid gap-3 md:grid-cols-2">
            {slips.map((slip) => (
              <li key={slip.id}>
                <SlipCard slip={slip} />
              </li>
            ))}
          </ul>
          {cursor ? (
            <div className="flex justify-center">
              <button type="button" className="btn btn-secondary" onClick={() => void loadMore()}>
                {t.loadMore}
              </button>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}

function SlipCard({ slip }: { slip: Slip }) {
  const status = STATUS[slip.status];
  const right = slip.legs.filter((leg) => leg.status === "WON").length;
  const decided = slip.legs.filter((leg) => leg.status !== "PENDING").length;

  return (
    <article className="card h-full p-4">
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold">
            {slip.legs.length === 1 ? t.slipSingle : t.slipCombo(slip.legs.length)}
          </p>
          <p className="mt-0.5 text-xs text-muted tabular-nums">
            {t.slipStakeAtOdds(points(slip.stake.minor), odds(slip.combined_odds))} ·{" "}
            {timeAgo(slip.settled_at ?? slip.placed_at)}
          </p>
        </div>
        <span className={`chip ${status.tone}`}>{status.label}</span>
      </header>

      <ul className="mt-3 space-y-2">
        {slip.legs.map((leg) => {
          const mark = LEG_MARK[leg.status];
          return (
            <li key={leg.leg_index} className="flex items-start gap-2 text-sm">
              <span className={`w-4 shrink-0 text-center font-bold ${mark.tone}`} aria-hidden>
                {mark.mark}
              </span>
              <span className="min-w-0 flex-1">
                <span className="line-clamp-2">{leg.question}</span>
                <span className="mt-0.5 block text-xs text-muted tabular-nums">
                  {leg.side === "YES" ? t.yes : t.no} · {odds(leg.locked_odds)}
                  {leg.resolution && leg.resolution !== "VOID"
                    ? ` · ${t.resolvedAs(leg.resolution === "YES" ? t.yes : t.no)}`
                    : null}
                  <span className="sr-only"> — {mark.label}</span>
                </span>
              </span>
            </li>
          );
        })}
      </ul>

      <Outcome slip={slip} right={right} decided={decided} />
    </article>
  );
}

function Outcome({ slip, right, decided }: { slip: Slip; right: number; decided: number }) {
  const line = "mt-3 border-t border-line pt-3 text-sm";

  if (slip.status === "PENDING") {
    return (
      <p className={`${line} text-muted`}>
        {t.pendingProgress(decided, slip.legs.length, points(slip.potential_payout.minor))}
      </p>
    );
  }

  if (slip.status === "WON") {
    return (
      <p className={`${line} flex items-baseline justify-between`}>
        <span className="text-muted">{t.paidOut}</span>
        <span className="text-lg font-bold tabular-nums text-yes">
          {points(slip.settled_payout.minor)} {t.pts}
        </span>
      </p>
    );
  }

  if (slip.status === "VOID" || slip.status === "INSURED") {
    return (
      <p className={`${line} text-muted`}>
        {slip.status === "VOID" ? t.voidNote : t.insuredNote}
      </p>
    );
  }

  return (
    <div className={line}>
      <p className="text-muted">{t.lostSummary(right, slip.legs.length)}</p>
      <p className="mt-1 flex items-baseline justify-between">
        <span className="text-muted">{t.stakeLost}</span>
        <span className="font-semibold tabular-nums">
          {points(slip.total_cost.minor)} {t.pts}
        </span>
      </p>
    </div>
  );
}
