import "./questions.css";

import Link from "next/link";
import type { ReactNode } from "react";

import { LinkPending, PendingWords } from "@/components/LinkPending";
import { FETCHING, FETCHING_SLOWLY, questionsPage } from "@/lib/content";
import { categoryLabel } from "@/lib/copy";
import type { QuestionIndexItem } from "@/lib/types";

import { type Family, titleFamilies } from "./families";

/** The id of the list the filter works on. */
export const DIRECTORY_ID = "question-list";

/**
 * Open questions by subject: the subjects in the order the raw names sort
 * (the anchors are `open-<raw name>`), each with the number it holds.
 */
export function byCategory(questions: QuestionIndexItem[]): [string, QuestionIndexItem[]][] {
  const groups = new Map<string, QuestionIndexItem[]>();
  for (const question of questions) {
    groups.set(question.category, [...(groups.get(question.category) ?? []), question]);
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

function Heading({ level, className, children }: { level: 3 | 4; className?: string; children: ReactNode }) {
  return level === 3 ? <h3 className={className}>{children}</h3> : <h4 className={className}>{children}</h4>;
}

/** After the slot, with a space unless the shared words start with a mark. */
function tail(after: string): string {
  return /^[?.,:;!]/.test(after) ? after : ` ${after}`;
}

/**
 * One family: its shared words with a blank where its members differ, then
 * each member as a link that shows only its own part. The link's name is
 * what it shows ("$5,000", which is also what a voice command says), and the
 * family's words describe it, so a screen reader hears the whole question.
 * The question's words are not repeated in every link: four hundred of them
 * would be the heaviest thing on the page.
 */
function FamilyBlock({
  family,
  id,
  level,
  withCategory,
}: {
  family: Family<QuestionIndexItem>;
  id: string;
  level: 3 | 4;
  withCategory: boolean;
}) {
  return (
    <div className="qx-family">
      <Heading level={level} className="qx-family__head">
        <span id={id}>
          {family.before}{" "}
          <span className="qx-slot">
            <span className="sr-only">{questionsPage.slot}</span>
          </span>
          {tail(family.after)}
        </span>
        <span className="qx-family__n">{questionsPage.count(family.members.length)}</span>
      </Heading>
      <ul className="qx-members">
        {family.members.map(({ item, slot }, index) => (
          // A position for a key, not the slug: the list never changes order
          // in the browser, and four hundred slugs of up to 137 characters
          // would be sent a second time in the page's data for nothing.
          <li key={index} {...(withCategory ? { "data-c": item.category } : {})}>
            {/* Not fetched ahead of a click: there are hundreds of these, each
                page is built when first asked for, and scrolling past them
                should not build them all. */}
            <Link href={`/questions/${item.slug}`} prefetch={false} className="qx-chip" aria-describedby={id}>
              {slot}
              <LinkPending />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A subject's questions, families first, then the questions that stand alone. */
function Entries({
  items,
  idPrefix,
  level,
  withCategory = false,
}: {
  items: QuestionIndexItem[];
  /** Makes each family heading's id unique on the page. */
  idPrefix: string;
  level: 3 | 4;
  withCategory?: boolean;
}) {
  const entries = titleFamilies(items);
  const families = entries.flatMap((entry) => (entry.kind === "family" ? [entry.family] : []));
  const singles = entries.flatMap((entry) => (entry.kind === "single" ? [entry.item] : []));
  return (
    <>
      {families.map((family, index) => (
        <FamilyBlock
          key={`${family.before}|${family.after}`}
          family={family}
          id={`${idPrefix}-${index}`}
          level={level}
          withCategory={withCategory}
        />
      ))}
      {singles.length > 0 ? (
        <div className="qx-others">
          {families.length > 0 ? <Heading level={level}>{questionsPage.others}</Heading> : null}
          <ul className="qx-singles">
            {singles.map((item, index) => (
              <li key={index} className="qx-single" {...(withCategory ? { "data-c": item.category } : {})}>
                <Link href={`/questions/${item.slug}`} prefetch={false} className="dp-link">
                  {item.question} <LinkPending />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  );
}

/**
 * Every question, as links: open ones by subject, then the most recently
 * finished, by whether they are waiting for a result or resolved. Drawn on
 * the server and complete without a script; the filter above it only hides
 * what does not match.
 */
export function Directory({
  open,
  finished,
  finishedTotal,
}: {
  open: QuestionIndexItem[];
  finished: QuestionIndexItem[];
  finishedTotal: number;
}) {
  // Waiting for a result, then the rest. The index leaves cancelled
  // questions out; should one arrive, it is listed with the resolved, where
  // nothing is claimed about its result.
  const finishedStates = [
    {
      state: "closed" as const,
      items: finished.filter((question) => question.state === "closed"),
    },
    {
      state: "resolved" as const,
      items: finished.filter((question) => question.state !== "closed"),
    },
  ].filter((group) => group.items.length > 0);

  return (
    <PendingWords label={FETCHING} slowLabel={FETCHING_SLOWLY}>
      <div id={DIRECTORY_ID}>
        {byCategory(open).map(([category, items]) => (
          <section
            key={category}
            className="qx-section"
            aria-labelledby={`open-${category}`}
            data-c={category}
            data-s="open"
          >
            <div className="qx-section__head">
              <h2 id={`open-${category}`} className="dp-h2">
                {categoryLabel(category)}
              </h2>
              <p className="qx-section__count">{questionsPage.count(items.length)}</p>
            </div>
            <Entries items={items} idPrefix={`f-${category}`} level={3} />
          </section>
        ))}

        {finished.length > 0 ? (
          <section className="qx-section" aria-labelledby="finished">
            <div className="qx-section__head">
              <h2 id="finished" className="dp-h2">
                {questionsPage.finished}
              </h2>
              <p className="qx-section__count">{questionsPage.count(finished.length)}</p>
            </div>
            <p className="qx-intro dp-sub">
              {questionsPage.finishedIntro}
              {finishedTotal > finished.length
                ? ` ${questionsPage.finishedShown(finished.length, finishedTotal)}`
                : null}
            </p>
            {finishedStates.map(({ state, items }) => (
              <div key={state} className="qx-sub" data-s={state}>
                <h3>{questionsPage.finishedStates[state]}</h3>
                <Entries items={items} idPrefix={`f-${state}`} level={4} withCategory />
              </div>
            ))}
          </section>
        ) : null}
      </div>
    </PendingWords>
  );
}
