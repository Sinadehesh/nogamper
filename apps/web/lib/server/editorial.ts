import "server-only";

import fs from "node:fs";
import path from "node:path";

import matter from "gray-matter";

/**
 * The site's own articles: Markdown files in content/articles, one per piece.
 *
 * Files rather than database rows, on purpose. A guide to quitting gambling
 * should be reviewed like code — a change to it is a diff somebody can read —
 * and it should still be served when the database is having a bad day. Each
 * file states its own title, description, dates and sources at the top, and
 * a file missing any of them fails the build rather than publishing half a
 * page.
 *
 * Readers' articles are a different thing and live in the API; see
 * lib/server/articles.ts.
 */

export const TOPICS = ["prediction-markets", "odds", "stepping-back"] as const;
export type Topic = (typeof TOPICS)[number];

export type EditorialSource = { label: string; href: string };

export type Editorial = {
  slug: string;
  title: string;
  description: string;
  topic: Topic;
  /** ISO dates, e.g. "2026-11-26". */
  published: string;
  updated: string;
  sources: EditorialSource[];
  body: string;
  words: number;
  readingMinutes: number;
};

const DIRECTORY = path.join(process.cwd(), "content", "articles");
const WORDS_PER_MINUTE = 220;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/;

function fail(file: string, problem: string): never {
  throw new Error(`content/articles/${file}: ${problem}`);
}

function text(file: string, data: Record<string, unknown>, key: string): string {
  const value = data[key];
  if (typeof value !== "string" || !value.trim()) fail(file, `"${key}" is missing`);
  return value.trim();
}

function isoDate(file: string, data: Record<string, unknown>, key: string): string {
  // YAML reads a bare 2026-11-26 as a date; accept that and the quoted form.
  const raw = data[key];
  const value = raw instanceof Date ? raw.toISOString().slice(0, 10) : String(raw ?? "").trim();
  if (!ISO_DATE.test(value)) fail(file, `"${key}" must be a date like 2026-11-26`);
  return value;
}

function parse(file: string): Editorial {
  const slug = file.replace(/\.md$/, "");
  if (!SLUG.test(slug)) fail(file, "the file name must be lower-case words joined by hyphens");

  const { data, content } = matter(fs.readFileSync(path.join(DIRECTORY, file), "utf8"));

  const topic = text(file, data, "topic") as Topic;
  if (!TOPICS.includes(topic)) fail(file, `"topic" must be one of ${TOPICS.join(", ")}`);

  const description = text(file, data, "description");
  // What a search result shows. Longer is cut off mid-sentence; much shorter
  // wastes the one line there is to say what the page is.
  if (description.length < 70 || description.length > 170) {
    fail(file, `"description" should be 70–170 characters (it is ${description.length})`);
  }

  const sources = Array.isArray(data.sources) ? data.sources : [];
  if (sources.length === 0) fail(file, "at least one source is required");
  for (const source of sources) {
    if (typeof source?.label !== "string" || !/^https:\/\//.test(String(source?.href))) {
      fail(file, "each source needs a label and an https:// href");
    }
  }

  const body = content.trim();
  const words = body.split(/\s+/).length;
  if (words < 300) fail(file, `the article is only ${words} words`);

  const published = isoDate(file, data, "published");
  const updated = data.updated === undefined ? published : isoDate(file, data, "updated");
  if (updated < published) fail(file, '"updated" is earlier than "published"');

  return {
    slug,
    title: text(file, data, "title"),
    description,
    topic,
    published,
    updated,
    sources: sources as EditorialSource[],
    body,
    words,
    readingMinutes: Math.max(1, Math.round(words / WORDS_PER_MINUTE)),
  };
}

let cache: Editorial[] | null = null;

/** Every article, newest first. */
export function allEditorial(): Editorial[] {
  if (cache) return cache;
  const files = fs.existsSync(DIRECTORY)
    ? fs.readdirSync(DIRECTORY).filter((name) => name.endsWith(".md"))
    : [];
  const articles = files
    .map(parse)
    .sort((a, b) => b.published.localeCompare(a.published) || a.title.localeCompare(b.title));

  // An article that links to another one which is not there is a dead link
  // on the day it is published. Caught here, it is a failed build instead.
  const slugs = new Set(articles.map((article) => article.slug));
  for (const article of articles) {
    for (const match of article.body.matchAll(/\]\(\/articles\/([^)#\s]+)/g)) {
      if (!slugs.has(match[1]!)) {
        fail(`${article.slug}.md`, `links to /articles/${match[1]}, which does not exist`);
      }
    }
  }

  cache = articles;
  return cache;
}

export function getEditorial(slug: string): Editorial | null {
  return allEditorial().find((article) => article.slug === slug) ?? null;
}
