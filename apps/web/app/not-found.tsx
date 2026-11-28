import type { Metadata } from "next";
import Link from "next/link";

import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { notFoundPage } from "@/lib/content";
import { t } from "@/lib/copy";

/**
 * The page for an address that leads nowhere: an unknown URL, a question or
 * an article that does not exist (their notFound()), the admin pages for
 * somebody who is not an operator. It renders inside the root layout and
 * answers with a real 404, which also tells search engines not to index it.
 *
 * One heading, one line, two ways on, in the page column every app page
 * shares (its h1 starts where theirs do). The header's button is the page's
 * one lime fill, so the list of questions is the secondary button. The front
 * page is a plain anchor: it is always reached by a full page load.
 */

// The whole title, written out: a 404 met under a segment with a title of its
// own (the admin pages) would otherwise lose the site's name after it. Next.js
// adds the noindex itself to every page that answers 404.
export const metadata: Metadata = {
  title: { absolute: `${notFoundPage.metaTitle} · ${t.appName}` },
};

export default function NotFound() {
  return (
    <>
      <SiteHeader />
      <main id="main" className="flex-1">
        <div className="wrap dp">
          <header className="dp-head">
            <h1>{notFoundPage.title}</h1>
            <p className="dp-lede">{notFoundPage.lede}</p>
          </header>
          {/* Not the kit's .btn-row, which turns a lone outlined button
              into a text link on a phone: here it stays a button, with the
              way home a text link beside or under it. */}
          <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
            <Link className="btn btn--secondary" href="/questions" prefetch={false}>
              {notFoundPage.questionsLink}
            </Link>
            <a className="link" href="/">
              {notFoundPage.homeLink}
            </a>
          </div>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
