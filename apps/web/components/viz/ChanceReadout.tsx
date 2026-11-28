import "./viz.css";

import { viz } from "@/lib/copy";
import { type PriceBand, pctPair } from "@/lib/viz";

import { Figure } from "./Figure";
import { cx } from "./style";

type ChanceReadoutProps = {
  /** The Yes probability, 0 to 1: a number or the API's string ("0.6200"). */
  yes: number | string;
  /** "header" for a page's lead figure, "card" for a card, "inline" in a sentence. */
  size?: "header" | "card" | "inline";
  /** Show No's figure as well, taken from Yes so the two add up to 100. */
  showNo?: boolean;
  /**
   * "live" for an open question; "last" for a closed or finished one, whose
   * figure is its last price (take it from `priceToShow`, never `probability`).
   */
  kind?: "live" | "last";
  /**
   * The game's band, when `yes` is a price held on it (`priceToShow` says
   * `held`): on its edge both figures print as bounds, "≤1%" and "≥99%".
   */
  held?: PriceBand;
  className?: string;
};

/**
 * The chance, with what it is beside it: "62% chance of yes".
 *
 * The figure is ink, not the accent: text never wears a data colour. The
 * short accent line beside the words ties it to the chart's line and the
 * split bar's Yes, and No gets the grey of its part of that bar.
 */
export function ChanceReadout({
  yes,
  size = "card",
  showNo = false,
  kind = "live",
  held,
  className,
}: ChanceReadoutProps) {
  const pair = pctPair(yes, held);
  const value = Number(yes);
  const keyed = size !== "inline";

  return (
    <span className={cx("viz-readout", `viz-readout--${size}`, className)}>
      <span className="viz-readout__side viz-readout__yes">
        <data className="viz-readout__figure" value={Number.isFinite(value) ? String(value) : ""}>
          <Figure text={pair.yes} unit={size !== "inline"} />
        </data>{" "}
        <span className="viz-readout__words">
          {keyed ? <span className="viz-key" aria-hidden="true" /> : null}
          {kind === "last" ? viz.lastChanceOfYes : viz.chanceOfYes}
        </span>
      </span>
      {showNo ? (
        <span className="viz-readout__side viz-readout__no">
          <data
            className="viz-readout__figure"
            value={Number.isFinite(value) ? String(Math.round((1 - value) * 10_000) / 10_000) : ""}
          >
            <Figure text={pair.no} unit={size !== "inline"} />
          </data>{" "}
          <span className="viz-readout__words">
            {keyed ? <span className="viz-key viz-key--no" aria-hidden="true" /> : null}
            {viz.chanceOfNo}
          </span>
        </span>
      ) : null}
    </span>
  );
}
