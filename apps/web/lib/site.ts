/**
 * Where this site lives, for everything that has to say so in full: canonical
 * links, the sitemap, structured data, the picture a link preview shows.
 *
 * `NEXT_PUBLIC_SITE_URL` is the address people type. When it is not set, the
 * host's own production address is used if there is one, and localhost
 * otherwise — so a preview build and a laptop each describe themselves
 * correctly without anybody remembering to configure them.
 *
 * It matters that this is right. A canonical link pointing at the wrong host
 * tells a search engine that every page here is a copy of a page somewhere
 * else, and it will believe that.
 */
function resolve(): string {
  const configured = process.env.NEXT_PUBLIC_SITE_URL?.trim();
  if (configured) return configured;

  const production = process.env.VERCEL_PROJECT_PRODUCTION_URL?.trim();
  if (production) return `https://${production}`;

  return "http://localhost:3000";
}

export const SITE_URL = resolve().replace(/\/+$/, "");

/** A site path as a full address. */
export function absolute(path: string): string {
  return `${SITE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}
