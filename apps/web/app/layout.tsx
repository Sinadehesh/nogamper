import type { Metadata, Viewport } from "next";

import { t } from "@/lib/copy";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: `${t.appName} — ${t.tagline}`, template: `%s · ${t.appName}` },
  description: t.description,
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
      </body>
    </html>
  );
}
