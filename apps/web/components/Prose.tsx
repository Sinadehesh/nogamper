import type { ReactElement } from "react";
import Markdown, { type Components, type Options } from "react-markdown";
import remarkGfm from "remark-gfm";

import "@/components/reading/reading.css";
import { articlesPage } from "@/lib/content";

/**
 * An article's Markdown, rendered.
 *
 * Two rules are doing security work here and should not be relaxed casually.
 *
 * **No raw HTML.** The renderer is given Markdown and produces elements from
 * it; HTML written into an article is never parsed as HTML. There is no
 * sanitiser because there is nothing to sanitise.
 *
 * **No images.** An image is a request from the reader's browser to whatever
 * address the author chose — a tracking pixel with a picture attached. Text
 * needs no third party.
 *
 * `fromReader` marks an article written by an account holder rather than by
 * the site. Its links are labelled as user-generated and not followed by
 * search engines, which removes the reason anybody would write an article
 * here in order to place a link.
 *
 * Everything else here is typesetting, done once on the server: each heading
 * gets an address of its own (and a link to it), so the page can list them
 * as contents; each table gets a frame, a caption naming the section it is
 * in, and its columns of figures set right-aligned. Not a word of the
 * article changes.
 */

const DISALLOWED = ["img", "script", "iframe", "style"];

/** A heading as the contents list it: its address and its words. */
export type ProseHeading = { id: string; text: string; depth: 2 | 3 };

// The few hast shapes touched here. (The full types live in a package this
// app does not depend on directly.)
type HastNode = {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
};

// Addresses the page itself uses; a heading that would take one gets "-2".
const RESERVED = ["main", "top", "sources", "more", "try", "contents", "contents-label", "readers", "method"];

function textOf(node: HastNode | undefined): string {
  if (!node) return "";
  if (node.type === "text") return node.value ?? "";
  return (node.children ?? []).map(textOf).join("");
}

function slug(text: string): string {
  const base = text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/['’‘"“”]/g, "")
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64)
    .replace(/-+$/, "");
  return base || "section";
}

function element(tagName: string, properties: Record<string, unknown>, children: HastNode[]): HastNode {
  return { type: "element", tagName, properties, children };
}

/** "−110", "+150", "1.91", "52.4%", "2,250", "6/4": a cell that is a figure. */
const FIGURE = /^[−\-+]?[£$€]?\d[\d,.]*(?:\/\d+)?\s?[%×]?$/;

function cellsOf(row: HastNode): HastNode[] {
  return (row.children ?? []).filter(
    (child) => child.type === "element" && (child.tagName === "td" || child.tagName === "th"),
  );
}

function rowsOf(section: HastNode | undefined): HastNode[] {
  return (section?.children ?? []).filter((child) => child.type === "element" && child.tagName === "tr");
}

function addClass(node: HastNode, name: string) {
  const properties = node.properties ?? {};
  const current = properties.className;
  const list = Array.isArray(current) ? current : typeof current === "string" ? [current] : [];
  node.properties = { ...properties, className: [...list, name] };
}

/** Digits in tabular figures, the points and commas between them at their own width. */
function splitDigits(node: HastNode): HastNode[] {
  if (node.type === "text") {
    return (node.value ?? "")
      .split(/(\d+)/)
      .filter(Boolean)
      .map((part) =>
        /^\d+$/.test(part)
          ? element("span", { className: ["rd-d"] }, [{ type: "text", value: part }])
          : { type: "text", value: part },
      );
  }
  if (node.children) node.children = node.children.flatMap(splitDigits);
  return [node];
}

/** A row of totals: every filled cell is bold and nothing else. */
function isTotal(row: HastNode): boolean {
  const filled = cellsOf(row).filter((cell) => textOf(cell).trim() !== "");
  return (
    filled.length > 0 &&
    filled.every((cell) => {
      const parts = (cell.children ?? []).filter((child) => !(child.type === "text" && !child.value?.trim()));
      return parts.length === 1 && parts[0]?.type === "element" && parts[0]?.tagName === "strong";
    })
  );
}

/** Sets a table's figures; true when every column is figures. */
function setTable(table: HastNode): boolean {
  const sections = (table.children ?? []).filter((child) => child.type === "element");
  const head = sections.find((section) => section.tagName === "thead");
  const body = sections.find((section) => section.tagName === "tbody");
  const headRows = rowsOf(head);
  const bodyRows = rowsOf(body);
  const columns = Math.max(0, ...[...headRows, ...bodyRows].map((row) => cellsOf(row).length));

  let figureColumns = 0;
  for (let column = 0; column < columns; column += 1) {
    const values = bodyRows
      .map((row) => textOf(cellsOf(row)[column]).trim())
      .filter((value) => value !== "");
    const figures = values.filter((value) => FIGURE.test(value)).length;
    if (figures < 2 || figures < values.length * 0.75) continue;
    figureColumns += 1;
    for (const row of [...headRows, ...bodyRows]) {
      const cell = cellsOf(row)[column];
      if (!cell) continue;
      addClass(cell, "rd-num");
      if (cell.tagName === "td") splitDigits(cell);
    }
  }
  for (const row of bodyRows) if (isTotal(row)) addClass(row, "rd-total");
  return columns > 0 && figureColumns === columns;
}

type ReadingOptions = {
  collect?: (heading: ProseHeading) => void;
  tableLabel: (n: number) => string;
  anchorFor: (heading: string) => string;
};

/**
 * Headings and tables, in the order they come. A Markdown h1 becomes an h2
 * (the page already has its h1), and h4 to h6 become h3.
 */
function rehypeReading(options: ReadingOptions) {
  return (tree: HastNode) => {
    const used = new Set(RESERVED);
    let section = "";
    let tables = 0;

    const visit = (parent: HastNode) => {
      const children = parent.children ?? [];
      for (let index = 0; index < children.length; index += 1) {
        const node = children[index];
        if (!node || node.type !== "element") continue;
        const tag = node.tagName ?? "";

        if (/^h[1-6]$/.test(tag)) {
          const depth: 2 | 3 = tag === "h1" || tag === "h2" ? 2 : 3;
          const text = textOf(node).replace(/\s+/g, " ").trim();
          const base = slug(text);
          let id = base;
          for (let n = 2; used.has(id); n += 1) id = `${base}-${n}`;
          used.add(id);
          node.tagName = `h${depth}`;
          node.properties = { ...node.properties, id };
          section = text;
          options.collect?.({ id, text, depth });
          // The heading and a link to it, side by side: the link stays out
          // of the heading, whose words remain its whole name.
          children[index] = element("div", { className: ["rd-h"], dataLevel: depth }, [
            node,
            element(
              "a",
              { className: ["rd-anchor"], href: `#${id}`, ariaLabel: options.anchorFor(text) },
              [{ type: "text", value: "#" }],
            ),
          ]);
          continue;
        }

        if (tag === "table") {
          tables += 1;
          const captionId = `table-${tables}`;
          used.add(captionId);
          const figuresOnly = setTable(node);
          node.properties = { ...node.properties, ariaLabelledBy: captionId };
          const frame = figuresOnly ? ["rd-table", "rd-table--figures"] : ["rd-table"];
          children[index] = element("figure", { className: frame }, [
            element("figcaption", { className: ["rd-table__cap"], id: captionId }, [
              element("span", { className: ["rd-table__n"] }, [
                { type: "text", value: options.tableLabel(tables) },
              ]),
              ...(section ? [element("span", {}, [{ type: "text", value: section }])] : []),
            ]),
            // Focusable so a keyboard can scroll a table wider than the
            // screen; named by the caption.
            element(
              "div",
              {
                className: ["rd-table__scroll"],
                role: "region",
                tabIndex: 0,
                ariaLabelledBy: captionId,
              },
              [node],
            ),
          ]);
          continue;
        }

        visit(node);
      }
    };

    visit(tree);
  };
}

function isInternal(href: string | undefined): boolean {
  return Boolean(href) && (href!.startsWith("/") || href!.startsWith("#"));
}

function components(fromReader: boolean): Components {
  return {
    a: ({ href, children, className, ...rest }) =>
      className === "rd-anchor" || isInternal(href) ? (
        <a href={href} className={className} aria-label={rest["aria-label"]}>
          {children}
        </a>
      ) : (
        <a href={href} rel={fromReader ? "nofollow ugc noopener noreferrer" : "noopener noreferrer"}>
          {children}
        </a>
      ),
  };
}

function options(fromReader: boolean, collect?: (heading: ProseHeading) => void): Options {
  return {
    remarkPlugins: [remarkGfm],
    rehypePlugins: [
      [
        rehypeReading,
        {
          collect,
          tableLabel: articlesPage.tableLabel,
          anchorFor: articlesPage.anchorLabel,
        } satisfies ReadingOptions,
      ],
    ],
    disallowedElements: DISALLOWED,
    skipHtml: true,
    components: components(fromReader),
  };
}

/**
 * The article and the headings in it, from one pass, so that the contents
 * and the headings' addresses cannot disagree.
 */
export function renderProse(
  markdown: string,
  fromReader = false,
): { body: ReactElement; headings: ProseHeading[] } {
  const headings: ProseHeading[] = [];
  // Markdown is a plain synchronous function (no hooks), so calling it here
  // runs the plugins now and fills `headings` before the page is laid out.
  const rendered = Markdown({ children: markdown, ...options(fromReader, (heading) => headings.push(heading)) });
  return { body: <div className="rd-prose">{rendered}</div>, headings };
}

export function Prose({ markdown, fromReader = false }: { markdown: string; fromReader?: boolean }) {
  return (
    <div className="rd-prose">
      <Markdown {...options(fromReader)}>{markdown}</Markdown>
    </div>
  );
}
