"use client";

import { useCallback, useEffect, useState } from "react";

import { getDiagnostics } from "@/lib/api";
import { t } from "@/lib/copy";
import { timeAgo } from "@/lib/format";
import type { Diagnostics } from "@/lib/types";

/**
 * Whether the markets are updating, at the top of every admin page.
 *
 * Not behind its own route: a separate status page gets opened only by
 * somebody who already suspects a problem, which is the wrong time to find
 * out. Collapsed to one line while things are fine, open when they are not.
 */
export function StatusBanner() {
  const [report, setReport] = useState<Diagnostics | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    const result = await getDiagnostics();
    setBusy(false);
    if (result.ok) {
      setReport(result.data);
      // Opens itself when something is wrong; never closes itself, so a
      // refresh does not snatch away what the operator was reading.
      if (result.data.layer !== "healthy") setOpen(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (!report) return null;

  const healthy = report.layer === "healthy";
  // Amber for "degraded", not red: a pass truncating under load is the system
  // doing what it was built to do, and colouring it as an outage would teach
  // the operator to ignore the banner.
  const tone = healthy ? "notice-ok" : report.layer === "degraded" ? "notice-warn" : "notice-error";

  return (
    <section className={`notice ${tone} !text-ink`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="font-bold">
          {healthy ? t.statusTitleHealthy : t.statusTitleProblem}
          <span className="chip ms-2 uppercase">{report.layer}</span>
        </p>
        <span className="flex gap-2">
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setOpen(!open)}>
            {open ? t.statusHide : t.statusShow}
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => void load()}
            disabled={busy}
          >
            {busy ? t.statusRefreshing : t.statusRefresh}
          </button>
        </span>
      </div>

      {open ? (
        <>
          <p className="mt-3 max-w-3xl text-sm">{report.advice}</p>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
            <Fact label={t.statusMarkets} value={String(report.markets_active)} />
            <Fact label={t.statusFresh} value={String(report.markets_fresh)} />
            <Fact label={t.statusStale} value={String(report.markets_stale)} />
            <Fact
              label={t.statusNewest}
              value={report.newest_price_at ? timeAgo(report.newest_price_at) : "—"}
            />
            <Fact
              label={t.statusCache}
              value={report.cache_reachable ? t.statusCacheOk : t.statusCacheDown}
            />
          </dl>

          <h3 className="mt-4 text-sm font-bold">{t.statusRuns}</h3>
          {report.runs.length === 0 ? (
            <p className="text-sm text-muted">{t.statusNoRuns}</p>
          ) : (
            <ul className="mt-1 space-y-1 text-sm">
              {report.runs.map((run) => (
                <li key={run.job_name} className="tabular-nums">
                  <span className="font-mono font-semibold">{run.job_name}</span>{" "}
                  <span className={run.outcome === "ok" ? "text-muted" : "font-semibold text-danger"}>
                    {t.statusRunLine(
                      run.outcome,
                      run.duration_seconds,
                      timeAgo(
                        new Date(Date.now() - run.finished_ago_seconds * 1000).toISOString(),
                      ),
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : null}
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="font-semibold tabular-nums">{value}</dd>
    </div>
  );
}
