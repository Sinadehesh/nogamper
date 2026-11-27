import { readFile } from "node:fs/promises";
import { join } from "node:path";

import { ImageResponse } from "next/og";

import { APP_NAME, t } from "@/lib/copy";

/**
 * The picture shown when a page is shared: its title on the site's soot
 * ground, in the site's typeface, with the mark and the name. One drawing
 * for every page, so a link from here is recognisable before it is read.
 *
 * Colours are written out rather than taken from the stylesheet. This is
 * rendered to a PNG on the server by a layout engine that has never heard of
 * a CSS variable. They are the dealt palette's (app/layout.tsx): soot, near
 * white, the grey, and the lime accent.
 *
 * The typeface is Schibsted Grotesk at 400, the site's headline weight, read
 * from lib/fonts beside this file: a static TrueType instance, because the
 * renderer reads neither the woff2 files the pages use nor a variable font.
 * If the file cannot be read, the picture is drawn in the renderer's own
 * face rather than not at all.
 */

export const OG_SIZE = { width: 1200, height: 630 };
export const OG_CONTENT_TYPE = "image/png";

const SOOT = "#0f0f0f";
const INK = "#ffffff";
const MUTED = "#8f8f8f";
const LIME = "#dafa9c";

/** The mark's colours, shared with the phone icon (app/apple-icon.tsx). */
export const MARK_COLOURS = { ground: SOOT, lit: LIME, dim: "#686868" };

const FONT_FILE = join(process.cwd(), "lib/fonts/SchibstedGrotesk-Regular.ttf");
let font: Promise<Buffer | null> | undefined;

function typeface(): Promise<Buffer | null> {
  font ??= readFile(FONT_FILE).catch(() => null);
  return font;
}

/** A row of three dots, the middle one lit: the site's mark. */
function Mark({ width }: { width: number }) {
  return (
    <svg width={width} height={width / 3} viewBox="0 0 36 12">
      <circle cx="6" cy="6" r="4.5" fill={MARK_COLOURS.dim} />
      <circle cx="18" cy="6" r="4.5" fill={MARK_COLOURS.lit} />
      <circle cx="30" cy="6" r="4.5" fill={MARK_COLOURS.dim} />
    </svg>
  );
}

export async function previewImage({ title, kicker }: { title: string; kicker?: string }) {
  // Long headlines step down in size rather than run off the card.
  const fontSize = title.length > 90 ? 56 : title.length > 55 ? 66 : 80;
  const data = await typeface();

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: SOOT,
          color: INK,
          padding: "72px 80px 64px",
          fontFamily: data ? "Schibsted Grotesk" : undefined,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column" }}>
          {kicker ? (
            <div style={{ display: "flex", fontSize: 30, color: LIME, marginBottom: 28 }}>
              {kicker}
            </div>
          ) : null}
          <div
            style={{
              display: "flex",
              fontSize,
              lineHeight: 1.06,
              letterSpacing: -0.035 * fontSize,
              maxWidth: 1000,
            }}
          >
            {title}
          </div>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderTop: "1px solid #2a2a2a",
            paddingTop: 36,
          }}
        >
          <div style={{ display: "flex", alignItems: "center" }}>
            <Mark width={72} />
            <div style={{ display: "flex", fontSize: 40, letterSpacing: -1, marginLeft: 20 }}>
              {APP_NAME}
            </div>
          </div>
          <div style={{ display: "flex", fontSize: 26, color: MUTED }}>{t.tagline}</div>
        </div>
      </div>
    ),
    {
      ...OG_SIZE,
      fonts: data ? [{ name: "Schibsted Grotesk", data, weight: 400, style: "normal" }] : undefined,
    },
  );
}
