import "./reading.css";

export type SourceLink = { label: string; href: string };

/** "doi.org", "who.int": where a link goes, so a reader can tell before following it. */
function host(href: string): string {
  try {
    return new URL(href).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

/**
 * Sources as a numbered list: the citation as written, a link on it, and the
 * site it leads to underneath. Links open in the same tab, as every other
 * link here does.
 */
export function Sources({
  id,
  title,
  sources,
  headingLevel = 2,
}: {
  id: string;
  title: string;
  sources: SourceLink[];
  headingLevel?: 2 | 3;
}) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <section aria-labelledby={id}>
      <Heading id={id} className="rd-sources-h">
        {title}
      </Heading>
      <ol className="rd-sources" role="list">
        {sources.map((source, index) => (
          <li key={source.href}>
            <span className="rd-sources__n" aria-hidden="true">
              {index + 1}
            </span>
            <span>
              <a href={source.href} rel="noopener noreferrer">
                {source.label}
              </a>
              <span className="rd-sources__host">{host(source.href)}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
