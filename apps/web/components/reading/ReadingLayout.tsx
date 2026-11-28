import type { ReactNode } from "react";

import "./reading.css";
import { Contents, ContentsDisclosure, type ContentsEntry } from "./Contents";

/**
 * The reading layout: the title over one column near 68 characters, the
 * contents to its left from 1024px (a line that opens, above the text, below
 * that), then whatever ends the page. Contents are shown for three sections
 * or more; a shorter piece is just the column.
 */
export function ReadingLayout({
  head,
  entries,
  label,
  count,
  children,
  end,
}: {
  head: ReactNode;
  entries: ContentsEntry[];
  label: string;
  count: string;
  children: ReactNode;
  end?: ReactNode;
}) {
  const withContents = entries.length >= 3;
  return (
    <article className={withContents ? "rd-layout" : "rd-layout rd-layout--bare"}>
      <header className="rd-layout__head">{head}</header>
      {withContents ? (
        <div className="rd-layout__toc">
          <Contents entries={entries} label={label} />
        </div>
      ) : null}
      <div className="rd-layout__main">
        {withContents ? (
          <div className="mb-8">
            <ContentsDisclosure entries={entries} label={label} count={count} />
          </div>
        ) : null}
        {children}
        {end ? <footer className="rd-end">{end}</footer> : null}
      </div>
    </article>
  );
}
