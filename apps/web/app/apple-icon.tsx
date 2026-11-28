import { ImageResponse } from "next/og";

import { MARK_COLOURS } from "@/lib/og";

/**
 * The mark as a PNG: for a phone's home screen, and for anything that wants
 * a logo and cannot take an SVG. The same drawing as icon.svg: a row of three
 * dots on soot, the middle one lit. Square, because the phone rounds it.
 */

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: MARK_COLOURS.ground,
        }}
      >
        <svg width="126" height="42" viewBox="0 0 36 12">
          <circle cx="6" cy="6" r="4.5" fill={MARK_COLOURS.dim} />
          <circle cx="18" cy="6" r="4.5" fill={MARK_COLOURS.lit} />
          <circle cx="30" cy="6" r="4.5" fill={MARK_COLOURS.dim} />
        </svg>
      </div>
    ),
    size,
  );
}
