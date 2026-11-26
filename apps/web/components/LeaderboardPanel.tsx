"use client";

import { useEffect, useState } from "react";

import { usePlayer } from "@/components/PlayerProvider";
import { getLeaderboard } from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { points, seasonName, signedPoints, timeUntil } from "@/lib/format";
import type { Leaderboard } from "@/lib/types";

/**
 * The season's standings. Initials only, and no prizes — the table exists to
 * give being right something to show for itself, and nothing more.
 */
export function LeaderboardPanel() {
  const { refresh } = usePlayer();
  const [board, setBoard] = useState<Leaderboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getLeaderboard().then((result) => {
      if (cancelled) return;
      if (result.ok) setBoard(result.data);
      else {
        if (result.status === 401) void refresh();
        setError(errorMessage(result.code));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  if (error) {
    return (
      <p role="alert" className="notice notice-error">
        {error}
      </p>
    );
  }
  if (!board) return <p className="py-10 text-center text-muted">{t.loading}</p>;

  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-xl font-bold">{t.leaderboardTitle(seasonName(board.season))}</h2>
        <p className="text-sm text-muted">
          {t.leaderboardEnds(timeUntil(board.ends_at))} · {t.leaderboardIntro}
        </p>
      </header>

      {/* The threshold is only worth saying to somebody who has not met it. */}
      <p className="notice">
        {board.my_rank
          ? t.leaderboardYou(board.my_rank)
          : `${t.leaderboardUnranked} ${t.leaderboardMinimum(board.min_volume_to_rank.display)}`}
      </p>

      {board.rows.length === 0 ? (
        <p className="py-8 text-center text-muted">{t.leaderboardEmpty}</p>
      ) : (
        <div className="card overflow-x-auto p-4">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">{t.colRank}</th>
                <th scope="col">{t.colPlayer}</th>
                <th scope="col" className="num">
                  {t.colRecord}
                </th>
                <th scope="col" className="num">
                  {t.colStaked}
                </th>
                <th scope="col" className="num">
                  {t.colNet}
                </th>
              </tr>
            </thead>
            <tbody>
              {board.rows.map((row) => (
                <tr key={`${row.rank}-${row.player}-${row.total_staked.minor}`} className={row.is_me ? "is-me" : ""}>
                  <td className="tabular-nums">{row.rank}</td>
                  <td>
                    {row.player}
                    {row.is_me ? <span className="chip ms-2">{t.you}</span> : null}
                  </td>
                  <td className="num">
                    {row.slips_won} / {row.slips_settled}
                  </td>
                  <td className="num">{points(row.total_staked.minor)}</td>
                  <td className={`num ${row.net_profit.minor >= 0 ? "text-yes" : "text-no"}`}>
                    {signedPoints(row.net_profit.minor)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
