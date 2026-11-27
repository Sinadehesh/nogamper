import "./viz.css";

import { viz } from "@/lib/copy";
import type { Side } from "@/lib/types";
import { count } from "@/lib/format";
import { gameFigures, type SlipLegInput, type SlipRules, slipFigures } from "@/lib/viz";

import { Figure } from "./Figure";
import { at, cx, vars } from "./style";

const { odds, points } = gameFigures;

/**
 * The game's own `chance()`, except where it would print a false "0.0%".
 * That only happens past the combined-odds limit (no slip the game prices
 * comes in below 0.1%), so on every slip the game would take the two agree.
 */
function chance(probability: number | string): string {
  const text = gameFigures.chance(probability);
  return text === "0.0%" && Number(probability) > 0 ? "<0.1%" : text;
}

/** "1,000×" for a whole limit, the game's own "2.50×" otherwise. */
function limit(value: string): string {
  const parsed = Number(value);
  return Number.isInteger(parsed) ? `${count(parsed)}×` : odds(parsed);
}

/** A modest round stake for the illustration: 100 points. */
const EXAMPLE_STAKE = 10_000;

type PickFiguresProps = {
  side: Side;
  /** The chosen side's own probability, as the API sends it ("0.6200"). */
  probability: string | number;
  /** In minor units (1/100 of a point). 100 points unless given. */
  stakeMinor?: number;
  rules: SlipRules;
  className?: string;
};

/**
 * One pick, three figures: its chance, the fair odds that follow from it
 * (1 ÷ p, truncated as the game does), and what a stake comes back as.
 * The same functions as the game's own cards and slip, so the figures here
 * are the ones the game shows.
 */
export function PickFigures({ side, probability, stakeMinor = EXAMPLE_STAKE, rules, className }: PickFiguresProps) {
  const figures = slipFigures([{ side, probability }], stakeMinor, rules);
  const pick = figures.picks[0];
  const p = Number(probability);
  const stake = points(stakeMinor);

  return (
    <div className={cx("viz-pick", className)}>
      <ol className="viz-pick__steps">
        <li className="viz-pick__step">
          <Figure className="viz-pick__figure" text={chance(p)} />
          <span className="viz-pick__words">{viz.pickChance(side)}</span>
        </li>
        {figures.refused === null && pick ? (
          <>
            <li className="viz-pick__arrow" aria-hidden="true">
              {viz.stepArrow}
            </li>
            <li className="viz-pick__step">
              <Figure className="viz-pick__figure" text={odds(pick.odds)} />
              <span className="viz-pick__words">{viz.pickOdds}</span>
              <span className="viz-pick__rule">{viz.pickRule(String(p))}</span>
            </li>
            <li className="viz-pick__arrow" aria-hidden="true">
              {viz.stepArrow}
            </li>
            <li className="viz-pick__step">
              <Figure className="viz-pick__figure" text={points(figures.payoutMinor)} />
              <span className="viz-pick__words">{viz.pickReturn(stake)}</span>
            </li>
          </>
        ) : null}
      </ol>
      {figures.refused === "unpriceable" ? (
        <p className="viz-pick__note">{viz.pickUnpriceableNote}</p>
      ) : null}
      {figures.capped ? <p className="viz-pick__note">{viz.slipCapped(rules.payout_cap.display)}</p> : null}
    </div>
  );
}

type SlipFiguresProps = {
  legs: SlipLegInput[];
  /** In minor units. 100 points unless given. */
  stakeMinor?: number;
  rules: SlipRules;
  className?: string;
};

/**
 * Several picks on one slip: the chance that all of them are right, drawn
 * as it shrinks with each pick added ("All 3 right: 23% chance"), and what
 * the slip would return, worked out exactly as the server prices it, with
 * its limits and its cap.
 */
export function SlipFiguresView({ legs, stakeMinor = EXAMPLE_STAKE, rules, className }: SlipFiguresProps) {
  const figures = slipFigures(legs, stakeMinor, rules);
  const count = figures.picks.length;
  const stake = points(stakeMinor);

  if (!count) return <p className={cx("viz-slip__note", className)}>{viz.slipEmpty}</p>;

  return (
    <div className={cx("viz-slip", className)}>
      <p className="viz-slip__title">{viz.stepsTitle}</p>
      <ol className="viz-slip__steps">
        {figures.picks.map((pick, index) => {
          const step = figures.steps[index] ?? 0;
          return (
            <li key={index} className="viz-slip__step" data-last={index === count - 1 ? "" : undefined}>
              <span className="viz-slip__label">
                {viz.stepPick(index + 1, pick.side === "YES" ? viz.yes : viz.no, chance(pick.probability))}
              </span>
              <span className="viz-slip__track" aria-hidden="true">
                <span className="viz-slip__fill" style={vars({ "--viz-p": at(step) })} />
              </span>
              <span className="viz-slip__value">{chance(step)}</span>
            </li>
          );
        })}
      </ol>
      <p className="viz-slip__total">
        <Figure className="viz-slip__all" text={viz.allRight(count, chance(figures.chance))} />
      </p>
      {figures.refused === null ? (
        <p className="viz-slip__return">
          <b>
            <Figure text={viz.slipPays(odds(figures.combinedOdds))} />
          </b>
          <Figure text={viz.slipReturn(points(figures.payoutMinor), stake)} />
        </p>
      ) : null}
      {figures.capped ? <p className="viz-slip__note">{viz.slipCapped(rules.payout_cap.display)}</p> : null}
      {figures.refused === "over_limit" ? (
        <p className="viz-slip__note">{viz.slipOverLimit(limit(rules.max_combined_odds))}</p>
      ) : null}
      {figures.refused === "unpriceable" ? <p className="viz-slip__note">{viz.slipUnpriceable}</p> : null}
      {figures.refused === "too_many" ? <p className="viz-slip__note">{viz.slipTooMany(rules.max_legs)}</p> : null}
    </div>
  );
}
