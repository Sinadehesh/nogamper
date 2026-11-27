import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AsOf } from "@/components/AsOf";
import { JsonLd } from "@/components/JsonLd";
import { PriceChart } from "@/components/PriceChart";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { PRICE_SOURCE, changeInWords, movesPage, questionPage } from "@/lib/content";
import { t } from "@/lib/copy";
import { chance, chancePair, dateTimeUtc, dateUtc, movement } from "@/lib/format";
import { breadcrumbLd, pageMetadata } from "@/lib/seo";
import { getQuestion } from "@/lib/server/questions";
import { GAME_OPEN } from "@/lib/site";
import type { PublicQuestion } from "@/lib/types";

type Props = { params: Promise<{ slug: string }> };

// Kept for five minutes, then built again behind the next visitor.
export const revalidate = 300;

// How long the host lets one build of this page run. The first build of a
// question's page waits for the game's server, and a resting one takes most
// of a minute to wake: see QUESTION_TIMEOUT_MS in lib/server/questions.ts,
// which has to stay under this.
export const maxDuration = 60;

// None are built ahead of time: there are hundreds, they come and go daily,
// and building them would make every deploy depend on the game's server being
// awake. Each is built the first time its address is asked for and kept.
//
// There is deliberately no loading.tsx beside this file. With one, the page
// would start arriving before it is known whether the question exists, and an
// address that has no question would be answered "200 OK" with "not found"
// written on it. Without one it is answered 404, and a build that fails leaves
// the last good copy in place (see `keepEarlierCopy`).
export function generateStaticParams() {
  return [];
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const answer = await getQuestion(slug);
  if (answer.status !== "ok") {
    return { title: questionPage.trail, robots: { index: false, follow: false } };
  }

  const question = answer.data;
  const resolved = question.state === "resolved" && question.outcome !== null;
  return pageMetadata({
    title: question.question,
    description: resolved
      ? questionPage.resolvedDescription(question.question, outcomeWord(question))
      : questionPage.metaDescription(question.question),
    path: `/questions/${question.slug}`,
    // A question that was cancelled, or that the site stopped following, still
    // answers at its address but is nobody's search result.
    index: question.state !== "void" && question.state !== "unfollowed",
  });
}

function outcomeWord(question: PublicQuestion): string {
  return question.outcome === "yes" ? t.yes : t.no;
}

/** When the price on the page was read: the answer's own time, less the price's age. */
function priceReadAt(question: PublicQuestion): string {
  const read = new Date(question.as_of).getTime() - question.probability.age_seconds * 1000;
  return new Date(read).toISOString();
}

function stateLine(question: PublicQuestion): string {
  switch (question.state) {
    case "open":
      return questionPage.states.open(dateTimeUtc(question.closes_at));
    case "closed":
      return questionPage.states.closed(dateUtc(question.closes_at));
    case "resolved":
      return questionPage.states.resolved(
        outcomeWord(question),
        dateUtc(question.resolved_at ?? question.ends_at),
      );
    case "void":
      return questionPage.states.void;
    case "unfollowed":
      return questionPage.states.unfollowed(dateUtc(priceReadAt(question)));
  }
}

/**
 * How far the chance has come over a day and over a week, each as "from X to
 * Y" — measured the way the list of moves measures it: from where the market
 * says the question stood then, to the price at the top of this page. One
 * rule on both pages, so the two never disagree about the same question.
 */
function changes(question: PublicQuestion) {
  const { reference } = question.changes;
  if (reference === null) return [];

  const now = Number(question.probability.yes);
  const windows = [
    { window: "day", label: questionPage.windows.day, change: question.changes.day },
    { window: "week", label: questionPage.windows.week, change: question.changes.week },
  ];
  return windows.flatMap(({ window, label, change }) => {
    if (change === null) return [];
    const was = Math.min(1, Math.max(0, Number(reference) - Number(change)));
    return [{ window, label, shown: movement(was, now) }];
  });
}

function chartSummary(question: PublicQuestion): string | null {
  const first = question.history[0];
  const last = question.history[question.history.length - 1];
  if (!first || !last) return null;

  const values = question.history.map((point) => Number(point.yes));
  return questionPage.chartSummary(
    chance(first.yes),
    dateUtc(first.at),
    chance(last.yes),
    dateUtc(last.at),
    chance(Math.min(...values)),
    chance(Math.max(...values)),
  );
}

const sameText = (one: string, other: string) =>
  one.trim().toLowerCase() === other.trim().toLowerCase();

/**
 * One question: what is asked, what the market says, how that has changed.
 *
 * Everything here is a measurement or a plainly labelled explanation of one.
 * The page does not say why a price moved or where it is going, and its one
 * invitation — to make a forecast with points — is shown only while there is
 * a game to make it in and a question still open to make it on.
 */
export default async function QuestionPage({ params }: Props) {
  const { slug } = await params;
  const answer = await getQuestion(slug);
  if (answer.status === "missing") notFound();
  if (answer.status === "unavailable") {
    // Thrown rather than shown as "not found": the question exists. A page
    // that has been built before goes on being served as it was. One that has
    // not is answered with a server error — which is the truth, and what
    // tells a search engine to come back rather than forget the address — and
    // with the framework's own "could not load, reload to try again" page.
    // Nothing is kept, so the next request builds it.
    throw new Error("The question's figures could not be fetched.");
  }

  const question = answer.data;
  const pair = chancePair(question.probability.yes);
  // Only an open question has a price that is still being read. Once it
  // closes, the number on the page is the last one from before it did.
  const open = question.state === "open";
  const moved = open ? changes(question) : [];
  const summary = chartSummary(question);
  const first = question.history[0];
  const last = question.history[question.history.length - 1];
  const rules = (question.description ?? "")
    .split(/\n+/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

  return (
    <>
      <JsonLd
        data={breadcrumbLd([
          { name: t.appName, path: "/" },
          { name: t.navQuestions, path: "/questions" },
          { name: question.question, path: `/questions/${question.slug}` },
        ])}
      />
      <SiteHeader />

      <main id="main" className="container-page flex-1 py-10 sm:py-14">
        <article className="max-w-3xl">
          <nav aria-label={questionPage.trail} className="text-sm text-muted">
            <Link href="/questions" className="hover:text-ink">
              {t.navQuestions}
            </Link>
            <span aria-hidden className="mx-2">
              /
            </span>
            <span>{question.category}</span>
          </nav>

          <div className="mt-6">
            {/* The wider subject the question belongs to, when it has one that
                is not simply the question again. */}
            {sameText(question.event_title, question.question) ? null : (
              <p className="text-sm text-muted">{question.event_title}</p>
            )}
            <h1 className="mt-1 text-3xl font-black leading-tight tracking-tight sm:text-4xl">
              {question.question}
            </h1>
          </div>
          <p className="mt-3 text-muted">{stateLine(question)}</p>
          <div className="mt-1">
            {/* For an open question the line dates its price, which is the
                figure the page is about and can be older than the answer it
                came in: a server just woken has the prices it went to sleep
                with. A page that can still change is watched for a newer
                copy; one that is finished is not. */}
            <AsOf
              at={open ? priceReadAt(question) : question.as_of}
              changing={open || question.state === "closed"}
            />
          </div>

          <section className="card mt-6 p-6" aria-labelledby="now">
            <h2 id="now" className="text-xs font-bold uppercase tracking-wide text-muted">
              {question.state === "resolved"
                ? t.resolvedLabel
                : open
                  ? t.marketSays
                  : questionPage.lastPrice}
            </h2>
            {question.state === "resolved" && question.outcome !== null ? (
              <p className="mt-2 text-5xl font-black">{outcomeWord(question)}</p>
            ) : (
              <div className="mt-2 flex flex-wrap items-baseline gap-x-8 gap-y-2">
                <p className="text-5xl font-black tabular-nums text-yes">
                  <span className="mr-2 text-base font-bold">{t.yes}</span>
                  {pair.yes}
                </p>
                <p className="text-2xl font-black tabular-nums text-no">
                  <span className="mr-2 text-sm font-bold">{t.no}</span>
                  {pair.no}
                </p>
              </div>
            )}
          </section>

          {moved.length > 0 ? (
            <section className="mt-10" aria-labelledby="changes">
              <h2 id="changes" className="text-xl font-bold tracking-tight">
                {questionPage.changesTitle}
              </h2>
              <dl className="mt-3 divide-y divide-line border-y border-line">
                {moved.map(({ label, shown }) => (
                  <div key={label} className="flex flex-wrap justify-between gap-x-6 py-3">
                    <dt className="text-muted">{label}</dt>
                    <dd className="font-semibold tabular-nums">
                      {movesPage.fromTo(shown.was, shown.now)}
                      <span className="ml-2 font-normal text-muted">
                        {changeInWords(shown.points, shown.direction)}
                      </span>
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="mt-2 text-sm text-muted">
                {questionPage.changesNote(
                  moved.some((row) => row.window === "day"),
                  moved.some((row) => row.window === "week"),
                )}
              </p>
            </section>
          ) : null}

          <section className="mt-10" aria-labelledby="chart">
            <h2 id="chart" className="text-xl font-bold tracking-tight">
              {questionPage.chartTitle}
            </h2>
            {summary && first && last ? (
              <figure className="mt-4">
                <PriceChart
                  points={question.history}
                  firstLabel={dateUtc(first.at)}
                  lastLabel={dateUtc(last.at)}
                />
                <figcaption className="mt-3 text-sm text-muted">
                  {summary} {questionPage.chartSource[question.history_source]}
                </figcaption>
              </figure>
            ) : (
              <p className="mt-3 text-muted">{questionPage.chartSource.none}</p>
            )}
          </section>

          {rules.length > 0 ? (
            <section className="mt-10" aria-labelledby="decided">
              <h2 id="decided" className="text-xl font-bold tracking-tight">
                {questionPage.decidedTitle}
              </h2>
              <p className="mt-2 text-sm text-muted">{questionPage.decidedIntro}</p>
              <blockquote className="mt-3 space-y-3 border-l-2 border-line pl-4 text-muted">
                <p>{rules[0]}</p>
                {rules.length > 1 ? (
                  <details>
                    <summary className="cursor-pointer font-semibold text-ink">
                      {questionPage.decidedMore}
                    </summary>
                    <div className="mt-3 space-y-3">
                      {rules.slice(1).map((paragraph, index) => (
                        <p key={`${index}-${paragraph.slice(0, 16)}`}>{paragraph}</p>
                      ))}
                    </div>
                  </details>
                ) : null}
              </blockquote>
            </section>
          ) : null}

          <section className="mt-10" aria-labelledby="meaning">
            <h2 id="meaning" className="text-xl font-bold tracking-tight">
              {questionPage.meaningTitle}
            </h2>
            {questionPage.meaning.map((paragraph) => (
              <p key={paragraph.slice(0, 24)} className="mt-3 text-muted">
                {paragraph}
              </p>
            ))}
            <p className="mt-3">
              <Link
                href="/articles/how-to-read-prediction-market-odds"
                className="font-semibold text-accent hover:underline"
              >
                {questionPage.meaningLink}
              </Link>
            </p>
          </section>

          {GAME_OPEN && open ? (
            <section className="notice mt-10" aria-labelledby="play">
              <h2 id="play" className="font-bold">
                {questionPage.playTitle}
              </h2>
              <p className="mt-1 text-sm">{questionPage.playBody}</p>
              <Link href="/play" className="btn btn-secondary btn-sm mt-3">
                {questionPage.playCta}
              </Link>
            </section>
          ) : null}

          <p className="mt-10 text-sm text-muted">{PRICE_SOURCE}</p>
          <p className="mt-4">
            <Link href="/moves" className="btn btn-secondary btn-sm">
              {questionPage.movesLink}
            </Link>
          </p>
        </article>
      </main>

      <SiteFooter />
    </>
  );
}
