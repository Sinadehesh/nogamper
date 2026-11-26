"use client";


import { useCallback, useEffect, useState } from "react";

import { getDiagnostics } from "@/lib/api";
import type { Diagnostics, JobRun } from "@/lib/types";

const TONE: Record<Diagnostics["layer"], "good" | "warn" | "bad"> = {
  healthy: "good",
  degraded: "warn",
  discovery: "bad",
  worker: "bad",
  upstream: "bad",
  cache: "bad",
  capacity: "bad",
};

const HEADLINE: Record<Diagnostics["layer"], string> = {
  healthy: "Everything is running",
  degraded: "Running, slightly behind",
  discovery: "No markets to price",
  worker: "The worker is the problem",
  upstream: "Polymarket is the problem",
  cache: "Redis is the problem",
  capacity: "Too many markets to price",
};

function minutes(seconds: number | null): string {
  if (seconds === null) return "never";
  if (seconds < 90) return `${Math.round(seconds)}s ago`;
  return `${Math.round(seconds / 60)}m ago`;
}

export function StatusBanner() {
  const [state, setState] = useState<Diagnostics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(true);
  const [expanded, setExpanded] = useState<boolean | null>(null);

  const load = useCallback(async () => {
    setChecking(true);
    const result = await getDiagnostics();
    if (result.ok) {
      setState(result.data);
      setError(null);
    } else {
      setError(result.detail);
    }
    setChecking(false);
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 60_000);
    return () => clearInterval(timer);
  }, [load]);

  if (error) {
    return <p className="admin-empty">{error}</p>;
  }
  if (!state) {
    return <p className="admin-empty">Checking…</p>;
  }

  const tone = TONE[state.layer];
  const open = expanded ?? tone === "bad";

  return (
    <section
      className={`status-banner is-${tone}${open ? " is-open" : ""}`}
      aria-live="polite"
    >
      <div className="status-head">
        <button
          type="button"
          className="status-title"
          aria-expanded={open}
          onClick={() => setExpanded(!open)}
        >
          <span className="status-dot" aria-hidden="true" />
          <h2>{HEADLINE[state.layer]}</h2>
          <span className="status-layer">{state.layer}</span>
          <span className="status-caret" aria-hidden="true">
            {open ? "▾" : "▸"}
          </span>
        </button>
        {open ? (
          <button type="button" onClick={() => void load()} disabled={checking}>
            {checking ? "Checking…" : "Check again"}
          </button>
        ) : null}
      </div>

      {!open ? null : (
        <>
          <p className="status-advice">{state.advice}</p>

          <JobRuns runs={state.runs} />

          <dl className="status-facts">
            <div>
              <dt>Last price</dt>
              <dd>{minutes(state.seconds_since_newest)}</dd>
            </div>
            <div>
              <dt>Markets priced</dt>
              <dd>
                {state.markets_fresh} of {state.markets_active}
                {/* The budget is shown only when it has been exceeded. On a
                healthy app it is a number nobody needs; on a broken one it is
                the whole diagnosis, because "0 of 7268" reads as a total
                outage until you know 7268 was never a supportable figure. */}
                {state.markets_active > state.markets_budget
                  ? ` · budget ${state.markets_budget}`
                  : ""}
                {state.markets_locked
                  ? ` · ${state.markets_locked} locked`
                  : ""}
              </dd>
            </div>
            <div>
              <dt>Cache</dt>
              <dd>
                {!state.cache_reachable
                  ? "unreachable"
                  : state.cache_sampled === 0
                    ? "nothing to check"
                    : `${state.cache_hits} of ${state.cache_sampled} sampled`}
              </dd>
            </div>
            <div>
              <dt>Jobs running</dt>
              <dd>
                {state.leases.length === 0
                  ? "none"
                  : state.leases
                      .map(
                        (j) =>
                          `${j.job_name} (${Math.round(j.held_for_seconds / 60)}m)`,
                      )
                      .join(", ")}
              </dd>
            </div>
          </dl>
        </>
      )}
    </section>
  );
}

function JobRuns({ runs }: { runs: JobRun[] }) {
  if (runs.length === 0) {
    return (
      <p className="status-runs-empty">
        No job has finished a run since this container started.
      </p>
    );
  }

  return (
    <ul className="status-runs">
      {runs.map((run) => (
        <li key={run.job_name} className={`is-${run.outcome}`}>
          <div className="status-run-head">
            <span className="status-run-name">{run.job_name}</span>
            <span className="admin-muted">
              {run.outcome} · {run.duration_seconds}s ·{" "}
              {ago(run.finished_ago_seconds)}
            </span>
          </div>
          <p className="status-run-detail">{summarise(run.detail)}</p>
        </li>
      ))}
    </ul>
  );
}

function ago(seconds: number): string {
  if (seconds < 90) return `${Math.round(seconds)}s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}

function summarise(detail: Record<string, unknown>): string {
  const parts: string[] = [];

  const reasons = detail.failure_reasons;
  if (
    reasons &&
    typeof reasons === "object" &&
    Object.keys(reasons).length > 0
  ) {
    parts.push(
      Object.entries(reasons as Record<string, number>)
        .map(([name, count]) => `${count}x ${name}`)
        .join(", "),
    );
  }
  if (typeof detail.error === "string") parts.push(detail.error);

  for (const [key, value] of Object.entries(detail)) {
    if (key === "failure_reasons" || key === "error" || key === "ran") continue;
    if (key === "duration_seconds") continue;
    if (typeof value === "number" && value !== 0)
      parts.push(`${key.replace(/_/g, " ")} ${value}`);
  }

  return parts.length > 0 ? parts.join(" · ") : "nothing to report";
}
