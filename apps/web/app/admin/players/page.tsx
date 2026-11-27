"use client";

import { useCallback, useEffect, useId, useState, type FormEvent } from "react";

import { adjustPlayer, getPlayers, setPlayerStatus } from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { date, points, signedPoints, timeAgo } from "@/lib/format";
import type { PlayerRow } from "@/lib/types";

type Flash = { ok: boolean; text: string } | null;

export default function AdminPlayersPage() {
  const [search, setSearch] = useState("");
  const [players, setPlayers] = useState<PlayerRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [flash, setFlash] = useState<Flash>(null);
  const [adjusting, setAdjusting] = useState<PlayerRow | null>(null);

  const load = useCallback(async (term: string) => {
    const result = await getPlayers(term);
    if (result.ok) {
      setPlayers(result.data.players);
      setTotal(result.data.total);
    } else {
      setFlash({ ok: false, text: result.status === 404 ? t.adminDenied : errorMessage(result.code) });
    }
  }, []);

  // Debounced, so the roster is not re-queried for every keystroke.
  useEffect(() => {
    const timer = window.setTimeout(() => void load(search), 250);
    return () => window.clearTimeout(timer);
  }, [search, load]);

  async function changeStatus(player: PlayerRow, status: PlayerRow["status"]) {
    const result = await setPlayerStatus(player.player_code, status);
    setFlash(
      result.ok
        ? { ok: true, text: t.adminStatusSet(player.player_code, result.data.status) }
        : { ok: false, text: errorMessage(result.code) },
    );
    void load(search);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-black tracking-tight">{t.adminPlayers}</h1>
        <input
          className="field max-w-xs"
          type="search"
          placeholder={t.adminSearch}
          aria-label={t.adminSearch}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </div>

      {flash ? (
        <p role={flash.ok ? "status" : "alert"} className={`notice ${flash.ok ? "notice-ok" : "notice-error"}`}>
          {flash.text}
        </p>
      ) : null}

      {adjusting ? (
        <AdjustForm
          player={adjusting}
          onClose={() => setAdjusting(null)}
          onDone={(message) => {
            setAdjusting(null);
            setFlash(message);
            void load(search);
          }}
        />
      ) : null}

      {players === null ? (
        <p className="text-muted">{t.loading}</p>
      ) : players.length === 0 ? (
        <p className="text-muted">{t.adminNoPlayers}</p>
      ) : (
        <article className="card overflow-x-auto p-4">
          <p className="mb-2 text-xs text-muted">{t.adminShowing(players.length, total)}</p>
          <table className="table">
            <thead>
              <tr>
                <th scope="col">{t.adminColPlayer}</th>
                <th scope="col">{t.adminColStatus}</th>
                <th scope="col" className="num">{t.adminColBalance}</th>
                <th scope="col" className="num">{t.adminColStaked}</th>
                <th scope="col" className="num">{t.adminColNet}</th>
                <th scope="col" className="num">{t.adminColSlips}</th>
                <th scope="col">{t.adminColBrakes}</th>
                <th scope="col">{t.adminColSeen}</th>
                <th scope="col" />
              </tr>
            </thead>
            <tbody>
              {players.map((player) => (
                <tr key={player.id} className={player.status === "BANNED" ? "opacity-60" : ""}>
                  <td>
                    <span className="block font-mono font-bold tracking-widest">
                      {player.player_code}
                    </span>
                    <span className="block text-xs">{player.display_name}</span>
                    <span className="block break-all text-xs text-muted">
                      {player.is_guest ? t.adminGuestTag : player.email}
                    </span>
                  </td>
                  <td>
                    <span className="chip">{player.status}</span>
                  </td>
                  <td className="num">{points(player.balance.minor)}</td>
                  <td className="num">{points(player.staked.minor)}</td>
                  <td className={`num ${player.net.minor >= 0 ? "text-yes" : "text-no"}`}>
                    {signedPoints(player.net.minor)}
                  </td>
                  <td className="num">
                    {player.won} / {player.slips}
                    {player.open_slips > 0 ? (
                      <span className="block text-xs text-muted">
                        {t.adminOpenCount(player.open_slips)}
                      </span>
                    ) : null}
                  </td>
                  <td className="text-xs">
                    {player.daily_limit ? (
                      <span className="block">{t.adminLimitTag(player.daily_limit.display)}</span>
                    ) : null}
                    {player.break_until ? (
                      <span className="block">{t.adminBreakTag(date(player.break_until))}</span>
                    ) : null}
                    {!player.daily_limit && !player.break_until ? "—" : null}
                  </td>
                  <td className="whitespace-nowrap text-xs text-muted">
                    {timeAgo(player.last_seen_at)}
                  </td>
                  <td>
                    <span className="flex justify-end gap-1">
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setAdjusting(player)}
                      >
                        {t.adminAdjust}
                      </button>
                      {player.status === "ACTIVE" ? (
                        <button
                          type="button"
                          className="btn btn-danger btn-sm"
                          onClick={() => void changeStatus(player, "BANNED")}
                        >
                          {t.adminBan}
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => void changeStatus(player, "ACTIVE")}
                        >
                          {t.adminUnban}
                        </button>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </article>
      )}
    </div>
  );
}

function AdjustForm({
  player,
  onClose,
  onDone,
}: {
  player: PlayerRow;
  onClose: () => void;
  onDone: (flash: Flash) => void;
}) {
  const amountId = useId();
  const reasonId = useId();
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const whole = Number(amount.replace(/[,\s]/g, ""));
    if (!Number.isInteger(whole) || whole === 0) return;

    setBusy(true);
    // A fresh reference per submission. The API refuses a repeated one, which
    // is what stops a double click from posting the adjustment twice.
    const result = await adjustPlayer({
      player_code: player.player_code,
      amount_minor: whole * 100,
      reason: reason.trim(),
      reference: crypto.randomUUID(),
    });
    setBusy(false);

    if (result.ok) {
      onDone({ ok: true, text: t.adminAdjusted2(result.data.player_code, result.data.balance.display) });
    } else {
      setError(errorMessage(result.code));
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-3 p-4">
      <h2 className="text-base font-bold">{t.adminAdjustTitle(player.player_code)}</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor={amountId} className="label">{t.adminAdjustAmount}</label>
          <input
            id={amountId}
            className="field tabular-nums"
            inputMode="numeric"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor={reasonId} className="label">{t.adminAdjustReason}</label>
          <input
            id={reasonId}
            className="field"
            maxLength={200}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </div>
      </div>
      {error ? <p role="alert" className="notice notice-error">{error}</p> : null}
      <div className="flex gap-2">
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy || !amount || !reason.trim()}>
          {busy ? t.saving : t.adminAdjustPost}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
          {t.cancel}
        </button>
      </div>
    </form>
  );
}
