import "@/components/reading/reading.css";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { AUTHOR_NAME, AUTHOR_URL, REPOSITORY_URL, about } from "@/lib/content";
import { pageMetadata } from "@/lib/seo";
import { getRules } from "@/lib/server/rules";

export const metadata = pageMetadata({
  title: about.title,
  description: about.metaDescription,
  path: "/about",
});

/**
 * The rules at a glance, read from the live settings, then why they are set
 * that way; where the prices come from; what was taken out; and, last and
 * apart, how the thing is built, for the people who read code.
 */
export default async function AboutPage() {
  const rules = await getRules();

  return (
    <>
      <SiteHeader />

      <main id="main" className="flex-1">
        <div className="wrap dp rd">
          <header className="dp-head">
            <h1>{about.title}</h1>
            <p className="dp-lede">{about.lede}</p>
          </header>

          <section className="rd-section" aria-labelledby="rules">
            <div className="rd-section__head">
              <h2 id="rules" className="dp-h2">
                {about.rulesTitle}
              </h2>
              <p>{about.rulesIntro}</p>
            </div>
            {rules ? (
              <dl className="rd-rules">
                {about.ruleRows(rules).map((row) => (
                  <div key={row.label} className="rd-rules__row">
                    <dt>{row.label}</dt>
                    <dd className="rd-rules__value">{row.value}</dd>
                    <dd className="rd-rules__why">{row.note}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="dp-empty">{about.rulesUnavailable}</p>
            )}

            <h3 className="rd-sub-h">{about.reasonsTitle}</h3>
            <ul className="rd-reasons" role="list">
              {about.rules(rules).map((rule) => (
                <li key={rule.title}>
                  <h4 className="rd-step__title">{rule.title}</h4>
                  <p>{rule.body}</p>
                </li>
              ))}
            </ul>
          </section>

          <section className="rd-section" aria-labelledby="source">
            <div className="rd-section__head">
              <h2 id="source" className="dp-h2">
                {about.sourceTitle}
              </h2>
              <p>{about.source}</p>
            </div>
            <ul className="rd-facts" role="list">
              {about.sourceFacts.map((fact) => (
                <li key={fact.key} className="rd-fact">
                  <p className="rd-fact__k">{fact.key}</p>
                  <p className="rd-fact__v">{fact.value}</p>
                  <p className="rd-fact__body">{fact.body}</p>
                </li>
              ))}
            </ul>
          </section>

          <section className="rd-section" aria-labelledby="absent">
            <div className="rd-section__head">
              <h2 id="absent" className="dp-h2">
                {about.absentTitle}
              </h2>
              <p>{about.absentIntro}</p>
            </div>
            <ul className="rd-marks rd-marks--cols" role="list">
              {about.absent.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>

          <section className="rd-band" aria-labelledby="build">
            <div className="rd-section__head">
              <p className="rd-eyebrow">{about.buildEyebrow}</p>
              <h2 id="build" className="dp-h2">
                {about.buildTitle}
              </h2>
              <p>{about.buildIntro}</p>
            </div>
            <ul className="rd-parts" role="list">
              {about.build.map((part) => (
                <li key={part.title} className="rd-part">
                  <h3>{part.title}</h3>
                  <p>{part.body}</p>
                </li>
              ))}
            </ul>
            <div className="rd-actions mt-6">
              <a href={REPOSITORY_URL} rel="noopener noreferrer" className="btn btn--secondary">
                {about.buildRepo}
              </a>
              {AUTHOR_NAME ? (
                AUTHOR_URL ? (
                  <a href={AUTHOR_URL} rel="noopener noreferrer" className="dp-link text-sm">
                    {about.buildBy(AUTHOR_NAME)}
                  </a>
                ) : (
                  <span className="text-sm text-muted">{about.buildBy(AUTHOR_NAME)}</span>
                )
              ) : null}
            </div>
          </section>
        </div>
      </main>

      <SiteFooter />
    </>
  );
}
