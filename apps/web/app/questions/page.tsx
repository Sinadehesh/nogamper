import Link from "next/link";

import { JsonLd } from "@/components/JsonLd";
import { LinkPending } from "@/components/LinkPending";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { FETCHING, FETCHING_SLOWLY, PRICE_SOURCE, questionsPage } from "@/lib/content";
import { t } from "@/lib/copy";
import { breadcrumbLd, pageMetadata } from "@/lib/seo";
import { keepEarlierCopy } from "@/lib/server/public";
import { allQuestions } from "@/lib/server/questions";
import type { QuestionIndexItem } from "@/lib/types";

// Kept for five minutes, then built again behind the next visitor.
export const revalidate = 300;

export const metadata = pageMetadata({
  title: questionsPage.metaTitle,
  description: questionsPage.metaDescription,
  path: "/questions",
  absoluteTitle: true,
});

// How many finished questions are listed. Their pages all still answer; this
// is only how far back the list on this page goes.
const FINISHED_SHOWN = 100;

function byCategory(questions: QuestionIndexItem[]): [string, QuestionIndexItem[]][] {
  const groups = new Map<string, QuestionIndexItem[]>();
  for (const question of questions) {
    groups.set(question.category, [...(groups.get(question.category) ?? []), question]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([category, items]) => [
      category,
      // Numbers read as numbers, so "$5,000" comes before "$10,000".
      [...items].sort((a, b) => a.question.localeCompare(b.question, "en", { numeric: true })),
    ]);
}

function QuestionLinks({ questions }: { questions: QuestionIndexItem[] }) {
  return (
    <ul className="mt-3 grid gap-x-8 gap-y-2 md:grid-cols-2">
      {questions.map((question) => (
        <li key={question.slug}>
          {/* Not fetched ahead of a click: there are hundreds of these, each
              page is built when first asked for, and scrolling past them
              should not build them all. */}
          <Link
            href={`/questions/${question.slug}`}
            prefetch={false}
            className="hover:text-accent hover:underline"
          >
            {question.question} <LinkPending label={FETCHING} slowLabel={FETCHING_SLOWLY} />
          </Link>
        </li>
      ))}
    </ul>
  );
}

/**
 * Every question, as a plain list of links.
 *
 * It exists so that each question's page can be reached by a person browsing
 * and by a search engine following links, not only from the game — which a
 * visitor without an account, and a crawler, never see.
 */
export default async function QuestionsPage() {
  const read = await allQuestions();
  // On the running site a list that could not be read leaves the page as it
  // was last built, rather than replacing four hundred links with an apology.
  if (read === null) keepEarlierCopy("The list of questions");
  const all = read ?? [];
  const open = all.filter((question) => question.state === "open");
  const finished = all.filter((question) => question.state !== "open").slice(0, FINISHED_SHOWN);

  return (
    <>
      <JsonLd
        data={breadcrumbLd([
          { name: t.appName, path: "/" },
          { name: t.navQuestions, path: "/questions" },
        ])}
      />
      <SiteHeader />

      <main id="main" className="container-page flex-1 py-10 sm:py-14">
        <div className="max-w-3xl">
          <h1 className="text-4xl font-black tracking-tight sm:text-5xl">{questionsPage.title}</h1>
          <p className="mt-4 text-lg text-muted">{questionsPage.lede}</p>
        </div>

        {read === null ? <p className="notice mt-8 max-w-2xl">{questionsPage.unavailable}</p> : null}
        {read?.length === 0 ? <p className="notice mt-8 max-w-2xl">{questionsPage.empty}</p> : null}

        {byCategory(open).map(([category, questions]) => (
          <section key={category} className="mt-10" aria-labelledby={`open-${category}`}>
            <h2 id={`open-${category}`} className="text-2xl font-bold tracking-tight">
              {category}
            </h2>
            <p className="mt-1 text-sm text-muted">{questionsPage.count(questions.length)}</p>
            <QuestionLinks questions={questions} />
          </section>
        ))}

        {finished.length > 0 ? (
          <section className="mt-14" aria-labelledby="finished">
            <h2 id="finished" className="text-2xl font-bold tracking-tight">
              {questionsPage.finished}
            </h2>
            <p className="mt-1 text-sm text-muted">{questionsPage.finishedIntro}</p>
            <QuestionLinks questions={finished} />
          </section>
        ) : null}

        <p className="mt-12 max-w-2xl text-sm text-muted">{PRICE_SOURCE}</p>
      </main>

      <SiteFooter />
    </>
  );
}
