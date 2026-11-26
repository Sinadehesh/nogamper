import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { AUTHOR_NAME, AUTHOR_URL, REPOSITORY_URL, about } from "@/lib/content";
import { pageMetadata } from "@/lib/seo";
import { getRules } from "@/lib/server/rules";

export const metadata = pageMetadata({
  title: about.title,
  description: about.metaDescription,
  path: "/about",
});

export default async function AboutPage() {
  const rules = await getRules();

  return (
    <>
      <SiteHeader />

      <main id="main" className="container-page flex-1 py-10 sm:py-14">
        <div className="max-w-3xl">
          <h1 className="text-4xl font-black tracking-tight">{about.title}</h1>
          <p className="mt-4 text-lg text-muted">{about.lede}</p>
        </div>

        <section className="mt-10" aria-labelledby="rules">
          <h2 id="rules" className="text-2xl font-bold tracking-tight">
            {about.rulesTitle}
          </h2>
          <ul className="mt-5 grid gap-3 md:grid-cols-2">
            {about.rules(rules).map((rule) => (
              <li key={rule.title} className="card p-5">
                <h3 className="font-bold">{rule.title}</h3>
                <p className="mt-2 text-sm text-muted">{rule.body}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-10 max-w-3xl" aria-labelledby="source">
          <h2 id="source" className="text-2xl font-bold tracking-tight">
            {about.sourceTitle}
          </h2>
          <p className="mt-3 text-muted">{about.source}</p>
        </section>

        <section className="mt-10 max-w-3xl" aria-labelledby="absent">
          <h2 id="absent" className="text-2xl font-bold tracking-tight">
            {about.absentTitle}
          </h2>
          <p className="mt-3 text-muted">{about.absentIntro}</p>
          <ul className="mt-4 grid gap-x-6 gap-y-2 sm:grid-cols-2">
            {about.absent.map((item) => (
              <li key={item} className="flex gap-2">
                <span className="font-bold text-no" aria-hidden>
                  ✕
                </span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-10" aria-labelledby="build">
          <h2 id="build" className="text-2xl font-bold tracking-tight">
            {about.buildTitle}
          </h2>
          <p className="mt-3 max-w-3xl text-muted">{about.buildIntro}</p>
          <ul className="mt-5 grid gap-3 md:grid-cols-3">
            {about.build.map((part) => (
              <li key={part.title} className="card p-5">
                <h3 className="font-bold">{part.title}</h3>
                <p className="mt-2 text-sm text-muted">{part.body}</p>
              </li>
            ))}
          </ul>
          <p className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2">
            <a href={REPOSITORY_URL} rel="noopener noreferrer" className="btn btn-secondary">
              {about.buildRepo}
            </a>
            {AUTHOR_NAME ? (
              AUTHOR_URL ? (
                <a
                  href={AUTHOR_URL}
                  rel="noopener noreferrer"
                  className="text-sm text-muted underline underline-offset-2"
                >
                  {about.buildBy(AUTHOR_NAME)}
                </a>
              ) : (
                <span className="text-sm text-muted">{about.buildBy(AUTHOR_NAME)}</span>
              )
            ) : null}
          </p>
        </section>
      </main>

      <SiteFooter />
    </>
  );
}
