import "server-only";

import { revalidatePath, revalidateTag } from "next/cache";

import { publicApi } from "@/lib/server/public";
import type { PublishedArticle, PublishedArticlePage, PublishedArticleSummary } from "@/lib/types";

/**
 * Readers' articles, as published — read from the API and cached.
 *
 * The cache is cleared the moment anything that could change the public
 * pages goes through this server: a review, a withdrawal, a deletion, a ban.
 * That matters most in one direction. An article that has been taken down
 * must be gone when the operator's screen says it is, not five minutes
 * later. The timed refresh is only the backstop for changes made some other
 * way.
 */

const REVALIDATE_SECONDS = 300;
const TAG = "reader-articles";

export function refreshReaderArticles(): void {
  revalidateTag(TAG, { expire: 0 });
  revalidatePath("/articles");
  revalidatePath("/articles/[slug]", "page");
  revalidatePath("/sitemap.xml");
}
const PAGE = 200;
// A ceiling on how many pages are walked for the sitemap. Far more than
// there will be; it exists so a misbehaving API cannot make this loop.
const MAX_PAGES = 25;

export async function listReaderArticles(limit = 30): Promise<PublishedArticleSummary[]> {
  const page = await publicApi<PublishedArticlePage>(
    `/v1/articles?limit=${limit}`,
    REVALIDATE_SECONDS,
    [TAG],
  );
  return page?.articles ?? [];
}

export async function allReaderArticles(): Promise<PublishedArticleSummary[]> {
  const all: PublishedArticleSummary[] = [];
  for (let index = 0; index < MAX_PAGES; index += 1) {
    const page = await publicApi<PublishedArticlePage>(
      `/v1/articles?limit=${PAGE}&offset=${index * PAGE}`,
      REVALIDATE_SECONDS,
      [TAG],
    );
    if (!page) break;
    all.push(...page.articles);
    if (all.length >= page.total || page.articles.length < PAGE) break;
  }
  return all;
}

export async function getReaderArticle(slug: string): Promise<PublishedArticle | null> {
  // The API matches addresses exactly; anything that could not be one is not
  // worth a request.
  if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug) || slug.length > 96) return null;
  return publicApi<PublishedArticle>(`/v1/articles/${slug}`, REVALIDATE_SECONDS, [TAG]);
}
