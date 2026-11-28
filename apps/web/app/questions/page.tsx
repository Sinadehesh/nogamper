import { JsonLd } from "@/components/JsonLd";
import { DIRECTORY_ID, Directory, byCategory } from "@/components/questions/Directory";
import { QuestionFilter } from "@/components/questions/QuestionFilter";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { PRICE_SOURCE, questionsPage } from "@/lib/content";
import { categoryLabel, t } from "@/lib/copy";
import { breadcrumbLd, pageMetadata } from "@/lib/seo";
import { keepEarlierCopy } from "@/lib/server/public";
import { allQuestions } from "@/lib/server/questions";

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

/**
 * Every question, as links.
 *
 * It exists so that each question's page can be reached by a person browsing
 * and by a search engine following links, not only from the game — which a
 * visitor without an account, and a crawler, never see. The index has no
 * figures (a chance per row would be one request per question), so the page
 * says once where the figures are, and makes four hundred titles scannable
 * instead: by subject, with near-identical titles gathered into families and
 * a filter that hides what does not match.
 */
export default async function QuestionsPage() {
  const read = await allQuestions();
  // On the running site a list that could not be read leaves the page as it
  // was last built, rather than replacing four hundred links with an apology.
  if (read === null) keepEarlierCopy("The list of questions");
  const all = read ?? [];
  const open = all.filter((question) => question.state === "open");
  const allFinished = all.filter((question) => question.state !== "open");
  const finished = allFinished.slice(0, FINISHED_SHOWN);
  const subjects = byCategory(open);

  return (
    <>
      <JsonLd
        data={breadcrumbLd([
          { name: t.appName, path: "/" },
          { name: t.navQuestions, path: "/questions" },
        ])}
      />
      <SiteHeader />

      <main id="main" className="flex-1">
        <div className="wrap dp">
          <header className="dp-head">
            <h1>{questionsPage.title}</h1>
            <p className="dp-lede">{questionsPage.lede}</p>
          </header>

          {read === null ? <p className="notice mt-8 max-w-2xl">{questionsPage.unavailable}</p> : null}
          {read?.length === 0 ? <p className="notice mt-8 max-w-2xl">{questionsPage.empty}</p> : null}

          {all.length > 0 ? (
            <>
              {/* The counts are also the way to each subject without a script. */}
              <nav className="qx-counts" aria-label={questionsPage.countsLabel}>
                {open.length > 0 ? (
                  <span className="qx-count qx-count--lead">
                    <b>{questionsPage.openCount(open.length)}</b>
                  </span>
                ) : null}
                {subjects.map(([category, items]) => (
                  <a key={category} className="qx-count" href={`#open-${category}`}>
                    {categoryLabel(category)} <b>{items.length}</b>
                  </a>
                ))}
                {allFinished.length > 0 ? (
                  <a className="qx-count" href="#finished">
                    {questionsPage.finishedCount(allFinished.length)}
                  </a>
                ) : null}
              </nav>

              <QuestionFilter
                listId={DIRECTORY_ID}
                total={open.length + finished.length}
                words={questionsPage.filter}
                categories={[...new Set(all.map((question) => question.category))]
                  .sort((a, b) => a.localeCompare(b))
                  .map((category) => ({ value: category, label: categoryLabel(category) }))}
                states={(["open", "closed", "resolved"] as const)
                  .filter((state) => all.some((question) => question.state === state))
                  .map((state) => ({ value: state, label: questionsPage.filter.states[state] }))}
              />

              <Directory open={open} finished={finished} finishedTotal={allFinished.length} />
            </>
          ) : null}

          <div className="dp-end">
            <p className="dp-small">{PRICE_SOURCE}</p>
          </div>
        </div>
      </main>

      <SiteFooter />
    </>
  );
}
