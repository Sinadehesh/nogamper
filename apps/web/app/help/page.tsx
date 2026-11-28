import Link from "next/link";
import { Fragment } from "react";

import "@/components/reading/reading.css";
import { WhenSignedIn } from "@/components/SignedIn";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { help } from "@/lib/content";
import { pageMetadata } from "@/lib/seo";
import { getRules } from "@/lib/server/rules";

export const metadata = pageMetadata({
  title: help.metaTitle,
  description: help.metaDescription,
  path: "/help",
});

function PhoneIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      <path
        d="M6.6 2.8 4.4 3.3a1.6 1.6 0 0 0-1.2 1.7c.6 6.2 5.6 11.2 11.8 11.8a1.6 1.6 0 0 0 1.7-1.2l.5-2.2a1.2 1.2 0 0 0-.7-1.4l-2.6-1.1a1.2 1.2 0 0 0-1.4.4l-.8 1a9.4 9.4 0 0 1-4.7-4.7l1-.8a1.2 1.2 0 0 0 .4-1.4L7.8 3.5a1.2 1.2 0 0 0-1.2-.7Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * Where to get help. Calm above everything: the urgent line first, then
 * people to call, each number one tap away; no effects, nothing that moves,
 * no accent colour. The order is the one that matters to somebody who
 * arrives here in trouble.
 */
export default async function HelpPage() {
  const rules = await getRules();

  return (
    <>
      {/* Somebody here may need to step away: the header offers no game. */}
      <SiteHeader quiet />

      <main id="main" className="flex-1">
        <div className="wrap dp rd">
          <header className="rd-help-head">
            <h1>{help.title}</h1>
            <section className="rd-urgent" aria-labelledby="emergency">
              <h2 id="emergency">{help.emergencyTitle}</h2>
              <p>{help.emergency}</p>
            </section>
            <p className="dp-lede">{help.lede}</p>
          </header>

          <section className="rd-section" aria-labelledby="resources">
            <div className="rd-section__head">
              <h2 id="resources" className="dp-h2">
                {help.resourcesTitle}
              </h2>
            </div>
            <ul className="rd-lines" role="list">
              {help.resources.map((resource) => (
                <li key={resource.name} className="rd-line">
                  <p className="rd-line__region">{resource.region}</p>
                  <h3>{resource.name}</h3>
                  {resource.contact && resource.tel ? (
                    <a
                      href={`tel:${resource.tel}`}
                      className="rd-tel"
                      aria-label={help.call(resource.name, resource.contact)}
                    >
                      <PhoneIcon />
                      <span>
                        {/* A number wraps only between its parts, never inside one. */}
                        {resource.contact.split(/ (?=\()/).map((part, index) => (
                          <Fragment key={part}>
                            {index > 0 ? " " : null}
                            <span className="whitespace-nowrap">{part}</span>
                          </Fragment>
                        ))}
                      </span>
                    </a>
                  ) : resource.contact ? (
                    <p className="rd-tel">{resource.contact}</p>
                  ) : null}
                  <p className="rd-line__body">{resource.body}</p>
                  <a href={resource.href} rel="noopener noreferrer" className="rd-line__web rd-plain-link">
                    {resource.linkLabel}
                  </a>
                </li>
              ))}
            </ul>
            <p className="rd-fine mt-4">{help.resourcesNote}</p>
          </section>

          <section className="rd-section" aria-labelledby="signs">
            <div className="rd-section__head">
              <h2 id="signs" className="dp-h2">
                {help.signsTitle}
              </h2>
              <p>{help.signsIntro}</p>
            </div>
            <ul className="rd-signs" role="list">
              {help.signs.map((sign) => (
                <li key={sign}>{sign}</li>
              ))}
            </ul>
            <p className="rd-fine mt-4">{help.signsOutro}</p>
          </section>

          <section className="rd-section" aria-labelledby="tools">
            <div className="rd-section__head">
              <h2 id="tools" className="dp-h2">
                {help.toolsTitle}
              </h2>
            </div>
            <ul className="rd-tools" role="list">
              {help.tools(rules).map((tool) => (
                <li key={tool.title} className="rd-tool">
                  <h3>{tool.title}</h3>
                  <p>{tool.body}</p>
                </li>
              ))}
            </ul>
            <WhenSignedIn>
              <p className="mt-5">
                <Link href="/play?tab=safer" className="btn btn--secondary" prefetch={false}>
                  {help.toolsCta}
                </Link>
              </p>
            </WhenSignedIn>
          </section>

          <section className="rd-section rd-measure" aria-labelledby="recovery">
            <h2 id="recovery" className="dp-h2">
              {help.recoveryTitle}
            </h2>
            <div className="rd-text mt-5">
              <p>{help.recovery}</p>
            </div>
          </section>
        </div>
      </main>

      <SiteFooter />
    </>
  );
}
