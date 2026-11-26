import type { MetadataRoute } from "next";

import { absolute } from "@/lib/site";

/**
 * What a crawler is asked to leave alone.
 *
 * The private screens and the API, which have nothing to offer a search
 * result. The sign-in and sign-up forms are deliberately *not* listed: they
 * carry a "noindex" of their own, and a crawler has to be allowed to fetch a
 * page to read that.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/api/", "/admin", "/play", "/write"] }],
    sitemap: absolute("/sitemap.xml"),
  };
}
