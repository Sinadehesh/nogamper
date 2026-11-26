"use client";

import { useCallback, useEffect, useState } from "react";

import { getInbox, replyToMessage, resolveMessage } from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { points, timeAgo } from "@/lib/format";
import type { Inbox, InboxItem } from "@/lib/types";

const FILTERS: { label: string; status?: string }[] = [
  { label: t.adminFilterAll },
  { label: t.adminFilterNew, status: "NEW" },
  { label: t.adminFilterSeen, status: "SEEN" },
  { label: t.adminFilterAnswered, status: "ANSWERED" },
];

type Flash = { ok: boolean; text: string } | null;

export default function AdminInboxPage() {
  const [filter, setFilter] = useState<string | undefined>(undefined);
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [flash, setFlash] = useState<Flash>(null);

  const load = useCallback(async () => {
    const result = await getInbox(filter);
    if (result.ok) setInbox(result.data);
    else setFlash({ ok: false, text: result.status === 404 ? t.adminDenied : errorMessage(result.code) });
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-black tracking-tight">
          {t.adminInbox}
          {inbox && inbox.unread > 0 ? (
            <span className="chip ms-3 align-middle">{t.adminInboxUnread(inbox.unread)}</span>
          ) : null}
        </h1>
        <div className="flex gap-1" role="group">
          {FILTERS.map((entry) => (
            <button
              key={entry.label}
              type="button"
              aria-pressed={filter === entry.status}
              className={`btn btn-sm ${filter === entry.status ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setFilter(entry.status)}
            >
              {entry.label}
            </button>
          ))}
        </div>
      </div>

      {flash ? (
        <p role={flash.ok ? "status" : "alert"} className={`notice ${flash.ok ? "notice-ok" : "notice-error"}`}>
          {flash.text}
        </p>
      ) : null}

      {inbox === null ? (
        <p className="text-muted">{t.loading}</p>
      ) : inbox.messages.length === 0 ? (
        <p className="text-muted">{t.adminInboxEmpty}</p>
      ) : (
        <ul className="space-y-3">
          {inbox.messages.map((message) => (
            <li key={message.id}>
              <MessageCard
                message={message}
                onChanged={(next) => {
                  setFlash(next);
                  void load();
                }}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function MessageCard({
  message,
  onChanged,
}: {
  message: InboxItem;
  onChanged: (flash: Flash) => void;
}) {
  const [reply, setReply] = useState("");
  const [note, setNote] = useState(message.admin_note ?? "");
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<{ ok: boolean; code?: string }>, done: string) {
    setBusy(true);
    const result = await action();
    setBusy(false);
    onChanged(
      result.ok ? { ok: true, text: done } : { ok: false, text: errorMessage(result.code ?? "") },
    );
  }

  return (
    <article className="card space-y-3 p-4">
      <header className="flex flex-wrap items-start justify-between gap-2 text-sm">
        <p>
          <span className="font-mono font-bold tracking-widest">{message.player_code}</span>{" "}
          <span>{message.display_name}</span>{" "}
          {message.is_guest ? <span className="chip">{t.adminGuestTag}</span> : null}
          <span className="block text-xs text-muted tabular-nums">
            {points(message.balance.minor)} {t.pts} · {message.player_status} ·{" "}
            {timeAgo(message.created_at)}
          </span>
        </p>
        <span className="flex gap-1">
          {message.kind === "PRIZE_CLAIM" ? <span className="chip">{t.adminPrizeClaim}</span> : null}
          <span className="chip">{message.status}</span>
        </span>
      </header>

      <p className="whitespace-pre-wrap">{message.body}</p>

      {message.reply_body ? (
        <div className="border-s-2 border-accent ps-3 text-sm">
          <p className="text-xs font-semibold text-accent">{t.adminYourReply}</p>
          <p className="whitespace-pre-wrap">{message.reply_body}</p>
        </div>
      ) : (
        <div className="space-y-2">
          <textarea
            className="field min-h-20"
            maxLength={2000}
            placeholder={t.adminReplyPlaceholder}
            aria-label={t.adminYourReply}
            value={reply}
            onChange={(event) => setReply(event.target.value)}
          />
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={busy || !reply.trim()}
            onClick={() => void run(() => replyToMessage(message.id, reply), t.adminReplySent)}
          >
            {t.adminReplySend}
          </button>
        </div>
      )}

      <div className="flex flex-wrap items-end gap-2 border-t border-line pt-3">
        <label className="min-w-0 flex-1">
          <span className="label">{t.adminNote}</span>
          <input
            className="field"
            maxLength={2000}
            placeholder={t.adminNotePlaceholder}
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </label>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={busy}
          onClick={() =>
            void run(() => resolveMessage(message.id, message.status, note), t.adminNoteSave)
          }
        >
          {t.adminNoteSave}
        </button>
        {message.status === "NEW" ? (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={busy}
            onClick={() =>
              void run(() => resolveMessage(message.id, "SEEN", note), t.adminMarkSeen)
            }
          >
            {t.adminMarkSeen}
          </button>
        ) : null}
      </div>
    </article>
  );
}
