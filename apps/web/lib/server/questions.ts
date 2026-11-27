import "server-only";

import { cache } from "react";

import { type PublicAnswer, publicApiAnswer } from "@/lib/server/public";
import type { Moves, PublicQuestion, QuestionIndex, QuestionIndexItem } from "@/lib/types";

/**
 * Questions, as anybody may read them: one question, the ones that moved, and
 * the list of all of them.
 *
 * Kept for five minutes, like the pages built from them. A chance that
 * changed a minute ago on a page that says so four minutes later is fine for
 * something read rather than staked on; the game itself reads its prices
 * live. Every page prints the time its figures are from.
 */

const REVALIDATE_SECONDS = 300;
const TAG = "questions";

// Much longer than the usual read. A question's page has nothing to show
// without its answer, and on a host that rests an idle server the first
// request is the one that wakes it. That takes most of a minute, and a visitor
// who waits and then gets the page is better served than one shown an error
// and asked to try again — twice. Under the page's `maxDuration`, with room
// left to draw it.
const QUESTION_TIMEOUT_MS = 50_000;

const PAGE = 500;
// A ceiling on how many pages are walked. Far more than there will be; it
// exists so a misbehaving API cannot make this loop.
const MAX_PAGES = 20;

// The API is deployed separately from this site, and for some minutes after a
// change to both, one is still the version before. An answer missing a part
// its page cannot be drawn without is treated as no answer — which the pages
// know how to live with — rather than drawn, and crashed on, half-way down.

function isMoves(value: unknown): value is Moves {
  const moves = value as Partial<Moves> | null;
  return (
    typeof moves === "object" &&
    moves !== null &&
    Array.isArray(moves.day) &&
    Array.isArray(moves.week) &&
    typeof moves.as_of === "string" &&
    typeof moves.day_threshold === "string" &&
    typeof moves.week_threshold === "string"
  );
}

function isQuestion(value: unknown): value is PublicQuestion {
  const question = value as Partial<PublicQuestion> | null;
  return (
    typeof question === "object" &&
    question !== null &&
    typeof question.slug === "string" &&
    typeof question.question === "string" &&
    typeof question.as_of === "string" &&
    typeof question.probability?.yes === "string" &&
    typeof question.changes === "object" &&
    question.changes !== null &&
    Array.isArray(question.history)
  );
}

function isIndex(value: unknown): value is QuestionIndex {
  const index = value as Partial<QuestionIndex> | null;
  return (
    typeof index === "object" &&
    index !== null &&
    typeof index.total === "number" &&
    Array.isArray(index.questions) &&
    index.questions.every(
      (question) =>
        typeof question?.slug === "string" &&
        typeof question.question === "string" &&
        typeof question.category === "string",
    )
  );
}

/**
 * Null when there is no list to show: the API could not be asked, or said its
 * figures are out of date and being read again.
 */
export async function getMoves(): Promise<Moves | null> {
  const answer = await publicApiAnswer<unknown>(
    "/v1/questions/moves?limit=12",
    REVALIDATE_SECONDS,
    { tags: [TAG] },
  );
  return answer.status === "ok" && isMoves(answer.data) ? answer.data : null;
}

/**
 * One question. Asked once however many parts of a page want it: the title
 * in the browser tab and the page beneath it have to be describing the same
 * answer.
 */
export const getQuestion = cache(async (slug: string): Promise<PublicAnswer<PublicQuestion>> => {
  // The API matches addresses exactly; anything that could not be one is not
  // worth a request.
  if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug) || slug.length > 200) return { status: "missing" };

  const answer = await publicApiAnswer<unknown>(`/v1/questions/${slug}`, REVALIDATE_SECONDS, {
    tags: [TAG],
    timeoutMs: QUESTION_TIMEOUT_MS,
  });
  if (answer.status !== "ok") return answer;
  return isQuestion(answer.data)
    ? { status: "ok", data: answer.data }
    : { status: "unavailable" };
});

/**
 * Every question with a page, open ones first — or null when the list could
 * not be read to the end. Never part of it: half a list shown as the list
 * would say that the other half had gone.
 */
export async function allQuestions(): Promise<QuestionIndexItem[] | null> {
  const all: QuestionIndexItem[] = [];
  const listed = new Set<string>();
  let read = 0;

  for (let index = 0; index < MAX_PAGES; index += 1) {
    const answer = await publicApiAnswer<unknown>(
      `/v1/questions?limit=${PAGE}&offset=${index * PAGE}`,
      REVALIDATE_SECONDS,
      { tags: [TAG] },
    );
    if (answer.status !== "ok" || !isIndex(answer.data)) return null;

    const page = answer.data;
    read += page.questions.length;
    for (const question of page.questions) {
      // An address is the market's and need not be unique, and a question
      // can move between two pages while they are being read. One address is
      // one page on this site, so it is listed once.
      if (listed.has(question.slug)) continue;
      listed.add(question.slug);
      all.push(question);
    }
    if (read >= page.total || page.questions.length < PAGE) break;
  }
  return all;
}
