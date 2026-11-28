import Link from "next/link";

import { JsonLd } from "@/components/JsonLd";
import { NotOpenYet } from "@/components/NotOpenYet";
import { OxFigure } from "@/components/reading/OxFigure";
import { Sources } from "@/components/reading/Sources";
import { MainAction, SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { DONATE_URL, mission } from "@/lib/content";
import { t } from "@/lib/copy";
import { breadcrumbLd, pageMetadata } from "@/lib/seo";
import { getRules } from "@/lib/server/rules";

export const metadata = pageMetadata({
  title: mission.metaTitle,
  description: mission.metaDescription,
  path: "/mission",
  ownImage: true,
});

/**
 * Why the site exists, what it does and what it will not do. The case rests
 * on a few numbers, so they are set as figures with their sources; the name's
 * story is drawn from its own three figures; the promises are a list with a
 * neutral mark, because a refusal is not a score.
 */
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
        <div className="wrap dp rd">
          <header className="dp-head">
            <p className="rd-eyebrow">{mission.eyebrow}</p>
            <h1>{mission.title}</h1>
            <p className="dp-lede">{mission.lede}</p>
          </header>

          <section className="rd-section" aria-labelledby="beliefs">
            <div className="rd-section__head">
              <h2 id="beliefs" className="dp-h2">
                {mission.beliefsTitle}
              </h2>
            </div>
            <ol className="rd-points" role="list">
              {mission.beliefs.map((belief) => (
                <li key={belief.title}>
                  <h3>{belief.title}</h3>
                  <p>{belief.body}</p>
                </li>
              ))}
            </ol>
          </section>

          <section className="rd-section" aria-labelledby="scale">
            <div className="rd-section__head">
              <h2 id="scale" className="dp-h2">
                {mission.scaleTitle}
              </h2>
            </div>
            <ul className="rd-stats" role="list">
              {mission.scaleFigures.map((stat) => (
                <li key={stat.figure} className="rd-stat">
                  <p className="rd-stat__fig">
                    <span className="rd-stat__q">{stat.qualifier}</span>
                    {stat.figure}
                    {stat.unit ? <span className="rd-stat__unit">{stat.unit}</span> : null}
                  </p>
                  <p className="rd-stat__what">{stat.what}</p>
                  <p className="rd-stat__src">{mission.scaleBy[stat.source]}</p>
                </li>
              ))}
            </ul>
            <div className="rd-two mt-8">
              <div className="rd-text">
                {mission.scale.map((paragraph) => (
                  <p key={paragraph.slice(0, 24)}>{paragraph}</p>
                ))}
              </div>
              <Sources
                id="scale-sources"
                title={mission.sourcesLabel}
                sources={mission.scaleSources}
                headingLevel={3}
              />
            </div>
          </section>

          <section className="rd-section" aria-labelledby="do">
            <div className="rd-section__head">
              <h2 id="do" className="dp-h2">
                {mission.doTitle}
              </h2>
            </div>
            <ul className="rd-dos" role="list">
              {mission.commitments(rules).map((commitment) => (
                <li key={commitment.title}>
                  <h3>{commitment.title}</h3>
                  <p>{commitment.body}</p>
                </li>
              ))}
            </ul>
          </section>

          <section className="rd-band" aria-labelledby="wont">
            <div className="rd-section__head">
              <h2 id="wont" className="dp-h2">
                {mission.wontTitle}
              </h2>
            </div>
            <ul className="rd-marks rd-marks--cols" role="list">
              {mission.wont(rules).map((promise) => (
                <li key={promise.slice(0, 32)}>{promise}</li>
              ))}
            </ul>
          </section>

          <div className="rd-section rd-two">
            <section aria-labelledby="for">
              <h2 id="for" className="dp-h2">
                {mission.forTitle}
              </h2>
              <div className="rd-text mt-5">
                {mission.forBody.map((paragraph) => (
                  <p key={paragraph.slice(0, 24)}>{paragraph}</p>
                ))}
              </div>
            </section>
            <section aria-labelledby="not-for">
              <h2 id="not-for" className="dp-h2">
                {mission.notForTitle}
              </h2>
              <div className="rd-text mt-5">
                {mission.notForBody.map((paragraph) => (
                  <p key={paragraph.slice(0, 24)}>{paragraph}</p>
                ))}
                <p>
                  <Link href="/help" className="rd-link" prefetch={false}>
                    {mission.notForLink}
                  </Link>
                </p>
              </div>
            </section>
          </div>

          <section className="rd-section" aria-labelledby="measure">
            <div className="rd-section__head">
              <h2 id="measure" className="dp-h2">
                {mission.measureTitle}
              </h2>
              <p>{mission.measureIntro}</p>
            </div>
            <ul className="rd-list" role="list">
              {mission.measures.map((measure) => (
                <li key={measure.slice(0, 24)}>{measure}</li>
              ))}
            </ul>
          </section>

          {mission.nameApplies ? (
            <section className="rd-band" aria-labelledby="name">
              <div className="rd-two">
                <div>
                  <h2 id="name" className="dp-h2">
                    {mission.nameTitle}
                  </h2>
                  <div className="rd-text mt-5">
                    {mission.name.map((paragraph) => (
                      <p key={paragraph.slice(0, 24)}>{paragraph}</p>
                    ))}
                  </div>
                  <div className="mt-6">
                    <Sources
                      id="name-sources"
                      title={mission.sourcesLabel}
                      sources={mission.nameSources}
                      headingLevel={3}
                    />
                  </div>
                </div>
                <OxFigure />
              </div>
            </section>
          ) : null}

          <section className="rd-close" aria-labelledby="paid">
            <div className="rd-two">
              <div>
                <h2 id="paid" className="dp-h2">
                  {mission.paidTitle}
                </h2>
                <div className="rd-text mt-5">
                  {mission.paid(rules, DONATE_URL !== "").map((paragraph) => (
                    <p key={paragraph.slice(0, 24)}>{paragraph}</p>
                  ))}
                  <p>
                    <Link href="/support" className="rd-link" prefetch={false}>
                      {mission.paidLink}
                    </Link>
                  </p>
                </div>
              </div>
              <div>
                <h2 id="independent" className="dp-h2">
                  {mission.independenceTitle}
                </h2>
                <div className="rd-text mt-5">
                  <p>{mission.independence}</p>
                </div>
              </div>
            </div>
            <div className="rd-actions mt-4">
              <MainAction fallback={<NotOpenYet />}>
                <svg className="m-arrow" viewBox="0 0 12 12" aria-hidden="true">
                  <path className="m-arrow__stem" d="M1 6h8" />
                  <path className="m-arrow__head" d="M4.5 2.5 8 6l-3.5 3.5" />
                </svg>
              </MainAction>
              <Link href="/articles" className="btn btn--secondary" prefetch={false}>
                {mission.ctaRead}
              </Link>
              <Link href="/help" className="btn btn-quiet" prefetch={false}>
                {mission.ctaHelp}
              </Link>
            </div>
          </section>
        </div>
      </main>

      <SiteFooter />
    </>
  );
}
