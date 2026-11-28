import "server-only";

import { getRules } from "@/lib/server/rules";
import { getMoves, getQuestion } from "@/lib/server/questions";
import { publicApiAnswer } from "@/lib/server/public";
import type { GameRules, Move, Moves, PublicQuestion, QuestionIndex } from "@/lib/types";
import { groupByEvent, type PriceBand, parseHistory, priceBand, priceToShow } from "@/lib/viz";

/**
 * What the front page is drawn from: the rules, the moves, and one open
 * question shown whole in the hero.
 *
 * Every figure on the page comes from here. When the moves or the hero's
 * question cannot be had, the page says so to its caller (`complete` is
 * false), which keeps the earlier copy on the running site rather than
 * replace real figures with a page that has none (lib/server/public.ts).
 */
export type FrontData = {
  rules: GameRules | null;
  moves: Moves | null;
  hero: PublicQuestion | null;
  /** The question the three steps walk through, and the two listed under it. */
  step: Move | null;
  others: Move[];
  /** The moves the "What moved" section lists, largest first, and which window they are from. */
  moved: { window: "day" | "week"; items: Move[] } | null;
  /** The game's band, from the rules (or lib/viz.ts's copy of them). */
  band: PriceBand;
  /**
   * The one time the page's figures are from, for its `AsOf`: the moves'
   * time, which is the hero's too when it is one of them (`asMoved`). A hero
   * read on its own was read at another moment, and the page is then dated
   * by the earlier of the two, so no figure on it is older than it says.
   */
  asOf: string | null;
  complete: boolean;
};

/** How many questions are asked for before the hero settles on none. */
const HERO_TRIES = 3;
/** How many moves the front page lists; the moves page has the rest. */
const MOVED_ROWS = 4;

const size = (move: Move) => Math.abs(Number(move.change));
const bySize = (moves: Move[]) => [...moves].sort((a, b) => size(b) - size(a));

/** A line worth the hero's chart: three days of readings, a day's worth of them. */
const FULL_SPAN_MS = 72 * 60 * 60 * 1000;
const FULL_POINTS = 24;

/**
 * Open, with a line to draw, and priced by the game where the market prices
 * it: a question the hero can show whole. The hero puts the market's chance
 * beside the game's two picks and the slip one makes, and those must be one
 * figure. A live price on the edge of the game's band is held there (a
 * market at 0.4% is dealt at 1%), so such a question is never the hero's;
 * nor is one whose price is out of date, which the game will not deal at,
 * or one whose page leads with a figure other than the game's price
 * (`priceToShow`).
 */
function showable(question: PublicQuestion, band: PriceBand): boolean {
  const yes = Number(question.probability.yes);
  return (
    question.state === "open" &&
    !question.probability.stale &&
    parseHistory(question.history).length >= 2 &&
    yes > band.min &&
    yes < band.max &&
    priceToShow(question, band).value === yes
  );
}

/**
 * A history long enough that the chart's line, its high and its marks a day
 * and a week back tell one story. A question that has only just been taken up
 * has a few of the site's own readings, which the chart draws as they are.
 */
function full(question: PublicQuestion): boolean {
  const points = parseHistory(question.history);
  const first = points[0];
  const last = points[points.length - 1];
  return points.length >= FULL_POINTS && !!first && !!last && last.t - first.t >= FULL_SPAN_MS;
}

/**
 * The hero's question as the moves answer has it, when it is one of the
 * moves. Its own answer is kept apart from the moves' and refreshed at
 * another moment, so the two could give one question two chances on one
 * page: "4.0%" in the hero over "From 32% to 3.2%" in its own row below. So
 * the hero takes from the moves what its row shows: the price (the move's
 * "now"), the moment (the moves' `as_of`, where its line then ends), and
 * where it stood at the start of each window it is listed in (the move's
 * "was", the chart's day-ago or week-ago mark). The rest, the line itself
 * and the question's words, is its own answer's.
 */
function asMoved(question: PublicQuestion, moves: Moves): PublicQuestion {
  const day = moves.day.find((move) => move.slug === question.slug);
  const week = moves.week.find((move) => move.slug === question.slug);
  const move = day ?? week;
  const at = Date.parse(moves.as_of);
  const now = Number(move?.now);
  if (!move || !Number.isFinite(at) || !Number.isFinite(now)) return question;

  // The change figures, from one reference: a listed window's change is to
  // the move's "was" (so the chart's mark is the row's figure exactly); one
  // not listed keeps its own answer's.
  const own = question.changes.reference === null ? Number.NaN : Number(question.changes.reference);
  const reference = Number.isFinite(own) ? own : now;
  const changeTo = (was: string) => (reference - Number(was)).toFixed(4);
  const changes: PublicQuestion["changes"] = {
    ...question.changes,
    reference: reference.toFixed(4),
    day: day ? changeTo(day.was) : Number.isFinite(own) ? question.changes.day : null,
    week: week ? changeTo(week.was) : Number.isFinite(own) ? question.changes.week : null,
    measured_at: move.measured_at,
  };
  return {
    ...question,
    probability: { ...question.probability, yes: move.now, no: (1 - now).toFixed(4), age_seconds: 0, stale: false },
    changes,
    history: question.history.filter((point) => Date.parse(point.at) <= at),
    as_of: moves.as_of,
  };
}

/** Whether the hero's figures are the moves': it is one of them. */
const listed = (question: PublicQuestion, moves: Moves | null) =>
  !!moves && [...moves.day, ...moves.week].some((move) => move.slug === question.slug);

/** The first of the questions tried with a full history, else the first that can be shown at all. */
async function firstShowable(slugs: string[], band: PriceBand, moves: Moves | null): Promise<PublicQuestion | null> {
  let fallback: PublicQuestion | null = null;
  for (const slug of slugs.slice(0, HERO_TRIES)) {
    const answer = await getQuestion(slug);
    if (answer.status !== "ok") continue;
    const question = moves ? asMoved(answer.data, moves) : answer.data;
    if (!showable(question, band)) continue;
    if (full(question)) return question;
    fallback ??= question;
  }
  return fallback;
}

/** When an open question's live price was read: its answer's time, less the price's age. */
function readAt(question: PublicQuestion): string {
  const read = Date.parse(question.as_of) - (question.probability.age_seconds || 0) * 1000;
  return Number.isFinite(read) ? new Date(read).toISOString() : question.as_of;
}

/** Any open question, from the index, for a day on which nothing moved. */
async function anyOpenSlugs(): Promise<string[]> {
  const answer = await publicApiAnswer<QuestionIndex>("/v1/questions?limit=24", 300, {
    tags: ["questions"],
  });
  if (answer.status !== "ok" || !Array.isArray(answer.data?.questions)) return [];
  return answer.data.questions
    .filter((question) => question?.state === "open" && typeof question.slug === "string")
    .map((question) => question.slug);
}

/** One row per question: a question in both lists keeps its larger move. */
function unique(moves: Move[]): Move[] {
  const seen = new Set<string>();
  return moves.filter((move) => (seen.has(move.slug) ? false : (seen.add(move.slug), true)));
}

/**
 * The steps' question: the one whose chance is nearest even, so both picks
 * read as real choices, and two more from other events (another category
 * first) to list under it.
 */
function stepQuestions(moves: Moves, heroSlug: string | null): { step: Move | null; others: Move[] } {
  const pool = unique(bySize([...moves.day, ...moves.week])).filter((move) => {
    const now = Number(move.now);
    return move.slug !== heroSlug && Number.isFinite(now) && now >= 0.05 && now <= 0.95;
  });
  const step = [...pool].sort((a, b) => Math.abs(Number(a.now) - 0.5) - Math.abs(Number(b.now) - 0.5))[0] ?? null;
  if (!step) return { step: null, others: [] };
  const events = new Set([step.event_title.trim().toLowerCase()]);
  const others: Move[] = [];
  const take = (move: Move) => {
    const event = move.event_title.trim().toLowerCase();
    if (others.length >= 2 || events.has(event)) return;
    events.add(event);
    others.push(move);
  };
  pool.filter((move) => move.category !== step.category).forEach(take);
  pool.forEach(take);
  return { step, others };
}

/** The day's moves when there are a few, else the week's. */
function movedList(moves: Moves): FrontData["moved"] {
  const day = unique(bySize(moves.day));
  const week = unique(bySize(moves.week));
  const window: "day" | "week" = day.length >= 3 || !week.length ? "day" : "week";
  const list = window === "day" ? day : week;
  if (!list.length) return null;
  // Grouped by event in the order of each event's largest move, then cut to
  // whole rows: five range buckets of one event are one story.
  const ordered = groupByEvent(list.slice(0, MOVED_ROWS)).flatMap((group) => group.items);
  return { window, items: ordered };
}

export async function frontData(): Promise<FrontData> {
  const [rules, moves] = await Promise.all([getRules(), getMoves()]);
  const band = priceBand(rules);

  let hero: PublicQuestion | null = null;
  if (moves) {
    hero = await firstShowable(
      unique([...bySize(moves.day), ...bySize(moves.week)]).map((move) => move.slug),
      band,
      moves,
    );
  }
  if (!hero) hero = await firstShowable(await anyOpenSlugs(), band, moves);

  const { step, others } = moves ? stepQuestions(moves, hero?.slug ?? null) : { step: null, others: [] };
  const moved = moves ? movedList(moves) : null;

  let asOf = moves?.as_of ?? null;
  if (hero && !listed(hero, moves)) {
    const heroAt = readAt(hero);
    asOf = asOf === null || Date.parse(heroAt) < Date.parse(asOf) ? heroAt : asOf;
  }

  return {
    rules,
    moves,
    hero,
    step,
    others,
    moved,
    band,
    asOf,
    complete: Boolean(moves && hero),
  };
}
