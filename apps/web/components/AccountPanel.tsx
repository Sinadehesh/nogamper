"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useState, type FormEvent } from "react";

import { usePlayer } from "@/components/PlayerProvider";
import { REMINDER_OPTIONS, readReminderMinutes, writeReminderMinutes } from "@/components/SessionReminder";
import { ShopCard } from "@/components/Shop";
import {
  changePassword,
  eraseAccount,
  getMyMessages,
  renamePlayer,
  sendMessage,
  signOut,
} from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { date, dateTimeUtc } from "@/lib/format";
import type { PlayerMessage } from "@/lib/types";

type Flash = { ok: boolean; text: string } | null;

function FlashLine({ flash }: { flash: Flash }) {
  if (!flash) return null;
  return (
    <p role={flash.ok ? "status" : "alert"} className={flash.ok ? "gm-note" : "gm-note gm-error"}>
      {flash.text}
    </p>
  );
}

export function AccountPanel({ onOpenSafer }: { onOpenSafer: () => void }) {
  const { player } = usePlayer();

  return (
    <section className="gm-feed" aria-labelledby="gm-view-title">
      <div className="gm-tools">
        <ProfileCard />
        {player.is_guest ? <KeepCard /> : <PasswordCard />}
        <ReminderCard />
        <ShopCard onOpenSafer={onOpenSafer} />
        <WritingCard />
        <ContactCard />
        <LeaveCard />
        <EraseCard />
      </div>
    </section>
  );
}

function Head({ id, title, intro }: { id: string; title: string; intro?: string }) {
  return (
    <div className="gm-tool__head">
      <h2 id={id} className="gm-h">
        {title}
      </h2>
      {intro ? <p className="gm-small">{intro}</p> : null}
    </div>
  );
}

function ProfileCard() {
  const { player, refresh } = usePlayer();
  const titleId = useId();
  const nameId = useId();

  const [name, setName] = useState(player.display_name);
  const [busy, setBusy] = useState(false);
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

  return (
    <article className="gm-panel gm-tool" aria-labelledby={titleId}>
      <Head id={titleId} title={t.accountTitle} />

      <dl className="gm-facts">
        <div>
          <dt>{t.accountCode}</dt>
          <dd className="gm-code">{player.player_code}</dd>
          <dd className="gm-small">{t.accountCodeHint}</dd>
        </div>
        <div>
          <dt>{t.accountEmail}</dt>
          <dd>{player.email ?? t.accountGuest}</dd>
        </div>
        <div>
          <dt>{t.accountSince}</dt>
          <dd>{date(player.member_since)}</dd>
        </div>
      </dl>

      <form onSubmit={rename} className="grid gap-2">
        <label htmlFor={nameId} className="label">
          {t.fieldDisplayName}
        </label>
        <div className="gm-inline">
          <input
            id={nameId}
            className="field"
            value={name}
            maxLength={24}
            autoComplete="nickname"
            onChange={(event) => setName(event.target.value)}
          />
          <button
            type="submit"
            className="btn btn--secondary"
            disabled={busy || name.trim() === player.display_name || name.trim().length < 2}
          >
            {busy ? t.saving : t.accountRename}
          </button>
        </div>
        <p className="gm-small">{t.fieldDisplayNameHint}</p>
      </form>
      <FlashLine flash={flash} />
    </article>
  );
}

/** A guest's way to keep what they have: the account they are on, with a password. */
function KeepCard() {
  const titleId = useId();
  return (
    <article className="gm-panel gm-tool" aria-labelledby={titleId}>
      <Head id={titleId} title={t.accountSignIn} intro={t.accountGuestKeep} />
      <Link href="/signup" prefetch={false} className="btn btn--secondary justify-self-start">
        {t.guestBannerAction}
      </Link>
    </article>
  );
}

function PasswordCard() {
  const titleId = useId();
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
    <article className="gm-panel gm-tool" aria-labelledby={titleId}>
      <Head id={titleId} title={t.passwordTitle} />
      <form onSubmit={submit} className="grid gap-4">
        <div className="grid gap-2">
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
        <div className="grid gap-2">
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
        <button
          type="submit"
          className="btn btn--secondary justify-self-start"
          disabled={busy || !current || !next}
        >
          {busy ? t.saving : t.passwordChange}
        </button>
      </form>
      <FlashLine flash={flash} />
    </article>
  );
}

/** The session reminder: a preference of this browser, kept in its storage. */
function ReminderCard() {
  const titleId = useId();
  const [minutes, setMinutes] = useState(0);
  useEffect(() => setMinutes(readReminderMinutes()), []);

  return (
    <article className="gm-panel gm-tool" aria-labelledby={titleId} id="reminder">
      <div className="gm-tool__head">
        <p className="gm-label">{t.deviceTitle}</p>
        <h2 id={titleId} className="gm-h">
          {t.reminderTitle}
        </h2>
        <p className="gm-small">{t.reminderIntro}</p>
      </div>
      <div className="gm-chips" role="group" aria-label={t.reminderOptions}>
        {REMINDER_OPTIONS.map((option) => (
          <button
            key={option}
            type="button"
            className="gm-chip"
            aria-pressed={minutes === option}
            onClick={() => {
              setMinutes(option);
              writeReminderMinutes(option);
            }}
          >
            {option === 0 ? t.reminderOff : t.reminderEvery(option)}
          </button>
        ))}
      </div>
    </article>
  );
}

/** A door to the writing page, which is a page of its own and not a view. */
function WritingCard() {
  const titleId = useId();
  return (
    <article className="gm-panel gm-tool" aria-labelledby={titleId}>
      <Head id={titleId} title={t.writeTitle} intro={t.writeIntro} />
      <Link href="/write" prefetch={false} className="btn btn--secondary justify-self-start">
        {t.writeLink}
      </Link>
    </article>
  );
}

const MESSAGE_STATUS: Record<PlayerMessage["status"], string> = {
  NEW: t.messageNew,
  SEEN: t.messageSeen,
  ANSWERED: t.messageAnswered,
};

function ContactCard() {
  const titleId = useId();
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
    <article className="gm-panel gm-tool" aria-labelledby={titleId}>
      <Head id={titleId} title={t.contactTitle} intro={t.contactIntro} />

      <form onSubmit={submit} className="grid gap-3">
        <label htmlFor={bodyId} className="sr-only">
          {t.contactTitle}
        </label>
        <textarea
          id={bodyId}
          className="field"
          maxLength={2000}
          placeholder={t.contactPlaceholder}
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
        <button
          type="submit"
          className="btn btn--secondary justify-self-start"
          disabled={busy || !body.trim()}
        >
          {busy ? t.contactSending : t.contactSend}
        </button>
      </form>
      <FlashLine flash={flash} />

      {messages.length > 0 ? (
        <div className="grid gap-3">
          <h3 className="gm-label">{t.contactHistory}</h3>
          <ul className="gm-messages">
            {messages.map((message) => (
              <li key={message.id}>
                <p className="flex items-center justify-between gap-2 gm-small">
                  <span>{dateTimeUtc(message.created_at)}</span>
                  <span className="gm-tag">{MESSAGE_STATUS[message.status]}</span>
                </p>
                <p className="whitespace-pre-wrap">{message.body}</p>
                {message.reply_body ? (
                  <div className="gm-reply">
                    <p className="gm-label">{t.contactReply}</p>
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
  const titleId = useId();
  const [leaving, setLeaving] = useState(false);

  async function leave() {
    setLeaving(true);
    await signOut();
    router.push("/");
    router.refresh();
  }

  return (
    <article className="gm-panel gm-tool" aria-labelledby={titleId}>
      <Head
        id={titleId}
        title={t.signOut}
        intro={player.is_guest ? t.accountSignOutGuest : t.accountSignOutNote}
      />
      <button
        type="button"
        className="btn btn--secondary justify-self-start"
        onClick={() => void leave()}
        disabled={leaving}
      >
        {leaving ? t.signingOut : t.signOut}
      </button>
    </article>
  );
}

function EraseCard() {
  const { player } = usePlayer();
  const router = useRouter();
  const titleId = useId();
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
    <article className="gm-panel gm-tool" aria-labelledby={titleId}>
      <Head id={titleId} title={t.eraseTitle} intro={t.eraseIntro} />

      {open ? (
        <form onSubmit={erase} className="gm-confirm">
          {player.is_guest ? (
            <p className="gm-small text-ink">{t.eraseConfirmGuest}</p>
          ) : (
            <div className="grid gap-2">
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
            </div>
          )}
          <div className="btn-row">
            <button
              type="submit"
              className="btn btn-danger"
              disabled={busy || (!player.is_guest && !password)}
            >
              {busy ? t.erasing : t.eraseButton}
            </button>
            <button type="button" className="gm-quiet" onClick={() => setOpen(false)}>
              {t.cancel}
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          className="btn btn-danger justify-self-start"
          onClick={() => setOpen(true)}
        >
          {t.eraseButton}
        </button>
      )}
      <FlashLine flash={flash} />
    </article>
  );
}
