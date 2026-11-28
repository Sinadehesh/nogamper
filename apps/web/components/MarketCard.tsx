"use client";

import { useId } from "react";

import { useQuestionPage } from "@/components/game/context";
import { bothSides, PickFace, Wording } from "@/components/game/Pick";
import { useSlip } from "@/components/SlipProvider";
import { ChanceReadout, SplitBar } from "@/components/viz";
import { categoryLabel, t, viz } from "@/lib/copy";
import { isPriceable } from "@/lib/odds";
import type { MarketRules, MarketSummary, Side } from "@/lib/types";
import { closesOn, shortDateTimeUtc } from "@/lib/viz";

/** Within this long of closing, the card gives the time as well as the day. */
const SOON_MS = 48 * 60 * 60 * 1000;

/**
 * One question.
 *
 * The chance leads, in words ("42% chance of yes"), with the split bar under
 * it; the two picks follow, each with its own side's chance and what it
 * pays. On a betting slip the big number is what you could win; here it is
 * how likely the thing is, which is the number that is actually true.
 */
export function MarketCard({
  market,
  rules,
  paused,
  readAt,
}: {
  market: MarketSummary;
  rules: MarketRules;
  /** The player is on a break or at their limit: show everything, offer nothing. */
  paused: boolean;
  /** When the feed was read, in milliseconds: what "soon" and "this year" are measured from. */
  readAt: number;
}) {
  const slip = useSlip();
  const titleId = useId();
  const page = useQuestionPage(market.question);
  const blocked = slip.blockedBecause(market);
  const stale = market.probability.stale;
  const chosen: Side | null = slip.has(market.id, "YES")
    ? "YES"
    : slip.has(market.id, "NO")
      ? "NO"
      : null;
  const sides = bothSides(
    market.probability.yes,
    (side) => isPriceable(market, side, rules),
    market.probability.no,
  );
  const settled = sides.some((side) => side.pays === null);
  const closesSoon = Date.parse(market.lock_at) - readAt < SOON_MS;
  const closes = closesSoon
    ? viz.closesOn(shortDateTimeUtc(market.lock_at))
    : closesOn(market.lock_at, new Date(readAt).toISOString());

  return (
    <article className="gm-card" aria-labelledby={titleId}>
      <p className="gm-card__meta">
        <span className="dp-tag">{categoryLabel(market.category)}</span>
        <span>{closes}</span>
        {stale ? <span>{t.priceUpdating}</span> : null}
      </p>

      <div>
        <h3 id={titleId} className="gm-card__q">
          <Wording text={market.question} />
        </h3>
        {market.event.title && market.event.title !== market.question ? (
          <p className="gm-card__event">{market.event.title}</p>
        ) : null}
      </div>

      <div className="gm-card__read">
        <ChanceReadout yes={market.probability.yes} size="card" />
        {page ? (
          // A new tab, so that looking at the chart never costs the picks
          // gathered on this page's slip.
          <a className="gm-link gm-card__chart" href={page} target="_blank" rel="noopener">
            {t.seeChart}
            <svg viewBox="0 0 10 10" aria-hidden="true">
              <path d="M3 1.5h5.5V7M8.5 1.5 1.5 8.5" />
            </svg>
            <span className="sr-only">{t.newTab}</span>
          </a>
        ) : null}
      </div>

      <SplitBar yes={market.probability.yes} size="sm" labels={false} className="gm-card__bar" />

      <div className="gm-picks">
        {sides.map((side) => {
          const selected = chosen === side.side;
          return (
            <button
              key={side.side}
              type="button"
              className="gm-pick"
              data-side={side.side === "YES" ? "yes" : "no"}
              aria-pressed={selected}
              aria-describedby={titleId}
              disabled={paused || stale || side.pays === null || (Boolean(blocked) && !selected)}
              onClick={() => slip.toggle(market, side.side)}
            >
              <PickFace side={side} />
            </button>
          );
        })}
      </div>

      {chosen ? (
        <p className="gm-card__note gm-card__note--on">{t.onSlip(chosen === "YES" ? t.yes : t.no)}</p>
      ) : settled ? (
        <p className="gm-card__note">{t.settledAlreadyHint}</p>
      ) : blocked ? (
        <p className="gm-card__note">{blocked}</p>
      ) : null}
    </article>
  );
}
