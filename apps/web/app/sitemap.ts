import type { MetadataRoute } from "next";

import { PRIVACY_UPDATED } from "@/lib/content";
import { allReaderArticles } from "@/lib/server/articles";
import { allEditorial } from "@/lib/server/editorial";
import { keepEarlierCopy } from "@/lib/server/public";
import { allQuestions } from "@/lib/server/questions";
import { absolute } from "@/lib/site";

// Drawn when it is asked for, from answers that are themselves kept for five
// minutes (lib/server/questions.ts, lib/server/articles.ts).
//
// Not built once and refreshed behind the reader, as the pages are. Built that
// way it was listed as "refreshed every five minutes" and then served by the
// host as a plain file, unchanged long after: a release that went out while
// the game's server had nothing to list published a map with no questions in
// it, and kept publishing it. Drawn on request there is no file to go stale.
export const dynamic = "force-dynamic";

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
  // gone. The list is kept and goes on being used while the server cannot be
  // asked, so that is rare. When there is no list at all, the running site
  // answers with an error — which a crawler takes as "come back later" —
  // rather than with a map that leaves them out.
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
