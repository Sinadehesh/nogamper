"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { asOf } from "@/lib/content";
import { t } from "@/lib/copy";
import { dateTimeUtc } from "@/lib/format";

/**
 * "As of …": the moment a page's figures describe, and a way out of it.
 *
 * The pages that show this are built once, kept, and handed to the next
 * visitor as they are while a newer copy is built behind them. On a quiet
 * site that next visitor may arrive hours later. So the page prints when its
 * figures are from — and where they are old and still changing, this looks
 * for the newer copy and shows it when it exists, rather than leaving the
 * reader with the old one.
 *
 * It looks a few times over about two minutes, which is how long a resting
 * server takes to wake and read its figures again, and then stops and says
 * so. Nothing here polls for ever.
 */

/** Older than this, figures that are still changing are worth asking about again. */
const STALE_AFTER_MS = 15 * 60_000;

/**
 * When to look, counted from when the page was opened. The first is soon, for
 * the usual case of a server that is awake. The rest outlast one that is not:
 * each look is answered with the copy that exists and starts a newer one
 * being built, so it is the look after that which finds it.
 */
const LOOK_AT_MS = [4_000, 15_000, 40_000, 70_000, 100_000, 130_000];
const GIVE_UP_AT_MS = 140_000;

/** Marks the line in the page's own HTML, so that a copy fetched to see how
 * new it is can be asked. */
const MARK = "data-as-of";

type Props = {
  /** When the figures were read. */
  at: string;
  /** Whether they are still changing. A finished question's are not. */
  changing: boolean;
  /** Extra classes for where the page puts the line. */
  className?: string;
};

/** The time printed on the copy of this page the server would hand out now. */
async function newestCopyIsFrom(): Promise<number | null> {
  // The page itself, as a document. One request, where asking the router to
  // refresh costs that and one more for every link on the screen.
  const response = await fetch(window.location.pathname, { cache: "no-store" });
  if (!response.ok) return null;
  const copy = new DOMParser().parseFromString(await response.text(), "text/html");
  const printed = copy.querySelector(`time[${MARK}]`)?.getAttribute("datetime");
  const time = printed ? Date.parse(printed) : Number.NaN;
  return Number.isFinite(time) ? time : null;
}

export function AsOf({ at, changing, className }: Props) {
  const router = useRouter();
  const [state, setState] = useState<"current" | "looking" | "gave-up">("current");
  // Counts the reader's own "try again"s, so that each starts the looking over.
  const [round, setRound] = useState(0);

  useEffect(() => {
    // Decided here and not while rendering: "old" is measured against the
    // reader's clock, which the server that built the page does not have.
    const mine = new Date(at).getTime();
    if (!changing || Date.now() - mine <= STALE_AFTER_MS) {
      setState("current");
      return;
    }

    setState("looking");
    let over = false;
    const look = async () => {
      try {
        const theirs = await newestCopyIsFrom();
        // A newer copy exists: take it. That changes `at`, which ends this
        // round of looking.
        if (!over && theirs !== null && theirs > mine) router.refresh();
      } catch {
        // Offline, or the request was cut short. The next look tries again.
      }
    };

    // Somebody who presses "try again" is answered now, not in four seconds.
    if (round > 0) void look();
    const timers = LOOK_AT_MS.map((delay) => window.setTimeout(look, delay));
    timers.push(window.setTimeout(() => setState("gave-up"), GIVE_UP_AT_MS));
    return () => {
      over = true;
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [at, changing, round, router]);

  return (
    <p className={`text-sm leading-normal text-muted ${className ?? ""}`}>
      {asOf.label}{" "}
      <time dateTime={at} className="text-ink/80" {...{ [MARK]: "" }}>
        {dateTimeUtc(at)}
      </time>
      {". "}
      {asOf.zone}{" "}
      <span role="status">
        {state === "looking" ? asOf.looking : null}
        {state === "gave-up" ? (
          <>
            {asOf.gaveUp}{" "}
            <button
              type="button"
              className="min-h-11 font-medium text-ink underline decoration-line-strong underline-offset-4 hover:decoration-current"
              onClick={() => setRound((previous) => previous + 1)}
            >
              {t.retry}
            </button>
          </>
        ) : null}
      </span>
    </p>
  );
}
