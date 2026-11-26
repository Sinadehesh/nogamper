import Link from "next/link";

import { JsonLd } from "@/components/JsonLd";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { DONATE_URL, price, support } from "@/lib/content";
import { t } from "@/lib/copy";
import { breadcrumbLd, pageMetadata } from "@/lib/seo";
import { getRules } from "@/lib/server/rules";

export const metadata = pageMetadata({
  title: support.metaTitle,
  description: support.metaDescription,
  path: "/support",
});

/**
 * How the site is paid for, and how to help pay for it.
 *
 * The page has to be true in four states — donations open or not, the shop
 * open or not — so each section is shown only when the thing it describes
 * exists. With neither, it says so plainly rather than showing a button that
 * goes nowhere.
 *
 * The Donate button is a plain link to Stripe's page. No script of Stripe's
 * runs here, and nothing about the visitor is sent along with the click.
 */
export default async function SupportPage() {
  const rules = await getRules();
  const shop = rules?.shop.open ? rules.shop : null;
  const donations = DONATE_URL !== "";

  return (
    <>
      <JsonLd
        data={breadcrumbLd([
          { name: t.appName, path: "/" },
          { name: support.metaTitle, path: "/support" },
        ])}
      />
      <SiteHeader />

      <main id="main" className="container-page flex-1 py-10 sm:py-14">
        <div className="max-w-2xl">
          <h1 className="text-3xl font-black tracking-tight sm:text-4xl">{support.title}</h1>
          <p className="mt-4 text-lg text-muted">{support.lede}</p>

          {!donations && !shop ? <p className="notice mt-6">{support.nothingYet}</p> : null}

          <h2 className="mt-10 text-xl font-bold tracking-tight">{support.costsTitle}</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-muted">
            {support.costs.map((cost) => (
              <li key={cost.slice(0, 24)}>{cost}</li>
            ))}
          </ul>
        </div>

        {donations || shop ? (
          <div className="mt-10 grid gap-5 lg:grid-cols-2">
            {donations ? (
              <section className="card p-6" aria-labelledby="donate">
                <h2 id="donate" className="text-xl font-bold tracking-tight">
                  {support.donateTitle}
                </h2>
                <p className="mt-3 text-sm text-muted">{support.donateBody}</p>
                <p className="mt-5">
                  <a
                    href={DONATE_URL}
                    className="btn btn-primary"
                    rel="noopener noreferrer"
                    target="_blank"
                  >
                    {support.donateCta}
                  </a>
                </p>
                <p className="mt-2 text-xs text-muted">{support.donateNote}</p>
              </section>
            ) : null}

            {shop && rules ? (
              <section className="card p-6" aria-labelledby="points">
                <h2 id="points" className="text-xl font-bold tracking-tight">
                  {support.pointsTitle}
                </h2>
                <p className="mt-3 text-sm text-muted">{support.pointsBody(rules)}</p>
                <h3 className="mt-4 text-sm font-semibold">{support.pointsPriceLabel}</h3>
                <ul className="mt-2 space-y-1 text-sm tabular-nums">
                  {shop.packs.map((pack) => (
                    <li key={pack.points.minor}>
                      {support.pointsPack(
                        pack.points.display,
                        price(pack.price_cents, shop.currency),
                      )}
                    </li>
                  ))}
                </ul>
                <p className="mt-5">
                  <Link href="/play?tab=account" className="btn btn-secondary">
                    {support.pointsCta}
                  </Link>
                </p>
                <p className="mt-2 text-xs text-muted">{support.pointsCtaNote}</p>
              </section>
            ) : null}
          </div>
        ) : null}

        <div className="max-w-2xl">
          {shop && rules ? (
            <>
              <h2 id="terms" className="mt-10 text-xl font-bold tracking-tight">
                {support.pointsTermsTitle}
              </h2>
              <ul className="mt-3 list-disc space-y-2 pl-5 text-muted">
                {support.pointsTerms(rules).map((term) => (
                  <li key={term.slice(0, 24)}>{term}</li>
                ))}
              </ul>

              <div className="notice notice-warn mt-6">
                <h2 className="font-bold">{support.cautionTitle}</h2>
                <p className="mt-2 text-sm">
                  {support.cautionBody}{" "}
                  <Link href="/help" className="font-semibold underline underline-offset-2">
                    {support.cautionLink}
                  </Link>
                </p>
              </div>
            </>
          ) : null}

          {donations || shop ? (
            <>
              <h2 id="refunds" className="mt-10 text-xl font-bold tracking-tight">
                {support.refundsTitle}
              </h2>
              <p className="mt-3 text-muted">{support.refundsBody}</p>
            </>
          ) : null}

          <h2 className="mt-10 text-xl font-bold tracking-tight">{support.otherTitle}</h2>
        </div>

        <ul className="mt-4 grid gap-4 md:grid-cols-3">
          {support.other.map((way) => (
            <li key={way.title} className="card p-5">
              <h3 className="font-bold">{way.title}</h3>
              <p className="mt-2 text-sm text-muted">{way.body}</p>
              <p className="mt-3 text-sm">
                <Link
                  href={way.href}
                  className="font-semibold text-accent underline underline-offset-2"
                >
                  {way.cta}
                </Link>
              </p>
            </li>
          ))}
        </ul>
      </main>

      <SiteFooter />
    </>
  );
}
