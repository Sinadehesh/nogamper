import type { NextConfig } from "next";

// Other names this deployment still answers to — an earlier name for the
// site, the address the host gave the project on its first day. Each is the
// whole site again at a second address, which is a duplicate to a search
// engine and a stale link to a person. They are sent on, permanently, to the
// one real address. Nothing is redirected unless both are set, and never the
// real address to itself.
const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? "").trim().replace(/\/+$/, "");
const FORMER_HOSTS = (process.env.FORMER_HOSTS ?? "")
  .split(",")
  .map((host) => host.trim().toLowerCase())
  .filter((host) => host !== "" && SITE_URL !== "" && !SITE_URL.endsWith(`//${host}`));

const config: NextConfig = {
  reactStrictMode: true,
  // Next.js sends "X-Powered-By: Next.js" on every response unless this is
  // set — a stack fingerprint with no benefit to a visitor, and one more
  // fact an outside prober does not need.
  poweredByHeader: false,
  // `next dev` would otherwise write AGENTS.md and CLAUDE.md into this folder
  // whenever it sees an AI coding assistant running. The repository's own
  // instructions for assistants are kept deliberately, so nothing is added
  // behind the owner's back.
  agentRules: false,
  // The development build's floating badge sits over the page's own corner,
  // in the way of the layout being checked.
  devIndicators: false,
  // The development server refuses its own live-reload connection from any
  // address but localhost, so a page opened at 127.0.0.1 never comes alive.
  // Development only: production builds ignore this.
  allowedDevOrigins: ["127.0.0.1"],
  env: {
    // Whether this build knows where the game's API is. A production build
    // with no API_BASE_URL has nothing behind its "Start playing" button, so
    // the site says the game is not open yet instead of offering buttons that
    // can only fail. Development always counts as open: there the default
    // address, this machine, is the right one.
    NEXT_PUBLIC_GAME_OPEN:
      process.env.API_BASE_URL?.trim() || process.env.NODE_ENV !== "production" ? "1" : "",
  },
  // The site's own articles are Markdown files read from disk. Pages built
  // ahead of time read them during the build; pages rendered on demand — a
  // reader's article, the listing when it refreshes — read them on the
  // server, which only has the files it was told it needs.
  outputFileTracingIncludes: {
    "/": ["./content/articles/*.md"],
    "/articles": ["./content/articles/*.md"],
    "/articles/[slug]": ["./content/articles/*.md"],
    "/articles/[slug]/opengraph-image": ["./content/articles/*.md"],
    "/sitemap.xml": ["./content/articles/*.md"],
  },
  async redirects() {
    return FORMER_HOSTS.map((host) => ({
      source: "/:path*",
      has: [{ type: "host" as const, value: host }],
      destination: `${SITE_URL}/:path*`,
      permanent: true,
    }));
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // This site is never meant to be framed: a page that can be
          // framed is a page whose "confirm" button can be placed under
          // somebody else's picture of a cat. Both headers, because
          // frame-ancestors is the standard and X-Frame-Options is what
          // older browsers understand.
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
          { key: "X-Frame-Options", value: "DENY" },
          // Nothing here uses a camera, a microphone, a location or a
          // payment sheet. Saying so means a script that somehow got onto
          // the page cannot ask for them either.
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=()",
          },
        ],
      },
      // The self-hosted fonts are fetched before the first line of text on
      // every page, so a returning visitor's browser keeps them for a year
      // and never asks again. That is only right while a file's name
      // changes with its contents: a changed font must get a new file name
      // (and the new name in app/globals.css and the preloads in
      // app/layout.tsx), or visitors keep the old one.
      {
        source: "/fonts/:path*",
        headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
      },
      // The design kit's stylesheets and scripts keep their names when a
      // newer copy of the kit replaces them, so they are kept for a day and
      // then checked again, the old copy serving meanwhile for up to a week.
      {
        source: "/assets/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=86400, stale-while-revalidate=604800",
          },
        ],
      },
    ];
  },
};

export default config;
