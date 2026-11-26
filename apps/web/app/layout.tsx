import type { Metadata, Viewport } from "next";
import { Vazirmatn } from "next/font/google";

import { fa } from "@/lib/i18n";
import "./globals.css";

const vazirmatn = Vazirmatn({
  subsets: ["arabic", "latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-vazirmatn",
});

export const metadata: Metadata = {
  title: fa.appName,
  description: fa.tagline,
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
};

const CAPTURE_INIT_DATA = `
try {
  var d = new URLSearchParams(location.hash.slice(1)).get('tgWebAppData');
  if (d) sessionStorage.setItem('app:init-data', d);
} catch (e) {}
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fa" dir="rtl" className={vazirmatn.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: CAPTURE_INIT_DATA }} />
      </head>
      <body className="min-h-dvh antialiased">{children}</body>
    </html>
  );
}
