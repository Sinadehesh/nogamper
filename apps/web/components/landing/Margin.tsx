import { MarginBars } from "@/components/viz";
import { landing } from "@/lib/content";
import { bookmakerTake } from "@/lib/odds";
import { getEditorial } from "@/lib/server/editorial";
import type { GameRules } from "@/lib/types";
import { marginPercent } from "@/lib/viz";

const escape = (text: string) =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/**
 * The margin, said once and large: the page's statement moment
 * (word-highlight, moments.md), the bookmaker's take on a slip of the most
 * picks the game allows, then the same figures for every length beside none,
 * and the two guides that go further (what a slip of many picks costs, and
 * how to stop).
 *
 * The statement is handed to the moment as written HTML: the moment wraps
 * each word in a span of its own as it mounts, and React, which only ever
 * renders the paragraph whole, never looks inside it.
 */
export function Margin({ rules }: { rules: GameRules | null }) {
  const margin = rules ? Number(rules.reference_margin) : Number.NaN;
  const figures =
    rules && Number.isFinite(margin) && margin > 0 && margin < 1 && rules.max_legs > 1
      ? {
          legs: rules.max_legs,
          margin: marginPercent(margin),
          take: `${(bookmakerTake(margin, rules.max_legs) * 100).toFixed(1)}%`,
        }
      : null;
  const statement = landing.marginStatement(figures);
  const html = `${escape(statement.lead)}<strong>${escape(statement.strong)}</strong>${escape(statement.end)}`;
  // A guide renamed or removed takes its link with it.
  const guides = landing.marginGuides.filter((item) => getEditorial(item.guide));

  return (
    <section
      className="section statement lp-margin"
      id="margin"
      data-moment="word-highlight"
      aria-labelledby="margin-h"
    >
      <div className="wrap">
        <p className="t-label lp-margin__label" id="margin-h">
          {landing.marginLabel}
        </p>
        <p className="mo-wh__text" dangerouslySetInnerHTML={{ __html: html }} />
        <MarginBars rules={rules} className="lp-margin__bars" />
        {guides.length ? (
          <p className="lp-margin__guides">
            {guides.map((item) => (
              <a key={item.guide} className="link" href={`/articles/${item.guide}`}>
                {item.label}
              </a>
            ))}
          </p>
        ) : null}
      </div>
    </section>
  );
}
