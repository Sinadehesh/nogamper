"use client";

import { useLinkStatus } from "next/link";

/**
 * A word inside a link while the page it leads to is on its way.
 *
 * A question's page is built the first time it is asked for. That is usually
 * quick. When the game's server has been resting it is not: the page waits
 * for it to wake, which takes most of a minute, and a link that has been
 * pressed and shows nothing for a minute looks broken.
 *
 * So the link says it is fetching, and then, if it still is, says why. Both
 * wait before they appear (half a second, and six: `.pending-hint` and
 * `.pending-hint-late` in the style sheet), so a page that arrives promptly
 * never flashes either.
 *
 * It has to be rendered inside the `<Link>` it reports on.
 */
type Props = {
  label: string;
  slowLabel: string;
  /** On a line of its own beneath the link's text, rather than after it. */
  ownLine?: boolean;
};

export function LinkPending({ label, slowLabel, ownLine = false }: Props) {
  const { pending } = useLinkStatus();
  if (!pending) return null;
  return (
    <span
      role="status"
      className={`text-[13px] leading-snug font-normal text-muted ${ownLine ? "mt-1.5 block" : ""}`}
    >
      <span className="pending-hint">{label}</span>{" "}
      <span className="pending-hint pending-hint-late">{slowLabel}</span>
    </span>
  );
}
