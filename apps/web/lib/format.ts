/**
 * Everything that turns a number or a timestamp into something to read.
 *
 * One fixed locale rather than the visitor's. The site is written in English,
 * and "1,000 points" beside "1.000 Punkte" on the same page reads as a bug,
 * not as a courtesy.
 */

const LOCALE = "en-US";

const WHOLE = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });
// Only ever given a whole number of hundredths (see `odds`), so it never rounds.
const ODDS = new Intl.NumberFormat(LOCALE, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const DATE = new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium" });
const DATE_TIME = new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium", timeStyle: "short" });

const MINOR_PER_POINT = 100;

/**
 * Minor units as whole points. Floored, never rounded: showing a player one
 * point more than they hold produces a stake the server then refuses.
 */
export function points(minor: number): string {
  const sign = minor < 0 ? "−" : "";
  return sign + WHOLE.format(Math.floor(Math.abs(minor) / MINOR_PER_POINT));
}

/** Signed, for a result: "+250", "−1,000", "0". */
export function signedPoints(minor: number): string {
  const whole = Math.floor(Math.abs(minor) / MINOR_PER_POINT);
  if (whole === 0) return "0";
  return (minor > 0 ? "+" : "−") + WHOLE.format(whole);
}

/**
 * Minor units as a whole number of points, for arithmetic on what is shown.
 *
 * Three figures printed side by side have to add up. Floored separately,
 * 480.00 staked and 366.59 returned give a net of −113.41 — which prints as
 * "480", "366" and "−113", and 480 − 366 is not 113. Wherever a result is
 * shown next to the amounts it came from, it is computed from these, so the
 * reader's own subtraction agrees with the page.
 */
export function wholePoints(minor: number): number {
  return Math.floor(Math.max(0, minor) / MINOR_PER_POINT);
}

/** A whole number with its sign: "+250", "−1,000", "0". */
export function signed(value: number): string {
  if (value === 0) return "0";
  return (value > 0 ? "+" : "−") + WHOLE.format(Math.abs(value));
}

export function count(value: number): string {
  return WHOLE.format(value);
}

/**
 * "2.00×" — how many times the stake comes back if the pick is right.
 *
 * Cut to two places, never rounded up, so that a multiplier and the payout
 * printed beside it multiply out: 100 points at "1.76×" pays 176, not 177.
 * Odds come at six places (1 ÷ 0.5665 is 1.765225), and rounded to two they
 * would print 1.77× next to the 176 the server pays. What is cut is the
 * multiplier a 100-point stake is paid at: the server rounds every payout
 * half up to a hundredth of a point, so odds of 2.119991 pay 212 for 100
 * points, and print 2.12× (plain truncation would print 2.11× beside 212).
 */
export function odds(value: string | number): string {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return String(value);
  // In millionths, as the server stores odds; a 100-point stake comes back
  // as (millionths + 50) ÷ 10,000 hundredths of a point per point, floored.
  const millionths = Math.round(parsed * 1_000_000);
  const hundredths = Math.floor((millionths + 50) / 10_000);
  return `${ODDS.format(hundredths / 100)}×`;
}

export function percent(probability: string | number, digits = 0): string {
  const parsed = Number(probability);
  if (!Number.isFinite(parsed)) return String(probability);
  const scaled = parsed * 100;
  // A chance that rounds to 0% or 100% is neither; say so rather than lie.
  if (digits === 0 && scaled > 0 && scaled < 1) return "<1%";
  if (digits === 0 && scaled > 99 && scaled < 100) return ">99%";
  return `${scaled.toFixed(digits)}%`;
}

/**
 * A probability for a card or a slip: whole percent in the middle, one
 * decimal near the ends.
 *
 * "1%" for both 1.0% and 1.45% hides a difference of half the payout — the
 * two are 100 to one and 69 to one — and the ends are exactly where a reader
 * is weighing a long shot.
 */
export function chance(probability: string | number): string {
  const parsed = Number(probability);
  if (!Number.isFinite(parsed)) return String(probability);
  return percent(parsed, parsed < 0.095 || parsed > 0.905 ? 1 : 0);
}

/**
 * Both sides of one question, formatted so that they add up.
 *
 * Rounded separately, 48.5% and 51.5% become 49% and 52% — a question whose
 * two answers total 101%. The NO side is therefore taken from the rounded YES
 * side, at the same precision.
 */
export function chancePair(yesProbability: string | number): { yes: string; no: string } {
  const parsed = Number(yesProbability);
  if (!Number.isFinite(parsed)) return { yes: "—", no: "—" };

  const digits = parsed < 0.095 || parsed > 0.905 ? 1 : 0;
  const yes = Number((parsed * 100).toFixed(digits));
  return { yes: `${yes.toFixed(digits)}%`, no: `${(100 - yes).toFixed(digits)}%` };
}

/**
 * One side's chance, printed as its question prints the pair: a YES side by
 * `chance()`, a NO side as the rest of the printed YES (`chancePair`). Printed
 * on its own, a NO at 36.5% beside a YES at 63.5% could round up too: 101% in
 * all. This way a card's two picks, a slip's lines and a question's page
 * always add up to 100% and always agree. `probability` is that side's own
 * (`probability.no` for a NO pick); odds are still worked out from it, never
 * from the printed figure.
 */
export function sideChance(probability: string | number, side: "YES" | "NO"): string {
  const parsed = Number(probability);
  if (!Number.isFinite(parsed)) return String(probability);
  if (side === "YES") return chance(parsed);
  return chancePair(Math.round((1 - parsed) * 10_000) / 10_000).no;
}

/**
 * A change in a chance, formatted so that its three numbers add up.
 *
 * "From 56% to 31%, down 25 points" has to survive the reader's own
 * subtraction. Rounded separately, 55.6% and 31.4% print as 56% and 31% while
 * their difference prints as 24 — so the difference is taken from the two
 * numbers as printed, at the precision they were printed at: whole points in
 * the middle, tenths when either end is near 0 or 100, where a point matters.
 *
 * `direction` is "flat" when the two print the same, whatever lies beneath.
 */
export function movement(
  was: string | number,
  now: string | number,
): { was: string; now: string; points: string; direction: "up" | "down" | "flat" } {
  const from = Number(was);
  const to = Number(now);
  if (!Number.isFinite(from) || !Number.isFinite(to)) {
    return { was: "—", now: "—", points: "—", direction: "flat" };
  }

  const nearAnEnd = (value: number) => value < 0.095 || value > 0.905;
  const digits = nearAnEnd(from) || nearAnEnd(to) ? 1 : 0;
  const printedFrom = Number((from * 100).toFixed(digits));
  const printedTo = Number((to * 100).toFixed(digits));
  const difference = Number((printedTo - printedFrom).toFixed(digits));

  return {
    was: `${printedFrom.toFixed(digits)}%`,
    now: `${printedTo.toFixed(digits)}%`,
    points: Math.abs(difference).toFixed(digits),
    direction: difference > 0 ? "up" : difference < 0 ? "down" : "flat",
  };
}

export function percentValue(probability: string, fallback = 50): number {
  const parsed = Number(probability);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(100, Math.max(0, Math.round(parsed * 100)));
}

function plural(value: number, unit: string): string {
  return `${WHOLE.format(value)} ${unit}${value === 1 ? "" : "s"}`;
}

/** "3 days", "5 hours", "12 minutes" — or "" once the moment has passed. */
export function timeUntil(isoTimestamp: string, now = Date.now()): string {
  const seconds = Math.floor((new Date(isoTimestamp).getTime() - now) / 1000);
  if (seconds <= 0) return "";
  if (seconds < 3600) return plural(Math.max(1, Math.floor(seconds / 60)), "minute");
  if (seconds < 86_400) return plural(Math.floor(seconds / 3600), "hour");
  return plural(Math.floor(seconds / 86_400), "day");
}

export function timeAgo(isoTimestamp: string, now = Date.now()): string {
  const seconds = Math.floor((now - new Date(isoTimestamp).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${plural(Math.floor(seconds / 60), "minute")} ago`;
  if (seconds < 86_400) return `${plural(Math.floor(seconds / 3600), "hour")} ago`;
  return `${plural(Math.floor(seconds / 86_400), "day")} ago`;
}

const MONTH_YEAR = new Intl.DateTimeFormat(LOCALE, {
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});

/** A season code as a person would say it: "2026-11" → "November 2026". */
export function seasonName(code: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(code);
  if (!match) return code;
  return MONTH_YEAR.format(new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, 1)));
}

const DATE_UTC = new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium", timeZone: "UTC" });

/**
 * A calendar date written as "2026-11-26", with no time attached.
 *
 * Formatted in UTC because that is how such a string is parsed: read in any
 * zone west of Greenwich it would otherwise print as the day before.
 */
export function calendarDate(isoDate: string): string {
  return DATE_UTC.format(new Date(isoDate));
}

const DATE_TIME_UTC = new Intl.DateTimeFormat(LOCALE, {
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZone: "UTC",
  timeZoneName: "short",
});

/**
 * A moment as a date in UTC — and, below, as a date and time that says so:
 * "Nov 27, 2026, 12:54 PM UTC".
 *
 * For pages that are built once and read anywhere. `date` and `dateTime`
 * borrow the clock of whatever runs them. In a visitor's browser that is the
 * visitor's; on a server it is nobody's, and a page built there would print a
 * time without saying whose it was.
 */
export function dateUtc(isoTimestamp: string): string {
  return DATE_UTC.format(new Date(isoTimestamp));
}

export function dateTimeUtc(isoTimestamp: string): string {
  return DATE_TIME_UTC.format(new Date(isoTimestamp));
}

export function date(isoTimestamp: string): string {
  return DATE.format(new Date(isoTimestamp));
}

export function dateTime(isoTimestamp: string): string {
  return DATE_TIME.format(new Date(isoTimestamp));
}

/** "24 hours", "3 days", "1 week", "30 days" — for a length of break. */
export function duration(hours: number): string {
  if (hours < 48) return plural(hours, "hour");
  if (hours === 168) return "1 week";
  return plural(Math.round(hours / 24), "day");
}

/**
 * What a person typed into a stake box, read strictly: whole points, with
 * commas and spaces allowed between the digits. Anything else is a problem
 * to say, not to guess at: "1.5" is not 15 points, and "abc" is not 0.
 * `minor` is in minor units, and 0 whenever there is a problem.
 */
export function readPoints(input: string): {
  minor: number;
  problem: "empty" | "fraction" | "invalid" | null;
} {
  const compact = input.replace(/[,\s]/g, "");
  if (!compact) return { minor: 0, problem: "empty" };
  if (/^\d*[.]\d*$/.test(compact) && /\d/.test(compact)) return { minor: 0, problem: "fraction" };
  if (!/^\d+$/.test(compact)) return { minor: 0, problem: "invalid" };
  const whole = Number(compact.slice(0, 12));
  return Number.isFinite(whole) ? { minor: whole * MINOR_PER_POINT, problem: null } : { minor: 0, problem: "invalid" };
}

/**
 * What a person typed into a points box, as minor units. Tolerant of commas
 * and spaces, deaf to everything else; never negative, never fractional.
 */
export function parsePoints(input: string): number {
  const digits = input.replace(/[,\s]/g, "").replace(/[^\d]/g, "");
  if (!digits) return 0;
  const whole = Number(digits.slice(0, 12));
  return Number.isFinite(whole) ? whole * MINOR_PER_POINT : 0;
}
