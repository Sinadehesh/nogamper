import { Analytics } from "@vercel/analytics/next";
import type { Metadata, Viewport } from "next";

import { landing } from "@/lib/content";
import { t } from "@/lib/copy";
import { SITE_URL } from "@/lib/site";
import "./globals.css";

// Proof of ownership for the search engines' own consoles, which is where
// "is this page indexed, and for what" gets answered. Each is a string the
// console hands out; unset, no tag is written.
const GOOGLE_VERIFICATION = process.env.GOOGLE_SITE_VERIFICATION?.trim();
const BING_VERIFICATION = process.env.BING_SITE_VERIFICATION?.trim();

export const metadata: Metadata = {
  // What every relative address in a page's metadata is resolved against:
  // canonical links, the preview image. Without it they are left relative,
  // and a relative canonical link is one a crawler is free to misread.
  metadataBase: new URL(SITE_URL),
  title: { default: landing.metaTitle, template: `%s · ${t.appName}` },
  description: t.description,
  applicationName: t.appName,
  openGraph: { type: "website", siteName: t.appName, locale: "en_US" },
  twitter: { card: "summary_large_image" },
  verification: {
    google: GOOGLE_VERIFICATION || undefined,
    other: BING_VERIFICATION ? { "msvalidate.01": BING_VERIFICATION } : undefined,
  },
  // What kind of site this is, said the way the design kit's checks read it.
  other: { "page-type": "software", "site-kind": "software" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // No maximumScale and no userScalable=false: pinch-to-zoom is how some
  // people read, and a page that forbids it has decided they should not.
  // One ground, dark, whatever the device prefers.
  themeColor: "#0f0f0f",
  colorScheme: "dark",
};

/**
 * The design kit (public/assets, the design skill's page kit, unmodified),
 * loaded into the cascade layer "kit" so that the site's own classes and
 * every Tailwind utility win over it, while it wins over Tailwind's reset.
 * The layer order is declared first here and again first in globals.css,
 * so whichever the browser meets first sets the same order. The files are
 * the kit's own, in the kit's own order.
 *
 * Then the dealt palette and type, exactly as the kit's dealer printed
 * them, after the kit's files and outside any layer, so they win over the
 * kit's defaults (layout.css resets --ly-scale on :root).
 */
const KIT_FILES = [
  "system.css",
  "ui/cards.css",
  "motion/motion.css",
  "backgrounds/backgrounds.css",
  "layout/layout.css",
  "icons/icon.css",
];

const KIT_STYLE = `@layer theme, base, kit, components, utilities;
${KIT_FILES.map((file) => `@import url("/assets/${file}") layer(kit);`).join("\n")}
:root {
  --p-bg: #0f0f0f; --p-surface: #1a1a1a; --p-ink: #ffffff; --p-muted: #8f8f8f;
  --p-accent: #dafa9c; --p-accent-ink: #0f0f0f; --p-action: #dafa9c; --p-action-ink: #0f0f0f;
  --p-inv-bg: #ffffff; --p-inv-surface: #ececec; --p-inv-ink: #0f0f0f; --p-inv-muted: #5f5f5f;
  --p-inv-accent: #0f0f0f; --p-inv-accent-ink: #ffffff; --p-inv-action: #0f0f0f; --p-inv-action-ink: #ffffff;
  --font-display: "Schibsted Grotesk", system-ui, sans-serif;
  --font-text: "Schibsted Grotesk", system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
  --display-weight: 400;
  --display-tracking: -0.035em;
  --display-tracking-xl: -0.042em;
  --ly-scale: 0.98;
}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // The kit's switches, as the deal set them: the kind of page, round
    // corners and pill buttons, solid buttons, the lit ground behind UI
    // panels, the hover and press layer on, and a dark page (which keeps the
    // dark footer dark; the kit's script would set it, and runs on one page).
    // No m-enter here: the hero's entrance belongs to the one page that
    // loads the kit's motion script, so no other page can hide its words
    // waiting for a script that never comes.
    <html
      lang="en"
      data-type="software"
      data-radius="round"
      data-buttons="solid"
      data-ground="sky"
      data-motion=""
      data-tone="dark"
    >
      <head>
        {/* The two Latin faces every page draws first, fetched alongside the
            stylesheets rather than after them. */}
        <link
          rel="preload"
          href="/fonts/schibsted-grotesk-latin.woff2"
          as="font"
          type="font/woff2"
          crossOrigin="anonymous"
        />
        <link
          rel="preload"
          href="/fonts/jetbrains-mono-latin.woff2"
          as="font"
          type="font/woff2"
          crossOrigin="anonymous"
        />
        <style dangerouslySetInnerHTML={{ __html: KIT_STYLE }} />
      </head>
      <body className="flex min-h-dvh flex-col antialiased">
        {/* The first stop for the Tab key on every page, the game's too. It
            stays out of sight until then, and shows over the logo. */}
        <a className="skip-link" href="#main">
          {t.skipToContent}
        </a>
        {children}
        {/* Page views, counted by the host without cookies and without
            identifying anybody — see /privacy. Only where the host provides
            it: anywhere else the script it loads does not exist. */}
        {process.env.VERCEL ? <Analytics /> : null}
      </body>
    </html>
  );
}
