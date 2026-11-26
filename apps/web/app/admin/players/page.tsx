"use client";


import { useCallback, useEffect, useState } from "react";

import { AdminNav } from "@/components/AdminNav";
import { StatusBanner } from "@/components/StatusBanner";
import { TelegramGate } from "@/components/TelegramGate";
import { adjustPlayer, getPlayers, setPlayerStatus } from "@/lib/api";
import type { PlayerRow } from "@/lib/types";

export default function PlayersPage() {
  return (
    <TelegramGate>
      <Roster />
    </TelegramGate>
  );
}

function toman(minor: number): string {
  const sign = minor < 0 ? "-" : "";
  return sign + Math.floor(Math.abs(minor) / 100).toLocaleString("en-US");
}

function Roster() {
  const [search, setSearch] = useState("");
  const [players, setPlayers] = useState<PlayerRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async (term: string) => {
    const result = await getPlayers(term);
    if (result.ok) {
      setPlayers(result.data.players);
      setTotal(result.data.total);
      setError(null);
    } else {
      setError(
        result.status === 404
          ? "This page is not available for your account."
          : result.detail,
      );
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void load(search), 250);
    return () => clearTimeout(timer);
  }, [search, load]);

  const adjust = useCallback(
    async (player: PlayerRow) => {
      const raw = window.prompt(
        `Adjust ${player.player_code} (${player.display_name}).\n\n` +
          `Balance now: ${player.balance.display} toman.\n` +
          `Enter a signed amount in TOMAN — e.g. 50000 to credit, -50000 to debit.`,
      );
      if (raw === null) return;

      const tomanAmount = Number(raw.replace(/[, ]/g, ""));
      if (!Number.isFinite(tomanAmount) || tomanAmount === 0) {
        setNotice("Enter a non-zero number.");
        return;
      }

      const reason = window.prompt("Why? (recorded on the ledger entry)");
      if (!reason?.trim()) return;

      setBusy(player.player_code);
      const result = await adjustPlayer({
        player_code: player.player_code,
        amount_minor: Math.round(tomanAmount * 100),
        reason: reason.trim(),
        reference: `${player.player_code}-${Date.now()}`,
      });
      setBusy(null);

      if (result.ok) {
        setNotice(
          `${player.player_code} now holds ${result.data.balance.display} toman.`,
        );
        await load(search);
      } else {
        setNotice(result.detail);
      }
    },
    [load, search],
  );

  const changeStatus = useCallback(
    async (player: PlayerRow, status: PlayerRow["status"]) => {
      const verb =
        status === "BANNED"
          ? "Ban"
          : status === "ACTIVE"
            ? "Reinstate"
            : "Restrict";
      const typed = window.prompt(
        `${verb} ${player.display_name}?\n\n` +
          (status === "BANNED"
            ? "They will be signed out immediately and cannot place predictions.\n\n"
            : "") +
          `Type the player code ${player.player_code} to confirm.`,
      );
      if (typed?.trim().toUpperCase() !== player.player_code) return;

      setBusy(player.player_code);
      const result = await setPlayerStatus(player.player_code, status);
      setBusy(null);

      setNotice(
        result.ok
          ? `${player.player_code} is now ${result.data.status}.`
          : result.detail,
      );
      if (result.ok) await load(search);
    },
    [load, search],
  );

  if (error) {
    return (
      <main className="admin-shell">
        <AdminNav />
        <p className="admin-empty">{error}</p>
      </main>
    );
  }

  return (
    <main className="admin-shell">
      <AdminNav />

      <header className="admin-head">
        <div>
          <h1 className="admin-title">Players</h1>
          <p className="admin-sub">{total.toLocaleString()} registered</p>
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="code, @username or name"
          className="admin-search"
        />
      </header>

      <StatusBanner />

      <GiveCoins
        onDone={(message) => {
          setNotice(message);
          void load(search);
        }}
      />

      {notice ? <p className="admin-notice">{notice}</p> : null}

      {players === null ? (
        <p className="admin-empty">Loading…</p>
      ) : players.length === 0 ? (
        <p className="admin-empty">Nobody matches that.</p>
      ) : (
        <div className="admin-panel">
          <div className="scroll">
            <table className="admin-table admin-roster">
              <thead>
                <tr>
                  <th>Player</th>
                  <th className="num">Balance</th>
                  <th className="num">Staked</th>
                  <th className="num">Returned</th>
                  <th className="num">Net</th>
                  <th className="num">W / L</th>
                  <th className="num">★</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {players.map((p) => (
                  <tr
                    key={p.id}
                    className={p.status === "BANNED" ? "is-banned" : ""}
                  >
                    <td>
                      <span className="admin-code">{p.player_code}</span>
                      <span className="sub">
                        {p.display_name}
                        {p.username ? ` · @${p.username}` : ""}
                        {p.status !== "ACTIVE" ? ` · ${p.status}` : ""}
                      </span>
                    </td>
                    <td className="num" data-label="Balance">
                      {p.balance.display}
                    </td>
                    <td className="num" data-label="Staked">
                      {p.staked.display}
                    </td>
                    <td className="num" data-label="Returned">
                      {p.returned.display}
                    </td>
                    <td
                      data-label="Net"
                      className={`num ${p.net.minor > 0 ? "is-bad" : "is-good"}`}
                    >
                      {p.net.display}
                    </td>
                    <td className="num" data-label="Won / lost">
                      {p.won} / {p.lost}
                      {p.open_slips ? (
                        <span className="sub">{p.open_slips} open</span>
                      ) : null}
                    </td>
                    <td className="num" data-label="Stars bought">
                      {p.lifetime_stars || "—"}
                    </td>
                    <td className="admin-actions">
                      <button
                        type="button"
                        disabled={busy === p.player_code}
                        onClick={() => void adjust(p)}
                      >
                        Adjust
                      </button>
                      <button
                        type="button"
                        disabled={busy === p.player_code}
                        className="is-danger"
                        onClick={() =>
                          void changeStatus(
                            p,
                            p.status === "BANNED" ? "ACTIVE" : "BANNED",
                          )
                        }
                      >
                        {p.status === "BANNED" ? "Unban" : "Ban"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="admin-note">
            Net is returned minus staked, from the ledger. Positive means the
            house is down against them. Open slips count their stake but not
            their outcome.
          </p>
        </div>
      )}
    </main>
  );
}

function GiveCoins({ onDone }: { onDone: (message: string) => void }) {
  const [id, setId] = useState("");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const give = useCallback(async () => {
    const telegramId = Number(id.trim());
    const toman = Number(amount.replace(/[, ]/g, ""));

    if (!Number.isSafeInteger(telegramId) || telegramId === 0) {
      setProblem("A Telegram id is a whole number — digits only, no letters.");
      return;
    }
    if (!Number.isFinite(toman) || toman === 0) {
      setProblem("Enter a non-zero amount. Negative takes coins away.");
      return;
    }
    if (!reason.trim()) {
      setProblem("Say why. It is recorded on the ledger entry.");
      return;
    }

    setProblem(null);
    setBusy(true);
    const result = await adjustPlayer({
      telegram_id: telegramId,
      amount_minor: Math.round(toman * 100),
      reason: reason.trim(),
      reference: `tg-${telegramId}-${Date.now()}`,
    });
    setBusy(false);

    if (!result.ok) {
      setProblem(result.detail);
      return;
    }
    setAmount("");
    setReason("");
    onDone(
      `${result.data.player_code} now holds ${result.data.balance.display} toman.`,
    );
  }, [id, amount, reason, onDone]);

  return (
    <section className="admin-panel admin-give">
      <h2>Give coins by Telegram id</h2>
      <div className="admin-give-row">
        <input
          value={id}
          onChange={(e) => setId(e.target.value)}
          inputMode="numeric"
          placeholder="Telegram id"
          dir="ltr"
        />
        <input
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          inputMode="numeric"
          placeholder="Toman (− takes)"
          dir="ltr"
        />
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Reason (goes on the ledger)"
        />
        <button type="button" disabled={busy} onClick={() => void give()}>
          {busy ? "Posting…" : "Give"}
        </button>
      </div>
      {problem ? <p className="admin-muted">{problem}</p> : null}
    </section>
  );
}
