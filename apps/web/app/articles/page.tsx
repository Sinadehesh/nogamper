import Link from "next/link";

import "@/components/reading/reading.css";
import { JsonLd } from "@/components/JsonLd";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { articlesPage } from "@/lib/content";
import { t } from "@/lib/copy";
import { dateUtc } from "@/lib/format";
import { breadcrumbLd, listLd, pageMetadata } from "@/lib/seo";
import { listReaderArticles } from "@/lib/server/articles";
import { TOPICS, allEditorial, type Editorial } from "@/lib/server/editorial";

export const metadata = pageMetadata({
  title: articlesPage.metaTitle,
  description: articlesPage.metaDescription,
  path: "/articles",
});

/**
 * The guides: a way in for somebody new (three in order, the first shown
 * large), then every guide by topic as a list to scan, then what readers have
 * written, which takes a line when there is nothing yet.
 */
export default async function ArticlesPage() {
  const guides = allEditorial();
  const fromReaders = await listReaderArticles();
  const bySlug = new Map(guides.map((guide) => [guide.slug, guide]));
  const path = articlesPage.startPath
    .map((slug) => bySlug.get(slug))
    .filter((guide): guide is Editorial => guide !== undefined);

  return (
    <>
      <JsonLd
        data={breadcrumbLd([
          { name: t.appName, path: "/" },
          { name: t.navGuides, path: "/articles" },
        ])}
      />
      <JsonLd
        data={listLd(articlesPage.metaTitle, [
          ...guides.map((guide) => `/articles/${guide.slug}`),
          ...fromReaders.map((article) => `/articles/${article.slug}`),
        ])}
      />
      <SiteHeader />

      <main id="main" className="flex-1">
        <div className="wrap dp rd">
          <header className="dp-head">
            <h1>{articlesPage.title}</h1>
            <p className="dp-lede">{articlesPage.lede}</p>
          </header>

          {path.length > 0 ? (
            <section className="rd-section" aria-labelledby="start">
              <div className="rd-section__head">
                <h2 id="start" className="dp-h2">
                  {articlesPage.startTitle}
                </h2>
                <p>{articlesPage.startIntro}</p>
              </div>
              <ol className="rd-path" role="list">
                {path.map((guide, index) => (
                  <li key={guide.slug}>
                    <Link
                      href={`/articles/${guide.slug}`}
                      className={index === 0 ? "rd-step rd-step--lead" : "rd-step"}
                      prefetch={false}
                    >
                      <span className="rd-step__n" aria-hidden="true">
                        {index + 1}
                      </span>
                      <span className="rd-step__title">{guide.title}</span>
                      {index === 0 ? <span className="rd-step__text">{guide.description}</span> : null}
                      <span className="rd-step__meta">
                        {articlesPage.topics[guide.topic].title} · {t.articleReading(guide.readingMinutes)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ol>
            </section>
          ) : null}

          <section className="rd-section" aria-labelledby="guides">
            <div className="rd-section__head">
              <h2 id="guides" className="dp-h2">
                {articlesPage.groupsTitle}
              </h2>
            </div>

            {TOPICS.map((topic) => {
              const inTopic = guides.filter((guide) => guide.topic === topic);
              if (inTopic.length === 0) return null;
              return (
                <section key={topic} className="rd-group" aria-labelledby={`topic-${topic}`}>
                  <div className="rd-group__head">
                    <h3 id={`topic-${topic}`} className="rd-step__title">
                      {articlesPage.topics[topic].title}
                    </h3>
                    <p>{articlesPage.topics[topic].blurb}</p>
                    <p className="rd-group__count">{articlesPage.guideCount(inTopic.length)}</p>
                  </div>
                  <ul className="rd-rows" role="list">
                    {inTopic.map((guide) => (
                      <li key={guide.slug}>
                        <Link href={`/articles/${guide.slug}`} className="rd-row" prefetch={false}>
                          <span className="rd-row__title">{guide.title}</span>
                          <span className="rd-row__text">{guide.description}</span>
                          <span className="rd-row__meta">{t.articleReading(guide.readingMinutes)}</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })}
          </section>

          <section className="rd-section rd-group" aria-labelledby="readers">
            <div className="rd-group__head">
              <h2 id="readers" className="rd-step__title">
                {articlesPage.readersTitle}
              </h2>
              {fromReaders.length > 0 ? <p>{articlesPage.readersIntro}</p> : null}
            </div>

            {fromReaders.length === 0 ? (
              <p className="rd-oneline self-start">
                <span>{articlesPage.readersEmpty}</span>
                <Link href="/write" className="dp-link" prefetch={false}>
                  {articlesPage.writeCta}
                </Link>
              </p>
            ) : (
              <div className="flex flex-col gap-5">
                <ul className="rd-rows" role="list">
                  {fromReaders.map((article) => (
                    <li key={article.slug}>
                      <Link href={`/articles/${article.slug}`} className="rd-row" prefetch={false}>
                        <span className="rd-row__title">{article.title}</span>
                        <span className="rd-row__text">
                          {article.summary}
                          <br />
                          {t.articleBy(article.author)} · {dateUtc(article.published_at)}
                        </span>
                        <span className="rd-row__meta">{t.articleReading(article.reading_minutes)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
                <p className="rd-oneline">
                  <span>
                    <strong className="font-medium text-ink">{articlesPage.writeTitle}</strong>{" "}
                    {articlesPage.writeBody}
                  </span>
                  <Link href="/write" className="dp-link" prefetch={false}>
                    {articlesPage.writeCta}
                  </Link>
                </p>
              </div>
            )}
          </section>

          <section className="rd-section rd-measure" aria-labelledby="method">
            <h2 id="method" className="rd-small-h">
              {articlesPage.methodTitle}
            </h2>
            <p className="rd-fine mt-2">{articlesPage.method}</p>
          </section>
        </div>
      </main>

      <SiteFooter />
    </>
  );
}
