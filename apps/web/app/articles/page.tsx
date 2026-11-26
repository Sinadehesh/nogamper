import Link from "next/link";

import { JsonLd } from "@/components/JsonLd";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { articlesPage } from "@/lib/content";
import { t } from "@/lib/copy";
import { date } from "@/lib/format";
import { breadcrumbLd, listLd, pageMetadata } from "@/lib/seo";
import { listReaderArticles } from "@/lib/server/articles";
import { TOPICS, allEditorial } from "@/lib/server/editorial";

export const metadata = pageMetadata({
  title: articlesPage.metaTitle,
  description: articlesPage.metaDescription,
  path: "/articles",
});

export default async function ArticlesPage() {
  const guides = allEditorial();
  const fromReaders = await listReaderArticles();

  return (
    <>
      <JsonLd
        data={breadcrumbLd([
          { name: t.appName, path: "/" },
          { name: t.navArticles, path: "/articles" },
        ])}
      />
      <JsonLd
        data={listLd(articlesPage.metaTitle, [
          ...guides.map((guide) => `/articles/${guide.slug}`),
          ...fromReaders.map((article) => `/articles/${article.slug}`),
        ])}
      />
      <SiteHeader />

      <main id="main" className="container-page flex-1 py-10 sm:py-14">
        <div className="max-w-3xl">
          <h1 className="text-4xl font-black tracking-tight sm:text-5xl">{articlesPage.title}</h1>
          <p className="mt-4 text-lg text-muted">{articlesPage.lede}</p>
        </div>

        {TOPICS.map((topic) => {
          const inTopic = guides.filter((guide) => guide.topic === topic);
          if (inTopic.length === 0) return null;
          return (
            <section key={topic} className="mt-12" aria-labelledby={`topic-${topic}`}>
              <h2 id={`topic-${topic}`} className="text-2xl font-bold tracking-tight">
                {articlesPage.topics[topic].title}
              </h2>
              <p className="mt-1 max-w-2xl text-muted">{articlesPage.topics[topic].blurb}</p>
              <ul className="mt-5 grid gap-3 md:grid-cols-2">
                {inTopic.map((guide) => (
                  <li key={guide.slug}>
                    <Link
                      href={`/articles/${guide.slug}`}
                      className="card block h-full p-5 hover:border-muted"
                    >
                      <h3 className="text-lg font-bold leading-snug">{guide.title}</h3>
                      <p className="mt-2 text-sm text-muted">{guide.description}</p>
                      <p className="mt-3 text-xs text-muted">
                        {t.articleReading(guide.readingMinutes)}
                      </p>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}

        <section className="mt-14" aria-labelledby="readers">
          <h2 id="readers" className="text-2xl font-bold tracking-tight">
            {articlesPage.readersTitle}
          </h2>
          <p className="mt-1 max-w-2xl text-muted">{articlesPage.readersIntro}</p>

          {fromReaders.length === 0 ? (
            <p className="mt-5 text-muted">{articlesPage.readersEmpty}</p>
          ) : (
            <ul className="mt-5 grid gap-3 md:grid-cols-2">
              {fromReaders.map((article) => (
                <li key={article.slug}>
                  <Link
                    href={`/articles/${article.slug}`}
                    className="card block h-full p-5 hover:border-muted"
                  >
                    <h3 className="text-lg font-bold leading-snug">{article.title}</h3>
                    <p className="mt-2 text-sm text-muted">{article.summary}</p>
                    <p className="mt-3 text-xs text-muted">
                      {t.articleBy(article.author)} · {date(article.published_at)} ·{" "}
                      {t.articleReading(article.reading_minutes)}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          )}

          <div className="notice mt-6 max-w-2xl">
            <h3 className="font-bold">{articlesPage.writeTitle}</h3>
            <p className="mt-1 text-sm">{articlesPage.writeBody}</p>
            <Link href="/write" className="btn btn-secondary btn-sm mt-3">
              {articlesPage.writeCta}
            </Link>
          </div>
        </section>

        <section className="mt-14 max-w-2xl" aria-labelledby="method">
          <h2 id="method" className="text-lg font-bold">
            {articlesPage.methodTitle}
          </h2>
          <p className="mt-2 text-sm text-muted">{articlesPage.method}</p>
        </section>
      </main>

      <SiteFooter />
    </>
  );
}
