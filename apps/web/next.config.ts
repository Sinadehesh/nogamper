import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // Next.js sends "X-Powered-By: Next.js" on every response unless this is
  // set — a stack fingerprint with no benefit to a player, and one more
  // fact an outside prober does not need.
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Content-Security-Policy",
            value: "frame-ancestors https://web.telegram.org https://*.telegram.org;",
          },
        ],
      },
    ];
  },
};

export default config;
