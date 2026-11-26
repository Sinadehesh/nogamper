"use client";


import { useEffect, useState } from "react";

import { coins, count, timeAgo } from "@/lib/format";
import { fa } from "@/lib/i18n";
import { getActivity } from "@/lib/api";
import type { ActivityEntry } from "@/lib/types";

export function ActivityTicker({ includeLosses = false }: { includeLosses?: boolean }) {
  const [entries, setEntries] = useState<ActivityEntry[]>([]);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      getActivity(12, includeLosses).then((result) => {
        if (!cancelled && result.ok) setEntries(result.data.entries);
      });

    void load();
    const timer = setInterval(load, 60_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [includeLosses]);

  if (entries.length === 0) return null;

  return (
    <section aria-label="Recent results" className="-mx-4">
      <ul className="flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none]">
        {entries.map((entry) => (
          <li
            key={entry.id}
            className="shrink-0 rounded-full bg-tg-secondary-bg px-3 py-1.5 text-[11px]"
          >
            <span className="font-semibold">{entry.player}</span>
            <span className="text-tg-hint">
              {" "}
              {entry.status === "WON"
                ? fa.activityWon
                : entry.status === "INSURED"
                  ? fa.activityRefunded
                  : fa.activityLost}{" "}
            </span>
            <span
              className={
                entry.status === "LOST"
                  ? "font-semibold tabular-nums text-tg-hint"
                  : "font-semibold tabular-nums text-emerald-400"
              }
            >
              {coins(entry.status === "LOST" ? entry.stake.minor : entry.payout.minor)}
            </span>
            <span className="text-tg-hint">
              {" "}
              {fa.activityOn(count(entry.leg_count))} · {timeAgo(entry.settled_at)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
