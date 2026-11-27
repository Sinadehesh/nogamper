import "server-only";

import { getRules } from "@/lib/server/rules";
import { getMoves, getQuestion } from "@/lib/server/questions";
import { publicApiAnswer } from "@/lib/server/public";
import type { GameRules, Move, Moves, PublicQuestion, QuestionIndex } from "@/lib/types";
import { groupByEvent, parseHistory } from "@/lib/viz";

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

/** Open, with a line to draw: a question the hero can show whole. */
function showable(question: PublicQuestion): boolean {
  return question.state === "open" && parseHistory(question.history).length >= 2;
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

/** The first of the questions tried with a full history, else the first that can be shown at all. */
async function firstShowable(slugs: string[]): Promise<PublicQuestion | null> {
  let fallback: PublicQuestion | null = null;
  for (const slug of slugs.slice(0, HERO_TRIES)) {
    const answer = await getQuestion(slug);
    if (answer.status !== "ok" || !showable(answer.data)) continue;
    if (full(answer.data)) return answer.data;
    fallback ??= answer.data;
  }
  return fallback;
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

  let hero: PublicQuestion | null = null;
  if (moves) {
    hero = await firstShowable(unique([...bySize(moves.day), ...bySize(moves.week)]).map((move) => move.slug));
  }
  if (!hero) hero = await firstShowable(await anyOpenSlugs());

  const { step, others } = moves ? stepQuestions(moves, hero?.slug ?? null) : { step: null, others: [] };
  const moved = moves ? movedList(moves) : null;

  return {
    rules,
    moves,
    hero,
    step,
    others,
    moved,
    complete: Boolean(moves && hero),
  };
}
