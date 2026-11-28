"use client";

import { useEffect, useState } from "react";

export type ContentsEntry = { id: string; text: string };

const number = (index: number) => String(index + 1).padStart(2, "0");

/** "1. Tell one person": a heading that carries its own number. */
const OWN_NUMBER = /^(\d{1,2}[.)])\s+/;

/**
 * Each entry's number and words. When the headings carry their own numbers
 * the list shows those, once, and none for a section without one (a guide's
 * "Sources" is not step 11); otherwise it numbers every entry itself.
 */
function Entry({ entry, index, own }: { entry: ContentsEntry; index: number; own: boolean }) {
  if (!own) {
    return (
      <>
        <span className="rd-toc__n" aria-hidden="true">
          {number(index)}
        </span>
        <span>{entry.text}</span>
      </>
    );
  }
  const match = OWN_NUMBER.exec(entry.text);
  return (
    <>
      <span className="rd-toc__n">{match ? match[1] : null}</span>{" "}
      <span>{match ? entry.text.slice(match[0].length) : entry.text}</span>
    </>
  );
}

const hasOwnNumbers = (entries: ContentsEntry[]) => entries.some((entry) => OWN_NUMBER.test(entry.text));

/**
 * A page's contents beside its text, from 1024px. It marks the section being
 * read: the last heading that has passed a line a third of the way down the
 * window. Nothing scrolls by itself; a link is an ordinary jump.
 */
export function Contents({ entries, label }: { entries: ContentsEntry[]; label: string }) {
  const [current, setCurrent] = useState<string | null>(null);

  useEffect(() => {
    const targets = entries
      .map((entry) => document.getElementById(entry.id))
      .filter((target): target is HTMLElement => target !== null);
    if (targets.length === 0) return;

    let frame = 0;
    const update = () => {
      frame = 0;
      const line = window.innerHeight / 3;
      let active: string | null = null;
      for (const target of targets) {
        if (target.getBoundingClientRect().top > line) break;
        active = target.id;
      }
      setCurrent(active);
    };
    const schedule = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };

    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [entries]);

  const own = hasOwnNumbers(entries);
  return (
    <nav className="rd-toc" aria-labelledby="contents-label">
      <p id="contents-label" className="rd-toc__label">
        {label}
      </p>
      <ol className="rd-toc__list" role="list">
        {entries.map((entry, index) => (
          <li key={entry.id}>
            <a href={`#${entry.id}`} aria-current={current === entry.id ? "location" : undefined}>
              <Entry entry={entry} index={index} own={own} />
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}

/** The same contents on a phone and a tablet: one line that opens. */
export function ContentsDisclosure({
  entries,
  label,
  count,
}: {
  entries: ContentsEntry[];
  label: string;
  count: string;
}) {
  const own = hasOwnNumbers(entries);
  return (
    <details className="rd-toc-m">
      <summary>
        <span>{label}</span>
        <span className="rd-toc-m__count">{count}</span>
      </summary>
      <nav aria-labelledby="contents-label-m">
        <p id="contents-label-m" className="sr-only">
          {label}
        </p>
        <ol className="rd-toc__list" role="list">
          {entries.map((entry, index) => (
            <li key={entry.id}>
              <a href={`#${entry.id}`}>
                <Entry entry={entry} index={index} own={own} />
              </a>
            </li>
          ))}
        </ol>
      </nav>
    </details>
  );
}
