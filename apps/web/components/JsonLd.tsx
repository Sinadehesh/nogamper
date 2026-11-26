/**
 * Structured data for a page, as a script the browser ignores and a search
 * engine reads.
 *
 * `<` is escaped because this is JSON inside HTML: a title containing
 * "</script>" would otherwise end the block early, and the rest of the title
 * would be markup.
 */
export function JsonLd({ data }: { data: object }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, "\\u003c") }}
    />
  );
}
