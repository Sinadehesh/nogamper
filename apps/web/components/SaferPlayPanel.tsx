"use client";

import Link from "next/link";
import { useEffect, useId, useState, type FormEvent } from "react";

import { usePlayer } from "@/components/PlayerProvider";
import { REMINDER_OPTIONS, readReminderMinutes, writeReminderMinutes } from "@/components/SessionReminder";
import { SpendLimitCard } from "@/components/Shop";
import { getRealityCheck, setDailyLimit, takeBreak, type ApiFailure } from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import {
  count,
  dateTime,
  duration,
  parsePoints,
  percent,
  signed,
  wholePoints,
} from "@/lib/format";
import type { RealityCheck } from "@/lib/types";

/**
 * The player's own brakes, and their own record.
 *
 * Everything on this tab is enforced by the server. The page only asks; it
 * does not decide, and it never offers a way round — there is no "end break"
 * button to disable because there is no route for one to call.
 */
export function SaferPlayPanel() {
  return (
    <section className="space-y-4">
      <p className="text-sm text-muted">{t.saferIntro}</p>
      <RealityCheckCard />
      <div className="grid gap-4 md:grid-cols-2">
        <DailyLimitCard />
        <BreakCard />
      </div>
      <SpendLimitCard />
      <ReminderCard />
      <p className="notice">
        {t.helpPrompt}{" "}
        <Link href="/help" className="font-semibold text-accent underline underline-offset-2">
          {t.helpLink}
        </Link>
      </p>
    </section>
  );
}

// ----- reality check --------------------------------------------------------

function RealityCheckCard() {
  const { refresh } = usePlayer();
  const [record, setRecord] = useState<RealityCheck | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getRealityCheck().then((result) => {
      if (cancelled) return;
      if (result.ok) setRecord(result.data);
      else {
        if (result.status === 401) void refresh();
        setError(errorMessage(result.code));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  return (
    <article className="card p-5">
      <h2 className="text-lg font-bold">{t.realityTitle}</h2>
      <p className="text-sm text-muted">{t.realityIntro}</p>

      {error ? (
        <p role="alert" className="notice notice-error mt-4">
          {error}
        </p>
      ) : !record ? (
        <p className="mt-4 text-muted">{t.loading}</p>
      ) : record.slips_settled === 0 ? (
        <p className="mt-4 text-muted">{t.realityEmpty}</p>
      ) : (
        <RecordBody record={record} />
      )}
    </article>
  );
}

function RecordBody({ record }: { record: RealityCheck }) {
  const margin = percent(record.reference_margin);
  const calibrated = record.calibration.filter((bucket) => bucket.picks > 0);

  // Whole points throughout, with each result worked out from the figures
  // printed beside it. This is the one card whose whole purpose is that the
  // numbers can be trusted; a net that is one point off the reader's own
  // subtraction would undo it.
  const staked = wholePoints(record.staked.minor);
  const returned = wholePoints(record.returned.minor);
  const net = returned - staked;
  const marginCost = wholePoints(record.margin_cost.minor);
  const netWithMargin = net - marginCost;

  return (
    <>
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
        <Stat label={t.statForecasts} value={String(record.slips_settled)} />
        <Stat label={t.statRight} value={t.ofTotal(record.slips_won, record.slips_settled)} />
        <Stat
          label={t.statPicks}
          value={t.ofTotal(record.picks_correct, record.picks_settled)}
        />
        <Stat label={t.statOpen} value={String(record.slips_open)} />
        <Stat label={t.statStaked} value={count(staked)} />
        <Stat label={t.statReturned} value={count(returned)} />
        <Stat label={t.statNet} value={signed(net)} tone={net >= 0 ? "text-yes" : "text-no"} />
        <Stat label={t.statActive} value={String(record.active_days_30d)} />
      </dl>

      <div className="mt-5 rounded-xl border border-line bg-sunken p-4">
        <h3 className="font-bold">{t.marginTitle}</h3>
        <p className="mt-1 text-sm text-muted">{t.marginBody(margin)}</p>
        {record.margin_cost.minor > 0 ? (
          <>
            <p className="mt-3 text-lg font-bold">
              {t.marginCost(
                marginCost > 0 ? `${count(marginCost)} ${t.pointsUnit}` : t.marginLessThanOne,
              )}
            </p>
            <p className="text-sm text-muted tabular-nums">
              {t.marginNet(signed(net), signed(netWithMargin))}
            </p>
          </>
        ) : (
          <p className="mt-3 text-sm">{t.marginNone}</p>
        )}
        <p className="mt-3 text-xs text-muted">{t.marginFootnote}</p>
      </div>

      {calibrated.length > 0 ? (
        <div className="mt-5">
          <h3 className="font-bold">{t.calibrationTitle}</h3>
          <p className="mt-1 text-sm text-muted">{t.calibrationIntro}</p>
          <table className="table mt-3">
            <thead>
              <tr>
                <th scope="col">{t.calibrationBand}</th>
                <th scope="col" className="num">
                  {t.calibrationPicks}
                </th>
                <th scope="col" className="num">
                  {t.calibrationHit}
                </th>
                <th scope="col" className="num">
                  {t.calibrationExpected}
                </th>
              </tr>
            </thead>
            <tbody>
              {calibrated.map((bucket) => (
                <tr key={bucket.low}>
                  <td className="tabular-nums">
                    {t.calibrationRange(percent(bucket.low), percent(bucket.high))}
                  </td>
                  <td className="num">{bucket.picks}</td>
                  <td className="num">{percent(bucket.correct / bucket.picks)}</td>
                  <td className="num">{bucket.expected ? percent(bucket.expected) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  );
}

function Stat({ label, value, tone = "" }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={`text-xl font-bold tabular-nums ${tone}`}>{value}</dd>
    </div>
  );
}

// ----- daily limit ----------------------------------------------------------

function describe(failure: ApiFailure): string {
  return failure.code === "limit_locked" && failure.until
    ? t.limitLockedUntil(dateTime(failure.until))
    : errorMessage(failure.code);
}

function DailyLimitCard() {
  const { player, applyLimits } = usePlayer();
  const { limits } = player;
  const fieldId = useId();

  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function save(minor: number | null) {
    setBusy(true);
    setMessage(null);
    const result = await setDailyLimit(minor);
    setBusy(false);
    if (result.ok) {
      applyLimits(result.data);
      setDraft("");
      setMessage({ ok: true, text: t.limitSaved });
    } else {
      setMessage({ ok: false, text: describe(result) });
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const minor = parsePoints(draft);
    if (minor > 0) void save(minor);
  }

  return (
    <article className="card p-5">
      <h2 className="text-lg font-bold">{t.limitTitle}</h2>
      <p className="text-sm text-muted">{t.limitIntro}</p>

      <p className="mt-4 font-semibold">
        {limits.daily_limit ? t.limitCurrent(limits.daily_limit.display) : t.limitNone}
      </p>
      <p className="text-sm text-muted">{t.limitSpent(limits.daily_spent.display)}</p>
      {limits.daily_limit && limits.daily_limit_loosen_at ? (
        <p className="mt-1 text-sm text-muted">
          {t.limitLockedUntil(dateTime(limits.daily_limit_loosen_at))}
        </p>
      ) : null}

      <form onSubmit={submit} className="mt-4">
        <label htmlFor={fieldId} className="label">
          {t.limitField}
        </label>
        <div className="flex gap-2">
          <input
            id={fieldId}
            className="field tabular-nums"
            inputMode="numeric"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <button type="submit" className="btn btn-primary shrink-0" disabled={busy || !draft.trim()}>
            {busy ? t.saving : t.limitSet}
          </button>
        </div>
      </form>

      {/* Offered only once the limit has stood long enough to be removed.
          While it has not, the line above already says when it will have —
          a button that can only ever answer "not yet" is noise. */}
      {limits.daily_limit && !limits.daily_limit_loosen_at ? (
        <button
          type="button"
          className="btn btn-quiet btn-sm mt-2"
          onClick={() => void save(null)}
          disabled={busy}
        >
          {t.limitRemove}
        </button>
      ) : null}

      {message ? (
        <p
          role={message.ok ? "status" : "alert"}
          className={`notice mt-3 ${message.ok ? "notice-ok" : "notice-error"}`}
        >
          {message.text}
        </p>
      ) : null}

      <p className="hint mt-3">{t.limitRule}</p>
    </article>
  );
}

// ----- break ----------------------------------------------------------------

function BreakCard() {
  const { player, applyLimits, onBreak } = usePlayer();
  const { limits } = player;

  const [pending, setPending] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function confirm() {
    if (pending === null) return;
    setBusy(true);
    const result = await takeBreak(pending);
    setBusy(false);
    setPending(null);
    if (result.ok) {
      applyLimits(result.data);
      setMessage({ ok: true, text: t.breakStarted });
    } else {
      setMessage({ ok: false, text: errorMessage(result.code) });
    }
  }

  return (
    <article className="card p-5">
      <h2 className="text-lg font-bold">{t.breakTitle}</h2>
      <p className="text-sm text-muted">{t.breakIntro}</p>

      {onBreak && limits.break_until ? (
        <p className="notice notice-warn mt-4 font-semibold">
          {t.breakActive(dateTime(limits.break_until))}
        </p>
      ) : null}

      <p className="label mt-4">{onBreak ? t.breakExtend : t.breakLength}</p>
      <div className="flex flex-wrap gap-2">
        {limits.break_options_hours.map((hours) => (
          <button
            key={hours}
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => {
              setMessage(null);
              setPending(hours);
            }}
          >
            {duration(hours)}
          </button>
        ))}
      </div>

      {pending !== null ? (
        <div role="alertdialog" aria-modal="false" className="notice notice-warn mt-3">
          <p className="font-bold">{t.breakConfirmTitle(duration(pending))}</p>
          <p className="mt-1 text-sm">{t.breakConfirmBody}</p>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => void confirm()}
              disabled={busy}
            >
              {busy ? t.working : t.breakConfirm}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setPending(null)}
              disabled={busy}
            >
              {t.cancel}
            </button>
          </div>
        </div>
      ) : null}

      {message ? (
        <p
          role={message.ok ? "status" : "alert"}
          className={`notice mt-3 ${message.ok ? "notice-ok" : "notice-error"}`}
        >
          {message.text}
        </p>
      ) : null}

      <p className="hint mt-3">{t.breakRule}</p>
    </article>
  );
}

// ----- session reminder -----------------------------------------------------

function ReminderCard() {
  const [minutes, setMinutes] = useState(0);
  useEffect(() => setMinutes(readReminderMinutes()), []);

  return (
    <article className="card p-5">
      <h2 className="text-lg font-bold">{t.reminderTitle}</h2>
      <p className="text-sm text-muted">{t.reminderIntro}</p>
      <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label={t.reminderTitle}>
        {REMINDER_OPTIONS.map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={minutes === option}
            className={`btn btn-sm ${minutes === option ? "btn-primary" : "btn-secondary"}`}
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
