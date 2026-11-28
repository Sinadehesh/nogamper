import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { JsonLd } from "@/components/JsonLd";
import { NotOpenYet } from "@/components/NotOpenYet";
import { renderProse } from "@/components/Prose";
import type { ContentsEntry } from "@/components/reading/Contents";
import { ReadingLayout } from "@/components/reading/ReadingLayout";
import { Sources } from "@/components/reading/Sources";
import { MainAction, SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { articlesPage } from "@/lib/content";
import { t } from "@/lib/copy";
import { calendarDate, dateUtc } from "@/lib/format";
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

function Trail({ section, sectionId }: { section: string; sectionId: string }) {
  return (
    <nav aria-label={t.articleBack} className="rd-trail">
      <Link href="/articles" prefetch={false}>
        {t.navGuides}
      </Link>
      <span aria-hidden="true" className="rd-trail__sep">
        /
      </span>
      <Link href={`/articles#${sectionId}`} prefetch={false}>
        {section}
      </Link>
    </nav>
  );
}

/**
 * What every article ends with: where real help is, and the game, once. A
 * guide about stepping back from gambling ends with the help alone (`quiet`):
 * it may have just asked its reader to close the tab, and nothing after that
 * invites them to play.
 */
function Closing({ quiet = false }: { quiet?: boolean }) {
  return (
    <>
      <p className="rd-note">
        {t.articleNotAdvice} {t.articleHelpPrompt}{" "}
        <Link href="/help" prefetch={false}>
          {t.articleHelpLink}
        </Link>
      </p>

      {quiet ? null : (
        <aside className="rd-try" aria-labelledby="try">
          <h2 id="try">{t.articleTryTitle}</h2>
          <p>{t.articleTryBody}</p>
          <div className="rd-try__actions">
            <MainAction fallback={<NotOpenYet />} />
            <Link href="/mission" className="dp-link" prefetch={false}>
              {articlesPage.tryOther}
            </Link>
          </div>
        </aside>
      )}
    </>
  );
}

function Guide({ guide }: { guide: Editorial }) {
  const path = `/articles/${guide.slug}`;
  const topic = articlesPage.topics[guide.topic];
  // Written for somebody who should step away: the header and the end of the
  // page offer help, not the game.
  const quiet = guide.topic === "stepping-back";
  const related = allEditorial()
    .filter((other) => other.slug !== guide.slug)
    .sort((a, b) => Number(b.topic === guide.topic) - Number(a.topic === guide.topic))
    .slice(0, 3);
  const { body, headings } = renderProse(guide.body);
  const entries: ContentsEntry[] = [
    ...headings.filter((heading) => heading.depth === 2),
    { id: "sources", text: t.articleSources },
  ];

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
          { name: t.navGuides, path: "/articles" },
          { name: guide.title, path },
        ])}
      />
      <SiteHeader quiet={quiet} />

      <main id="main" className="flex-1">
        <div className="wrap dp rd">
          <ReadingLayout
            label={articlesPage.tocLabel}
            count={articlesPage.tocCount(entries.length)}
            head={
              <>
                <Trail section={topic.title} sectionId={`topic-${guide.topic}`} />
                <h1 className="rd-title">{guide.title}</h1>
                <p className="dp-lede">{guide.description}</p>
                <p className="rd-byline">
                  <span>{t.articleByTeam}</span>
                  <time dateTime={guide.published}>
                    {t.articlePublished(calendarDate(guide.published))}
                  </time>
                  {guide.updated !== guide.published ? (
                    <time dateTime={guide.updated}>
                      {t.articleUpdated(calendarDate(guide.updated))}
                    </time>
                  ) : null}
                  <span>{t.articleReading(guide.readingMinutes)}</span>
                </p>
              </>
            }
            entries={entries}
            end={
              <>
                <Sources id="sources" title={t.articleSources} sources={guide.sources} />
                <Closing quiet={quiet} />
              </>
            }
          >
            {body}
          </ReadingLayout>

          {related.length > 0 ? (
            <section className="rd-next" aria-labelledby="more">
              <h2 id="more" className="dp-h2">
                {t.articleMore}
              </h2>
              <ul className="rd-next__list" role="list">
                {related.map((other) => (
                  <li key={other.slug}>
                    <Link href={`/articles/${other.slug}`} className="rd-card" prefetch={false}>
                      <span className="rd-card__kicker">{articlesPage.topics[other.topic].title}</span>
                      <span className="rd-card__title">{other.title}</span>
                      <span className="rd-card__meta">{t.articleReading(other.readingMinutes)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      </main>

      <SiteFooter />
    </>
  );
}

function FromReader({ article }: { article: PublishedArticle }) {
  const path = `/articles/${article.slug}`;
  const edited = article.edited_at.slice(0, 10) !== article.published_at.slice(0, 10);
  const { body, headings } = renderProse(article.body, true);
  const entries: ContentsEntry[] = headings.filter((heading) => heading.depth === 2);

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
          { name: t.navGuides, path: "/articles" },
          { name: article.title, path },
        ])}
      />
      <SiteHeader />

      <main id="main" className="flex-1">
        <div className="wrap dp rd">
          <ReadingLayout
            label={articlesPage.tocLabel}
            count={articlesPage.tocCount(entries.length)}
            head={
              <>
                <Trail section={articlesPage.readersTitle} sectionId="readers" />
                <p className="rd-chip">{t.articleFromReader}</p>
                <h1 className="rd-title">{article.title}</h1>
                <p className="dp-lede">{article.summary}</p>
                <p className="rd-byline">
                  <strong>{t.articleBy(article.author)}</strong>
                  <time dateTime={article.published_at}>
                    {t.articlePublished(dateUtc(article.published_at))}
                  </time>
                  {edited ? (
                    <time dateTime={article.edited_at}>
                      {t.articleUpdated(dateUtc(article.edited_at))}
                    </time>
                  ) : null}
                  <span>{t.articleReading(article.reading_minutes)}</span>
                </p>
              </>
            }
            entries={entries}
            end={
              <>
                <p className="rd-reader-note">{t.articleReaderNote}</p>
                <Closing />
              </>
            }
          >
            {body}
          </ReadingLayout>
        </div>
      </main>

      <SiteFooter />
    </>
  );
}
