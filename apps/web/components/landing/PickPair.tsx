import { Figure } from "@/components/viz/Figure";
import { t } from "@/lib/copy";

import type { sides } from "./figures";

/**
 * The two picks of one question, as the game draws them: one shape and one
 * weight for both, each with its word, its chance and what it pays. Only the
 * chosen side fills (Yes lime, No white, both with dark text), so neither
 * reads as the recommended one before anybody chooses (decision 6).
 *
 * A drawn part: it sits inside a picture of the game (aria-hidden there), so
 * these are spans, not buttons.
 */
export function PickPair({
  choices,
  chosen,
  className,
}: {
  choices: ReturnType<typeof sides>;
  chosen?: "YES" | "NO";
  className?: string;
}) {
  return (
    <span className={className ? `lp-picks ${className}` : "lp-picks"}>
      {choices.map((choice) => (
        <span
          key={choice.side}
          className="lp-pick"
          data-side={choice.side === "YES" ? "yes" : "no"}
          data-chosen={choice.side === chosen ? "" : undefined}
        >
          <span className="lp-pick__head">
            <span className="lp-pick__word">{choice.side === "YES" ? t.yes : t.no}</span>
            <Figure className="lp-pick__chance" text={choice.chance} />
          </span>
          <span className="lp-pick__pays">{choice.pays ? t.pays(choice.pays) : t.settledAlready}</span>
        </span>
      ))}
    </span>
  );
}
