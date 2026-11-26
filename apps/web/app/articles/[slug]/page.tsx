import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { JsonLd } from "@/components/JsonLd";
import { Prose } from "@/components/Prose";
import { StartActions } from "@/components/SignedIn";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { articlesPage } from "@/lib/content";
import { t } from "@/lib/copy";
import { calendarDate, date } from "@/lib/format";
import { articleLd, breadcrumbLd, pageMetadata } from "@/lib/seo";
import { getReaderArticle } from "@/lib/server/articles";
import { allEditorial, getEditorial, type Editorial } from "@/lib/server/editorial";
import type { PublishedArticle } from "@/lib/types";

type Props = { params: Promise<{ slug: string }> };

// The site's own articles are known when it is built and are built with it.
// A reader's article is fetched the first time its address is asked for.
export function generateStaticParams() {
  return allEditorial().map((article) => ({ slug: article.slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const path = `/articles/${slug}`;

  const guide = getEditorial(slug);
  if (guide) {
    return pageMetadata({
      title: guide.title,
      description: guide.description,
      path,
      ownImage: true,
      article: { published: guide.published, modified: guide.updated, author: t.appName },
    });
  }

  const article = await getReaderArticle(slug);
  if (!article) return { title: t.navArticles, robots: { index: false, follow: false } };
  return pageMetadata({
    title: article.title,
    description: article.summary,
    path,
    ownImage: true,
    article: {
      published: article.published_at,
      modified: article.edited_at,
      author: article.author,
    },
  });
}

export default async function ArticlePage({ params }: Props) {
  const { slug } = await params;

  const guide = getEditorial(slug);
  if (guide) return <Guide guide={guide} />;

  const article = await getReaderArticle(slug);
  if (!article) notFound();
  return <FromReader article={article} />;
}

function Trail({ section, sectionId }: { section?: string; sectionId?: string }) {
  return (
    <nav aria-label={t.articleBack} className="text-sm text-muted">
      <Link href="/articles" className="hover:text-ink">
        {t.navArticles}
      </Link>
      {section ? (
        <>
          <span aria-hidden className="mx-2">
            /
          </span>
          <Link href={`/articles#${sectionId}`} className="hover:text-ink">
            {section}
          </Link>
        </>
      ) : null}
    </nav>
  );
}

/** What every article ends with: where real help is, and what this site is. */
function Closing() {
  return (
    <>
      <p className="notice mt-10 max-w-2xl text-sm">
        {t.articleNotAdvice} {t.articleHelpPrompt}{" "}
        <Link href="/help" className="font-semibold text-accent underline underline-offset-2">
          {t.articleHelpLink}
        </Link>
      </p>

      <aside className="card mt-6 max-w-2xl p-5">
        <h2 className="text-lg font-bold">{t.articleTryTitle}</h2>
        <p className="mt-1 text-sm text-muted">{t.articleTryBody}</p>
        <div className="mt-4 flex flex-wrap items-start gap-3">
          <StartActions secondary={false} />
          <Link href="/mission" className="btn btn-quiet">
            {t.navMission}
          </Link>
        </div>
      </aside>
    </>
  );
}

function Guide({ guide }: { guide: Editorial }) {
  const path = `/articles/${guide.slug}`;
  const topic = articlesPage.topics[guide.topic];
  const related = allEditorial()
    .filter((other) => other.slug !== guide.slug)
    .sort((a, b) => Number(b.topic === guide.topic) - Number(a.topic === guide.topic))
    .slice(0, 3);

  return (
    <>
      <JsonLd
        data={articleLd({
          path,
          title: guide.title,
          description: guide.description,
          published: guide.published,
          modified: guide.updated,
          words: guide.words,
        })}
      />
      <JsonLd
        data={breadcrumbLd([
          { name: t.appName, path: "/" },
          { name: t.navArticles, path: "/articles" },
          { name: guide.title, path },
        ])}
      />
      <SiteHeader />

      <main id="main" className="container-page flex-1 py-10 sm:py-14">
        <article>
          <Trail section={topic.title} sectionId={`topic-${guide.topic}`} />
          <h1 className="mt-3 max-w-3xl text-4xl font-black leading-tight tracking-tight sm:text-5xl">
            {guide.title}
          </h1>
          <p className="mt-4 max-w-2xl text-lg text-muted">{guide.description}</p>
          <p className="mt-4 text-sm text-muted">
            {t.articleByTeam} ·{" "}
            <time dateTime={guide.published}>
              {t.articlePublished(calendarDate(guide.published))}
            </time>
            {guide.updated !== guide.published ? (
              <>
                {" · "}
                <time dateTime={guide.updated}>
                  {t.articleUpdated(calendarDate(guide.updated))}
                </time>
              </>
            ) : null}
            {" · "}
            {t.articleReading(guide.readingMinutes)}
          </p>

          <div className="mt-8">
            <Prose markdown={guide.body} />
          </div>

          <section className="mt-10 max-w-2xl" aria-labelledby="sources">
            <h2 id="sources" className="text-lg font-bold">
              {t.articleSources}
            </h2>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
              {guide.sources.map((source) => (
                <li key={source.href}>
                  <a
                    href={source.href}
                    rel="noopener noreferrer"
                    className="text-accent underline underline-offset-2"
                  >
                    {source.label}
                  </a>
                </li>
              ))}
            </ul>
          </section>

          <Closing />
        </article>

        {related.length > 0 ? (
          <section className="mt-12" aria-labelledby="more">
            <h2 id="more" className="text-xl font-bold tracking-tight">
              {t.articleMore}
            </h2>
            <ul className="mt-4 grid gap-3 md:grid-cols-3">
              {related.map((other) => (
                <li key={other.slug}>
                  <Link
                    href={`/articles/${other.slug}`}
                    className="card block h-full p-4 hover:border-muted"
                  >
                    <h3 className="font-bold leading-snug">{other.title}</h3>
                    <p className="mt-2 text-xs text-muted">
                      {t.articleReading(other.readingMinutes)}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </main>

      <SiteFooter />
    </>
  );
}

function FromReader({ article }: { article: PublishedArticle }) {
  const path = `/articles/${article.slug}`;
  const edited = article.edited_at.slice(0, 10) !== article.published_at.slice(0, 10);

  return (
    <>
      <JsonLd
        data={articleLd({
          path,
          title: article.title,
          description: article.summary,
          published: article.published_at,
          modified: article.edited_at,
          author: article.author,
          words: article.body.split(/\s+/).length,
        })}
      />
      <JsonLd
        data={breadcrumbLd([
          { name: t.appName, path: "/" },
          { name: t.navArticles, path: "/articles" },
          { name: article.title, path },
        ])}
      />
      <SiteHeader />

      <main id="main" className="container-page flex-1 py-10 sm:py-14">
        <article>
          <Trail section={articlesPage.readersTitle} sectionId="readers" />
          <p className="chip mt-4">{t.articleFromReader}</p>
          <h1 className="mt-3 max-w-3xl text-4xl font-black leading-tight tracking-tight sm:text-5xl">
            {article.title}
          </h1>
          <p className="mt-4 max-w-2xl text-lg text-muted">{article.summary}</p>
          <p className="mt-4 text-sm text-muted">
            {t.articleBy(article.author)} ·{" "}
            <time dateTime={article.published_at}>
              {t.articlePublished(date(article.published_at))}
            </time>
            {edited ? (
              <>
                {" · "}
                <time dateTime={article.edited_at}>
                  {t.articleUpdated(date(article.edited_at))}
                </time>
              </>
            ) : null}
            {" · "}
            {t.articleReading(article.reading_minutes)}
          </p>

          <div className="mt-8">
            <Prose markdown={article.body} fromReader />
          </div>

          <p className="mt-10 max-w-2xl text-sm text-muted">{t.articleReaderNote}</p>
          <Closing />
        </article>
      </main>

      <SiteFooter />
    </>
  );
}
