"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { Prose } from "@/components/Prose";
import "@/components/reading/reading.css";
import {
  createArticle,
  deleteArticle,
  getMyArticles,
  submitArticle,
  updateArticle,
  withdrawArticle,
  type ApiResult,
} from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { timeAgo } from "@/lib/format";
import type { ArticleDraft, ArticleLimits, MyArticle, MyArticles } from "@/lib/types";

/**
 * The author's desk: a list of their articles, and an editor.
 *
 * It does not autosave. An editor that saves by itself is an editor that
 * sometimes saves the half-sentence you were about to delete, and for writing
 * that will be read by a stranger it is better that saving is something the
 * author did. Leaving the page with unsaved changes asks first.
 *
 * Nothing here decides what is allowed. The limits shown come from the API
 * and the API enforces them; a button being enabled is a convenience.
 */

type Flash = { ok: boolean; text: string } | null;
type Open = { id: string | null; draft: ArticleDraft; saved: ArticleDraft };

const EMPTY: ArticleDraft = { title: "", summary: "", body: "" };
const EDITABLE = new Set(["DRAFT", "REJECTED", "REMOVED"]);

const sameDraft = (a: ArticleDraft, b: ArticleDraft) =>
  a.title === b.title && a.summary === b.summary && a.body === b.body;

export function Writer({ displayName }: { displayName: string }) {
  const [desk, setDesk] = useState<MyArticles | null>(null);
  const [open, setOpen] = useState<Open | null>(null);
  const [flash, setFlash] = useState<Flash>(null);
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<MyArticle | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);

  const load = useCallback(async () => {
    const result = await getMyArticles();
    if (result.ok) setDesk(result.data);
    else setFlash({ ok: false, text: errorMessage(result.code) });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const dirty = open !== null && !sameDraft(open.draft, open.saved);

  // The browser's own "leave this page?" prompt, only while there is
  // something to lose.
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // The confirmation is the browser's own modal: it holds the focus, the
  // page behind it cannot be reached, and Escape keeps the article.
  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (pendingDelete && !node.open) node.showModal();
    if (!pendingDelete && node.open) node.close();
  }, [pendingDelete]);

  async function act(action: () => Promise<ApiResult<unknown>>, done?: string): Promise<boolean> {
    setBusy(true);
    setFlash(null);
    const result = await action();
    setBusy(false);
    if (!result.ok) {
      setFlash({ ok: false, text: errorMessage(result.code) });
      return false;
    }
    if (done) setFlash({ ok: true, text: done });
    await load();
    return true;
  }

  /** Save what is in the editor. Returns the article's id, or null on failure. */
  async function save(): Promise<string | null> {
    if (!open) return null;
    setBusy(true);
    setFlash(null);
    const result = open.id
      ? await updateArticle(open.id, open.draft)
      : await createArticle(open.draft);
    setBusy(false);

    if (!result.ok) {
      setFlash({ ok: false, text: errorMessage(result.code) });
      return null;
    }
    // What the server stored, which is what was typed after tidying: a title
    // with its stray spaces collapsed, a body with its line endings made even.
    const stored = {
      title: result.data.title,
      summary: result.data.summary,
      body: result.data.body,
    };
    setOpen({ id: result.data.id, draft: stored, saved: stored });
    setFlash({ ok: true, text: t.writeSaved });
    await load();
    return result.data.id;
  }

  async function saveAndSubmit() {
    const id = dirty || !open?.id ? await save() : open.id;
    if (!id) return;
    const sent = await act(() => submitArticle(id));
    if (sent) setOpen(null);
  }

  const heading = (
    <header className="dp-head">
      <h1>{t.writeTitle}</h1>
      <p className="dp-lede">{t.writeIntro}</p>
    </header>
  );

  if (desk === null) {
    return (
      <>
        {heading}
        {flash ? (
          <p role="alert" className="notice notice-error mt-8 max-w-2xl">
            {flash.text}
          </p>
        ) : (
          <p role="status" className="dp-empty mt-8 max-w-2xl">
            {t.loading}
          </p>
        )}
      </>
    );
  }

  if (!desk.can_write) {
    // Either a guest, who needs an account, or an account that has been
    // restricted. A guest is by far the likelier, and is the one with
    // something they can do about it.
    return (
      <>
        {heading}
        <div className="rd-state mt-8">
          <p>{t.writeNeedsAccount}</p>
          <p>
            <Link href="/signup?next=/write" className="btn btn--primary" prefetch={false}>
              {t.writeNeedsAccountCta}
            </Link>
          </p>
        </div>
      </>
    );
  }

  return (
    <>
      {heading}

      {flash ? (
        <p
          role={flash.ok ? "status" : "alert"}
          className={`notice mt-6 max-w-2xl ${flash.ok ? "notice-ok" : "notice-error"}`}
        >
          {flash.text}
        </p>
      ) : null}

      <div className={open ? "rd-desk rd-desk--editing" : "rd-desk"}>
        <div className="min-w-0">
          {open ? (
            <Editor
              open={open}
              limits={desk.limits}
              article={desk.articles.find((entry) => entry.id === open.id) ?? null}
              publishesDirectly={desk.publishes_directly}
              busy={busy}
              dirty={dirty}
              onChange={(draft) => setOpen({ ...open, draft })}
              onSave={() => void save()}
              onSubmit={() => void saveAndSubmit()}
              onClose={() => {
                if (dirty && !window.confirm(t.writeDiscard)) return;
                setOpen(null);
                setFlash(null);
              }}
            />
          ) : (
            <section aria-labelledby="mine">
              <h2 id="mine" className="dp-h2">
                {t.writeMine}
              </h2>
              {desk.articles.length === 0 ? (
                <p className="dp-empty">{t.writeNone}</p>
              ) : (
                <ul className="rd-entries" role="list">
                  {desk.articles.map((article) => (
                    <li key={article.id} className="rd-entry">
                      <div className="rd-entry__top">
                        <h3 className="rd-entry__title">{article.title}</h3>
                        <span className="rd-status" data-status={article.status}>
                          {t.articleStatus[article.status]}
                        </span>
                      </div>
                      <p className="rd-entry__meta">
                        {t.writeEdited(timeAgo(article.edited_at))} ·{" "}
                        {t.articleReading(article.reading_minutes)}
                      </p>
                      <p className="rd-entry__note">{t.articleStatusNote[article.status]}</p>
                      {article.review_note ? (
                        <p className="rd-review">
                          <span className="rd-review__who">{t.writeReviewNote}</span>
                          {article.review_note}
                        </p>
                      ) : null}

                      <div className="rd-entry__actions">
                        {EDITABLE.has(article.status) ? (
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            disabled={busy}
                            onClick={() => {
                              const draft = {
                                title: article.title,
                                summary: article.summary,
                                body: article.body,
                              };
                              setFlash(null);
                              setOpen({ id: article.id, draft, saved: draft });
                            }}
                          >
                            {t.writeOpen}
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            disabled={busy}
                            onClick={() => void act(() => withdrawArticle(article.id))}
                          >
                            {t.writeWithdraw}
                          </button>
                        )}
                        {article.status === "PUBLISHED" ? (
                          <Link
                            href={`/articles/${article.slug}`}
                            className="btn btn-quiet btn-sm"
                            prefetch={false}
                          >
                            {t.writeView}
                          </Link>
                        ) : null}
                        <button
                          type="button"
                          className="btn btn-danger btn-sm"
                          disabled={busy}
                          onClick={() => setPendingDelete(article)}
                        >
                          {t.writeDelete}
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </div>

        <aside className="rd-desk__side" aria-labelledby="rules">
          <h2 id="rules" className="rd-small-h">
            {t.writeRulesTitle}
          </h2>
          <ul className="rd-desk__rules" role="list">
            {t.writeRules(displayName).map((rule) => (
              <li key={rule}>{rule}</li>
            ))}
          </ul>
          {open ? null : (
            <p>
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => {
                  setFlash(null);
                  setOpen({ id: null, draft: EMPTY, saved: EMPTY });
                }}
              >
                {t.writeNew}
              </button>
            </p>
          )}
        </aside>
      </div>

      <dialog
        ref={dialog}
        className="rd-dialog"
        role="alertdialog"
        aria-labelledby="delete-title"
        aria-describedby="delete-body"
        onClose={() => setPendingDelete(null)}
      >
        <h2 id="delete-title">{t.writeDeleteTitle}</h2>
        {pendingDelete ? <p className="text-ink">{pendingDelete.title}</p> : null}
        <p id="delete-body">{t.writeDeleteBody}</p>
        <div className="rd-dialog__actions">
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setPendingDelete(null)}>
            {t.writeDeleteKeep}
          </button>
          <button
            type="button"
            className="btn btn-danger btn-sm"
            disabled={busy}
            onClick={() => {
              const target = pendingDelete;
              setPendingDelete(null);
              if (target) void act(() => deleteArticle(target.id));
            }}
          >
            {t.writeDeleteConfirm}
          </button>
        </div>
      </dialog>
    </>
  );
}

function within(value: string, min: number, max: number): boolean {
  const length = value.trim().length;
  return length >= min && length <= max;
}

function Editor({
  open,
  limits,
  article,
  publishesDirectly,
  busy,
  dirty,
  onChange,
  onSave,
  onSubmit,
  onClose,
}: {
  open: Open;
  limits: ArticleLimits;
  article: MyArticle | null;
  publishesDirectly: boolean;
  busy: boolean;
  dirty: boolean;
  onChange: (draft: ArticleDraft) => void;
  onSave: () => void;
  onSubmit: () => void;
  onClose: () => void;
}) {
  const ids = { title: useId(), summary: useId(), body: useId() };
  const [previewing, setPreviewing] = useState(false);
  const { draft } = open;

  const titleOk = within(draft.title, limits.title_min, limits.title_max);
  const summaryOk = within(draft.summary, limits.summary_min, limits.summary_max);
  const bodyOk = within(draft.body, limits.body_min, limits.body_max);
  const complete = titleOk && summaryOk && bodyOk;

  return (
    <section className="rd-editor">
      <button type="button" className="btn btn-quiet btn-sm rd-editor__back" onClick={onClose}>
        ← {t.writeMine}
      </button>

      {article?.review_note ? (
        <p className="rd-review">
          <span className="rd-review__who">{t.writeReviewNote}</span>
          {article.review_note}
        </p>
      ) : null}

      <div className="rd-field">
        <label htmlFor={ids.title} className="label">
          {t.fieldArticleTitle}
        </label>
        <input
          id={ids.title}
          className="field rd-title-input"
          value={draft.title}
          maxLength={limits.title_max + 40}
          onChange={(event) => onChange({ ...draft, title: event.target.value })}
        />
        <p className={`hint rd-count ${draft.title && !titleOk ? "is-off" : ""}`}>
          {t.lengthRange(draft.title.trim().length, limits.title_min, limits.title_max)}
        </p>
      </div>

      <div className="rd-field">
        <label htmlFor={ids.summary} className="label">
          {t.fieldArticleSummary}
        </label>
        <textarea
          id={ids.summary}
          className="field"
          rows={3}
          value={draft.summary}
          onChange={(event) => onChange({ ...draft, summary: event.target.value })}
        />
        <p className={`hint rd-count ${draft.summary && !summaryOk ? "is-off" : ""}`}>
          {t.fieldArticleSummaryHint}{" "}
          {t.lengthRange(draft.summary.trim().length, limits.summary_min, limits.summary_max)}
        </p>
      </div>

      <div className="rd-field">
        <div className="rd-field__top">
          <label htmlFor={ids.body} className="label">
            {t.fieldArticleBody}
          </label>
          <div className="rd-seg" role="group" aria-label={t.writeTabs}>
            <button type="button" aria-pressed={!previewing} onClick={() => setPreviewing(false)}>
              {t.writeTabEdit}
            </button>
            <button type="button" aria-pressed={previewing} onClick={() => setPreviewing(true)}>
              {t.writeTabPreview}
            </button>
          </div>
        </div>

        {previewing ? (
          <div className="rd-preview">
            {draft.body.trim() ? (
              <Prose markdown={draft.body} fromReader />
            ) : (
              <p className="text-muted">{t.writePreviewEmpty}</p>
            )}
          </div>
        ) : (
          <textarea
            id={ids.body}
            className="field rd-body-input"
            rows={20}
            value={draft.body}
            onChange={(event) => onChange({ ...draft, body: event.target.value })}
          />
        )}
        <p className={`hint rd-count ${draft.body && !bodyOk ? "is-off" : ""}`}>
          {t.fieldArticleBodyHint}{" "}
          {t.lengthRange(draft.body.trim().length, limits.body_min, limits.body_max)}
        </p>
      </div>

      <div className="rd-editor__bar">
        <div className="rd-actions">
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy || !complete || !dirty}
            onClick={onSave}
          >
            {busy ? t.saving : t.writeSave}
          </button>
          <button
            type="button"
            className="btn btn--primary"
            disabled={busy || !complete}
            onClick={onSubmit}
          >
            {publishesDirectly ? t.writePublish : t.writeSubmit}
          </button>
        </div>
        <p className="hint">{publishesDirectly ? t.writePublishNote : t.writeSubmitNote}</p>
      </div>
    </section>
  );
}
