import { articlesPage } from "@/lib/content";
import { t } from "@/lib/copy";
import { OG_CONTENT_TYPE, OG_SIZE, previewImage } from "@/lib/og";
import { getReaderArticle } from "@/lib/server/articles";
import { getEditorial } from "@/lib/server/editorial";

export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;
export const alt = t.navArticles;

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;

  const guide = getEditorial(slug);
  if (guide) {
    return previewImage({ title: guide.title, kicker: articlesPage.topics[guide.topic].title });
  }

  const article = await getReaderArticle(slug);
  return previewImage({
    title: article?.title ?? t.navArticles,
    kicker: article ? t.articleFromReader : undefined,
  });
}
