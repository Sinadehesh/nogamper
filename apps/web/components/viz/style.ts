import type { CSSProperties } from "react";

/** Class names, the empty ones left out. */
export function cx(...names: (string | false | null | undefined)[]): string {
  return names.filter(Boolean).join(" ");
}

/** Custom properties for a style attribute: `vars({ "--viz-yes": 62 })`. */
export function vars(values: Record<`--${string}`, string | number>): CSSProperties {
  const style: Record<string, string> = {};
  for (const [name, value] of Object.entries(values)) style[name] = String(value);
  return style as CSSProperties;
}

/** A probability as a position on a 0-to-100 track, to two places. */
export function at(probability: number): number {
  return Math.round(Math.min(1, Math.max(0, probability)) * 10_000) / 100;
}
