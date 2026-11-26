"use client";


import { useCallback, useEffect, useState } from "react";

import { AdminNav } from "@/components/AdminNav";
import { StatusBanner } from "@/components/StatusBanner";
import { TelegramGate } from "@/components/TelegramGate";
import { getInbox, replyToMessage, resolveMessage } from "@/lib/api";
import type { InboxItem } from "@/lib/types";

const FILTERS = [
  { key: "NEW", label: "New" },
  { key: "SEEN", label: "Seen" },
  { key: "ANSWERED", label: "Answered" },
  { key: "", label: "All" },
] as const;

export default function MessagesPage() {
  return (
    <TelegramGate>
      <Inbox />
    </TelegramGate>
  );
}

function Inbox() {
  const [filter, setFilter] = useState<string>("NEW");
  const [items, setItems] = useState<InboxItem[] | null>(null);
  const [unread, setUnread] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async (status: string) => {
    const result = await getInbox(status || undefined);
    if (result.ok) {
      setItems(result.data.messages);
      setUnread(result.data.unread);
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
    void load(filter);
  }, [filter, load]);

  const triage = useCallback(
    async (item: InboxItem, status: string) => {
      let note: string | undefined;
      if (status === "ANSWERED") {
        const typed = window.prompt(
          `Mark ${item.player_code}'s message answered.\n\n` +
            "Optional note for yourself — the player never sees this.",
        );
        if (typed === null) return;
        note = typed.trim() || undefined;
      }

      setBusy(item.id);
      const result = await resolveMessage(item.id, status, note);
      setBusy(null);
      if (result.ok) await load(filter);
      else setError(result.detail);
    },
    [filter, load],
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
          <h1 className="admin-title">Messages</h1>
          <p className="admin-sub">{unread} unread</p>
        </div>
        <div className="admin-segmented" role="group" aria-label="Filter">
          {FILTERS.map((f) => (
            <button
              key={f.key || "all"}
              type="button"
              aria-pressed={filter === f.key}
              className={filter === f.key ? "is-on" : ""}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </header>

      <StatusBanner />

      {items === null ? (
        <p className="admin-empty">Loading…</p>
      ) : items.length === 0 ? (
        <p className="admin-empty">Nothing here.</p>
      ) : (
        <div className="admin-messages">
          {items.map((m) => (
            <article key={m.id} className="admin-panel admin-message">
              <div className="admin-message-head">
                <div>
                  <span className="admin-code">{m.player_code}</span>
                  <span className="sub">
                    {m.display_name}
                    {m.username ? ` · @${m.username}` : ""} ·{" "}
                    {m.balance.display} toman
                    {m.player_status !== "ACTIVE"
                      ? ` · ${m.player_status}`
                      : ""}
                  </span>
                </div>
                <span
                  className={`admin-chip${m.kind === "PRIZE_CLAIM" ? " is-claim" : ""}`}
                >
                  {m.kind === "PRIZE_CLAIM" ? "prize claim" : "message"}
                </span>
              </div>

              <p className="admin-message-body" dir="auto">
                {m.body}
              </p>

              {m.reply_body ? (
                <div className="admin-reply">
                  <p dir="auto">{m.reply_body}</p>
                  <span className="admin-muted">
                    {m.reply_delivered
                      ? "Sent by the bot"
                      : "Saved — Telegram would not deliver it. They will read it in the app."}
                  </span>
                </div>
              ) : (
                <ReplyBox
                  item={m}
                  onSent={() => void load(filter)}
                  onError={(detail) => setError(detail)}
                />
              )}

              {m.admin_note ? (
                <p className="admin-note">Note: {m.admin_note}</p>
              ) : null}

              <div className="admin-message-foot">
                <span className="admin-muted">
                  {new Date(m.created_at).toLocaleString()} · {m.status}
                </span>
                <div className="admin-actions">
                  {m.status === "NEW" ? (
                    <button
                      type="button"
                      disabled={busy === m.id}
                      onClick={() => void triage(m, "SEEN")}
                    >
                      Seen
                    </button>
                  ) : null}
                  {m.status !== "ANSWERED" ? (
                    <button
                      type="button"
                      disabled={busy === m.id}
                      onClick={() => void triage(m, "ANSWERED")}
                    >
                      Answered
                    </button>
                  ) : null}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </main>
  );
}

function ReplyBox({
  item,
  onSent,
  onError,
}: {
  item: InboxItem;
  onSent: () => void;
  onError: (detail: string) => void;
}) {
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const send = useCallback(async () => {
    const text = body.trim();
    if (!text || sending) return;
    setSending(true);
    const result = await replyToMessage(item.id, text);
    setSending(false);

    if (!result.ok) {
      onError(result.detail);
      return;
    }
    if (!result.data.delivered) {
      setNotice(
        result.data.delivery_detail ??
          "Saved, but Telegram would not deliver it.",
      );
      return;
    }
    setBody("");
    onSent();
  }, [body, sending, item.id, onSent, onError]);

  return (
    <div className="admin-replybox">
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={3}
        maxLength={2000}
        dir="auto"
        placeholder={`Reply to ${item.player_code} — sent by the bot, not from your account`}
      />
      <div className="admin-actions">
        {notice ? <span className="admin-muted">{notice}</span> : null}
        <button
          type="button"
          disabled={sending || !body.trim()}
          onClick={() => void send()}
        >
          {sending ? "Sending…" : "Send reply"}
        </button>
      </div>
    </div>
  );
}
