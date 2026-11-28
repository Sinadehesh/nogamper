import { bothSides, PickFace, Wording } from "@/components/game/Pick";
import { ChanceReadout, SplitBar } from "@/components/viz";
import { Figure } from "@/components/viz/Figure";
import { categoryLabel, t } from "@/lib/copy";
import { points } from "@/lib/format";
import { fairOdds } from "@/lib/odds";
import type { GameRules, Move, Moves } from "@/lib/types";
import { closesOn, slipFigures } from "@/lib/viz";

/** The stake the picture shows a pick at: 100 points, in minor units. */
const SHOWN_STAKE = 10_000;

/**
 * The question the picture shows: one of the questions that moved, open and
 * well inside the game's band, so both picks are real ones. Null when there
 * is none to hand, and then there is no picture.
 */
export function previewQuestion(moves: Moves | null): Move | null {
  if (!moves) return null;
  const all = [...moves.day, ...moves.week];
  const inside = all.find((move) => {
    const yes = Number(move.now);
    return yes >= 0.15 && yes <= 0.85;
  });
  return inside ?? all[0] ?? null;
}

/**
 * A picture of the game: one live question as a card shows it, with yes
 * picked and the slip that pick makes, in the front page's words. Drawn, not
 * working: the parts are spans, hidden from a screen reader, which hears one
 * sentence saying what the picture shows.
 */
export function GamePreview({
  move,
  asOf,
  rules,
}: {
  move: Move;
  /** When the figures are from: the reference for "this year" in the date. */
  asOf: string;
  rules: GameRules | null;
}) {
  const yes = Number(move.now);
  const priceable = (_side: unknown, probability: number) =>
    rules
      ? probability >= Number(rules.min_prob) && probability <= Number(rules.max_prob)
      : probability > 0 && probability < 1;
  const [yesSide, noSide] = bothSides(move.now, priceable);
  const figures = rules ? slipFigures([{ side: "YES", probability: yes }], SHOWN_STAKE, rules) : null;
  const payout = figures
    ? figures.refused === null
      ? points(figures.payoutMinor)
      : null
    : yes > 0 && yes < 1
      ? points(Math.round(SHOWN_STAKE * fairOdds(yes)))
      : null;

  return (
    <figure className="gm-preview gm">
      {payout ? (
        <p className="sr-only">
          {t.previewLabel(move.question, yesSide.chance, noSide.chance, payout)}
        </p>
      ) : null}
      <div className="gm-preview__stage" aria-hidden="true">
        <div className="gm-card">
          <p className="gm-card__meta">
            <span className="dp-tag">{categoryLabel(move.category)}</span>
            <span>{closesOn(move.closes_at, asOf)}</span>
          </p>
          <div>
            <p className="gm-card__q">
              <Wording text={move.question} />
            </p>
            {move.event_title && move.event_title !== move.question ? (
              <p className="gm-card__event">{move.event_title}</p>
            ) : null}
          </div>
          <div className="gm-card__read">
            <ChanceReadout yes={move.now} size="card" />
          </div>
          <SplitBar yes={move.now} size="sm" labels={false} className="gm-card__bar" />
          <span className="gm-picks">
            {[yesSide, noSide].map((side) => (
              <span
                key={side.side}
                className="gm-pick"
                data-side={side.side === "YES" ? "yes" : "no"}
                data-chosen={side.side === "YES" ? "" : undefined}
              >
                <PickFace side={side} />
              </span>
            ))}
          </span>
        </div>
        {payout ? (
          <div className="gm-preview__slip">
            <span className="gm-label">{t.slipTitle}</span>
            <b>
              <Figure text={t.slipPick(t.yes, yesSide.chance)} />
            </b>
            <span>
              <Figure text={t.slipStakeLine(points(SHOWN_STAKE))} />
            </span>
            <span>
              <Figure text={t.slipPaysLine(payout)} />
            </span>
          </div>
        ) : null}
      </div>
      <figcaption>{t.previewCaption}</figcaption>
    </figure>
  );
}
