import Link from "next/link";

import { JsonLd } from "@/components/JsonLd";
import { StartActions } from "@/components/SignedIn";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { mission } from "@/lib/content";
import { t } from "@/lib/copy";
import { breadcrumbLd, pageMetadata } from "@/lib/seo";
import { getRules } from "@/lib/server/rules";

export const metadata = pageMetadata({
  title: mission.metaTitle,
  description: mission.metaDescription,
  path: "/mission",
  ownImage: true,
});

export default async function MissionPage() {
  const rules = await getRules();

  return (
    <>
      <JsonLd
        data={breadcrumbLd([
          { name: t.appName, path: "/" },
          { name: mission.metaTitle, path: "/mission" },
        ])}
      />
      <SiteHeader />

      <main id="main" className="flex-1">
        <section className="container-page py-12 sm:py-20">
          <p className="text-sm font-semibold uppercase tracking-wide text-accent">
            {mission.eyebrow}
          </p>
          <h1 className="mt-3 max-w-3xl text-4xl font-black leading-[1.05] tracking-tight sm:text-6xl">
            {mission.title}
          </h1>
          <p className="mt-6 max-w-2xl text-lg text-muted">{mission.lede}</p>
        </section>

        <section className="border-y border-line bg-surface" aria-labelledby="beliefs">
          <div className="container-page py-12">
            <h2 id="beliefs" className="text-2xl font-bold tracking-tight">
              {mission.beliefsTitle}
            </h2>
            <ol className="mt-6 grid gap-4 md:grid-cols-3">
              {mission.beliefs.map((belief) => (
                <li key={belief.title} className="rounded-2xl border border-line bg-bg p-5">
                  <h3 className="text-lg font-bold">{belief.title}</h3>
                  <p className="mt-2 text-sm text-muted">{belief.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="container-page py-12" aria-labelledby="scale">
          <div className="max-w-2xl">
            <h2 id="scale" className="text-2xl font-bold tracking-tight">
              {mission.scaleTitle}
            </h2>
            <div className="prose-block mt-4 text-muted">
              {mission.scale.map((paragraph) => (
                <p key={paragraph.slice(0, 24)}>{paragraph}</p>
              ))}
            </div>
            <p className="mt-5 text-xs font-semibold uppercase tracking-wide text-muted">
              {mission.sourcesLabel}
            </p>
            <ul className="mt-1 space-y-1 text-sm">
              {mission.scaleSources.map((source) => (
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
          </div>
        </section>

        <section className="border-y border-line bg-surface" aria-labelledby="do">
          <div className="container-page py-12">
            <h2 id="do" className="text-2xl font-bold tracking-tight">
              {mission.doTitle}
            </h2>
            <ul className="mt-6 grid gap-4 md:grid-cols-2">
              {mission.commitments(rules).map((commitment) => (
                <li
                  key={commitment.title}
                  // An odd one out at the end takes the full row instead of
                  // leaving half of it empty.
                  className="rounded-2xl border border-line bg-bg p-5 md:last:odd:col-span-2"
                >
                  <h3 className="text-lg font-bold">{commitment.title}</h3>
                  <p className="mt-2 text-sm text-muted">{commitment.body}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="container-page py-12" aria-labelledby="wont">
          <div className="max-w-2xl">
            <h2 id="wont" className="text-2xl font-bold tracking-tight">
              {mission.wontTitle}
            </h2>
            <ul className="mt-5 space-y-3">
              {mission.wont.map((promise) => (
                <li key={promise} className="flex gap-3">
                  <span aria-hidden className="mt-0.5 font-bold text-no">
                    ✕
                  </span>
                  <span>{promise}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="border-y border-line bg-surface">
          <div className="container-page grid gap-8 py-12 md:grid-cols-2">
            <div aria-labelledby="for">
              <h2 id="for" className="text-2xl font-bold tracking-tight">
                {mission.forTitle}
              </h2>
              <div className="prose-block mt-4 text-muted">
                {mission.forBody.map((paragraph) => (
                  <p key={paragraph.slice(0, 24)}>{paragraph}</p>
                ))}
              </div>
            </div>
            <div aria-labelledby="not-for">
              <h2 id="not-for" className="text-2xl font-bold tracking-tight">
                {mission.notForTitle}
              </h2>
              <div className="prose-block mt-4 text-muted">
                {mission.notForBody.map((paragraph) => (
                  <p key={paragraph.slice(0, 24)}>{paragraph}</p>
                ))}
              </div>
              <p className="mt-4">
                <Link
                  href="/help"
                  className="font-semibold text-accent underline underline-offset-2"
                >
                  {mission.notForLink}
                </Link>
              </p>
            </div>
          </div>
        </section>

        <section className="container-page py-12" aria-labelledby="measure">
          <div className="max-w-2xl">
            <h2 id="measure" className="text-2xl font-bold tracking-tight">
              {mission.measureTitle}
            </h2>
            <p className="mt-4 text-muted">{mission.measureIntro}</p>
            <ul className="mt-4 list-disc space-y-2 pl-5">
              {mission.measures.map((measure) => (
                <li key={measure.slice(0, 24)}>{measure}</li>
              ))}
            </ul>

            <h2 className="mt-12 text-2xl font-bold tracking-tight">
              {mission.independenceTitle}
            </h2>
            <p className="mt-4 text-muted">{mission.independence}</p>

            <div className="mt-10 flex flex-wrap items-start gap-3">
              <StartActions secondary={false} />
              <Link href="/articles" className="btn btn-secondary">
                {mission.ctaRead}
              </Link>
              <Link href="/help" className="btn btn-quiet">
                {mission.ctaHelp}
              </Link>
            </div>
          </div>
        </section>
      </main>

      <SiteFooter />
    </>
  );
}
