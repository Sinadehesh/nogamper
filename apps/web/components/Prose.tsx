import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

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
 */

const DISALLOWED = ["img", "script", "iframe", "style"];

function isInternal(href: string | undefined): boolean {
  return Boolean(href) && (href!.startsWith("/") || href!.startsWith("#"));
}

function components(fromReader: boolean): Components {
  return {
    // The page already has its <h1>; an article's own top heading is a
    // section of that page.
    h1: ({ children }) => <h2>{children}</h2>,
    h4: ({ children }) => <h3>{children}</h3>,
    h5: ({ children }) => <h3>{children}</h3>,
    h6: ({ children }) => <h3>{children}</h3>,
    a: ({ href, children }) =>
      isInternal(href) ? (
        <a href={href}>{children}</a>
      ) : (
        <a href={href} rel={fromReader ? "nofollow ugc noopener noreferrer" : "noopener noreferrer"}>
          {children}
        </a>
      ),
    table: ({ children }) => (
      <div className="prose-table">
        <table>{children}</table>
      </div>
    ),
  };
}

export function Prose({ markdown, fromReader = false }: { markdown: string; fromReader?: boolean }) {
  return (
    <div className="prose">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        disallowedElements={DISALLOWED}
        skipHtml
        components={components(fromReader)}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
