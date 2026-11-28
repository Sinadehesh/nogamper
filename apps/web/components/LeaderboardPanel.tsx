"use client";

import { useEffect, useState } from "react";

import { usePlayer } from "@/components/PlayerProvider";
import { Figure } from "@/components/viz/Figure";
import { getLeaderboard } from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { dateTimeUtc, points, seasonName, signedPoints } from "@/lib/format";
import type { Leaderboard } from "@/lib/types";

/**
 * The season's standings. Initials only, and no prizes: the table exists to
 * give being right something to show for itself, and nothing more. Net
 * points are ink either way; a loss is not drawn red, nor a gain green.
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
      <p role="alert" className="gm-note gm-error">
        {error}
      </p>
    );
  }
  if (!board) {
    return (
      <p className="gm-loading" role="status">
        {t.loading}
      </p>
    );
  }

  const season = seasonName(board.season);

  return (
    <section className="gm-feed" aria-labelledby="gm-board-title">
      <div className="gm-panel grid gap-5">
        <header className="grid gap-1">
          <h2 id="gm-board-title" className="gm-h">
            {t.leaderboardTitle(season)}
          </h2>
          <p className="gm-small">{t.leaderboardEnds(dateTimeUtc(board.ends_at))}</p>
        </header>

        {/* The threshold is only worth saying to somebody who has not met it. */}
        <div className="gm-note gm-note--line">
          <p>
            {board.my_rank
              ? t.leaderboardYou(board.my_rank)
              : `${t.leaderboardUnranked} ${t.leaderboardMinimum(board.min_volume_to_rank.display)}`}
          </p>
          {board.my_total_staked.minor > 0 ? (
            <p className="gm-small mt-1">
              <Figure
                text={t.leaderboardYourNet(
                  signedPoints(board.my_net_profit.minor),
                  points(board.my_total_staked.minor),
                )}
              />
            </p>
          ) : null}
        </div>

        {board.rows.length === 0 ? (
          <p className="gm-empty">{t.leaderboardEmpty}</p>
        ) : (
          <div className="gm-board">
            <table>
              <caption>{t.leaderboardCaption(season)}</caption>
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
                  <tr
                    key={`${row.rank}-${row.player}-${row.total_staked.minor}`}
                    data-me={row.is_me ? "" : undefined}
                    aria-current={row.is_me ? "true" : undefined}
                  >
                    <td className="rank">{row.rank ?? "—"}</td>
                    <td>
                      <span className="inline-flex items-center gap-2">
                        {row.player}
                        {row.is_me ? <span className="gm-tag">{t.you}</span> : null}
                      </span>
                    </td>
                    <td className="num">
                      {row.slips_won} / {row.slips_settled}
                    </td>
                    <td className="num">
                      <Figure text={points(row.total_staked.minor)} />
                    </td>
                    <td className="num">
                      <Figure text={signedPoints(row.net_profit.minor)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
