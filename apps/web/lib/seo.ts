import type { Metadata } from "next";

import { landing } from "@/lib/content";
import { APP_NAME, t } from "@/lib/copy";
import { SITE_URL, absolute } from "@/lib/site";

/**
 * How each page describes itself to a search engine and to a link preview.
 *
 * One function, because the description of a page has several copies — the
 * title, the canonical link, the Open Graph card — and the way they go wrong
 * is by drifting apart: a page whose preview shows last month's headline, or
 * whose canonical link still points at the page it was copied from.
 */

type PageMeta = {
  /** The page's own title. The site name is appended by the layout. */
  title: string;
  description: string;
  /** The page's path, e.g. "/mission". Becomes the canonical address. */
  path: string;
  /** Use the title exactly as given, with no site name appended. */
  absoluteTitle?: boolean;
  /** False for pages that are nobody's search result: forms, private screens. */
  index?: boolean;
  /** True when an opengraph-image file sits beside the page. The site's
      default picture is then left out, so that the page's own is used: stated
      here, the default would win. */
  ownImage?: boolean;
  article?: { published: string; modified?: string; author: string };
};

// The site's own picture, for any page that has not drawn one of its own.
//
// Stated on every page rather than inherited from the layout, because it is
// not inherited: a page that sets its own Open Graph card replaces the
// layout's card whole, picture included, and its links would then be shared
// with no image at all. A page that *does* have its own drawing — an
// opengraph-image file beside it — overrides this.
const DEFAULT_IMAGE = { url: "/opengraph-image", width: 1200, height: 630, alt: landing.headline };

export function pageMetadata(meta: PageMeta): Metadata {
  const { title, description, path, absoluteTitle = false, index = true, article } = meta;
  // Spread in rather than assigned: a key that is present but undefined is
  // still a key, and counts as the page having said "no picture".
  const picture = meta.ownImage ? {} : { images: [DEFAULT_IMAGE] };

  return {
    title: absoluteTitle ? { absolute: title } : title,
    description,
    alternates: { canonical: path },
    robots: index ? { index: true, follow: true } : { index: false, follow: false },
    openGraph: {
      type: article ? "article" : "website",
      title,
      description,
      url: path,
      siteName: APP_NAME,
      locale: "en_US",
      ...picture,
      ...(article
        ? {
            publishedTime: article.published,
            modifiedTime: article.modified ?? article.published,
            authors: [article.author],
          }
        : {}),
    },
    twitter: { card: "summary_large_image", title, description, ...picture },
  };
}

// ----- structured data --------------------------------------------------------
//
// Plain statements of fact about the page, in the vocabulary search engines
// read. Nothing here claims more than the page shows: no ratings, no review
// counts, no FAQ markup on pages that are not lists of questions.

const PUBLISHER = {
  "@type": "Organization",
  name: APP_NAME,
  url: SITE_URL,
  logo: { "@type": "ImageObject", url: absolute("/apple-icon") },
};

export function organizationLd() {
  return { "@context": "https://schema.org", ...PUBLISHER, description: t.description };
}

export function websiteLd() {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: APP_NAME,
    url: SITE_URL,
    description: t.description,
    inLanguage: "en",
    publisher: PUBLISHER,
  };
}

export function breadcrumbLd(trail: { name: string; path: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: trail.map((step, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: step.name,
      item: absolute(step.path),
    })),
  };
}

export function listLd(name: string, paths: string[]) {
  return {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name,
    itemListElement: paths.map((path, index) => ({
      "@type": "ListItem",
      position: index + 1,
      url: absolute(path),
    })),
  };
}

export function articleLd(article: {
  path: string;
  title: string;
  description: string;
  published: string;
  modified: string;
  /** A reader's name for a reader's article; omitted for the site's own. */
  author?: string;
  words: number;
}) {
  return {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: article.title,
    description: article.description,
    datePublished: article.published,
    dateModified: article.modified,
    wordCount: article.words,
    inLanguage: "en",
    mainEntityOfPage: { "@type": "WebPage", "@id": absolute(article.path) },
    image: [absolute(`${article.path}/opengraph-image`)],
    author: article.author
      ? { "@type": "Person", name: article.author }
      : { "@type": "Organization", name: APP_NAME, url: SITE_URL },
    publisher: PUBLISHER,
  };
}
