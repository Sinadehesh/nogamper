import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AsOf } from "@/components/AsOf";
import { JsonLd } from "@/components/JsonLd";
import { QuestionFigures, StateLine, meaningOf, outcomeOf, outcomeWord } from "@/components/questions/Question";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { LineChart } from "@/components/viz";
import { PRICE_SOURCE, questionPage } from "@/lib/content";
import { categoryLabel, t } from "@/lib/copy";
import { dateTimeUtc } from "@/lib/format";
import { breadcrumbLd, pageMetadata } from "@/lib/seo";
import { getQuestion } from "@/lib/server/questions";
import { getRules } from "@/lib/server/rules";
import { GAME_OPEN } from "@/lib/site";
import type { PublicQuestion } from "@/lib/types";
import { MS, onEdge, pct, pctPair, priceBand, priceToShow } from "@/lib/viz";

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
  const outcome = outcomeOf(question);
  return pageMetadata({
    title: question.question,
    description: outcome
      ? questionPage.resolvedDescription(question.question, outcomeWord(outcome))
      : questionPage.metaDescription(question.question),
    path: `/questions/${question.slug}`,
    // A question that was cancelled, or that the site stopped following, still
    // answers at its address but is nobody's search result.
    index: question.state !== "void" && question.state !== "unfollowed",
  });
}

/**
 * How much older than the page's own time the market's reading it shows may
 * be before the page says when that reading is from.
 */
const READING_NOTE_AFTER_MS = MS.HOUR / 4;

/** When the price on the page was read: the answer's own time, less the price's age. */
function priceReadAt(question: PublicQuestion): string {
  const read = new Date(question.as_of).getTime() - question.probability.age_seconds * 1000;
  return new Date(read).toISOString();
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
 *
 * Its order is its argument: the question and its state; the chance, how it
 * has changed and the week's range; the price history, which is the centre
 * of the page; what the number means; how the answer is decided.
 */
export default async function QuestionPage({ params }: Props) {
  const { slug } = await params;
  // The rules give the game's band, where the API holds a live price: read
  // together, and never waited on (a failure is null, and the band then
  // comes from the copy of /v1/rules in lib/viz.ts).
  const [answer, gameRules] = await Promise.all([getQuestion(slug), getRules()]);
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
  // Only an open question has a price that is still being read. Once it
  // closes, the number on the page is the last one from before it did.
  const open = question.state === "open";
  const readAt = priceReadAt(question);
  const band = priceBand(gameRules);
  // The figure the page leads with: the market's own latest reading where
  // the API holds the live price on the game's band, or where that reading
  // is newer than the live price.
  const shown = priceToShow(question, band);
  // When the page's figures are from: when the market was last read, by the
  // API (the live price) or by the market's own series, whichever is later.
  // A reading that stands in for a held price is older than the live read
  // that held it. Dated by the reading instead, a copy built a minute ago
  // would look an hour old to the reader's clock, and the line would go
  // looking for figures nobody has (AsOf).
  const datedAt = Date.parse(shown.at) > Date.parse(readAt) ? shown.at : readAt;
  // So where the chance shown is that older reading, by a quarter of an hour
  // or more, a line under the date says when the reading is from, as the
  // chart's own "Now" does: one figure, two times, each named.
  const readingAt =
    open && Date.parse(datedAt) - Date.parse(shown.at) >= READING_NOTE_AFTER_MS ? shown.at : null;
  // Where the game's price for a pick sits on the band's edge it can differ
  // from the market's figure above, and where it does (a reading beyond the
  // edge, or a held price printed as its bound) the play panel says so, with
  // the figures. Every figure in that line prints as the game prints a
  // chance, so the band's "1.0%" is the "1.0%" of the price beside it.
  const game = pctPair(question.probability.yes);
  const gameDiffers =
    open &&
    onEdge(question.probability.yes, band) !== null &&
    (shown.held === true || pct(shown.value) !== game.yes);
  const rules = (question.description ?? "")
    .split(/\n+/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
  const hasHistory = question.history.length > 0;

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

      <main id="main" className="flex-1">
        <article className="wrap dp">
          <nav aria-label={questionPage.trail} className="qp-trail">
            <Link href="/questions" className="dp-link">
              {t.navQuestions}
            </Link>
            <span aria-hidden="true">/</span>
            <span>{categoryLabel(question.category)}</span>
          </nav>

          <header className="qp-head">
            {/* The wider subject the question belongs to, when it has one that
                is not simply the question again. */}
            {sameText(question.event_title, question.question) ? null : (
              <p className="qp-kicker">{question.event_title}</p>
            )}
            <h1 className="qp-title">{question.question}</h1>
            <StateLine question={question} readAt={readAt} />
          </header>

          <QuestionFigures question={question} band={band} />
          {/* For an open question the line dates its price, which is the
              figure the page is about and can be older than the answer it
              came in: a server just woken has the prices it went to sleep
              with. A page that can still change is watched for a newer copy;
              one that is finished is not. */}
          <AsOf
            at={open ? datedAt : question.as_of}
            changing={open || question.state === "closed"}
            className="qp-asof"
          />
          {readingAt ? (
            <p className="qp-asof__reading text-sm leading-normal text-muted">
              {questionPage.readingAt(dateTimeUtc(readingAt))}
            </p>
          ) : null}

          <section className="qp-chart" aria-labelledby="chart">
            <div className="qp-chart__head">
              <h2 id="chart" className="dp-h2">
                {questionPage.chartTitle}
              </h2>
              {hasHistory && question.history_source !== "none" ? (
                <p className="dp-sub">
                  {questionPage.chartSource[question.history_source]} {questionPage.chartScale}
                </p>
              ) : null}
            </div>
            <LineChart question={question} labelledBy="chart" band={band} />
          </section>

          <div className="qp-pair">
            <section className="qp-meaning" aria-labelledby="meaning">
              <h2 id="meaning" className="dp-h2">
                {questionPage.meaningTitle}
              </h2>
              {meaningOf(question, band).map((paragraph) => (
                <p key={paragraph.slice(0, 32)}>{paragraph}</p>
              ))}
              <p>
                <Link href="/articles/how-to-read-prediction-market-odds" className="link">
                  {questionPage.meaningLink}
                </Link>
              </p>
            </section>

            {GAME_OPEN && open ? (
              <section className="qp-play dp-panel" aria-labelledby="play">
                <h2 id="play">{questionPage.playTitle}</h2>
                <p>{questionPage.playBody}</p>
                {gameDiffers ? (
                  <p className="qp-play__band">
                    {questionPage.playBand(pct(band.min), pct(band.max), game.yes, game.no)}
                  </p>
                ) : null}
                <Link href="/play" className="btn btn--secondary">
                  {questionPage.playCta}
                </Link>
              </section>
            ) : null}
          </div>

          {rules.length > 0 ? (
            <section className="qp-rules" aria-labelledby="decided">
              <h2 id="decided" className="dp-h2">
                {questionPage.decidedTitle}
              </h2>
              <p className="qp-rules__intro dp-label">{questionPage.decidedIntro}</p>
              <div className="qp-rules__text">
                <p>{rules[0]}</p>
                {rules.length > 1 ? (
                  <details>
                    <summary>{questionPage.decidedMore}</summary>
                    <div className="qp-rules__more">
                      {rules.slice(1).map((paragraph, index) => (
                        <p key={`${index}-${paragraph.slice(0, 16)}`}>{paragraph}</p>
                      ))}
                    </div>
                  </details>
                ) : null}
              </div>
            </section>
          ) : null}

          <div className="dp-end">
            <p className="dp-small">{PRICE_SOURCE}</p>
            <p>
              <Link href="/moves" className="link">
                {questionPage.movesLink}
              </Link>
            </p>
          </div>
        </article>
      </main>

      <SiteFooter />
    </>
  );
}
