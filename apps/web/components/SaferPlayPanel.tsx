"use client";

import Link from "next/link";
import { useEffect, useId, useState, type CSSProperties, type FormEvent } from "react";

import { usePlayer } from "@/components/PlayerProvider";
import { SpendLimitCard } from "@/components/Shop";
import { Figure } from "@/components/viz/Figure";
import { getRealityCheck, setDailyLimit, takeBreak, type ApiFailure } from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import {
  count,
  dateTimeUtc,
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
 * Everything on this view is enforced by the server. The page only asks; it
 * does not decide, and it never offers a way round — there is no "end break"
 * button to disable because there is no route for one to call. Calm on
 * purpose: no accent, no alarm colour, the rules stated beside each control.
 */
export function SaferPlayPanel() {
  return (
    <section className="gm-feed" aria-labelledby="gm-view-title">
      <div className="gm-tools">
        <DailyLimitCard />
        <BreakCard />
      </div>
      <SpendLimitCard />
      <RealityCheckCard />
      <p className="gm-note gm-note--line">
        {t.helpPrompt}{" "}
        <Link href="/help" prefetch={false} className="gm-link">
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
    <article className="gm-panel gm-tool" aria-labelledby="gm-record-title">
      <div className="gm-tool__head">
        <h2 id="gm-record-title" className="gm-h">
          {t.realityTitle}
        </h2>
        <p className="gm-small">{t.realityIntro}</p>
      </div>

      {error ? (
        <p role="alert" className="gm-note gm-error">
          {error}
        </p>
      ) : !record ? (
        <p className="gm-small" role="status">
          {t.loading}
        </p>
      ) : record.slips_settled === 0 ? (
        <p className="gm-empty">{t.realityEmpty}</p>
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
      <dl className="gm-stats">
        <Stat label={t.statForecasts} value={String(record.slips_settled)} />
        <Stat label={t.statRight} value={t.ofTotal(record.slips_won, record.slips_settled)} />
        <Stat label={t.statPicks} value={t.ofTotal(record.picks_correct, record.picks_settled)} />
        <Stat label={t.statOpen} value={String(record.slips_open)} />
        <Stat label={t.statStaked} value={count(staked)} />
        <Stat label={t.statReturned} value={count(returned)} />
        <Stat label={t.statNet} value={signed(net)} />
        <Stat label={t.statActive} value={String(record.active_days_30d)} />
      </dl>

      <div className="gm-sub">
        <h3 className="gm-h gm-h--sm">{t.marginTitle}</h3>
        <p className="gm-small">{t.marginBody(margin)}</p>
        {record.margin_cost.minor > 0 ? (
          <>
            <p className="gm-h">
              <Figure
                text={t.marginCost(
                  marginCost > 0 ? `${count(marginCost)} ${t.pointsUnit}` : t.marginLessThanOne,
                )}
              />
            </p>
            <p className="gm-small">
              <Figure text={t.marginNet(signed(net), signed(netWithMargin))} />
            </p>
          </>
        ) : (
          <p className="gm-small text-ink">{t.marginNone}</p>
        )}
        <p className="gm-small">{t.marginFootnote}</p>
      </div>

      {calibrated.length > 0 ? (
        <div className="grid gap-2">
          <h3 className="gm-h gm-h--sm">{t.calibrationTitle}</h3>
          <p className="gm-small">{t.calibrationIntro}</p>
          <div className="overflow-x-auto">
            <table className="gm-cal">
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
                    <td>{t.calibrationRange(percent(bucket.low), percent(bucket.high))}</td>
                    <td className="num">{bucket.picks}</td>
                    <td className="num">{percent(bucket.correct / bucket.picks)}</td>
                    <td className="num">{bucket.expected ? percent(bucket.expected) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        <Figure text={value} />
      </dd>
    </div>
  );
}

// ----- daily limit ----------------------------------------------------------

function describe(failure: ApiFailure): string {
  return failure.code === "limit_locked" && failure.until
    ? t.limitLockedUntil(dateTimeUtc(failure.until))
    : errorMessage(failure.code);
}

function DailyLimitCard() {
  const { player, applyLimits } = usePlayer();
  const { limits } = player;
  const fieldId = useId();
  const noteId = useId();

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

  const limit = limits.daily_limit;
  const used = limit && limit.minor > 0 ? Math.min(100, (limits.daily_spent.minor / limit.minor) * 100) : 0;

  return (
    <article className="gm-panel gm-tool" aria-labelledby="gm-limit-title">
      <div className="gm-tool__head">
        <h2 id="gm-limit-title" className="gm-h">
          {t.limitTitle}
        </h2>
        <p className="gm-small">{t.limitIntro}</p>
      </div>

      <div className="gm-now">
        {limit ? (
          <>
            <p className="gm-label">{t.limitStakedToday}</p>
            <p className="gm-now__figure">
              <Figure text={t.limitOf(limits.daily_spent.display, limit.display)} />
            </p>
            <div
              className="gm-meter"
              role="img"
              aria-label={t.limitMeter(limits.daily_spent.display, limit.display)}
              style={{ "--gm-used": `${used}%` } as CSSProperties}
            >
              <span />
            </div>
            <p className="gm-small">{t.limitCurrent(limit.display)}</p>
          </>
        ) : (
          <>
            <p className="gm-h">{t.limitNone}</p>
            <p className="gm-small">
              <Figure text={t.limitSpent(limits.daily_spent.display)} />
            </p>
          </>
        )}
        {limit && limits.daily_limit_loosen_at ? (
          <p className="gm-small">{t.limitLockedUntil(dateTimeUtc(limits.daily_limit_loosen_at))}</p>
        ) : null}
      </div>

      <form onSubmit={submit} className="grid gap-2">
        <label htmlFor={fieldId} className="label">
          {t.limitField}
        </label>
        <div className="gm-inline">
          <input
            id={fieldId}
            className="field"
            inputMode="numeric"
            autoComplete="off"
            value={draft}
            aria-describedby={noteId}
            onChange={(event) => setDraft(event.target.value)}
          />
          <button type="submit" className="btn btn--secondary" disabled={busy || !draft.trim()}>
            {busy ? t.saving : t.limitSet}
          </button>
        </div>
      </form>

      {/* Offered only once the limit has stood long enough to be removed.
          While it has not, the line above already says when it will have —
          a button that can only ever answer "not yet" is noise. */}
      {limit && !limits.daily_limit_loosen_at ? (
        <button
          type="button"
          className="gm-quiet justify-self-start"
          onClick={() => void save(null)}
          disabled={busy}
        >
          {t.limitRemove}
        </button>
      ) : null}

      {message ? (
        <p role={message.ok ? "status" : "alert"} className={message.ok ? "gm-note" : "gm-note gm-error"}>
          {message.text}
        </p>
      ) : null}

      <p id={noteId} className="gm-tool__rule">
        {t.limitRule}
      </p>
    </article>
  );
}

// ----- break ----------------------------------------------------------------

function BreakCard() {
  const { player, applyLimits, onBreak } = usePlayer();
  const { limits } = player;
  const confirmTitleId = useId();

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
    <article className="gm-panel gm-tool" aria-labelledby="gm-break-title">
      <div className="gm-tool__head">
        <h2 id="gm-break-title" className="gm-h">
          {t.breakTitle}
        </h2>
        <p className="gm-small">{t.breakIntro}</p>
      </div>

      {onBreak && limits.break_until ? (
        <div className="gm-now">
          <p className="gm-label">{t.breakLabel}</p>
          <p className="gm-h">{t.breakActive(dateTimeUtc(limits.break_until))}</p>
        </div>
      ) : null}

      <div className="grid gap-2">
        <p className="label">{onBreak ? t.breakExtend : t.breakLength}</p>
        <div className="gm-chips" role="group" aria-label={t.breakOptions}>
          {limits.break_options_hours.map((hours) => (
            <button
              key={hours}
              type="button"
              className="gm-chip"
              aria-pressed={pending === hours}
              onClick={() => {
                setMessage(null);
                setPending(hours);
              }}
            >
              {duration(hours)}
            </button>
          ))}
        </div>
      </div>

      {pending !== null ? (
        <div role="alertdialog" aria-modal="false" aria-labelledby={confirmTitleId} className="gm-confirm">
          <p id={confirmTitleId} className="gm-h gm-h--sm">
            {t.breakConfirmTitle(duration(pending))}
          </p>
          <p className="gm-small">{t.breakConfirmBody}</p>
          <div className="btn-row">
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => void confirm()}
              disabled={busy}
            >
              {busy ? t.working : t.breakConfirm}
            </button>
            <button
              type="button"
              className="gm-quiet"
              onClick={() => setPending(null)}
              disabled={busy}
            >
              {t.cancel}
            </button>
          </div>
        </div>
      ) : null}

      {message ? (
        <p role={message.ok ? "status" : "alert"} className={message.ok ? "gm-note" : "gm-note gm-error"}>
          {message.text}
        </p>
      ) : null}

      <p className="gm-tool__rule">{t.breakRule}</p>
    </article>
  );
}
