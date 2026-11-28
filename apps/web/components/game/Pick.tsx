import { Figure } from "@/components/viz/Figure";
import { t } from "@/lib/copy";
import { odds } from "@/lib/format";
import { fairOdds } from "@/lib/odds";
import type { Side } from "@/lib/types";
import { pctPair, sideProbability } from "@/lib/viz";

/**
 * One side of a question as the game draws it, the front page's pill: the
 * word, the side's chance, and what a pick on it pays. Both sides share one
 * shape and one weight; only a chosen side fills (decision 6).
 */

export type Side2 = {
  side: Side;
  /** The side's chance as printed, from Yes so the two add up to 100. */
  chance: string;
  /** "pays 2.35×", or null when the game would not price this side. */
  pays: string | null;
};

/**
 * Both sides from the Yes price. The No side's own probability is the API's
 * `no` string where there is one, else `sideProbability`: never 1 − yes in
 * floating point, whose odds would come out a millionth short of the game's.
 */
export function bothSides(
  yes: string | number,
  priceable: (side: Side, probability: number) => boolean,
  no?: string,
): [Side2, Side2] {
  const pair = pctPair(yes);
  const make = (side: Side): Side2 => {
    const probability = side === "NO" && no !== undefined ? Number(no) : sideProbability(yes, side);
    return {
      side,
      chance: side === "YES" ? pair.yes : pair.no,
      pays: priceable(side, probability) ? t.pays(odds(fairOdds(probability))) : null,
    };
  };
  return [make("YES"), make("NO")];
}

/** The inside of a pick: the same for the game's buttons and its pictures. */
export function PickFace({ side }: { side: Side2 }) {
  return (
    <>
      <span className="gm-pick__head">
        <span className="gm-pick__word">{side.side === "YES" ? t.yes : t.no}</span>
        <Figure className="gm-pick__chance" text={side.chance} />
      </span>
      <span className="gm-pick__pays">{side.pays ?? t.settledAlready}</span>
    </>
  );
}

/**
 * A question's wording with each range ("65-89", "$5,000-$10,000") kept on
 * one line: a phone would otherwise break it at the hyphen.
 */
export function Wording({ text }: { text: string }) {
  const parts = text.split(/(\S*\d-\S*\d\S*)/);
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <span key={index} className="gm-nobreak">
            {part}
          </span>
        ) : (
          part
        ),
      )}
    </>
  );
}
