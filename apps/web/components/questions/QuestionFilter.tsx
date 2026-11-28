"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";

/**
 * A search and two sets of choices over the list of every question.
 *
 * The list itself is drawn on the server and is complete without this part:
 * every question is a link a person or a search engine can follow. This only
 * hides the rows that do not match, so nothing of the list is sent twice and
 * nothing moves on the page while it wakes up. It reads the rows once, from
 * the page, and after that touches only their `hidden` attribute and the
 * counts.
 *
 * Without a script it is not shown at all (`@media (scripting: none)` in
 * questions.css); the links at the top still lead to each subject.
 */

type Option = { value: string; label: string };

type Words = {
  search: string;
  placeholder: string;
  subject: string;
  state: string;
  all: string;
  showingAll: string;
  showing: string;
  sectionCount: string;
  none: string;
  clear: string;
};

type Props = {
  /** The id of the server-drawn list. */
  listId: string;
  /** How many questions it lists, so the count is there before the page wakes up. */
  total: number;
  words: Words;
  categories: Option[];
  states: Option[];
};

type Row = { el: HTMLElement; text: string; category: string; state: string };

/** The rows of the list (components/questions/Directory.tsx): one link each. */
const ROWS = ":is(.qx-members, .qx-singles) > li";
const SHOWN_ROWS = ":is(.qx-members, .qx-singles) > li:not([hidden])";

/** Lower case, without accents, curly quotes or thousands commas: "Mélenchon" is found as "melenchon", "$100,000" as "100000". */
function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{M}+/gu, "")
    .replace(/[‘’]/g, "'")
    .replace(/(\d),(?=\d)/g, "$1")
    .toLowerCase();
}

/**
 * A row's whole question. A family's link shows only its own part ("$5,000");
 * the rest is the family's heading, with that part where the blank is.
 */
function questionOf(row: HTMLElement): string {
  const link = row.querySelector("a");
  const words = row.closest(".qx-family")?.querySelector<HTMLElement>(".qx-family__head > [id]");
  const blank = words?.querySelector(".qx-slot");
  if (!link || !words || !blank) return row.textContent ?? "";
  let before = "";
  let after = "";
  let past = false;
  for (const node of words.childNodes) {
    if (node === blank) past = true;
    else if (past) after += node.textContent ?? "";
    else before += node.textContent ?? "";
  }
  return `${before}${link.textContent ?? ""}${after}`;
}

function fill(template: string, shown: number, total: number): string {
  return template.replace("{shown}", String(shown)).replace("{total}", String(total));
}

export function QuestionFilter({ listId, total, words, categories, states }: Props) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [state, setState] = useState("");
  const [counts, setCounts] = useState({ shown: total, total });
  const rows = useRef<Row[]>([]);
  const input = useRef<HTMLInputElement>(null);
  const id = useId();

  // The rows, read once. Text typed before the page woke up is kept.
  useEffect(() => {
    const list = document.getElementById(listId);
    if (!list) return;
    rows.current = [...list.querySelectorAll<HTMLElement>(ROWS)].map((el) => ({
      el,
      text: fold(questionOf(el)),
      category: el.closest<HTMLElement>("[data-c]")?.dataset.c ?? "",
      state: el.closest<HTMLElement>("[data-s]")?.dataset.s ?? "",
    }));
    for (const count of list.querySelectorAll<HTMLElement>(".qx-section__count")) {
      count.dataset.all = count.textContent ?? "";
    }
    const typed = input.current?.value ?? "";
    if (typed) setQuery(typed);
    setCounts({ shown: rows.current.length, total: rows.current.length });
  }, [listId]);

  useEffect(() => {
    const list = document.getElementById(listId);
    if (!list || rows.current.length === 0) return;
    const terms = fold(query).split(/\s+/).filter(Boolean);
    let shown = 0;
    for (const row of rows.current) {
      const match =
        (!category || row.category === category) &&
        (!state || row.state === state) &&
        terms.every((term) => row.text.includes(term));
      row.el.hidden = !match;
      if (match) shown += 1;
    }
    // Inside out, so a family is settled before the section around it.
    const groups = [...list.querySelectorAll<HTMLElement>(".qx-family, .qx-others, .qx-sub, .qx-section")];
    for (const group of groups.reverse()) {
      group.hidden = group.querySelector(SHOWN_ROWS) === null;
    }
    for (const section of list.querySelectorAll<HTMLElement>(".qx-section")) {
      const count = section.querySelector<HTMLElement>(".qx-section__count");
      if (!count) continue;
      const all = section.querySelectorAll(ROWS).length;
      const visible = section.querySelectorAll(SHOWN_ROWS).length;
      count.textContent =
        visible === all ? (count.dataset.all ?? "") : fill(words.sectionCount, visible, all);
    }
    setCounts({ shown, total: rows.current.length });
  }, [listId, query, category, state, words.sectionCount]);

  const clear = useCallback(() => {
    if (input.current) input.current.value = "";
    setQuery("");
    setCategory("");
    setState("");
    input.current?.focus();
  }, []);

  const filtered = query !== "" || category !== "" || state !== "";

  return (
    <div className="qx-filter dp-panel" role="search">
      <div className="qx-filter__row">
        <div className="qx-search">
          <label htmlFor={`${id}-q`} className="qx-group__name">
            {words.search}
          </label>
          <input
            ref={input}
            id={`${id}-q`}
            type="search"
            className="field"
            placeholder={words.placeholder}
            autoComplete="off"
            spellCheck={false}
            onInput={(event) => setQuery(event.currentTarget.value)}
          />
        </div>
        <Choices
          name={words.subject}
          all={words.all}
          options={categories}
          value={category}
          onChange={setCategory}
        />
        <Choices name={words.state} all={words.all} options={states} value={state} onChange={setState} />
      </div>
      <div className="qx-status">
        <p role="status" aria-live="polite" aria-atomic="true">
          {counts.shown === 0
            ? words.none
            : counts.shown === counts.total
              ? fill(words.showingAll, counts.shown, counts.total)
              : fill(words.showing, counts.shown, counts.total)}
        </p>
        {filtered ? (
          <button type="button" className="qx-clear" onClick={clear}>
            {words.clear}
          </button>
        ) : null}
      </div>
    </div>
  );
}

/** One set of choices: "All" and each option, one pressed at a time. */
function Choices({
  name,
  all,
  options,
  value,
  onChange,
}: {
  name: string;
  all: string;
  options: Option[];
  value: string;
  onChange: (value: string) => void;
}) {
  const id = useId();
  return (
    <div className="qx-group" role="group" aria-labelledby={id}>
      <span id={id} className="qx-group__name">
        {name}
      </span>
      <div className="qx-group__options">
        {[{ value: "", label: all }, ...options].map((option) => (
          <button
            key={option.value || "all"}
            type="button"
            className="qx-option"
            aria-pressed={value === option.value}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
