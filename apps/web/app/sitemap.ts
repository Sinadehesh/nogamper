import type { MetadataRoute } from "next";

import { PRIVACY_UPDATED } from "@/lib/content";
import { allReaderArticles } from "@/lib/server/articles";
import { allEditorial } from "@/lib/server/editorial";
import { absolute } from "@/lib/site";

/**
 * Every page worth a search engine's time, and when each last changed.
 *
 * Dates are real ones — an article's own, never "now". A sitemap that claims
 * everything changed today teaches a crawler to ignore the field, and then
 * it does not come back promptly for the page that actually did.
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const guides = allEditorial();
  const fromReaders = await allReaderArticles();
  const newestGuide = guides[0]?.updated;

  return [
    { url: absolute("/"), changeFrequency: "weekly", priority: 1 },
    { url: absolute("/mission"), changeFrequency: "monthly", priority: 0.9 },
    {
      url: absolute("/articles"),
      lastModified: newestGuide,
      changeFrequency: "weekly",
      priority: 0.9,
    },
    { url: absolute("/help"), changeFrequency: "monthly", priority: 0.9 },
    { url: absolute("/about"), changeFrequency: "monthly", priority: 0.7 },
    { url: absolute("/privacy"), lastModified: PRIVACY_UPDATED, priority: 0.3 },
    ...guides.map((guide) => ({
      url: absolute(`/articles/${guide.slug}`),
      lastModified: guide.updated,
      priority: 0.8,
    })),
    ...fromReaders.map((article) => ({
      url: absolute(`/articles/${article.slug}`),
      lastModified: article.edited_at,
      priority: 0.5,
    })),
  ];
}
