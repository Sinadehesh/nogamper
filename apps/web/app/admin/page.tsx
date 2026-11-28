"use client";

import { useEffect, useState } from "react";

import { getOverview } from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { count, date, points, signedPoints, timeAgo } from "@/lib/format";
import type { Overview } from "@/lib/types";

const WINDOWS = [7, 30, 90] as const;

export default function AdminOverviewPage() {
  const [days, setDays] = useState<number>(30);
  const [report, setReport] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getOverview(days).then((result) => {
      if (cancelled) return;
      if (result.ok) {
        setReport(result.data);
        setError(null);
      } else {
        setError(result.status === 404 ? t.adminDenied : errorMessage(result.code));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [days]);

  if (error) {
    return (
      <p role="alert" className="notice notice-error">
        {error}
      </p>
    );
  }
  if (!report) return <p className="text-muted">{t.loading}</p>;

  const { players, forecasts, points: flow, safer_play: safer } = report;
  const busiest = Math.max(1, ...report.daily.map((day) => day.forecasts));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-black tracking-tight">{t.adminOverview}</h1>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-muted">{t.adminGenerated(timeAgo(report.generated_at))}</span>
          <span className="flex gap-1" role="group">
            {WINDOWS.map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={days === option}
                className={`btn btn-sm ${days === option ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setDays(option)}
              >
                {t.adminWindow(option)}
              </button>
            ))}
          </span>
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <Tile label={t.adminPlayersTotal} value={count(players.total)}
              note={`${t.adminRegistered}: ${count(players.registered)} · ${t.adminGuests}: ${count(players.guests)}`} />
        <Tile label={t.adminNew} value={count(players.new_in_window)} />
        <Tile label={t.adminForecasters} value={count(players.forecast_in_window)}
              note={`${t.adminClaimed}: ${count(players.claimed_in_window)}`} />
        <Tile label={t.adminForecastsPlaced} value={count(forecasts.placed)} />
        <Tile label={t.adminForecastsRight} value={`${count(forecasts.won)} / ${count(forecasts.settled)}`} />
        <Tile label={t.adminForecastsOpen} value={count(forecasts.open)} />
      </dl>

      <section className="grid items-start gap-5 lg:grid-cols-2">
        <article className="card p-5">
          <h2 className="text-lg font-bold">{t.adminPointsTitle}</h2>
          <p className="mt-1 text-sm text-muted">{t.adminPointsNote}</p>
          <table className="table mt-3">
            <tbody>
              <FlowRow label={t.adminGranted} value={points(flow.granted.minor)} />
              <FlowRow label={t.adminBought} value={points(flow.bought.minor)} />
              <FlowRow label={t.adminStaked} value={points(flow.staked.minor)} />
              <FlowRow label={t.adminReturned} value={points(flow.returned.minor)} />
              <FlowRow label={t.adminAdjusted} value={signedPoints(flow.adjusted.minor)} />
              <FlowRow label={t.adminNetChange} value={signedPoints(flow.net_change.minor)} strong />
            </tbody>
          </table>
        </article>

        <article className="card p-5">
          <h2 className="text-lg font-bold">{t.adminSaferTitle}</h2>
          <dl className="mt-3 grid grid-cols-3 gap-3">
            <Tile label={t.adminWithLimit} value={count(safer.with_daily_limit)} flat />
            <Tile label={t.adminOnBreak} value={count(safer.on_break)} flat />
            <Tile label={t.adminErased} value={count(safer.erased)} flat />
          </dl>
        </article>
      </section>

      <article className="card overflow-x-auto p-5">
        <h2 className="text-lg font-bold">{t.adminDailyTitle}</h2>
        <table className="table mt-3">
          <thead>
            <tr>
              <th scope="col">{t.adminDay}</th>
              <th scope="col" className="num">{t.adminDayNew}</th>
              <th scope="col" className="num">{t.adminDayForecasters}</th>
              <th scope="col">{t.adminDayForecasts}</th>
            </tr>
          </thead>
          <tbody>
            {[...report.daily].reverse().map((day) => (
              <tr key={day.day}>
                <td className="whitespace-nowrap">{date(day.day)}</td>
                <td className="num">{count(day.new_players)}</td>
                <td className="num">{count(day.forecasters)}</td>
                <td>
                  <span className="flex items-center gap-3">
                    <span className="rd-admin-fig w-10">{count(day.forecasts)}</span>
                    <span className="h-2 flex-1 rounded-full bg-sunken" aria-hidden>
                      <span
                        className="block h-full rounded-full bg-accent"
                        style={{ width: `${(day.forecasts / busiest) * 100}%` }}
                      />
                    </span>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>

      <article className="card overflow-x-auto p-5">
        <h2 className="text-lg font-bold">{t.adminLedgerTitle}</h2>
        <table className="table mt-3">
          <thead>
            <tr>
              <th scope="col">{t.adminEntryType}</th>
              <th scope="col" className="num">{t.adminEntries}</th>
              <th scope="col" className="num">{t.adminPlayers}</th>
              <th scope="col" className="num">{t.adminNet}</th>
            </tr>
          </thead>
          <tbody>
            {report.ledger.map((row) => (
              <tr key={row.entry_type}>
                <td className="font-mono text-xs">{row.entry_type}</td>
                <td className="num">{count(row.entries)}</td>
                <td className="num">{count(row.players)}</td>
                <td className="num">{signedPoints(row.net.minor)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </div>
  );
}

function Tile({
  label,
  value,
  note,
  flat = false,
}: {
  label: string;
  value: string;
  note?: string;
  flat?: boolean;
}) {
  return (
    <div className={flat ? "" : "card p-4"}>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="text-2xl font-bold">{value}</dd>
      {note ? <dd className="mt-0.5 text-xs text-muted">{note}</dd> : null}
    </div>
  );
}

function FlowRow({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return (
    <tr className={strong ? "font-bold" : ""}>
      <td>{label}</td>
      <td className="num">{value}</td>
    </tr>
  );
}
