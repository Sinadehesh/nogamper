"use client";


import { useCallback, useEffect, useState } from "react";

import { getMyMessages, sendMessage } from "@/lib/api";
import { coins, count } from "@/lib/format";
import { fa, translateError } from "@/lib/i18n";
import { shareInviteLink } from "@/lib/share";
import type { Money, PlayerMessage, UserProfile } from "@/lib/types";

const STATUS_LABEL: Record<PlayerMessage["status"], string> = {
  NEW: fa.prizeStatusNew,
  SEEN: fa.prizeStatusSeen,
  ANSWERED: fa.prizeStatusAnswered,
};

export function PrizePanel({
  profile,
  referralBonus,
  signupBonus,
}: {
  profile: UserProfile;
  referralBonus: Money | null;
  signupBonus: Money | null;
}) {
  const [body, setBody] = useState("");
  const [asClaim, setAsClaim] = useState(true);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<"code" | "id" | "invite" | null>(null);
  const [history, setHistory] = useState<PlayerMessage[]>([]);

  const load = useCallback(async () => {
    const result = await getMyMessages();
    if (result.ok) setHistory(result.data.messages);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const submit = useCallback(async () => {
    if (!body.trim() || sending) return;
    setSending(true);
    setError(null);

    const result = await sendMessage(
      body.trim(),
      asClaim ? "PRIZE_CLAIM" : "MESSAGE",
    );
    setSending(false);

    if (result.ok) {
      setBody("");
      setSent(true);
      await load();
    } else {
      setError(translateError(result.code, result.detail));
    }
  }, [body, asClaim, sending, load]);

  const copy = useCallback(
    async (what: "code" | "id" | "invite", value: string) => {
      try {
        await navigator.clipboard.writeText(value);
        setCopied(what);
        setTimeout(() => setCopied(null), 1800);
      } catch {
      }
    },
    [],
  );

  const share = useCallback(async () => {
    if (!profile.invite_link || !referralBonus || !signupBonus) return;
    const outcome = await shareInviteLink(
      profile.invite_link,
      fa.inviteShareText(signupBonus.display, referralBonus.display),
    );
    if (outcome === "copied") {
      setCopied("invite");
      setTimeout(() => setCopied(null), 1800);
    }
  }, [profile.invite_link, referralBonus, signupBonus]);

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <h2 className="text-lg font-black">{fa.prizeTitle}</h2>
        <p className="text-sm leading-relaxed text-tg-hint">{fa.prizeIntro}</p>
      </header>

      <div className="flex items-center justify-between gap-3 rounded-2xl bg-tg-secondary-bg px-4 py-3">
        <div className="flex flex-col gap-0.5">
          <span className="text-[11px] text-tg-hint">{fa.prizeCodeLabel}</span>
          <span
            className="font-mono text-xl font-black tracking-[0.2em]"
            dir="ltr"
          >
            {profile.player_code}
          </span>
          <span className="text-[11px] leading-relaxed text-tg-hint">
            {fa.prizeCodeHint}
          </span>
          {/* The player's own Telegram ID, shown only to them.
           *
           * It is here because the operator could not turn their own admin
           * access on: ADMIN_TELEGRAM_IDS wants a numeric Telegram ID, and
           * finding it meant leaving the app for a third-party bot. The app
           * already knows the number — it authenticated with it — so not
           * showing it was making the person read their own ID out of
           * somebody else's service. */}
          <button
            type="button"
            onClick={() => void copy("id", String(profile.telegram_id))}
            className="pt-1 text-start text-[11px] text-tg-hint"
          >
            {fa.prizeTelegramIdLabel}:{" "}
            <span className="font-mono underline decoration-dotted" dir="ltr">
              {profile.telegram_id}
            </span>{" "}
            {copied === "id" ? fa.prizeCodeCopied : ""}
          </button>
        </div>
        <button
          type="button"
          onClick={() => void copy("code", profile.player_code)}
          className="shrink-0 rounded-xl bg-tg-button px-3 py-2 text-xs font-bold text-tg-button-text"
        >
          {copied === "code" ? fa.prizeCodeCopied : "کپی"}
        </button>
      </div>

      {/* Built from the same player_code above via start_param, so this is
       *  a third view of one identifier rather than a second system. Absent
       *  entirely when the server has not configured the bot username and
       *  Mini App short name — see UserProfile.invite_link. */}
      {profile.invite_link ? (
        <div className="flex flex-col gap-2 rounded-2xl border border-[#e8b73a]/35 bg-[#e8b73a]/10 px-4 py-3">
          <span className="text-sm font-bold text-[#e8b73a]">
            {fa.inviteTitle}
          </span>
          {referralBonus ? (
            <span className="text-xs leading-relaxed text-tg-hint">
              {fa.inviteBody(referralBonus.display)}
            </span>
          ) : null}
          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={() => void share()}
              className="flex-1 rounded-xl bg-[#e8b73a] px-3 py-2 text-xs font-bold text-black"
            >
              {copied === "invite" ? fa.inviteLinkCopied : fa.inviteShare}
            </button>
            <button
              type="button"
              onClick={() => void copy("invite", profile.invite_link ?? "")}
              className="shrink-0 rounded-xl border border-[#e8b73a]/45 px-3 py-2 text-xs font-bold text-[#e8b73a]"
            >
              {fa.inviteCopyLink}
            </button>
          </div>
          {profile.referred_count > 0 ? (
            <span className="text-[11px] text-tg-hint">
              {fa.inviteStatsReferred(count(profile.referred_count))}
              {" · "}
              {fa.inviteStatsEarned(coins(profile.referral_earned.minor))}
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-col gap-2">
        <textarea
          value={body}
          onChange={(e) => {
            setBody(e.target.value);
            setSent(false);
          }}
          rows={4}
          maxLength={2000}
          placeholder={fa.prizePlaceholder}
          className="w-full resize-none rounded-2xl bg-tg-secondary-bg px-4 py-3 text-sm
                     leading-relaxed text-tg-text placeholder:text-tg-hint
                     focus:outline-none focus:ring-2 focus:ring-tg-button"
        />

        <label className="flex items-center gap-2 px-1 text-xs text-tg-hint">
          <input
            type="checkbox"
            checked={asClaim}
            onChange={(e) => setAsClaim(e.target.checked)}
            className="size-4 accent-[var(--color-boost)]"
          />
          {fa.prizeAsClaim}
        </label>

        {error ? (
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {error}
          </p>
        ) : null}
        {sent ? (
          <p className="rounded-xl bg-[color-mix(in_srgb,var(--color-yes)_15%,transparent)] px-3 py-2 text-sm">
            {fa.prizeSent}
          </p>
        ) : null}

        <button
          type="button"
          disabled={!body.trim() || sending}
          onClick={submit}
          className="w-full rounded-2xl bg-tg-button px-4 py-3.5 text-base font-bold
                     text-tg-button-text disabled:opacity-40"
        >
          {sending ? fa.prizeSending : fa.prizeSend}
        </button>

        <p className="px-1 text-[11px] leading-relaxed text-tg-hint">
          {fa.prizeNoValueNote}
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-bold">{fa.prizeHistory}</h3>
        {history.length === 0 ? (
          <p className="text-sm text-tg-hint">{fa.prizeEmpty}</p>
        ) : (
          history.map((message) => (
            <article
              key={message.id}
              className="flex flex-col gap-1 rounded-2xl bg-tg-secondary-bg px-4 py-3"
            >
              <div className="flex items-center justify-between gap-2 text-[11px] text-tg-hint">
                <span>
                  {message.kind === "PRIZE_CLAIM"
                    ? fa.prizeKindClaim
                    : fa.prizeKindMessage}
                </span>
                <span
                  className={
                    message.status === "ANSWERED"
                      ? "font-bold text-[var(--color-yes)]"
                      : "font-bold"
                  }
                >
                  {STATUS_LABEL[message.status]}
                </span>
              </div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed">
                {message.body}
              </p>
              {/* The operator's answer, in the place the question was asked.
               *
               * Also delivered to them in Telegram by the bot — but a bot
               * cannot open a conversation the player has not opened first, so
               * for some players this is the only place the answer arrives.
               * That is the reason it is stored rather than only sent. */}
              {message.reply_body ? (
                <div className="mt-1 rounded-xl border-s-2 border-[var(--color-yes)] bg-tg-bg px-3 py-2">
                  <span className="text-[11px] text-tg-hint">
                    {fa.prizeReplyLabel}
                  </span>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">
                    {message.reply_body}
                  </p>
                </div>
              ) : null}
            </article>
          ))
        )}
      </div>
    </section>
  );
}
