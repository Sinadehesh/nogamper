"use client";

import { useEffect, useState } from "react";

import { t } from "@/lib/copy";

/**
 * A nudge after the player has been here a while.
 *
 * Betting products are built to make time disappear; this is the opposite
 * mechanism, the same "reality check" a regulated operator is required to
 * offer. It is a preference of this device rather than of the account — it
 * lives in localStorage — because it costs nothing to keep there and a
 * reminder is not something a server needs to enforce.
 *
 * On by default, at half an hour. Opting out is one tap, on the account view
 * or from the reminder itself.
 */

const STORAGE_KEY = "session-reminder-minutes";
const CHANGED_EVENT = "session-reminder-changed";
const DEFAULT_MINUTES = 30;

export const REMINDER_OPTIONS = [0, 15, 30, 60] as const;

export function readReminderMinutes(): number {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === null) return DEFAULT_MINUTES;
    const minutes = Number(stored);
    return (REMINDER_OPTIONS as readonly number[]).includes(minutes) ? minutes : DEFAULT_MINUTES;
  } catch {
    // Storage can be unavailable — private windows, blocked site data. The
    // reminder still works at its default; it just cannot be changed.
    return DEFAULT_MINUTES;
  }
}

export function writeReminderMinutes(minutes: number): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, String(minutes));
  } catch {
    // See above.
  }
  window.dispatchEvent(new Event(CHANGED_EVENT));
}

export function SessionReminder({
  onTakeBreak,
  onSettings,
}: {
  onTakeBreak: () => void;
  /** Opens the place the reminder is set, so turning it off is one tap away. */
  onSettings?: () => void;
}) {
  const [interval, setIntervalMinutes] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [dismissedAt, setDismissedAt] = useState(0);

  useEffect(() => {
    setIntervalMinutes(readReminderMinutes());
    const onChange = () => setIntervalMinutes(readReminderMinutes());
    window.addEventListener(CHANGED_EVENT, onChange);
    return () => window.removeEventListener(CHANGED_EVENT, onChange);
  }, []);

  useEffect(() => {
    // Counts minutes with the tab in front. Time spent with it in the
    // background is not time spent here.
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") setElapsed((minutes) => minutes + 1);
    }, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const due = interval > 0 && elapsed > 0 && elapsed - dismissedAt >= interval;
  if (!due) return null;

  return (
    <div role="status" className="gm-toast gm">
      <p className="gm-h gm-h--sm">{t.reminderHeadline(elapsed)}</p>
      <p className="gm-small">{t.reminderBody}</p>
      <div className="btn-row">
        <button
          type="button"
          className="btn btn--secondary btn-sm"
          onClick={() => {
            setDismissedAt(elapsed);
            onTakeBreak();
          }}
        >
          {t.reminderBreak}
        </button>
        <button type="button" className="gm-quiet" onClick={() => setDismissedAt(elapsed)}>
          {t.reminderContinue}
        </button>
        {onSettings ? (
          <button
            type="button"
            className="gm-quiet"
            onClick={() => {
              setDismissedAt(elapsed);
              onSettings();
            }}
          >
            {t.reminderChange}
          </button>
        ) : null}
      </div>
    </div>
  );
}
