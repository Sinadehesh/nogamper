"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useState, type FormEvent } from "react";

import { usePlayer } from "@/components/PlayerProvider";
import {
  changePassword,
  eraseAccount,
  getMyMessages,
  renamePlayer,
  sendMessage,
  signOut,
} from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { date, timeAgo } from "@/lib/format";
import type { PlayerMessage } from "@/lib/types";

type Flash = { ok: boolean; text: string } | null;

function FlashLine({ flash }: { flash: Flash }) {
  if (!flash) return null;
  return (
    <p
      role={flash.ok ? "status" : "alert"}
      className={`notice mt-3 ${flash.ok ? "notice-ok" : "notice-error"}`}
    >
      {flash.text}
    </p>
  );
}

export function AccountPanel() {
  const { player } = usePlayer();

  return (
    <section className="space-y-4">
      <ProfileCard />
      {player.is_guest ? null : <PasswordCard />}
      <ContactCard />
      <LeaveCard />
    </section>
  );
}

function ProfileCard() {
  const { player, refresh } = usePlayer();
  const router = useRouter();
  const nameId = useId();

  const [name, setName] = useState(player.display_name);
  const [busy, setBusy] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [flash, setFlash] = useState<Flash>(null);

  async function rename(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    const result = await renamePlayer(name);
    setBusy(false);
    if (result.ok) {
      await refresh();
      setFlash({ ok: true, text: t.renamed });
    } else {
      setFlash({ ok: false, text: errorMessage(result.code) });
    }
  }

  async function leave() {
    setLeaving(true);
    await signOut();
    router.push("/");
    router.refresh();
  }

  return (
    <article className="card p-5">
      <h2 className="text-lg font-bold">{t.accountTitle}</h2>

      <dl className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-3">
        <div>
          <dt className="text-xs text-muted">{t.accountCode}</dt>
          <dd className="font-mono text-lg font-bold tracking-widest">{player.player_code}</dd>
          <dd className="hint">{t.accountCodeHint}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">{t.accountEmail}</dt>
          <dd className="break-all font-semibold">{player.email ?? t.accountGuest}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">{t.accountSince}</dt>
          <dd className="font-semibold">{date(player.member_since)}</dd>
        </div>
      </dl>

      <form onSubmit={rename} className="mt-5">
        <label htmlFor={nameId} className="label">
          {t.fieldDisplayName}
        </label>
        <div className="flex gap-2">
          <input
            id={nameId}
            className="field"
            value={name}
            maxLength={24}
            onChange={(event) => setName(event.target.value)}
          />
          <button
            type="submit"
            className="btn btn-secondary shrink-0"
            disabled={busy || name.trim() === player.display_name || name.trim().length < 2}
          >
            {busy ? t.saving : t.accountRename}
          </button>
        </div>
        <p className="hint">{t.fieldDisplayNameHint}</p>
      </form>
      <FlashLine flash={flash} />

      <div className="mt-5 border-t border-line pt-4">
        <button type="button" className="btn btn-secondary" onClick={() => void leave()} disabled={leaving}>
          {leaving ? t.signingOut : t.signOut}
        </button>
      </div>
    </article>
  );
}

function PasswordCard() {
  const currentId = useId();
  const nextId = useId();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<Flash>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    const result = await changePassword(current, next);
    setBusy(false);
    if (result.ok) {
      setCurrent("");
      setNext("");
      setFlash({ ok: true, text: t.passwordChanged });
    } else {
      setFlash({ ok: false, text: errorMessage(result.code) });
    }
  }

  return (
    <article className="card p-5">
      <h2 className="text-lg font-bold">{t.passwordTitle}</h2>
      <form onSubmit={submit} className="mt-3 grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor={currentId} className="label">
            {t.passwordCurrent}
          </label>
          <input
            id={currentId}
            className="field"
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor={nextId} className="label">
            {t.passwordNew}
          </label>
          <input
            id={nextId}
            className="field"
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(event) => setNext(event.target.value)}
          />
        </div>
        <div className="sm:col-span-2">
          <button type="submit" className="btn btn-secondary" disabled={busy || !current || !next}>
            {busy ? t.saving : t.passwordChange}
          </button>
        </div>
      </form>
      <FlashLine flash={flash} />
    </article>
  );
}

const MESSAGE_STATUS: Record<PlayerMessage["status"], string> = {
  NEW: t.messageNew,
  SEEN: t.messageSeen,
  ANSWERED: t.messageAnswered,
};

function ContactCard() {
  const bodyId = useId();
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<Flash>(null);
  const [messages, setMessages] = useState<PlayerMessage[]>([]);

  const load = useCallback(async () => {
    const result = await getMyMessages();
    if (result.ok) setMessages(result.data.messages);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    const result = await sendMessage(body);
    setBusy(false);
    if (result.ok) {
      setBody("");
      setFlash({ ok: true, text: t.contactSent });
      void load();
    } else {
      setFlash({ ok: false, text: errorMessage(result.code) });
    }
  }

  return (
    <article className="card p-5">
      <h2 className="text-lg font-bold">{t.contactTitle}</h2>
      <p className="text-sm text-muted">{t.contactIntro}</p>

      <form onSubmit={submit} className="mt-3">
        <label htmlFor={bodyId} className="sr-only">
          {t.contactTitle}
        </label>
        <textarea
          id={bodyId}
          className="field min-h-24"
          maxLength={2000}
          placeholder={t.contactPlaceholder}
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
        <button type="submit" className="btn btn-secondary mt-2" disabled={busy || !body.trim()}>
          {busy ? t.contactSending : t.contactSend}
        </button>
      </form>
      <FlashLine flash={flash} />

      {messages.length > 0 ? (
        <div className="mt-5">
          <h3 className="label">{t.contactHistory}</h3>
          <ul className="space-y-3">
            {messages.map((message) => (
              <li key={message.id} className="rounded-xl bg-sunken p-3 text-sm">
                <p className="flex items-center justify-between gap-2 text-xs text-muted">
                  <span>{timeAgo(message.created_at)}</span>
                  <span className="chip">{MESSAGE_STATUS[message.status]}</span>
                </p>
                <p className="mt-1 whitespace-pre-wrap">{message.body}</p>
                {message.reply_body ? (
                  <div className="mt-2 border-s-2 border-accent ps-3">
                    <p className="text-xs font-semibold text-accent">{t.contactReply}</p>
                    <p className="whitespace-pre-wrap">{message.reply_body}</p>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </article>
  );
}

function LeaveCard() {
  const { player } = usePlayer();
  const router = useRouter();
  const passwordId = useId();

  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<Flash>(null);

  async function erase(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    const result = await eraseAccount(player.is_guest ? null : password);
    if (result.ok) {
      router.push("/");
      router.refresh();
      return;
    }
    setBusy(false);
    setFlash({ ok: false, text: errorMessage(result.code) });
  }

  return (
    <article className="card p-5">
      <h2 className="text-lg font-bold">{t.eraseTitle}</h2>
      <p className="text-sm text-muted">{t.eraseIntro}</p>

      {open ? (
        <form onSubmit={erase} className="mt-3 max-w-sm">
          {player.is_guest ? (
            <p className="notice notice-warn">{t.eraseConfirmGuest}</p>
          ) : (
            <>
              <label htmlFor={passwordId} className="label">
                {t.eraseConfirmLabel}
              </label>
              <input
                id={passwordId}
                className="field"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </>
          )}
          <div className="mt-3 flex gap-2">
            <button
              type="submit"
              className="btn btn-danger"
              disabled={busy || (!player.is_guest && !password)}
            >
              {busy ? t.erasing : t.eraseButton}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setOpen(false)}>
              {t.cancel}
            </button>
          </div>
        </form>
      ) : (
        <button type="button" className="btn btn-danger mt-3" onClick={() => setOpen(true)}>
          {t.eraseButton}
        </button>
      )}
      <FlashLine flash={flash} />
    </article>
  );
}
