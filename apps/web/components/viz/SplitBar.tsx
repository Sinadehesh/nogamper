import "./viz.css";

import { viz } from "@/lib/copy";
import { pctPair } from "@/lib/viz";

import { at, cx, vars } from "./style";

type SplitBarProps = {
  /** The Yes probability, 0 to 1. */
  yes: number | string;
  /** Bar height: "sm" 4px for dense rows, "md" 8px, "lg" 12px. */
  size?: "sm" | "md" | "lg";
  /** Print "Yes 62%" and "No 38%" above the bar. Off where the figures are beside it already. */
  labels?: boolean;
  className?: string;
};

/**
 * Yes and No on one bar from 0 to 100: Yes from the left in the accent, No
 * to the right in grey, a 2px gap between them and a tick at the middle.
 *
 * Neither side is drawn as the one to pick. A screen reader is told both
 * figures in words whatever `labels` says.
 */
export function SplitBar({ yes, size = "md", labels = true, className }: SplitBarProps) {
  const value = Math.min(1, Math.max(0, Number(yes)));
  const valid = Number.isFinite(value);
  const pair = pctPair(value);

  return (
    <span className={cx("viz-split", `viz-split--${size}`, className)} style={vars({ "--viz-yes": valid ? at(value) : 50 })}>
      <span className="viz-sr">{viz.split(pair.yes, pair.no)}</span>
      {labels ? (
        <span className="viz-split__labels" aria-hidden="true">
          <span>
            <b>{viz.yes}</b> <span className="viz-num">{pair.yes}</span>
          </span>
          <span>
            <b>{viz.no}</b> <span className="viz-num">{pair.no}</span>
          </span>
        </span>
      ) : null}
      <span className="viz-split__track" aria-hidden="true">
        <span className="viz-split__tick" />
        <span className="viz-split__bar">
          {valid && value > 0 ? <span className="viz-split__yes" /> : null}
          {valid && value < 1 ? <span className="viz-split__no" /> : null}
        </span>
      </span>
    </span>
  );
}
