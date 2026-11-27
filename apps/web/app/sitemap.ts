import type { MetadataRoute } from "next";

import { PRIVACY_UPDATED } from "@/lib/content";
import { allReaderArticles } from "@/lib/server/articles";
import { allEditorial } from "@/lib/server/editorial";
import { keepEarlierCopy } from "@/lib/server/public";
import { allQuestions } from "@/lib/server/questions";
import { absolute } from "@/lib/site";

// Kept for five minutes, then built again behind the next reader.
export const revalidate = 300;

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
  const read = await allQuestions();
  // A map that lists four hundred pages one hour and none the next, because
  // the game's server was asleep when it was drawn, tells a crawler they have
  // gone. On the running site the map stays as it was last drawn instead;
  // only a fresh build, with no earlier map, is drawn without them.
  if (read === null) keepEarlierCopy("The list of questions, for the sitemap,");
  const questions = read ?? [];

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
    { url: absolute("/moves"), changeFrequency: "hourly", priority: 0.8 },
    { url: absolute("/questions"), changeFrequency: "daily", priority: 0.7 },
    { url: absolute("/about"), changeFrequency: "monthly", priority: 0.7 },
    { url: absolute("/support"), changeFrequency: "monthly", priority: 0.4 },
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
    // No date on these: a question's row is touched every time its price is
    // read, and "changed a minute ago" on four hundred pages, every time, is
    // exactly the claim a crawler learns to ignore.
    ...questions.map((question) => ({
      url: absolute(`/questions/${question.slug}`),
      changeFrequency: question.state === "open" ? ("daily" as const) : ("yearly" as const),
      priority: question.state === "open" ? 0.6 : 0.3,
    })),
  ];
}
