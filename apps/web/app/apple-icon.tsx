import { ImageResponse } from "next/og";

/**
 * The mark as a PNG: for a phone's home screen, and for anything that wants
 * a logo and cannot take an SVG. Drawn from the same shape as icon.svg.
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
          background: "#0d6b63",
        }}
      >
        <svg width="132" height="132" viewBox="0 0 32 32">
          <path
            d="M7 21.5 13 14l4.5 4.5L25 9"
            fill="none"
            stroke="#ffffff"
            strokeWidth="2.75"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle cx="25" cy="9" r="2.75" fill="#ffffff" />
        </svg>
      </div>
    ),
    size,
  );
}
