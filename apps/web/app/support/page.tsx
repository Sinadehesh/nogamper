import Link from "next/link";

import "@/components/reading/reading.css";
import { JsonLd } from "@/components/JsonLd";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { DONATE_PAYEE, DONATE_URL, price, support } from "@/lib/content";
import { t } from "@/lib/copy";
import { breadcrumbLd, pageMetadata } from "@/lib/seo";
import { getRules } from "@/lib/server/rules";

export const metadata = pageMetadata({
  title: support.metaTitle,
  description: support.metaDescription,
  path: "/support",
});

/** One of the other ways to help, as a card that is a link. */
function Way({ way }: { way: (typeof support.other)[number] }) {
  const inner = (
    <>
      <span className="rd-card__title">{way.title}</span>
      <span className="rd-card__text">{way.body}</span>
      <span className="rd-card__go">{way.cta}</span>
    </>
  );
  // The front page runs the kit's scripts and is always reached by a full
  // page load; another site is left the ordinary way.
  if (way.href === "/") {
    return (
      <a href="/" className="rd-card">
        {inner}
      </a>
    );
  }
  if (/^https?:\/\//.test(way.href)) {
    return (
      <a href={way.href} rel="noopener noreferrer" className="rd-card">
        {inner}
      </a>
    );
  }
  return (
    <Link href={way.href} className="rd-card" prefetch={false}>
      {inner}
    </Link>
  );
}

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
  // With no way to give, the page says who pays and leaves out what money
  // would be for, so it does not ask for what it cannot take.
  const giving = donations || shop !== null;

  return (
    <>
      <JsonLd
        data={breadcrumbLd([
          { name: t.appName, path: "/" },
          { name: support.metaTitle, path: "/support" },
        ])}
      />
      <SiteHeader />

      <main id="main" className="flex-1">
        <div className="wrap dp rd">
          <header className="dp-head">
            <h1>{support.title}</h1>
            <p className="dp-lede">{giving ? support.lede : support.ledeClosed}</p>
          </header>

          {giving ? null : <p className="rd-state mt-8">{support.nothingYet}</p>}

          {giving ? (
            <section className="rd-section" aria-labelledby="costs">
              <div className="rd-section__head">
                <h2 id="costs" className="dp-h2">
                  {support.costsTitle}
                </h2>
              </div>
              <ol className="rd-costs" role="list">
                {support.costs.map((cost) => (
                  <li key={cost.slice(0, 24)}>{cost}</li>
                ))}
              </ol>
            </section>
          ) : null}

          {giving ? (
            <div className="rd-section rd-give">
              {donations ? (
                <section className="rd-give__card" aria-labelledby="donate">
                  <h2 id="donate" className="dp-h2">
                    {support.donateTitle}
                  </h2>
                  <p className="rd-give__text">{support.donateBody}</p>
                  <p>
                    <a
                      href={DONATE_URL}
                      className="btn btn--primary"
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      {support.donateCta}
                    </a>
                  </p>
                  <div className="flex flex-col gap-1">
                    <p className="rd-give__fine">{support.donateNote}</p>
                    {DONATE_PAYEE ? (
                      <p className="rd-give__fine">{support.donatePayee(DONATE_PAYEE)}</p>
                    ) : null}
                  </div>
                </section>
              ) : null}

              {shop && rules ? (
                <section className="rd-give__card" aria-labelledby="points">
                  <h2 id="points" className="dp-h2">
                    {support.pointsTitle}
                  </h2>
                  <p className="rd-give__text">{support.pointsBody(rules)}</p>
                  <div>
                    <h3 className="dp-label mb-2">{support.pointsPriceLabel}</h3>
                    <ul className="rd-packs" role="list">
                      {shop.packs.map((pack) => (
                        <li key={pack.points.minor}>
                          {support.pointsPack(pack.points.display, price(pack.price_cents, shop.currency))}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <p>
                    <Link href="/play?tab=account" className="btn btn--secondary" prefetch={false}>
                      {support.pointsCta}
                    </Link>
                  </p>
                  <p className="rd-give__fine">{support.pointsCtaNote}</p>
                </section>
              ) : null}
            </div>
          ) : null}

          {shop && rules ? (
            <section className="rd-section" aria-labelledby="terms">
              <div className="rd-section__head">
                <h2 id="terms" className="dp-h2">
                  {support.pointsTermsTitle}
                </h2>
              </div>
              <ol className="rd-terms" role="list">
                {support.pointsTerms(rules).map((term) => (
                  <li key={term.slice(0, 24)}>{term}</li>
                ))}
              </ol>
              <div className="rd-urgent mt-8">
                <h3>{support.cautionTitle}</h3>
                <p>
                  {support.cautionBody}{" "}
                  <Link href="/help" className="rd-plain-link" prefetch={false}>
                    {support.cautionLink}
                  </Link>
                </p>
              </div>
            </section>
          ) : null}

          {giving ? (
            <section className="rd-section rd-measure" aria-labelledby="refunds">
              <h2 id="refunds" className="dp-h2">
                {support.refundsTitle}
              </h2>
              <div className="rd-text mt-5">
                <p>{support.refundsBody}</p>
              </div>
            </section>
          ) : null}

          <section className="rd-section" aria-labelledby="other">
            <div className="rd-section__head">
              <h2 id="other" className="dp-h2">
                {support.otherTitle}
              </h2>
            </div>
            <ul className="rd-ways" role="list">
              {support.other.map((way) => (
                <li key={way.title}>
                  <Way way={way} />
                </li>
              ))}
            </ul>
          </section>
        </div>
      </main>

      <SiteFooter />
    </>
  );
}
