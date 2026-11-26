import Link from "next/link";

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

export default async function HelpPage() {
  const rules = await getRules();

  return (
    <>
      <SiteHeader />

      <main id="main" className="container-page flex-1 py-10 sm:py-14">
        <div className="max-w-3xl">
          <h1 className="text-4xl font-black tracking-tight">{help.title}</h1>
          <p className="mt-4 text-lg text-muted">{help.lede}</p>

          <section className="notice notice-warn mt-8" aria-labelledby="emergency">
            <h2 id="emergency" className="font-bold">
              {help.emergencyTitle}
            </h2>
            <p className="mt-1">{help.emergency}</p>
          </section>

          <section className="mt-10" aria-labelledby="resources">
            <h2 id="resources" className="text-2xl font-bold tracking-tight">
              {help.resourcesTitle}
            </h2>
            <ul className="mt-5 space-y-3">
              {help.resources.map((resource) => (
                <li key={resource.name} className="card p-5">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                    {resource.region}
                  </p>
                  <h3 className="mt-1 text-lg font-bold">{resource.name}</h3>
                  {"contact" in resource && resource.contact ? (
                    <p className="mt-1 text-xl font-black tabular-nums">{resource.contact}</p>
                  ) : null}
                  <p className="mt-2 text-sm text-muted">{resource.body}</p>
                  <a
                    href={resource.href}
                    rel="noopener noreferrer"
                    className="mt-3 inline-block font-semibold text-accent underline underline-offset-2"
                  >
                    {resource.linkLabel}
                  </a>
                </li>
              ))}
            </ul>
            <p className="mt-4 text-sm text-muted">{help.resourcesNote}</p>
          </section>

          <section className="mt-10" aria-labelledby="signs">
            <h2 id="signs" className="text-2xl font-bold tracking-tight">
              {help.signsTitle}
            </h2>
            <p className="mt-3 text-muted">{help.signsIntro}</p>
            <ul className="mt-3 list-disc space-y-1 ps-6">
              {help.signs.map((sign) => (
                <li key={sign}>{sign}</li>
              ))}
            </ul>
            <p className="mt-4 text-sm text-muted">{help.signsOutro}</p>
          </section>

          <section className="mt-10" aria-labelledby="tools">
            <h2 id="tools" className="text-2xl font-bold tracking-tight">
              {help.toolsTitle}
            </h2>
            <ul className="mt-5 grid gap-3 sm:grid-cols-2">
              {help.tools(rules).map((tool) => (
                <li key={tool.title} className="card p-4">
                  <h3 className="font-bold">{tool.title}</h3>
                  <p className="mt-1 text-sm text-muted">{tool.body}</p>
                </li>
              ))}
            </ul>
            <WhenSignedIn>
              <Link href="/play?tab=safer" className="btn btn-secondary mt-4">
                {help.toolsCta}
              </Link>
            </WhenSignedIn>
          </section>

          <section className="mt-10" aria-labelledby="recovery">
            <h2 id="recovery" className="text-2xl font-bold tracking-tight">
              {help.recoveryTitle}
            </h2>
            <p className="mt-3 text-muted">{help.recovery}</p>
          </section>
        </div>
      </main>

      <SiteFooter />
    </>
  );
}
