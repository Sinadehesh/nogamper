import Link from "next/link";

import { JsonLd } from "@/components/JsonLd";
import { StartActions, WhenGameOpen, WhenSignedOut } from "@/components/SignedIn";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { landing } from "@/lib/content";
import { t } from "@/lib/copy";
import { percent } from "@/lib/format";
import { bookmakerTake } from "@/lib/odds";
import { organizationLd, pageMetadata, websiteLd } from "@/lib/seo";
import { getEditorial } from "@/lib/server/editorial";
import { getRules } from "@/lib/server/rules";

const PICK_COUNTS = [1, 2, 3, 4, 5];

export const metadata = pageMetadata({
  title: landing.metaTitle,
  description: landing.metaDescription,
  path: "/",
  absoluteTitle: true,
});

export default async function LandingPage() {
  const rules = await getRules();
  const margin = Number(rules?.reference_margin ?? "0.05");
  const marginLabel = percent(margin);
  // A guide that has been renamed or removed simply drops out of the list.
  const reading = landing.readSlugs.flatMap((slug) => getEditorial(slug) ?? []);

  return (
    <>
      <JsonLd data={websiteLd()} />
      <JsonLd data={organizationLd()} />
      <SiteHeader />

      <main id="main" className="flex-1">
        <section className="container-page py-12 sm:py-20">
          <p className="text-sm font-semibold uppercase tracking-wide text-accent">
            {landing.eyebrow}
          </p>
          <h1 className="mt-3 max-w-3xl text-4xl font-black leading-[1.05] tracking-tight sm:text-6xl">
            {landing.headline}
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-muted">{landing.lede}</p>

          <div className="mt-8 flex flex-wrap items-start gap-3">
            <StartActions />
          </div>
          <WhenGameOpen>
            <p className="mt-4 text-sm text-muted">
              {landing.ctaNote} <WhenSignedOut>{t.adultsConfirm}</WhenSignedOut>
            </p>
          </WhenGameOpen>
        </section>

        <section className="border-y border-line bg-surface">
          <div className="container-page py-12">
            <h2 className="text-2xl font-bold tracking-tight">{landing.promisesTitle}</h2>
            <ul className="mt-6 grid gap-4 md:grid-cols-3">
              {landing.promises(rules).map((promise) => (
                <li key={promise.title} className="rounded-2xl border border-line bg-bg p-5">
                  <h3 className="text-lg font-bold">{promise.title}</h3>
                  <p className="mt-2 text-sm text-muted">{promise.body}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="container-page py-12">
          <h2 className="text-2xl font-bold tracking-tight">{landing.stepsTitle}</h2>
          <ol className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {landing.steps(rules).map((step, index) => (
              <li key={step.title}>
                <span
                  className="flex size-9 items-center justify-center rounded-full bg-accent
                             font-bold tabular-nums text-on-accent"
                  aria-hidden
                >
                  {index + 1}
                </span>
                <h3 className="mt-3 font-bold">{step.title}</h3>
                <p className="mt-1 text-sm text-muted">{step.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="border-y border-line bg-surface">
          <div className="container-page grid gap-8 py-12 lg:grid-cols-2 lg:items-center">
            <div>
              <h2 className="text-2xl font-bold tracking-tight">{landing.mathTitle}</h2>
              <p className="mt-4 text-muted">{landing.mathIntro(marginLabel)}</p>
              <p className="mt-4 text-muted">{landing.mathOutro}</p>
            </div>

            {/* Bars as well as figures: the point is how fast the first column
                grows, and that is a shape before it is a number. The bar is
                scaled so five picks fill it; the label carries the value. */}
            <table className="table">
              <thead>
                {/* Headings may wrap here, unlike in the operator's tables:
                    held on one line they are wider than a small phone, and
                    the page then scrolls sideways. */}
                <tr className="align-bottom">
                  <th scope="col" className="whitespace-normal">
                    {landing.mathColumnPicks}
                  </th>
                  <th scope="col" className="whitespace-normal">
                    {landing.mathThere(marginLabel)}
                  </th>
                  <th scope="col" className="num whitespace-normal">
                    {landing.mathHere}
                  </th>
                </tr>
              </thead>
              <tbody>
                {PICK_COUNTS.map((count) => {
                  const take = bookmakerTake(margin, count);
                  const widest = bookmakerTake(margin, PICK_COUNTS[PICK_COUNTS.length - 1]!);
                  return (
                    <tr key={count}>
                      <th scope="row" className="font-semibold normal-case tracking-normal text-ink">
                        {landing.mathPicks(count)}
                      </th>
                      <td>
                        <span className="flex items-center gap-3">
                          <span className="tabular-nums w-12 font-semibold text-no">
                            {percent(take, 1)}
                          </span>
                          <span className="h-2 flex-1 rounded-full bg-sunken" aria-hidden>
                            <span
                              className="block h-full rounded-full bg-no"
                              style={{ width: `${(take / widest) * 100}%` }}
                            />
                          </span>
                        </span>
                      </td>
                      <td className="num font-semibold text-yes">{landing.mathNothing}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        {reading.length > 0 ? (
          <section className="container-page py-12" aria-labelledby="reading">
            <h2 id="reading" className="text-2xl font-bold tracking-tight">
              {landing.readTitle}
            </h2>
            <p className="mt-2 max-w-2xl text-muted">{landing.readIntro}</p>
            <ul className="mt-6 grid gap-4 md:grid-cols-3">
              {reading.map((guide) => (
                <li key={guide.slug} className="card p-5">
                  <h3 className="font-bold">
                    <Link href={`/articles/${guide.slug}`} className="hover:text-accent">
                      {guide.title}
                    </Link>
                  </h3>
                  <p className="mt-2 text-sm text-muted">{guide.description}</p>
                </li>
              ))}
            </ul>
            <p className="mt-5">
              <Link
                href="/articles"
                className="font-semibold text-accent underline underline-offset-2"
              >
                {landing.readAll}
              </Link>
            </p>
          </section>
        ) : null}

        <section className="border-t border-line bg-surface">
          <div className="container-page py-12">
          <h2 className="text-2xl font-bold tracking-tight">{landing.whyTitle}</h2>
          <div className="prose-block mt-4 max-w-2xl text-muted">
            {landing.why.map((paragraph) => (
              <p key={paragraph.slice(0, 24)}>{paragraph}</p>
            ))}
          </div>
          <p className="mt-5">
            <Link href="/mission" className="font-semibold text-accent underline underline-offset-2">
              {landing.whyMissionLink}
            </Link>
          </p>
          <p className="notice mt-6 max-w-2xl">
            {landing.whyHelpPrompt}{" "}
            <Link href="/help" className="font-semibold text-accent underline underline-offset-2">
              {landing.whyHelpLink}
            </Link>
          </p>
          </div>
        </section>
      </main>

      <SiteFooter />
    </>
  );
}
