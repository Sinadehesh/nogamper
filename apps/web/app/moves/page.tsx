import Link from "next/link";

import { AsOf } from "@/components/AsOf";
import { JsonLd } from "@/components/JsonLd";
import { MovesKey, MovesSection, asPercentagePoints } from "@/components/questions/Moves";
import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import { PRICE_SOURCE, movesPage } from "@/lib/content";
import { t } from "@/lib/copy";
import { dateTimeUtc } from "@/lib/format";
import { breadcrumbLd, listLd, pageMetadata } from "@/lib/seo";
import { keepEarlierCopy } from "@/lib/server/public";
import { getMoves } from "@/lib/server/questions";

// Kept for five minutes, then built again behind the next visitor.
export const revalidate = 300;

export const metadata = pageMetadata({
  title: movesPage.metaTitle,
  description: movesPage.metaDescription,
  path: "/moves",
  absoluteTitle: true,
});

/**
 * The questions whose chances changed most.
 *
 * It reports; it does not explain and it does not predict, and the page says
 * so in as many words. Nothing on it is coloured as a gain or a loss, counts
 * down, or asks to be acted on — a list of prices that just moved is the one
 * thing on this site that could be mistaken for a tip sheet, so it is built
 * not to read like one. Up and down are drawn in one colour; the arrow's
 * direction and the two figures say which way it went.
 */
export default async function MovesPage() {
  const moves = await getMoves();
  // Could not be read, or the figures are out of date (a server just woken
  // has yesterday's until it has read the market again, and says so rather
  // than send them). On the running site either leaves the page as it was
  // last built.
  if (moves === null) keepEarlierCopy("The list of moves");
  const listed = moves ? [...moves.day, ...moves.week] : [];
  const measuredAt = moves?.measured_at ?? null;

  return (
    <>
      <JsonLd
        data={breadcrumbLd([
          { name: t.appName, path: "/" },
          { name: t.navMoves, path: "/moves" },
        ])}
      />
      {listed.length > 0 ? (
        <JsonLd
          data={listLd(
            movesPage.title,
            [...new Set(listed.map((move) => `/questions/${move.slug}`))],
          )}
        />
      ) : null}
      <SiteHeader />

      <main id="main" className="flex-1">
        <div className="wrap dp">
          <div className="mv-top">
            <header className="dp-head">
              <h1>{movesPage.title}</h1>
              <p className="dp-lede">{movesPage.lede}</p>
              <p className="dp-sub">{movesPage.notATipLine}</p>
              {moves ? (
                <div className="flex flex-col gap-1">
                  {measuredAt ? (
                    <p className="dp-small">{movesPage.measured(dateTimeUtc(measuredAt))}</p>
                  ) : null}
                  <AsOf at={moves.as_of} changing />
                </div>
              ) : null}
            </header>
            {moves ? <MovesKey moves={moves} /> : null}
          </div>

          {moves === null ? (
            <p className="notice mt-8 max-w-2xl">{movesPage.unavailable}</p>
          ) : (
            <>
              <MovesSection
                id="day"
                title={movesPage.dayTitle}
                window="day"
                moves={moves.day}
                empty={movesPage.emptyDay(asPercentagePoints(moves.day_threshold))}
                reference={moves.as_of}
                measuredAt={measuredAt}
              />
              <MovesSection
                id="week"
                title={movesPage.weekTitle}
                window="week"
                moves={moves.week}
                empty={movesPage.emptyWeek(asPercentagePoints(moves.week_threshold))}
                reference={moves.as_of}
                measuredAt={measuredAt}
              />
            </>
          )}

          <section className="mv-tip" aria-labelledby="not-a-tip">
            <h2 id="not-a-tip" className="dp-h2">
              {movesPage.notATipTitle}
            </h2>
            {movesPage.notATip.map((paragraph) => (
              <p key={paragraph.slice(0, 24)}>{paragraph}</p>
            ))}
          </section>

          <div className="dp-end">
            <p className="dp-small">{PRICE_SOURCE}</p>
            <p>
              <Link href="/questions" className="link">
                {movesPage.allLink}
              </Link>
            </p>
          </div>
        </div>
      </main>

      <SiteFooter />
    </>
  );
}
