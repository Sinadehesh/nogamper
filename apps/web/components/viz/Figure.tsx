import { cx } from "./style";

/**
 * Figures in the display face: the digits tabular, as the brief asks, and
 * everything between them (".", ",", ":", words) at its own width. Set
 * wholly tabular, Schibsted Grotesk gives a decimal point or a colon a
 * whole digit's width, and "0.5%" reads "0 . 5%".
 *
 * Works for a figure ("62%", "1.61×", "1,000") and for a sentence with
 * figures in it ("All 3 right: 23% chance"). `unit` sets a trailing "%" or
 * "×" smaller, for a figure the size of a headline.
 */
export function Figure({ text, unit = false, className }: { text: string; unit?: boolean; className?: string }) {
  const match = unit ? /^(.*?)([%×])$/.exec(text) : null;
  const body = match ? (match[1] ?? text) : text;
  const tail = match ? match[2] : null;
  return (
    <span className={cx("viz-fig", className)}>
      {body.split(/(\d+)/).map((part, index) =>
        /^\d+$/.test(part) ? (
          <span key={index} className="viz-fig__d">
            {part}
          </span>
        ) : (
          part
        ),
      )}
      {tail ? <span className="viz-fig__unit">{tail}</span> : null}
    </span>
  );
}
