"use client";


import { useCallback, useEffect, useState } from "react";

import { AdminNav } from "@/components/AdminNav";
import { StatusBanner } from "@/components/StatusBanner";
import { TelegramGate } from "@/components/TelegramGate";
import { getEconomyReport } from "@/lib/api";
import type { BreakEvenBucket, EconomyReport, RevenueDay } from "@/lib/types";

const DEFAULT_USD_PER_STAR = 0.013;

const WINDOWS = [7, 30, 90] as const;

export default function AdminPage() {
  return (
    <TelegramGate>
      <Economy />
    </TelegramGate>
  );
}

function Economy() {
  const [days, setDays] = useState<number>(30);
  const [rate, setRate] = useState<number>(DEFAULT_USD_PER_STAR);
  const [report, setReport] = useState<EconomyReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (windowDays: number) => {
    setLoading(true);
    const result = await getEconomyReport(windowDays);
    if (result.ok) {
      setReport(result.data);
      setError(null);
    } else {
      setError(
        result.status === 404
          ? "This page is not available for your account."
          : result.detail,
      );
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load(days);
  }, [days, load]);

  if (error) {
    return (
      <main className="admin-shell">
        <AdminNav />
        <p className="admin-empty">{error}</p>
      </main>
    );
  }

  if (!report) {
    return (
      <main className="admin-shell">
        <AdminNav />
        <p className="admin-empty">Loading…</p>
      </main>
    );
  }

  const usd = (stars: number) => stars * rate;

  return (
    <main className="admin-shell" style={{ opacity: loading ? 0.6 : 1 }}>
      <AdminNav />

      <header className="admin-head">
        <div>
          <h1 className="admin-title">Economy</h1>
          <p className="admin-sub">
            Last {report.window_days} days · generated{" "}
            {new Date(report.generated_at).toLocaleString()}
          </p>
        </div>

        <div className="admin-controls">
          <div
            className="admin-segmented"
            role="group"
            aria-label="Time window"
          >
            {WINDOWS.map((w) => (
              <button
                key={w}
                type="button"
                onClick={() => setDays(w)}
                aria-pressed={days === w}
                className={days === w ? "is-on" : ""}
              >
                {w}d
              </button>
            ))}
          </div>

          <label className="admin-rate">
            <span>USD / Star</span>
            <input
              type="number"
              step="0.001"
              min="0"
              value={rate}
              onChange={(e) => setRate(Number(e.target.value) || 0)}
            />
          </label>
        </div>
      </header>

      <StatusBanner />

      <section className="admin-tiles">
        <Tile
          label={`Stars, net · ${report.window_days}d`}
          value={report.revenue.stars_net.toLocaleString()}
          note={`≈ $${usd(report.revenue.stars_net).toFixed(2)} at your rate`}
          emphasis
        />
        <Tile
          label="Per day"
          value={report.stars_per_day.toLocaleString()}
          note={`≈ $${usd(report.stars_per_day).toFixed(2)}/day`}
        />
        <Tile
          label="Paying players"
          value={report.revenue.paying_players.toLocaleString()}
          note={`${(report.players.conversion_rate * 100).toFixed(1)}% of players who bet`}
        />
        <Tile
          label="Per paying player"
          value={report.stars_per_paying_player.toLocaleString()}
          note={`≈ $${usd(report.stars_per_paying_player).toFixed(2)} ARPPU`}
        />
        <Tile
          label="Lifetime, net"
          value={report.lifetime.stars_net.toLocaleString()}
          note={
            report.lifetime.stars_refunded > 0
              ? `${report.lifetime.stars_refunded.toLocaleString()} refunded`
              : "no refunds yet"
          }
        />
        <Tile
          label="Refunds"
          value={report.revenue.refunds.toLocaleString()}
          note={`${report.revenue.stars_refunded.toLocaleString()} Stars given back`}
          warn={
            report.revenue.stars_refunded > report.revenue.stars_gross * 0.1
          }
        />
      </section>

      <BreakEven report={report} />

      <section className="admin-panel">
        <h2>Stars per day</h2>
        <p className="admin-note">
          Every day in the window has a bar, including the empty ones — a chart
          that drops dead days draws a straight line through them.
        </p>
        <StarsChart days={report.daily} rate={rate} />
      </section>

      <div className="admin-split">
        <section className="admin-panel">
          <h2>Where coins come from and go</h2>
          <p className="admin-note">
            The vig has no ledger entry of its own — it is priced into the odds,
            so it exists only as the gap between stakes and payouts. That gap is
            the house edge below, and it is the engine of the whole model.
          </p>
          <table className="admin-table">
            <tbody>
              <Row
                label="Sold for Stars"
                money={report.balance.minted_purchased}
              />
              <Row label="Given away free" money={report.balance.minted_free} />
              <Row
                label="House edge (the vig)"
                money={report.balance.house_edge}
                good
              />
              <Row
                label="Decayed from idle accounts"
                money={report.balance.decayed}
              />
              <Row
                label="Burned on rewards"
                money={report.balance.burned_on_rewards}
              />
              <Row
                label="Net change in circulation"
                money={report.balance.net_change}
                strong
              />
            </tbody>
          </table>
        </section>

        <section className="admin-panel">
          <h2>Which pack sells</h2>
          <p className="admin-note">
            Coins per Star is usually the reason one tier outsells another, so
            it sits beside the sales rather than a table away.
          </p>
          <table className="admin-table">
            <thead>
              <tr>
                <th>Pack</th>
                <th>Stars</th>
                <th>Coins/★</th>
                <th>Sold</th>
                <th>Share</th>
              </tr>
            </thead>
            <tbody>
              {report.packages.map((pack) => (
                <tr key={pack.code}>
                  <td>{pack.code}</td>
                  <td className="num">{pack.stars_price}</td>
                  <td className="num">{pack.coins_per_star}</td>
                  <td className="num">{pack.purchases}</td>
                  <td className="num">
                    {(pack.share_of_stars * 100).toFixed(0)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      <section className="admin-panel">
        <h2>Players</h2>
        <table className="admin-table">
          <tbody>
            <tr>
              <td>Registered</td>
              <td className="num">{report.players.total.toLocaleString()}</td>
            </tr>
            <tr>
              <td>New in window</td>
              <td className="num">
                {report.players.new_in_window.toLocaleString()}
              </td>
            </tr>
            <tr>
              <td>Placed a bet</td>
              <td className="num">
                {report.players.staked_in_window.toLocaleString()}
              </td>
            </tr>
            <tr>
              <td>Claimed the daily drip</td>
              <td className="num">
                {report.players.claimed_in_window.toLocaleString()}
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <details className="admin-panel admin-raw">
        <summary>Full ledger by entry type</summary>
        <table className="admin-table">
          <thead>
            <tr>
              <th>Entry type</th>
              <th>Net</th>
              <th>Entries</th>
              <th>Players</th>
            </tr>
          </thead>
          <tbody>
            {report.ledger.map((row) => (
              <tr key={row.entry_type}>
                <td>{row.entry_type}</td>
                <td className="num">{row.net.display}</td>
                <td className="num">{row.entries}</td>
                <td className="num">{row.players}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </main>
  );
}


const BUCKET_LABELS: Record<BreakEvenBucket["bucket"], string> = {
  far_below: "Under half break-even",
  below: "Below break-even",
  at: "Around break-even",
  above: "2–5× break-even",
  far_above: "Over 5× break-even",
};

function bucketTone(bucket: BreakEvenBucket["bucket"]): string {
  if (bucket === "far_below" || bucket === "below") return "var(--admin-below)";
  if (bucket === "at") return "var(--admin-at)";
  return "var(--admin-above)";
}

function BreakEven({ report }: { report: EconomyReport }) {
  const buckets = report.break_even_buckets;
  const total = buckets.reduce((sum, b) => sum + b.players, 0);
  const widest = Math.max(...buckets.map((b) => b.players), 1);
  const freeShare = report.free_players_share;

  return (
    <section className="admin-panel">
      <h2>Can they play for free forever?</h2>
      <p className="admin-note">
        A player earns up to {report.break_even_daily_stake.display} a day free
        and burns the vig on everything they stake. Below that daily stake they
        never need to buy a Star. This distribution is the forecast; the revenue
        above it is the receipt.
      </p>

      {total === 0 ? (
        <p className="admin-empty">
          Nobody has placed a bet in this window, so there is nothing to
          distribute yet.
        </p>
      ) : (
        <>
          <div className="admin-bars">
            {buckets.map((bucket) => (
              <div className="admin-bar-row" key={bucket.bucket}>
                <span className="admin-bar-label">
                  {BUCKET_LABELS[bucket.bucket]}
                </span>
                <div className="admin-bar-track">
                  <div
                    className="admin-bar-fill"
                    style={{
                      width: `${Math.max((bucket.players / widest) * 100, bucket.players ? 2 : 0)}%`,
                      background: bucketTone(bucket.bucket),
                    }}
                  />
                </div>
                <span className="admin-bar-value">{bucket.players}</span>
              </div>
            ))}
          </div>

          <p
            className={freeShare > 0.8 ? "admin-verdict warn" : "admin-verdict"}
          >
            <strong>{(freeShare * 100).toFixed(0)}%</strong> of active players
            stake below break-even.{" "}
            {freeShare > 0.8
              ? "Almost nobody is on a path to paying — the drip is covering the vig. Cut the drip or raise the vig."
              : "A meaningful share will run out and face the buy-or-wait decision."}
          </p>
        </>
      )}
    </section>
  );
}


function StarsChart({ days, rate }: { days: RevenueDay[]; rate: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const peak = Math.max(...days.map((d) => d.stars), 1);
  const width = 100;
  const gap = 0.35;
  const barWidth = Math.max(width / days.length - gap, 0.6);

  if (days.every((d) => d.stars === 0)) {
    return <p className="admin-empty">No Stars in this window yet.</p>;
  }

  const active = hover === null ? null : days[hover];

  return (
    <div className="admin-chart">
      <svg
        viewBox={`0 0 ${width} 32`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Stars per day over ${days.length} days`}
      >
        {days.map((day, i) => {
          const height = (day.stars / peak) * 30;
          return (
            <rect
              key={day.day}
              x={i * (barWidth + gap)}
              y={32 - height}
              width={barWidth}
              height={Math.max(height, day.stars ? 0.5 : 0)}
              rx={0.4}
              fill="var(--admin-stars)"
              opacity={hover === null || hover === i ? 1 : 0.45}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            />
          );
        })}
      </svg>

      <div className="admin-chart-foot">
        {active ? (
          <span>
            <strong>{new Date(active.day).toLocaleDateString()}</strong> ·{" "}
            {active.stars.toLocaleString()} Stars (≈ $
            {(active.stars * rate).toFixed(2)}) · {active.purchases} purchase
            {active.purchases === 1 ? "" : "s"} from {active.payers} player
            {active.payers === 1 ? "" : "s"}
          </span>
        ) : (
          <span className="admin-muted">
            Peak {peak.toLocaleString()} Stars · hover a bar for the day
          </span>
        )}
      </div>
    </div>
  );
}


function Tile({
  label,
  value,
  note,
  emphasis,
  warn,
}: {
  label: string;
  value: string;
  note?: string;
  emphasis?: boolean;
  warn?: boolean;
}) {
  return (
    <div
      className={`admin-tile${emphasis ? " is-hero" : ""}${warn ? " is-warn" : ""}`}
    >
      <span className="admin-tile-label">{label}</span>
      <span className="admin-tile-value">{value}</span>
      {note ? <span className="admin-tile-note">{note}</span> : null}
    </div>
  );
}

function Row({
  label,
  money,
  good,
  strong,
}: {
  label: string;
  money: { display: string; minor: number };
  good?: boolean;
  strong?: boolean;
}) {
  return (
    <tr className={strong ? "is-strong" : ""}>
      <td>{label}</td>
      <td className={`num${good ? " is-good" : ""}`}>{money.display}</td>
    </tr>
  );
}
