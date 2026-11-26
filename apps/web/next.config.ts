import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // Next.js sends "X-Powered-By: Next.js" on every response unless this is
  // set — a stack fingerprint with no benefit to a visitor, and one more
  // fact an outside prober does not need.
  poweredByHeader: false,
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
    ];
  },
};

export default config;
