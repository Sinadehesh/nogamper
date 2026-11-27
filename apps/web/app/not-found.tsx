import type { Metadata } from "next";
import Link from "next/link";

import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { notFoundPage } from "@/lib/content";

/**
 * The page for an address that leads nowhere: an unknown URL, a question or
 * an article that does not exist (their notFound()), the admin pages for
 * somebody who is not an operator. It renders inside the root layout and
 * answers with a real 404, which also tells search engines not to index it.
 *
 * One heading, one line, two ways on. The front page is a plain anchor: it
 * is always reached by a full page load.
 */

// Next.js adds the noindex itself to every page that answers 404.
export const metadata: Metadata = { title: notFoundPage.metaTitle };

export default function NotFound() {
  return (
    <>
      <SiteHeader />
      <main id="main" className="flex-1">
        <div className="wrap py-16 sm:py-24">
          <h1>{notFoundPage.title}</h1>
          <p className="t-lead measure mt-6">{notFoundPage.lede}</p>
          <div className="btn-row mt-8">
            <Link className="btn btn--primary" href="/questions" prefetch={false}>
              {notFoundPage.questionsLink}
            </Link>
            <a className="btn btn--secondary" href="/">
              {notFoundPage.homeLink}
            </a>
          </div>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
