import { ImageResponse } from "next/og";

import { APP_NAME, t } from "@/lib/copy";

/**
 * The picture shown when a page is shared: its title on the site's paper,
 * with the name and the mark. One drawing for every page, so a link from
 * here is recognisable before it is read.
 *
 * Colours are written out rather than taken from the stylesheet. This is
 * rendered to a PNG on the server by a layout engine that has never heard of
 * a CSS variable.
 */

export const OG_SIZE = { width: 1200, height: 630 };
export const OG_CONTENT_TYPE = "image/png";

const PAPER = "#f6f5f1";
const INK = "#18212b";
const MUTED = "#566170";
const ACCENT = "#0d6b63";

export function previewImage({ title, kicker }: { title: string; kicker?: string }) {
  // Long headlines step down in size rather than run off the card.
  const fontSize = title.length > 90 ? 52 : title.length > 55 ? 62 : 76;

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: PAPER,
          color: INK,
          padding: "68px 76px",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column" }}>
          {kicker ? (
            <div
              style={{
                display: "flex",
                fontSize: 28,
                color: ACCENT,
                letterSpacing: 2,
                textTransform: "uppercase",
                marginBottom: 22,
              }}
            >
              {kicker}
            </div>
          ) : null}
          <div style={{ display: "flex", fontSize, lineHeight: 1.08, letterSpacing: -1.5 }}>
            {title}
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center" }}>
            <div
              style={{
                width: 60,
                height: 60,
                borderRadius: 14,
                background: ACCENT,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                marginRight: 18,
              }}
            >
              <svg width="44" height="44" viewBox="0 0 32 32">
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
            <div style={{ display: "flex", fontSize: 38 }}>{APP_NAME}</div>
          </div>
          <div style={{ display: "flex", fontSize: 26, color: MUTED }}>{t.tagline}</div>
        </div>
      </div>
    ),
    OG_SIZE,
  );
}
