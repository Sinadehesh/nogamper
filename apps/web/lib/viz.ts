/**
 * The arithmetic and the words behind the site's charts and figures.
 *
 * Everything here is a pure function of the data the API publishes, so it
 * runs the same on the server that draws a page and in the browser that
 * makes it interactive. No clock is read anywhere: a page built once and
 * cached says what was true at its `as_of`, and "now" always means that.
 *
 * Four rules hold throughout.
 *
 * - **Chances print as the game prints them**: whole in the middle, with one
 *   decimal under 9.5% and over 90.5%, the rule of the game's `chance()` in
 *   `lib/format.ts`, with its float `toFixed` rounding. So a price never
 *   prints one way here and another on a game card or a slip beside it. Only
 *   where one decimal would still print a false 0% or 100% does a chance
 *   print as "<0.1%" or ">99.9%".
 * - **The market's own reading, not the game's held price.** The API holds
 *   an open question's live price inside the game's band (1% to 99%, see
 *   `PriceBand`). Where it is held there and the market's own latest reading
 *   lies beyond, the pages show that reading (`priceToShow`), as they do
 *   wherever that reading is newer than the live price; where nothing says
 *   where the market stands, the held price prints as the bound it is
 *   ("≤1%"), never as a price (`pctHeld`).
 * - **A change is "from 54% to 62%"**, and its size, where prose needs one, is
 *   in percentage points taken from the two figures as printed, so a reader's
 *   own subtraction agrees with the page.
 * - **The slip figures are the game's own**: `fairOdds` from `lib/odds.ts`
 *   for each pick, then the server's `price_slip` arithmetic (product of the
 *   truncated odds, half-up rounding, the cap) done exactly, in integers.
 */

import { viz } from "@/lib/copy";
import { chance, dateUtc, odds, points } from "@/lib/format";
import { bookmakerTake, fairOdds } from "@/lib/odds";
import type { HistoryPoint, Move, Moves, PublicQuestion, Side } from "@/lib/types";

const LOCALE = "en-US";
const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

// ---------------------------------------------------------------------------
// Chances as text
// ---------------------------------------------------------------------------

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

/**
 * The digits a chance prints with: one under 9.5% and over 90.5%, else none.
 * The game's own rule (`chance()` in lib/format.ts), tested the same way on
 * the probability itself, so the two agree at every edge.
 */
export function pctDigits(probability: number): 0 | 1 {
  return probability < 0.095 || probability > 0.905 ? 1 : 0;
}

/**
 * A chance as a percentage: "62%", "5.5%", "0.4%", "99.5%".
 *
 * For every chance the game can show (1% to 99%) this is exactly what the
 * game's `chance()` prints, so a figure here and a pick's price beside it
 * never differ. Below and above that, one decimal can still round to a false
 * 0.0% or 100.0%; such a chance prints as "<0.1%" or ">99.9%", which is what
 * it is. Certainty either way prints whole: "0%" and "100%".
 */
export function pct(probability: number | string): string {
  const parsed = Number(probability);
  if (!Number.isFinite(parsed)) return viz.missing;
  const value = clamp01(parsed);
  // Certain either way is whole; anything short of it never prints as if it were.
  if (value === 0) return "0%";
  if (value === 1) return "100%";
  const text = (value * 100).toFixed(pctDigits(value));
  if (Number(text) === 0) return "<0.1%";
  if (Number(text) === 100) return ">99.9%";
  return `${text}%`;
}

// ---------------------------------------------------------------------------
// The game's band: where the API holds an open question's live price
// ---------------------------------------------------------------------------

/**
 * The chances the game deals at: `min_prob` to `max_prob` in /v1/rules.
 *
 * The API holds every open question's live price inside this band. Its price
 * reader keeps the market's midpoint to it (`fetch_token_price` in
 * apps/api/backend/clients/clob.py), and so does discovery (`_clamp` in
 * clients/gamma.py), so a market at 0.4% comes back as "0.0100". That is the
 * price the game deals at, and the game keeps it. It is not what the market
 * says. The rest of a question's answer is the market's own and is not held:
 * the source's history, the change figures and the price they were measured
 * to (`changes.reference`), and a move's `was`. The site's own snapshots
 * (`history_source` "own") record the held price, and so does a move's `now`.
 */
export type PriceBand = { min: number; max: number };

/**
 * The band for code that has no rules to hand. It mirrors /v1/rules
 * (`min_prob` "0.01", `max_prob` "0.99"); where the rules can be read, use
 * `priceBand(rules)`, which comes back to this only when they cannot.
 */
export const GAME_BAND: PriceBand = { min: 0.01, max: 0.99 };

/** The band from the rules, or `GAME_BAND` when they could not be read. */
export function priceBand(rules?: { min_prob: string; max_prob: string } | null): PriceBand {
  const min = Number(rules?.min_prob);
  const max = Number(rules?.max_prob);
  return Number.isFinite(min) && Number.isFinite(max) && min > 0 && min < max && max < 1
    ? { min, max }
    : GAME_BAND;
}

/**
 * The edge of the band a price sits exactly on, at the API's four places, or
 * null. A held price sits there: a market at 0.4% and one at exactly 1% both
 * come back as "0.0100", so on its own such a price says only "1% or less".
 */
export function onEdge(value: number | string, band: PriceBand = GAME_BAND): "min" | "max" | null {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  const at = round4(parsed);
  if (at === round4(band.min)) return "min";
  if (at === round4(band.max)) return "max";
  return null;
}

/** One of the band's edges as a percentage: "1%", "99%", "1.5%". */
export function bandPercent(edge: number): string {
  return marginPercent(edge);
}

/**
 * A price that may be held at the band's edge, printed so that it is not
 * false. Exactly on an edge it stands for that edge or anything beyond it, so
 * it prints as the bound it is, "≤1%" or "≥99%"; anywhere else it is a price,
 * printed as `pct` prints it.
 */
export function pctHeld(value: number | string, band: PriceBand = GAME_BAND): string {
  const edge = onEdge(value, band);
  if (edge === "min") return `≤${bandPercent(band.min)}`;
  if (edge === "max") return `≥${bandPercent(band.max)}`;
  return pct(value);
}

/** The band as No sees it: Yes held at 1% is No held at 99%. */
function mirrorBand(band: PriceBand): PriceBand {
  return { min: round4(1 - band.max), max: round4(1 - band.min) };
}

/**
 * Yes and No, printed so that they add up to 100: No is taken from Yes as
 * printed, at the same precision.
 *
 * `held` is for a Yes that is a held price: on the band's edge both sides
 * print as the bounds they are ("≤1%" and "≥99%").
 */
export function pctPair(yesProbability: number | string, held?: PriceBand): { yes: string; no: string } {
  const parsed = Number(yesProbability);
  if (!Number.isFinite(parsed)) return { yes: viz.missing, no: viz.missing };
  const value = clamp01(parsed);
  if (held && onEdge(value, held)) {
    return { yes: pctHeld(value, held), no: pctHeld(round4(1 - value), mirrorBand(held)) };
  }
  const yes = pct(value);
  const mirror: Record<string, string> = { "0%": "100%", "100%": "0%", "<0.1%": ">99.9%", ">99.9%": "<0.1%" };
  const mirrored = mirror[yes];
  if (mirrored) return { yes, no: mirrored };
  const digits = pctDigits(value);
  const printed = Number((value * 100).toFixed(digits));
  return { yes, no: `${(100 - printed).toFixed(digits)}%` };
}

export type PrintedChange = {
  was: string;
  now: string;
  /**
   * In percentage points, from the printed figures: "8", "11.5". Empty when
   * `now` is a held price, which stands for a range and so has no one size.
   */
  size: string;
  direction: "up" | "down" | "flat";
};

/**
 * A change in a chance, as printed: its two ends, and a size that adds up.
 *
 * `held` is for a `now` that may be a held price (a move's `now` is the
 * game's): exactly on the band's edge it prints as a bound ("≤1%"), the size
 * is not known, and the direction is known only from a start inside the band
 * ("flat" otherwise, which here means "cannot be told").
 */
export function printedChange(was: number | string, now: number | string, held?: PriceBand): PrintedChange {
  const from = Number(was);
  const to = Number(now);
  if (!Number.isFinite(from) || !Number.isFinite(to)) {
    return { was: viz.missing, now: viz.missing, size: viz.missing, direction: "flat" };
  }
  const a = clamp01(from);
  const b = clamp01(to);
  const edge = held ? onEdge(b, held) : null;
  if (held && edge) {
    const toward = edge === "min" ? a > held.min : a < held.max;
    return {
      was: pct(a),
      now: pctHeld(b, held),
      size: "",
      direction: toward ? (edge === "min" ? "down" : "up") : "flat",
    };
  }
  const digitsA = pctDigits(a);
  const digitsB = pctDigits(b);
  const digits = Math.max(digitsA, digitsB);
  const printedA = Number((a * 100).toFixed(digitsA));
  const printedB = Number((b * 100).toFixed(digitsB));
  const difference = Number((printedB - printedA).toFixed(digits));
  return {
    was: pct(a),
    now: pct(b),
    size: Math.abs(difference).toFixed(digits).replace(/\.0$/, ""),
    direction: difference > 0 ? "up" : difference < 0 ? "down" : "flat",
  };
}

/**
 * "from 54% to 62%", or "unchanged at 62%". With `held` (see `printedChange`),
 * a held `now` whose change cannot be told is said as itself: "now ≤1%".
 */
export function fromTo(was: number | string, now: number | string, start = false, held?: PriceBand): string {
  const change = printedChange(was, now, held);
  if (change.direction === "flat") {
    if (!change.size) return `${start ? viz.rangeNow : viz.now} ${change.now}`;
    return start ? viz.unchangedStart(change.now) : viz.unchanged(change.now);
  }
  return start ? viz.fromToStart(change.was, change.now) : viz.fromTo(change.was, change.now);
}

/** "54% → 62%", or "62%" when the two print the same (or a held `now` cannot be told from its start). */
export function fromToArrow(was: number | string, now: number | string, held?: PriceBand): string {
  const change = printedChange(was, now, held);
  return change.direction === "flat" ? change.now : viz.arrow(change.was, change.now);
}

/** "up 8 percentage points", "down 1 percentage point", or "" when flat or not known. */
export function changeSize(was: number | string, now: number | string, held?: PriceBand): string {
  const change = printedChange(was, now, held);
  if (change.direction === "flat" || !change.size) return "";
  return change.direction === "up" ? viz.up(change.size) : viz.down(change.size);
}

/**
 * "From 54% to 62%, up 8 percentage points." — a change, for a screen reader.
 * A held `now` has no one size, so its sentence ends at it: "From 3.5% to ≤1%."
 */
export function changeSentence(was: number | string, now: number | string, held?: PriceBand): string {
  const change = printedChange(was, now, held);
  if (!change.size) return `${fromTo(was, now, true, held)}.`;
  if (change.direction === "flat") return `${viz.unchangedStart(change.now)}.`;
  return viz.sentence(fromTo(was, now, true, held), changeSize(was, now, held));
}

// ---------------------------------------------------------------------------
// Dates (UTC, never relative: a cached page must not say "in 3 days")
// ---------------------------------------------------------------------------

const MONTH_DAY = new Intl.DateTimeFormat(LOCALE, {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});
const TIME = new Intl.DateTimeFormat(LOCALE, {
  hour: "numeric",
  minute: "2-digit",
  timeZone: "UTC",
});
const WEEKDAY_DATE = new Intl.DateTimeFormat(LOCALE, {
  weekday: "long",
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});
const SHORT_DATE_TIME = new Intl.DateTimeFormat(LOCALE, {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZone: "UTC",
  timeZoneName: "short",
});

function toMs(value: string | number | Date): number {
  return value instanceof Date ? value.getTime() : typeof value === "number" ? value : Date.parse(value);
}

/** "Dec 1" — with the year when it is not the year of `reference`. */
export function shortDateUtc(when: string | number | Date, reference?: string | number | Date): string {
  const ms = toMs(when);
  if (!Number.isFinite(ms)) return viz.missing;
  const sameYear =
    reference !== undefined &&
    new Date(toMs(reference)).getUTCFullYear() === new Date(ms).getUTCFullYear();
  return sameYear ? MONTH_DAY.format(ms) : dateUtc(new Date(ms).toISOString());
}

/** "Nov 26, 3:00 PM UTC". */
export function shortDateTimeUtc(when: string | number | Date): string {
  const ms = toMs(when);
  return Number.isFinite(ms) ? SHORT_DATE_TIME.format(ms) : viz.missing;
}

/** "Closes Dec 1" — a date, never a countdown. */
export function closesOn(closesAt: string, reference?: string): string {
  return viz.closesOn(shortDateUtc(closesAt, reference));
}

/** "Closed Nov 27". */
export function closedOn(closedAt: string, reference?: string): string {
  return viz.closedOn(shortDateUtc(closedAt, reference));
}

// ---------------------------------------------------------------------------
// One question: which price to show, and how it has changed
// ---------------------------------------------------------------------------

export type PriceReading = {
  /** The Yes probability, 0 to 1. */
  value: number;
  /** When that price was read. */
  at: string;
  /** "live" for an open question; "last" once it has closed. */
  kind: "live" | "last";
  /**
   * True when the figure is a price held on the game's band (see
   * `PriceBand`) and nothing says where the market stands beyond it: print it
   * as the bound it is (`pctHeld`, or the parts' `held` prop), never as a
   * price.
   */
  held?: boolean;
};

/**
 * How long before the live price the market's own latest reading may have
 * been read and still say where a held price lies beyond the band's edge.
 */
const READING_MAX_AGE = 3 * HOUR;

/** Two readings this close in time are one moment. */
const SAME_MOMENT = 60_000;

/**
 * The price a question's page leads with.
 *
 * For an open question that is the live price, with two exceptions, both
 * from the market's own latest reading: the last point of the source's
 * history. (The site's own snapshots are of the API's price, so they never
 * count as one.)
 *
 * - **A reading newer than the live price** is the price. The live price is
 *   then older than what the market has said since, usually one the API fell
 *   back on when it could not read the market (it says `stale`), hours old,
 *   while the market's own series went on: a page that led with it would put
 *   "21%" over a line that ends at 0.1%.
 * - **A live price held on the band's edge.** The API holds the live price
 *   inside the game's band (`PriceBand`), so a market at 0.4% comes back as
 *   1%. When the reading was read at most 3 hours before the live price (in
 *   normal running, within 3 hours of `as_of`) and lies beyond the edge, that
 *   reading is the price. A reading exactly on the edge says the market is
 *   there, and the live price stands. With no such reading the live price is
 *   all there is, and it is marked `held`.
 *
 * A reading is shown as "live", at its own time, so the readout, the bars,
 * the range, the chart's end and the sentences all agree with the line,
 * which ends on that reading and does not jump.
 *
 * For a closed or finished question it is the last point of its history (a
 * resolved one's last before its result, `seriesOf`), not `probability`:
 * that is the price the site stored when it stopped reading, which can
 * disagree with the chart by a long way (map 4.1). Only with no history at
 * all is it used.
 */
export function priceToShow(question: PublicQuestion, band: PriceBand = GAME_BAND): PriceReading {
  const series = seriesOf(question);
  const last = series[series.length - 1];
  if (question.state === "open") {
    const value = clamp01(Number(question.probability.yes));
    const asOf = Date.parse(question.as_of);
    const readAt = asOf - (question.probability.age_seconds || 0) * 1000;
    const liveAt = Number.isFinite(readAt) ? readAt : asOf;
    const at = new Date(liveAt).toISOString();
    // The market's own latest reading, if it has one by the time of the answer.
    const reading =
      question.history_source === "source" && last && !(last.t > asOf + SAME_MOMENT) ? last : null;
    const reported = (point: ChartPoint): PriceReading => ({
      value: point.v,
      at: new Date(point.t).toISOString(),
      kind: "live",
    });
    if (reading && reading.t > liveAt + SAME_MOMENT) return reported(reading);

    const edge = onEdge(value, band);
    if (!edge) return { value, at, kind: "live" };
    const recent = reading && liveAt - reading.t <= READING_MAX_AGE ? reading : null;
    if (recent && (edge === "min" ? recent.v < band.min : recent.v > band.max)) return reported(recent);
    if (recent && onEdge(recent.v, band) === edge) return { value, at, kind: "live" };
    return { value, at, kind: "live", held: true };
  }
  if (last) {
    // The site's own snapshots are of the held price: on an edge, a bound.
    const held = question.history_source === "own" && onEdge(last.v, band) !== null;
    return { value: last.v, at: new Date(last.t).toISOString(), kind: "last", ...(held ? { held } : {}) };
  }
  const value = clamp01(Number(question.probability.yes));
  return { value, at: question.as_of, kind: "last", ...(onEdge(value, band) ? { held: true } : {}) };
}

export type ChangeWindow = { was: number; now: number; at: string };

export type ChangeWindows = {
  day: ChangeWindow | null;
  week: ChangeWindow | null;
  /** When the change figures were read: what "a day ago" counts back from. */
  measuredAt: string | null;
};

/** 4 places, so that 0.2170 + 0.7670 is 0.984 and not 0.9840000000000001. */
function round4(value: number): number {
  return Math.round(value * 10_000) / 10_000;
}

/**
 * How near to a moment the market's own series must have a reading to say
 * where the question stood then. The series is hourly, with at most a
 * two-hour step.
 */
const WINDOW_REACH = 2 * HOUR;

/**
 * How close that reading must be to the reference for a change the source
 * left out to be read as none (see `changeWindows`).
 */
const UNCHANGED_WITHIN = 0.01;

/** The market's own reading nearest to `t`, within `WINDOW_REACH`, or null. */
function readingNear(question: PublicQuestion, t: number): ChartPoint | null {
  // The site's own snapshots have holes, and record the held price.
  if (question.history_source !== "source") return null;
  let nearest: ChartPoint | null = null;
  for (const point of seriesOf(question)) {
    if (!nearest || Math.abs(point.t - t) < Math.abs(nearest.t - t)) nearest = point;
  }
  return nearest && Math.abs(nearest.t - t) <= WINDOW_REACH ? nearest : null;
}

/**
 * Where the question stood a day and a week before its change figures were
 * read: `reference − change`, at `measured_at − 24 h` and `− 7 d`.
 *
 * The source leaves a change of zero out of its answer (none of the hundreds
 * it sends is ever 0), and the API passes it on as null, so a question that
 * did not move reads as one with no figure. A null change is read as none
 * when the market's own series confirms it: a reading near the window's
 * start within a percentage point of the reference. Otherwise it stays
 * unknown, and so does a window the series does not reach, such as a week
 * for a question younger than a week (`youngerThan`).
 *
 * Use these for open questions only. A finished question's figures were read
 * before it closed, so "a day ago" would no longer be true.
 */
export function changeWindows(question: PublicQuestion): ChangeWindows {
  const { reference, measured_at: measuredAt } = question.changes;
  const ref = Number(reference);
  const measured = measuredAt ? Date.parse(measuredAt) : Number.NaN;
  const window = (change: string | null, back: number): ChangeWindow | null => {
    if (reference === null || !Number.isFinite(ref) || !Number.isFinite(measured)) return null;
    let delta = 0;
    if (change === null) {
      const then = readingNear(question, measured - back);
      if (!then || Math.abs(then.v - ref) > UNCHANGED_WITHIN) return null;
    } else {
      delta = Number(change);
      if (!Number.isFinite(delta)) return null;
    }
    return {
      was: clamp01(round4(ref - delta)),
      now: clamp01(ref),
      at: new Date(measured - back).toISOString(),
    };
  };
  return {
    day: window(question.changes.day, DAY),
    week: window(question.changes.week, 7 * DAY),
    measuredAt,
  };
}

/**
 * True when the market's own series starts well inside the last day (or
 * week): the question is younger than that, so a missing change figure is
 * missing "yet". The API sends a week of the series, so an older question's
 * starts at that week's edge.
 */
export function youngerThan(question: PublicQuestion, window: "day" | "week"): boolean {
  if (question.history_source !== "source") return false;
  const first = seriesOf(question)[0];
  const asOf = Date.parse(question.as_of);
  if (!first || !Number.isFinite(asOf)) return false;
  return first.t > asOf - (window === "day" ? DAY : 7 * DAY) + WINDOW_REACH;
}

// ---------------------------------------------------------------------------
// What moved: grouped by event, day and week together
// ---------------------------------------------------------------------------

export type EventGroup<T> = { title: string; category: string; items: T[] };

/**
 * Moves that belong to one event, together: five range buckets of one tweet
 * count are one story, not five. Groups keep the order of their first (and so
 * largest) move; items keep theirs.
 */
export function groupByEvent<T extends { event_title: string; category: string }>(
  items: T[],
): EventGroup<T>[] {
  const groups = new Map<string, EventGroup<T>>();
  for (const item of items) {
    const key = item.event_title.trim().toLowerCase();
    const group = groups.get(key);
    if (group) group.items.push(item);
    else groups.set(key, { title: item.event_title, category: item.category, items: [item] });
  }
  return [...groups.values()];
}

export type MergedMove = Omit<Move, "was" | "now" | "change" | "measured_at"> & {
  now: number;
  day: { was: number; measured_at: string } | null;
  week: { was: number; measured_at: string } | null;
  /** The larger of the two changes, in probability: what the list is sorted by. */
  size: number;
};

/** One row per question, with its day and its week, largest change first. */
export function mergeWindows(moves: Moves): MergedMove[] {
  const rows = new Map<string, MergedMove>();
  const add = (move: Move, window: "day" | "week") => {
    const now = clamp01(Number(move.now));
    const was = clamp01(Number(move.was));
    if (!Number.isFinite(now) || !Number.isFinite(was)) return;
    const existing = rows.get(move.slug);
    const row: MergedMove = existing ?? {
      slug: move.slug,
      question: move.question,
      category: move.category,
      event_title: move.event_title,
      closes_at: move.closes_at,
      now,
      day: null,
      week: null,
      size: 0,
    };
    row[window] = { was, measured_at: move.measured_at };
    row.size = Math.max(row.size, Math.abs(now - was));
    rows.set(move.slug, row);
  };
  for (const move of moves.day) add(move, "day");
  for (const move of moves.week) add(move, "week");
  return [...rows.values()].sort((a, b) => b.size - a.size);
}

// ---------------------------------------------------------------------------
// A bookmaker's margin, beside none
// ---------------------------------------------------------------------------

export type MarginRow = { legs: number; take: number; printed: string };

/** What a margin of `margin` a pick takes from slips of 1 to `maxLegs` picks. */
export function marginTakes(margin: number, maxLegs: number): MarginRow[] {
  const rows: MarginRow[] = [];
  for (let legs = 1; legs <= Math.max(1, Math.floor(maxLegs)); legs += 1) {
    const take = bookmakerTake(margin, legs);
    rows.push({ legs, take, printed: `${(take * 100).toFixed(1)}%` });
  }
  return rows;
}

/** "5%" for a margin of 0.05: whole when it is whole, one decimal when not. */
export function marginPercent(margin: number): string {
  const scaled = margin * 100;
  return `${Number.isInteger(Math.round(scaled * 10) / 10) ? scaled.toFixed(0) : scaled.toFixed(1)}%`;
}

// ---------------------------------------------------------------------------
// The slip: the game's own figures, worked out exactly
// ---------------------------------------------------------------------------

export type SlipRules = {
  min_prob: string;
  max_prob: string;
  max_combined_odds: string;
  payout_cap: { minor: number; display: string };
  max_legs: number;
};

export type SlipLegInput = {
  side: Side;
  /** The chosen side's own probability, as the API sends it ("0.6200"). */
  probability: string | number;
  question?: string;
};

/**
 * The probability of the side picked, from the Yes price, to four places.
 *
 * The game reads a No price from the API's own `no` string. Worked out as
 * `1 − yes` in floating point it would come out as 0.16000000000000003, and
 * its odds a millionth short of the game's.
 */
export function sideProbability(yes: string | number, side: Side): number {
  const value = Number(yes);
  if (side === "YES") return value;
  return Number((1 - value).toFixed(4));
}

export type PricedPick = {
  side: Side;
  probability: number;
  priceable: boolean;
  /** Fair odds, truncated to six places: `fairOdds` from lib/odds.ts. */
  odds: number;
  question?: string;
};

export type SlipFigures = {
  picks: PricedPick[];
  /** After each pick: the chance that every pick so far is right. */
  steps: number[];
  /** The product of the picks' probabilities. */
  chance: number;
  /** The product of the truncated odds, truncated to six places. */
  combinedOdds: number;
  stakeMinor: number;
  grossMinor: number;
  payoutMinor: number;
  capped: boolean;
  /** Why the game would not take this slip, or null. */
  refused: "unpriceable" | "over_limit" | "too_many" | "empty" | null;
};

const MICRO = 1_000_000n;

/** The server's `ROUND_HALF_UP` on a positive fraction, in integers. */
function divideHalfUp(numerator: bigint, denominator: bigint): bigint {
  return (2n * numerator + denominator) / (2n * denominator);
}

/**
 * The figures the game's slip would show, worked out the way the server does
 * (`apps/api/backend/engine/odds.py`, `price_slip`): each pick's odds are
 * `1 / p` truncated to six places, the slip's are their product, and the
 * return is the stake times that product, rounded half up, then capped.
 */
export function slipFigures(
  legs: SlipLegInput[],
  stakeMinor: number,
  rules: SlipRules,
): SlipFigures {
  const minProb = Number(rules.min_prob);
  const maxProb = Number(rules.max_prob);
  const picks: PricedPick[] = legs.map((leg) => {
    const probability = Number(leg.probability);
    const priceable = probability >= minProb && probability <= maxProb;
    return {
      side: leg.side,
      probability,
      priceable,
      odds: priceable ? fairOdds(probability) : 0,
      question: leg.question,
    };
  });

  const steps: number[] = [];
  let running = 1;
  for (const pick of picks) {
    running *= pick.probability;
    steps.push(running);
  }

  const base: SlipFigures = {
    picks,
    steps,
    chance: picks.length ? running : 0,
    combinedOdds: 0,
    stakeMinor,
    grossMinor: 0,
    payoutMinor: 0,
    capped: false,
    refused: null,
  };
  if (!picks.length) return { ...base, refused: "empty" };
  if (picks.length > rules.max_legs) return { ...base, refused: "too_many" };
  if (picks.some((pick) => !pick.priceable)) return { ...base, refused: "unpriceable" };

  // Each pick's odds as an exact count of millionths, as the server stores them.
  let product = 1n;
  let scale = 1n;
  for (const pick of picks) {
    product *= BigInt(Math.round(pick.odds * 1_000_000));
    scale *= MICRO;
  }
  const combinedMicro = (product * MICRO) / scale;
  const combinedOdds = Number(combinedMicro) / 1_000_000;

  // `exact_product > max_combined_odds`, compared exactly.
  const [whole, fraction = ""] = String(rules.max_combined_odds).split(".");
  const limitMicro = BigInt(whole || "0") * MICRO + BigInt((fraction + "000000").slice(0, 6));
  if (product * MICRO > limitMicro * scale) {
    return { ...base, combinedOdds, refused: "over_limit" };
  }

  const gross = divideHalfUp(BigInt(Math.max(0, Math.floor(stakeMinor))) * product, scale);
  const cap = BigInt(rules.payout_cap.minor);
  const payout = gross < cap ? gross : cap;
  return {
    ...base,
    combinedOdds,
    grossMinor: Number(gross),
    payoutMinor: Number(payout),
    capped: gross > cap,
  };
}

/** The figures as the game prints them, so the two never disagree. */
export const gameFigures = { chance, odds, points };

// ---------------------------------------------------------------------------
// History as a series
// ---------------------------------------------------------------------------

export type ChartPoint = { t: number; v: number };

/**
 * Points in time order, unreadable ones dropped, values held to 0..1, and one
 * reading to a minute. The market's hourly series has been seen to repeat an
 * hour seconds apart (2:00:03 and 2:00:39, and no 3:00), and twice the same
 * time; the chart's table lists times to the minute, so two such readings
 * would be two rows of "2:00 AM" with two figures. They are one moment, and
 * the later reading stands for it.
 */
export function parseHistory(history: HistoryPoint[]): ChartPoint[] {
  const points = history
    .map((point) => ({ t: Date.parse(point.at), v: Number(point.yes) }))
    .filter((point) => Number.isFinite(point.t) && Number.isFinite(point.v))
    .map((point) => ({ t: point.t, v: clamp01(point.v) }))
    .sort((a, b) => a.t - b.t);
  const series: ChartPoint[] = [];
  for (const point of points) {
    const previous = series[series.length - 1];
    if (previous && Math.floor(previous.t / MINUTE) === Math.floor(point.t / MINUTE)) {
      series[series.length - 1] = point;
    } else {
      series.push(point);
    }
  }
  return series;
}

/**
 * A question's own series, as every part of its page reads it: the history
 * (`parseHistory`), and for a resolved question only the readings up to its
 * result. A reading after `resolved_at` is of a market already decided, and
 * drawn on, it would put a last price days after "Settled on …" on the same
 * page.
 */
function seriesOf(question: PublicQuestion): ChartPoint[] {
  const points = parseHistory(question.history);
  const settled = question.state === "resolved" && question.resolved_at ? Date.parse(question.resolved_at) : Number.NaN;
  return Number.isFinite(settled) ? points.filter((point) => point.t <= settled + SAME_MOMENT) : points;
}

/** The longest gap a line may be drawn across, by where the history came from. */
export function gapLimit(source: PublicQuestion["history_source"]): number {
  // The site's own snapshots stop while its server sleeps; a line across that
  // would draw prices nobody read. The market's own series is hourly with at
  // most a two-hour step, so only a much longer hole breaks it.
  return source === "own" ? 2 * HOUR : 6 * HOUR;
}

/** The series cut where readings are further apart than `maxGap`. */
export function segmentByGaps(points: ChartPoint[], maxGap: number): ChartPoint[][] {
  const segments: ChartPoint[][] = [];
  let current: ChartPoint[] = [];
  for (const point of points) {
    const previous = current[current.length - 1];
    if (previous && point.t - previous.t > maxGap) {
      segments.push(current);
      current = [];
    }
    current.push(point);
  }
  if (current.length) segments.push(current);
  return segments;
}

/** Midnight, UTC, of every day inside the span. */
export function utcDayTicks(start: number, end: number): number[] {
  const ticks: number[] = [];
  for (let tick = Math.ceil(start / DAY) * DAY; tick <= end; tick += DAY) ticks.push(tick);
  return ticks;
}

export function extremes(points: ChartPoint[]): { low: ChartPoint; high: ChartPoint } | null {
  const firstPoint = points[0];
  if (!firstPoint) return null;
  let low = firstPoint;
  let high = firstPoint;
  for (const point of points) {
    // The latest of equal lows and highs: the one a reader looks for.
    if (point.v <= low.v) low = point;
    if (point.v >= high.v) high = point;
  }
  return { low, high };
}

// ---------------------------------------------------------------------------
// The price chart: its geometry, decided on the server
// ---------------------------------------------------------------------------

/**
 * The chart's three widths. Its labels are laid out once for the narrowest
 * width of each (`floor`): positions there scale with the width while label
 * sizes do not, so a layout without collisions at the floor has none at any
 * width above it. The container queries in viz.css switch at `min` — keep the
 * two in step.
 */
export const LINE_CHART = {
  breakpoints: [
    { id: "xs", min: 0, floor: 256, plotH: 200, top: 32, left: 36, right: 60, xBand: 30 },
    { id: "s", min: 340, floor: 340, plotH: 208, top: 32, left: 36, right: 60, xBand: 30 },
    { id: "m", min: 520, floor: 520, plotH: 248, top: 32, left: 42, right: 66, xBand: 30 },
    { id: "l", min: 840, floor: 840, plotH: 300, top: 34, left: 44, right: 70, xBand: 32 },
  ],
  /** Labels are set in the monospaced face: every character is 0.6em wide. */
  labelFont: 11,
  tickFont: 10.5,
  charWidth: 0.6,
  labelPadX: 4,
  labelH: 18,
  /** Between a marker's edge and its label. */
  gap: 5,
  /** The widest plot any page gives the chart: where the last range ends. */
  widest: 1600,
} as const;

export type BreakpointId = (typeof LINE_CHART.breakpoints)[number]["id"];

export type Placement = {
  dx: number;
  dy: number;
  show: boolean;
  /**
   * A line from a label set away from its point back to it: its top, from
   * the label's top edge, and its length, in px.
   */
  leader?: { top: number; length: number };
};

type Rect = { x0: number; y0: number; x1: number; y1: number };

function overlaps(a: Rect, b: Rect, pad: number): boolean {
  return a.x0 < b.x1 + pad && b.x0 < a.x1 + pad && a.y0 < b.y1 + pad && b.y0 < a.y1 + pad;
}

/** Liang–Barsky: does the segment cross the rectangle? */
function segmentHits(x1: number, y1: number, x2: number, y2: number, r: Rect): boolean {
  if (Math.max(x1, x2) < r.x0 || Math.min(x1, x2) > r.x1) return false;
  if (Math.max(y1, y2) < r.y0 || Math.min(y1, y2) > r.y1) return false;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const edges = [
    [-dx, x1 - r.x0],
    [dx, r.x1 - x1],
    [-dy, y1 - r.y0],
    [dy, r.y1 - y1],
  ] as const;
  let t0 = 0;
  let t1 = 1;
  for (const [p, q] of edges) {
    if (p === 0) {
      if (q < 0) return false;
    } else {
      const t = q / p;
      if (p < 0) {
        if (t > t1) return false;
        if (t > t0) t0 = t;
      } else {
        if (t < t0) return false;
        if (t < t1) t1 = t;
      }
    }
  }
  return t0 <= t1;
}

function textWidth(characters: number, font: number = LINE_CHART.labelFont, padded = true): number {
  return characters * font * LINE_CHART.charWidth + (padded ? 2 * LINE_CHART.labelPadX : 0);
}

export type ChartLabelKind = "dayAgo" | "weekAgo" | "high" | "low" | "closed";

export type ChartLabel = {
  id: ChartLabelKind;
  /** The words, then the figure: "A day ago" and "98%". */
  word: string;
  value: string;
  /** Where it points: a fraction of the width, and a probability. */
  fx: number;
  v: number;
  /** "top" labels sit in the band above the plot, over a vertical rule. */
  mode: "point" | "top";
  placements: Record<BreakpointId, Placement>;
};

export type ChartMarker = {
  kind: "end" | "ref" | "bead" | "dot" | "outcome";
  fx: number;
  v: number;
  /** Radius in px, ring included: what labels keep clear of. */
  r: number;
  outcome?: "yes" | "no";
};

export type ChartTick = {
  fx: number;
  long: string;
  short: string;
  placements: Record<BreakpointId, Placement & { text: "long" | "short" }>;
};

export type ChartRow = {
  t: number;
  v: number;
  note: string | null;
  /** The figure to print, where it is not `pct(v)`: a held price's bound ("≤1%"). */
  text?: string;
};

export type LineChartModel = {
  state: PublicQuestion["state"];
  empty: boolean;
  start: number;
  end: number;
  /** SVG path data on a 0..100 square: the line, and the wash beneath it. */
  line: string;
  area: string;
  markers: ChartMarker[];
  labels: ChartLabel[];
  ticks: ChartTick[];
  /** Fractions of the width where a vertical rule is drawn (closing). */
  rules: number[];
  end_label: { v: number; value: string; word: string; outcome: "yes" | "no" | null };
  points: ChartPoint[];
  rows: ChartRow[];
  summary: string;
  keyFigures: { term: string; value: string }[];
};

type Candidate =
  | "above"
  | "below"
  | "above-right"
  | "above-left"
  | "below-right"
  | "below-left"
  | "right"
  | "left"
  | "top";

/** The widest a breakpoint's plot is drawn: where its range ends. */
function widestPlot(index: number): number {
  const next = LINE_CHART.breakpoints[index + 1];
  const bp = LINE_CHART.breakpoints[index];
  if (!bp) return 0;
  return (next ? next.min - 1 : LINE_CHART.widest) - bp.left - bp.right;
}

/**
 * Where each label goes, at each breakpoint.
 *
 * A label is tried in a few places around the point it names, in an order
 * that suits it (a high above, a low below), and takes the first place that
 * stays inside the chart and clear of every label already placed, every
 * marker, the closing rule and the line itself.
 *
 * Laid out at the breakpoint's narrowest plot. Wider, points move apart while
 * labels keep their size, so nothing that was clear there can collide. The
 * one exception is the line: a label beside its point covers, as the chart
 * widens, a slice of time ever closer to it. So the line is tested over every
 * moment the label could cover anywhere in the breakpoint's range, which is
 * the same test for a label centred over its point and a stricter one beside it.
 */
function placeLabels(
  specs: Omit<ChartLabel, "placements">[],
  markers: ChartMarker[],
  rules: number[],
  segments: ChartPoint[][],
  start: number,
  span: number,
): Record<BreakpointId, Placement>[] {
  const hidden = (): Placement => ({ dx: 0, dy: 0, show: false });
  const results = specs.map(
    (): Record<BreakpointId, Placement> => ({ xs: hidden(), s: hidden(), m: hidden(), l: hidden() }),
  );
  // The line in (fraction of width, probability): the same at every width.
  const lines = segments.map((segment) =>
    segment.map((point) => ({ f: (point.t - start) / span, v: point.v })),
  );

  LINE_CHART.breakpoints.forEach((bp, bpIndex) => {
    const width = bp.floor - bp.left - bp.right;
    const widest = Math.max(width, widestPlot(bpIndex));
    const height = bp.plotH;
    const px = (fx: number) => fx * width;
    const py = (v: number) => (1 - v) * height;
    const markerRects = markers.map((marker) => ({
      x0: px(marker.fx) - marker.r,
      x1: px(marker.fx) + marker.r,
      y0: py(marker.v) - marker.r,
      y1: py(marker.v) + marker.r,
    }));
    const placed: Rect[] = [];

    const hitsLine = (rect: Rect, ax: number, fx: number) => {
      // Offsets from the point, and the slice of time they cover at either
      // end of the range; the union of the two is every slice in between.
      const a = rect.x0 - ax - 1;
      const b = rect.x1 - ax + 1;
      const f0 = fx + Math.min(a / width, a / widest);
      const f1 = fx + Math.max(b / width, b / widest);
      const v0 = 1 - (rect.y1 + 1.5) / height;
      const v1 = 1 - (rect.y0 - 1.5) / height;
      const box = { x0: f0, x1: f1, y0: v0, y1: v1 };
      return lines.some((line) =>
        line.some((point, i) => {
          const next = line[i + 1];
          if (!next) return point.f >= f0 && point.f <= f1 && point.v >= v0 && point.v <= v1;
          return segmentHits(point.f, point.v, next.f, next.v, box);
        }),
      );
    };

    specs.forEach((spec, index) => {
      const w = textWidth(spec.word.length + (spec.value ? 1 + spec.value.length : 0));
      const h = LINE_CHART.labelH;
      const ax = px(spec.fx);
      const ay = py(spec.v);
      const own = markers.find(
        (marker) => Math.abs(marker.fx - spec.fx) < 1e-9 && Math.abs(marker.v - spec.v) < 1e-9,
      );
      const r = own?.r ?? 4;
      const ownRule = spec.mode === "top" ? spec.fx : null;

      const box = (candidate: Candidate): Rect | null => {
        if (w > width) return null;
        const g = LINE_CHART.gap;
        let x0: number;
        let y0: number;
        switch (candidate) {
          case "above":
            x0 = ax - w / 2;
            y0 = ay - r - g - h;
            break;
          case "below":
            x0 = ax - w / 2;
            y0 = ay + r + g;
            break;
          case "above-right":
            x0 = ax + r - 2;
            y0 = ay - r - 2 - h;
            break;
          case "above-left":
            x0 = ax - r + 2 - w;
            y0 = ay - r - 2 - h;
            break;
          case "below-right":
            x0 = ax + r - 2;
            y0 = ay + r + 2;
            break;
          case "below-left":
            x0 = ax - r + 2 - w;
            y0 = ay + r + 2;
            break;
          case "right":
            x0 = ax + r + g;
            y0 = ay - h / 2;
            break;
          case "left":
            x0 = ax - r - g - w;
            y0 = ay - h / 2;
            break;
          case "top":
            x0 = ax - w / 2;
            y0 = -bp.top + 3;
            break;
        }
        if (x0 < 0) x0 = 0;
        if (x0 + w > width) x0 = width - w;
        const rect = { x0, y0, x1: x0 + w, y1: y0 + h };
        // Inside the plot and the band above it; never into the dates below.
        if (rect.y0 < -bp.top + 1 || rect.y1 > height) return null;
        // A side label that had to be pushed back over its own point is no
        // longer beside it.
        if ((candidate === "right" || candidate === "left") && rect.x0 < ax + r && rect.x1 > ax - r) {
          return null;
        }
        return rect;
      };

      const clearOf = (rect: Rect) => {
        if (placed.some((other) => overlaps(rect, other, 3))) return false;
        if (markerRects.some((marker) => overlaps(rect, marker, 1))) return false;
        return !rules.some((fx) => {
          if (ownRule !== null && Math.abs(fx - ownRule) < 1e-9) return false;
          const x = px(fx);
          return rect.x0 - 2 < x && x < rect.x1 + 2;
        });
      };

      const base: Candidate[] =
        spec.mode === "top"
          ? ["top"]
          : spec.id === "high"
            ? ["above", "above-right", "above-left", "right", "left", "below"]
            : spec.id === "low"
              ? ["below", "below-right", "below-left", "right", "left", "above"]
              : ["above", "below", "above-right", "above-left", "below-right", "below-left"];
      // Then a little further off, with a leader back to the point; and for a
      // reference, last of all, the band above the plot.
      const tries: { candidate: Candidate; lift: number }[] = base.map((candidate) => ({ candidate, lift: 0 }));
      if (spec.mode === "point") {
        const sides: Candidate[] = spec.id === "low" ? ["below", "above"] : ["above", "below"];
        for (const lift of [14, 28, 42, 56]) for (const candidate of sides) tries.push({ candidate, lift });
        if (spec.id === "dayAgo" || spec.id === "weekAgo") tries.push({ candidate: "top", lift: 0 });
      }

      let chosen: Rect | null = null;
      let leader: Placement["leader"];
      for (const { candidate, lift } of tries) {
        const unlifted = box(candidate);
        if (!unlifted) continue;
        const shift = candidate === "above" ? -lift : candidate === "below" ? lift : 0;
        const rect = { ...unlifted, y0: unlifted.y0 + shift, y1: unlifted.y1 + shift };
        if (rect.y0 < -bp.top + 1 || rect.y1 > height) continue;
        if (!clearOf(rect)) continue;
        // The band above the plot is above every price, so nothing there
        // crosses the line; a leader drawn from it may, and that is allowed.
        if (candidate !== "top" && hitsLine(rect, ax, spec.fx)) continue;
        let lead: Rect | null = null;
        if (candidate === "top" && spec.mode === "point") lead = { x0: ax - 1, x1: ax + 1, y0: rect.y1, y1: ay - r };
        else if (lift > 0 && candidate === "above") lead = { x0: ax - 1, x1: ax + 1, y0: rect.y1, y1: ay - r };
        else if (lift > 0 && candidate === "below") lead = { x0: ax - 1, x1: ax + 1, y0: ay + r, y1: rect.y0 };
        if (lead) {
          if (lead.y1 - lead.y0 < 3) continue;
          if (placed.some((other) => overlaps(lead, other, 2))) continue;
          const others = markerRects.filter((_, i) => markers[i] !== own);
          if (others.some((marker) => overlaps(lead, marker, 1))) continue;
          leader = { top: round1(lead.y0 - rect.y0), length: round1(lead.y1 - lead.y0) };
        }
        chosen = rect;
        break;
      }

      const slot = results[index];
      if (chosen && slot) {
        placed.push(chosen);
        slot[bp.id] = {
          dx: round1(chosen.x0 - ax),
          dy: round1(chosen.y0 - ay),
          show: true,
          ...(leader ? { leader } : {}),
        };
      }
    });
  });
  return results;
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

function placeTicks(ticks: { fx: number; long: string; short: string; first: boolean }[]) {
  type TickPlacement = Placement & { text: "long" | "short" };
  const hidden = (): TickPlacement => ({ dx: 0, dy: 0, show: false, text: "short" });
  const results = ticks.map(
    (): Record<BreakpointId, TickPlacement> => ({ xs: hidden(), s: hidden(), m: hidden(), l: hidden() }),
  );
  for (const bp of LINE_CHART.breakpoints) {
    const width = bp.floor - bp.left - bp.right;
    const unitW = textWidth(viz.chartUtc.length, LINE_CHART.tickFont, false);
    // The dates may run under the gutters, but not into the "UTC" at the end.
    const minX = -bp.left + 2;
    const maxX = width + bp.right - unitW - 8;
    const placed: Rect[] = [];
    const order = ticks
      .map((tick, index) => ({ tick, index }))
      .sort((a, b) => {
        // The first and the last are placed first; the rest left to right.
        const rank = (i: number) => (i === 0 ? 0 : i === ticks.length - 1 ? 1 : 2);
        return rank(a.index) - rank(b.index) || a.index - b.index;
      });
    for (const { tick, index } of order) {
      const options: ("long" | "short")[] =
        bp.id === "xs" || bp.id === "s"
          ? tick.first
            ? ["long", "short"]
            : ["short"]
          : ["long", "short"];
      for (const option of options) {
        const text = option === "long" ? tick.long : tick.short;
        const w = textWidth(text.length, LINE_CHART.tickFont, false);
        const ax = tick.fx * width;
        let x0 = ax - w / 2;
        if (x0 < minX) x0 = minX;
        if (x0 + w > maxX) x0 = maxX - w;
        const rect = { x0, y0: 0, x1: x0 + w, y1: 10 };
        if (ax < minX || ax > maxX + w / 2) continue;
        if (placed.some((other) => overlaps(rect, other, 6))) continue;
        placed.push(rect);
        const slot = results[index];
        if (slot) slot[bp.id] = { dx: round1(x0 - ax), dy: 0, show: true, text: option };
        break;
      }
    }
  }
  return results;
}

export type LineChartOptions = {
  /** Draw the day-ago and week-ago markers (open questions only). */
  references?: boolean;
  /** The game's band, from the rules where they are to hand (see `priceToShow`). */
  band?: PriceBand;
};

/** The series the price chart draws, which the week's range is also taken from. */
type DrawnSeries = {
  /** The readings in time order (`seriesOf`), ending, for an open question, on the price shown. */
  points: ChartPoint[];
  /** The price the page leads with (`priceToShow`). */
  live: PriceReading;
  /** The points that are held prices, to print as their bounds. */
  held: Set<ChartPoint>;
};

/**
 * The line the chart draws, once for every part that reads it: the chart
 * itself and the week's range (`weekRange`). Built twice, the two had
 * different lows on one page: a reading within a minute of the live price
 * gives way to it on the line (below), and a range taken from the raw
 * history kept it.
 */
function drawnSeries(question: PublicQuestion, band: PriceBand): DrawnSeries {
  const open = question.state === "open";
  const live = priceToShow(question, band);
  const points = [...seriesOf(question)];
  // An open question's line ends at the price the page shows, so the chart
  // and the big figure above it say the same thing. Where that is the
  // market's own latest reading (a price held on the band's edge, or one
  // newer than the live price), it is the line's last point already, and the
  // line ends there rather than jump to the held or older price. With no
  // history there is no line to end, and the chart says so rather than draw
  // one lonely dot.
  let heldEnd: ChartPoint | null = null;
  const readAt = Date.parse(live.at);
  const latest = points[points.length - 1];
  if (open && latest && Number.isFinite(readAt) && !(latest.t === readAt && latest.v === live.value)) {
    const end = { t: readAt, v: live.value };
    const before = points[points.length - 2];
    if (live.held) {
      // A held price is not the market's reading: it follows it, and never
      // takes its place.
      if (readAt > latest.t + 60_000 || (readAt > latest.t && latest.v !== live.value)) {
        points.push(end);
        heldEnd = end;
      }
    } else if (readAt > latest.t + 60_000) {
      points.push(end);
    } else if (Math.abs(readAt - latest.t) <= 60_000 && latest.v !== live.value && (!before || before.t < readAt)) {
      // Two readings within a minute of each other are one moment: the one
      // the page leads with stands for it, so the line ends on its figure.
      points[points.length - 1] = end;
    }
  }
  // A held price prints as its bound: the live one at the end, and each of
  // the site's own snapshots (which record the held price) on the band's edge.
  const held = new Set<ChartPoint>(heldEnd ? [heldEnd] : []);
  if (question.history_source === "own") {
    for (const point of points) if (onEdge(point.v, band)) held.add(point);
  }
  return { points, live, held };
}

/**
 * Where it stood a day and a week before the change figures were read, as
 * points the chart marks and its high and low count, up to the line's end.
 */
function markPoints(windows: ChangeWindows | null, end: number): ChartPoint[] {
  const marks: ChartPoint[] = [];
  for (const window of [windows?.day, windows?.week]) {
    if (!window) continue;
    const at = Date.parse(window.at);
    if (Number.isFinite(at) && at <= end) marks.push({ t: at, v: window.was });
  }
  return marks;
}

/**
 * Everything the price chart draws, worked out once on the server: the line,
 * where its markers and labels go at each width, the day ticks, the table
 * and the sentences that say the same in words.
 */
export function lineChartModel(question: PublicQuestion, options: LineChartOptions = {}): LineChartModel {
  const state = question.state;
  const open = state === "open";
  const resolved = state === "resolved" && (question.outcome === "yes" || question.outcome === "no");
  const reference = question.as_of;
  const band = options.band ?? GAME_BAND;

  const { points, live, held } = drawnSeries(question, band);
  const printed = (point: ChartPoint): string => (held.has(point) ? pctHeld(point.v, band) : pct(point.v));

  const endWord = open ? viz.endNow : resolved ? viz.endResult : viz.endLast;

  const first = points[0];
  const last = points[points.length - 1];
  if (!first || !last) {
    return {
      state,
      empty: true,
      start: 0,
      end: 0,
      line: "",
      area: "",
      markers: [],
      labels: [],
      ticks: [],
      rules: [],
      end_label: {
        v: resolved ? (question.outcome === "yes" ? 1 : 0) : live.value,
        value:
          resolved && question.outcome
            ? viz.resultWord(question.outcome)
            : live.held
              ? pctHeld(live.value, band)
              : pct(live.value),
        word: endWord,
        outcome: resolved ? question.outcome : null,
      },
      points: [],
      rows: [],
      summary: viz.chartEmpty,
      keyFigures: [],
    };
  }

  const windows = open && options.references !== false ? changeWindows(question) : null;
  const resolvedAt = resolved && question.resolved_at ? Date.parse(question.resolved_at) : Number.NaN;

  let start = first.t;
  let end = last.t;
  if (windows?.week) start = Math.min(start, Date.parse(windows.week.at));
  if (windows?.day) start = Math.min(start, Date.parse(windows.day.at));
  if (Number.isFinite(resolvedAt)) end = Math.max(end, resolvedAt);
  if (end - start < HOUR) start = end - DAY; // one price: a day of axis, the point at its end
  const span = end - start;
  const fx = (t: number) => (t - start) / span;

  // The line and its wash, on a 0..100 square stretched to the plot.
  const segments = segmentByGaps(points, gapLimit(question.history_source));
  const coordinate = (point: ChartPoint) =>
    `${(fx(point.t) * 100).toFixed(2)},${((1 - point.v) * 100).toFixed(2)}`;
  const line = segments
    .filter((segment) => segment.length > 1)
    .map((segment) => segment.map((point, i) => `${i ? "L" : "M"}${coordinate(point)}`).join(""))
    .join("");
  const area = segments
    .filter((segment) => segment.length > 1)
    .map((segment) => {
      const a = segment[0];
      const b = segment[segment.length - 1];
      if (!a || !b) return "";
      return (
        `M${(fx(a.t) * 100).toFixed(2)},100` +
        segment.map((point) => `L${coordinate(point)}`).join("") +
        `L${(fx(b.t) * 100).toFixed(2)},100Z`
      );
    })
    .join("");

  const markers: ChartMarker[] = [];
  const labels: Omit<ChartLabel, "placements">[] = [];
  const rules: number[] = [];

  // Readings with nothing either side of them: a dot, or they would not show.
  for (const segment of segments) {
    const only = segment[0];
    if (segment.length === 1 && only && only !== last) {
      markers.push({ kind: "dot", fx: fx(only.t), v: only.v, r: 4 });
    }
  }

  // The end of the line, unless the result marks the same place.
  const outcomeV = question.outcome === "yes" ? 1 : 0;
  const outcomeCovers =
    resolved &&
    Number.isFinite(resolvedAt) &&
    Math.abs(fx(resolvedAt) - fx(last.t)) < 0.03 &&
    Math.abs(outcomeV - last.v) < 0.03;
  if (!outcomeCovers) markers.push({ kind: "end", fx: fx(last.t), v: last.v, r: 7 });
  if (resolved && Number.isFinite(resolvedAt)) {
    markers.push({
      kind: "outcome",
      fx: fx(resolvedAt),
      v: question.outcome === "yes" ? 1 : 0,
      r: 7,
      outcome: question.outcome ?? undefined,
    });
  }

  const printedEnd = printed(last);
  const nearEnd = (t: number) => Math.abs(fx(t) - fx(last.t)) < 0.04;

  // Where it stood a day and a week before the change figures were read.
  const refs: { id: "dayAgo" | "weekAgo"; window: ChangeWindow | null; word: string }[] = [
    { id: "dayAgo", window: windows?.day ?? null, word: viz.chartDayAgo },
    { id: "weekAgo", window: windows?.week ?? null, word: viz.chartWeekAgo },
  ];
  const refPoints: ChartPoint[] = [];
  for (const ref of refs) {
    if (!ref.window) continue;
    const at = Date.parse(ref.window.at);
    if (!Number.isFinite(at) || at < start || at > end) continue;
    markers.push({ kind: "ref", fx: fx(at), v: ref.window.was, r: 6 });
    labels.push({ id: ref.id, word: ref.word, value: pct(ref.window.was), fx: fx(at), v: ref.window.was, mode: "point" });
    refPoints.push({ t: at, v: ref.window.was });
  }

  // The lowest and the highest of everything the chart draws: the line with
  // its live end, and the day-ago and week-ago marks. Over the line alone, a
  // sparse history of the site's own readings could print "High 24%" beside
  // "A day ago 91%". When a mark or the end is the extreme, its own label
  // already says so and no second one is added.
  const range = extremes([...points, ...refPoints].sort((a, b) => a.t - b.t));
  if (range && printed(range.low) !== printed(range.high)) {
    for (const [id, point, word] of [
      ["high", range.high, viz.high],
      ["low", range.low, viz.low],
    ] as const) {
      const value = printed(point);
      const isEnd = point === last || (nearEnd(point.t) && value === printedEnd);
      // A ring already marks the spot when a reference is the high or the low.
      const ringThere = markers.some(
        (marker) =>
          marker.kind === "ref" &&
          Math.abs(marker.fx - fx(point.t)) < 0.015 &&
          pct(marker.v) === value,
      );
      if (!isEnd && !ringThere) markers.push({ kind: "bead", fx: fx(point.t), v: point.v, r: 5 });
      const repeated =
        isEnd ||
        labels.some((label) => label.value === value && Math.abs(label.fx - fx(point.t)) < 0.04);
      if (!repeated) labels.push({ id, word, value, fx: fx(point.t), v: point.v, mode: "point" });
    }
  }

  // When forecasts closed, for a question waiting for its result.
  if (state === "closed") {
    const closesAt = Date.parse(question.closes_at);
    if (Number.isFinite(closesAt) && closesAt >= start && closesAt <= end) {
      rules.push(fx(closesAt));
      labels.unshift({
        id: "closed",
        word: viz.chartClosed(shortDateUtc(closesAt, reference)),
        value: "",
        fx: fx(closesAt),
        v: 1,
        mode: "top",
      });
    }
  }

  // Lay the labels out: the rule's label first, then by how much each says.
  const order: ChartLabelKind[] = ["closed", "dayAgo", "weekAgo", "high", "low"];
  labels.sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
  const specs = labels.map((label) =>
    label.mode === "top" ? { ...label, word: label.word.trimEnd() } : label,
  );
  const placements = placeLabels(
    specs.map((label) => (label.mode === "top" ? { ...label, value: "" } : label)),
    markers,
    rules,
    segments,
    start,
    span,
  );
  const placedLabels: ChartLabel[] = specs.flatMap((label, index) => {
    const placement = placements[index];
    return placement ? [{ ...label, placements: placement }] : [];
  });

  // A tick at every UTC midnight; the month on the first and when it turns.
  const dayTicks = utcDayTicks(start, end);
  const tickSpecs = dayTicks.map((tick, index) => {
    const date = new Date(tick);
    const monthTurns = date.getUTCDate() === 1;
    return {
      fx: fx(tick),
      long: MONTH_DAY.format(tick),
      short: index === 0 || monthTurns ? MONTH_DAY.format(tick) : String(date.getUTCDate()),
      first: index === 0 || monthTurns,
    };
  });
  const tickPlacements = placeTicks(tickSpecs);
  const ticks: ChartTick[] = tickSpecs.flatMap((tick, index) => {
    const placement = tickPlacements[index];
    return placement ? [{ fx: tick.fx, long: tick.long, short: tick.short, placements: placement }] : [];
  });

  // The table, with the readings a reader would look for marked.
  const notes = new Map<ChartPoint, string>();
  if (range) {
    notes.set(range.high, viz.noteHigh);
    notes.set(range.low, viz.noteLow);
  }
  notes.set(last, open ? viz.noteNow : viz.noteLast);
  const rows: ChartRow[] = points.map((point, index) => {
    const next = points[index + 1];
    const gap = next ? next.t - point.t : 0;
    const noteParts = [notes.get(point)];
    if (next && gap > gapLimit(question.history_source)) {
      noteParts.push(viz.noteGap(String(Math.round(gap / HOUR))));
    }
    const note = noteParts.filter(Boolean).join(". ");
    return { t: point.t, v: point.v, note: note || null, ...(held.has(point) ? { text: printed(point) } : {}) };
  });

  // The same, said in words.
  const summary =
    points.length === 1
      ? viz.chartOne(printedEnd, shortDateUtc(last.t, reference))
      : viz.chartSummary(
          printed(first),
          shortDateUtc(first.t, reference),
          printedEnd,
          shortDateUtc(last.t, reference),
          printed(range?.low ?? last),
          printed(range?.high ?? last),
        );

  const keyFigures: { term: string; value: string }[] = [
    { term: open ? viz.keyNow : viz.keyLast, value: viz.keyAt(printedEnd, shortDateTimeUtc(last.t)) },
  ];
  if (windows?.day) {
    keyFigures.push({ term: viz.keyDayAgo, value: viz.keyAt(pct(windows.day.was), shortDateTimeUtc(windows.day.at)) });
  }
  if (windows?.week) {
    keyFigures.push({ term: viz.keyWeekAgo, value: viz.keyAt(pct(windows.week.was), shortDateTimeUtc(windows.week.at)) });
  }
  if (range) {
    keyFigures.push({ term: viz.keyLow, value: viz.keyAt(printed(range.low), shortDateTimeUtc(range.low.t)) });
    keyFigures.push({ term: viz.keyHigh, value: viz.keyAt(printed(range.high), shortDateTimeUtc(range.high.t)) });
  }
  if (state === "closed") {
    keyFigures.push({ term: viz.keyClosed, value: shortDateTimeUtc(question.closes_at) });
  }
  if (resolved && question.outcome) {
    keyFigures.push({
      term: viz.keyResult,
      value: question.resolved_at
        ? viz.keyAt(viz.resultWord(question.outcome), shortDateTimeUtc(question.resolved_at))
        : viz.resultWord(question.outcome),
    });
  }

  return {
    state,
    empty: false,
    start,
    end,
    line,
    area,
    markers,
    labels: placedLabels,
    ticks,
    rules,
    end_label: {
      v: resolved ? (question.outcome === "yes" ? 1 : 0) : last.v,
      value: resolved && question.outcome ? viz.resultWord(question.outcome) : printedEnd,
      word: endWord,
      outcome: resolved ? question.outcome : null,
    },
    points,
    rows,
    summary,
    keyFigures,
  };
}

/** Hours and minutes in UTC, for a row of the table: "8:00 PM". */
export function timeUtc(t: number): string {
  return TIME.format(t);
}

/** "Friday, Nov 21", for a day's rows in the table. */
export function weekdayDateUtc(t: number): string {
  return WEEKDAY_DATE.format(t);
}

/** The UTC day a moment falls on, as a number of days since 1970. */
export function utcDay(t: number): number {
  return Math.floor(t / DAY);
}

export const MS = { HOUR, DAY } as const;

/**
 * The lowest and highest price of the week, and the price to show beside
 * them (see `priceToShow`): what the 7-day range bar draws.
 *
 * Taken from what the chart draws (`drawnSeries`) and the marks it puts on
 * it, so the range's low and high are the chart's: an open question's
 * day-ago and week-ago figures are readings from this week too, and a
 * sparse history of the site's own readings must not give a range they fall
 * outside.
 *
 * `since` and `until` are the first and last moments those figures cover.
 * A question younger than a week, a finished one whose history ends with its
 * result, and one drawn from the site's own snapshots (with holes in them)
 * cover less than the week their range is named for: say so from these.
 */
export function weekRange(
  question: PublicQuestion,
  band: PriceBand = GAME_BAND,
): {
  low: number;
  high: number;
  now: number;
  kind: PriceReading["kind"];
  held?: boolean;
  since: number;
  until: number;
} | null {
  const { points, live: shown } = drawnSeries(question, band);
  const last = points[points.length - 1];
  if (!last) return null;
  const windows = question.state === "open" ? changeWindows(question) : null;
  const all = [...points, ...markPoints(windows, last.t)];
  const values = all.map((point) => point.v);
  // The price shown is the line's end; counted again in case it is not.
  const low = Math.min(...values, shown.value);
  const high = Math.max(...values, shown.value);
  // Held figures print as bounds (RangeBar's `held`): the price shown, when
  // it is held, and the site's own snapshots on the band's edge.
  const ownEdge = question.history_source === "own" && (onEdge(low, band) !== null || onEdge(high, band) !== null);
  return {
    low,
    high,
    now: shown.value,
    kind: shown.kind,
    ...(shown.held || ownEdge ? { held: true } : {}),
    since: Math.min(...all.map((point) => point.t)),
    until: last.t,
  };
}

// ---------------------------------------------------------------------------
// Labels over a 0-to-100 track (MoveTrack and RangeBar, large)
// ---------------------------------------------------------------------------

/**
 * A figure's width in Schibsted Grotesk at 500, as `<Figure>` sets it: the
 * digits tabular (0.635em), and everything else at its own width, as
 * measured in the browser: "." and "," 0.29em, "%" 0.87em, "<", ">" and "×"
 * 0.635em. A sign the face's Latin files lack ("≤", "≥") is drawn from
 * another face, whose width is not known here: a generous 0.7em.
 */
export function figureWidth(text: string, fontPx: number): number {
  let em = 0;
  for (const char of text) {
    if (char === "." || char === ",") em += 0.29;
    else if (char === "%") em += 0.87;
    else if (char.charCodeAt(0) > 0xff) em += 0.7;
    else em += 0.635;
  }
  return em * fontPx;
}

/** JetBrains Mono: 0.6em a character. */
export function monoWidth(text: string, fontPx: number): number {
  return text.length * 0.6 * fontPx;
}

export type TrackLabelSpec = {
  /** Where its marker is, 0 to 1. */
  x: number;
  /** The label's width in px. */
  width: number;
  /** Its marker's radius, ring included. */
  r: number;
};

export type TrackLabelPlace = {
  /** From the marker's x to the label's left edge, px. */
  offset: number;
  /** 0 sits on the track's label line; 1 is a line higher. */
  row: number;
  align: "left" | "center" | "right";
};

export type TrackLayout = { places: TrackLabelPlace[]; padLeft: number; padRight: number };

type Kind = "out" | "center" | "in";

/**
 * Where the labels over one or two markers go, and how much room the track
 * needs beside it for them.
 *
 * Each label prefers to sit beyond its marker, away from the other one, so
 * the two never meet; near an end of the track it moves over its marker or
 * inward, whichever needs the least room beside the track; if neither pair
 * of places fits, the earlier label goes up a line. Worked out at the
 * narrowest width the part is drawn at: wider, markers move apart and labels
 * keep their size, so nothing can come to overlap.
 */
export function layoutTrackLabels(specs: TrackLabelSpec[], narrowest = 300, gap = 10): TrackLayout {
  const offset = (kind: Kind, side: "left" | "right", w: number, r: number) => {
    if (kind === "center") return -w / 2;
    if (side === "left") return kind === "out" ? r - w : -r;
    return kind === "out" ? -r : r - w;
  };
  const align = (kind: Kind, side: "left" | "right"): TrackLabelPlace["align"] => {
    if (kind === "center") return "center";
    if (side === "left") return kind === "out" ? "right" : "left";
    return kind === "out" ? "left" : "right";
  };

  const [a, b] = specs;
  if (!a) return { places: [], padLeft: 0, padRight: 0 };

  // The track's own width depends on the room it gives its labels: settle it.
  let rail = narrowest;
  let best: TrackLayout = { places: [], padLeft: 0, padRight: 0 };
  for (let pass = 0; pass < 3; pass += 1) {
    if (!b) {
      const off = -a.width / 2;
      const left = a.x * rail + off;
      best = {
        places: [{ offset: off, row: 0, align: "center" }],
        padLeft: Math.max(0, -left),
        padRight: Math.max(0, left + a.width - rail),
      };
    } else {
      const combos: [Kind, Kind][] = [
        ["out", "out"],
        ["center", "out"],
        ["out", "center"],
        ["center", "center"],
        ["in", "out"],
        ["out", "in"],
        ["in", "center"],
        ["center", "in"],
        ["in", "in"],
      ];
      let chosen: (TrackLayout & { cost: number }) | null = null;
      for (const [ka, kb] of combos) {
        const offA = offset(ka, "left", a.width, a.r);
        const offB = offset(kb, "right", b.width, b.r);
        const a0 = a.x * rail + offA;
        const b0 = b.x * rail + offB;
        if (a0 + a.width + gap > b0) continue;
        const padLeft = Math.max(0, -Math.min(a0, b0));
        const padRight = Math.max(0, Math.max(a0 + a.width, b0 + b.width) - rail);
        const cost = padLeft + padRight;
        if (!chosen || cost < chosen.cost - 0.5) {
          chosen = {
            places: [
              { offset: offA, row: 0, align: align(ka, "left") },
              { offset: offB, row: 0, align: align(kb, "right") },
            ],
            padLeft,
            padRight,
            cost,
          };
        }
      }
      if (chosen) {
        best = { places: chosen.places, padLeft: chosen.padLeft, padRight: chosen.padRight };
      } else {
        const offA = offset("out", "left", a.width, a.r);
        const offB = offset("out", "right", b.width, b.r);
        const a0 = a.x * rail + offA;
        const b0 = b.x * rail + offB;
        best = {
          places: [
            { offset: offA, row: 1, align: "right" },
            { offset: offB, row: 0, align: "left" },
          ],
          padLeft: Math.max(0, -Math.min(a0, b0)),
          padRight: Math.max(0, Math.max(a0 + a.width, b0 + b.width) - rail),
        };
      }
    }
    rail = Math.max(80, narrowest - best.padLeft - best.padRight);
  }
  return {
    places: best.places.map((place) => ({ ...place, offset: Math.round(place.offset * 10) / 10 })),
    padLeft: Math.ceil(best.padLeft) + 2,
    padRight: Math.ceil(best.padRight) + 2,
  };
}

// ---------------------------------------------------------------------------
// A chance in words (the question page's "What the number means")
// ---------------------------------------------------------------------------

export type ChanceBand =
  | "noAlmost"
  | "noVery"
  | "no"
  | "noLean"
  | "even"
  | "yesLean"
  | "yes"
  | "yesVery"
  | "yesAlmost";

/**
 * How many in 100 a chance is, as `pct` prints it: 22 for "22%", 5.5 for
 * "5.5%". A figure under 1% or over 99% is said so, never rounded to a
 * false 0 or 100.
 */
export function inHundred(probability: number | string): number | "under1" | "over99" {
  const printed = pct(probability);
  if (printed === viz.missing) return Number.NaN;
  if (printed.startsWith("<")) return "under1";
  if (printed.startsWith(">")) return "over99";
  const value = Number(printed.replace(/%/g, ""));
  if (value > 0 && value < 1) return "under1";
  if (value > 99 && value < 100) return "over99";
  return value;
}

/**
 * Which plain description fits a chance of yes: how far it is from even, and
 * which way, in bands that mirror each other about 50%. Taken from the figure
 * as printed, so the words and the number beside them agree at every edge.
 */
export function chanceBand(probability: number | string): ChanceBand {
  const shown = inHundred(probability);
  const value = shown === "under1" ? 0.5 : shown === "over99" ? 99.5 : shown;
  if (!Number.isFinite(value)) return "even";
  if (value < 5) return "noAlmost";
  if (value < 20) return "noVery";
  if (value < 35) return "no";
  if (value < 45) return "noLean";
  if (value <= 55) return "even";
  if (value <= 65) return "yesLean";
  if (value <= 80) return "yes";
  if (value <= 95) return "yesVery";
  return "yesAlmost";
}
