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
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // No maximumScale and no userScalable=false: pinch-to-zoom is how some
  // people read, and a page that forbids it has decided they should not.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f5f1" },
    { media: "(prefers-color-scheme: dark)", color: "#0f141a" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="flex min-h-dvh flex-col antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:start-3 focus:top-3 focus:z-50
                     focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2"
        >
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
