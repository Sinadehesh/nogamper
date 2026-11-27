"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useState } from "react";

import { Prose } from "@/components/Prose";
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

const STATUS_TONE: Record<MyArticle["status"], string> = {
  DRAFT: "",
  SUBMITTED: "text-warn",
  PUBLISHED: "text-yes",
  REJECTED: "text-no",
  REMOVED: "text-no",
};

export function Writer({ displayName }: { displayName: string }) {
  const [desk, setDesk] = useState<MyArticles | null>(null);
  const [open, setOpen] = useState<Open | null>(null);
  const [flash, setFlash] = useState<Flash>(null);
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<MyArticle | null>(null);

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

  if (desk === null) {
    return flash ? (
      <p role="alert" className="notice notice-error">
        {flash.text}
      </p>
    ) : (
      <p className="text-muted">{t.loading}</p>
    );
  }

  const heading = (
    <header className="max-w-2xl">
      <h1 className="text-4xl font-black tracking-tight">{t.writeTitle}</h1>
      <p className="mt-3 text-lg text-muted">{t.writeIntro}</p>
    </header>
  );

  if (!desk.can_write) {
    // Either a guest, who needs an account, or an account that has been
    // restricted. A guest is by far the likelier, and is the one with
    // something they can do about it.
    return (
      <>
        {heading}
        <div className="notice mt-8 max-w-2xl">
          <p>{t.writeNeedsAccount}</p>
          <Link href="/signup?next=/write" className="btn btn-primary btn-sm mt-3">
            {t.writeNeedsAccountCta}
          </Link>
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
        <>
          <section className="mt-8 max-w-2xl" aria-labelledby="rules">
            <h2 id="rules" className="text-base font-bold">
              {t.writeRulesTitle}
            </h2>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">
              {t.writeRules(displayName).map((rule) => (
                <li key={rule}>{rule}</li>
              ))}
            </ul>
            <button
              type="button"
              className="btn btn-primary mt-5"
              onClick={() => {
                setFlash(null);
                setOpen({ id: null, draft: EMPTY, saved: EMPTY });
              }}
            >
              {t.writeNew}
            </button>
          </section>

          <section className="mt-10" aria-labelledby="mine">
            <h2 id="mine" className="text-xl font-bold tracking-tight">
              {t.writeMine}
            </h2>
            {desk.articles.length === 0 ? (
              <p className="mt-3 text-muted">{t.writeNone}</p>
            ) : (
              <ul className="mt-4 space-y-3">
                {desk.articles.map((article) => (
                  <li key={article.id} className="card max-w-3xl p-4">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <h3 className="text-base font-bold leading-snug">{article.title}</h3>
                      <span className={`chip ${STATUS_TONE[article.status]}`}>
                        {t.articleStatus[article.status]}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-muted">
                      {t.writeEdited(timeAgo(article.edited_at))} ·{" "}
                      {t.articleReading(article.reading_minutes)}
                    </p>
                    <p className="mt-2 text-sm text-muted">
                      {t.articleStatusNote[article.status]}
                    </p>
                    {article.review_note ? (
                      <p className="mt-3 border-s-2 border-accent ps-3 text-sm">
                        <span className="block text-xs font-semibold text-accent">
                          {t.writeReviewNote}
                        </span>
                        {article.review_note}
                      </p>
                    ) : null}

                    <div className="mt-4 flex flex-wrap gap-2">
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
                        <Link href={`/articles/${article.slug}`} className="btn btn-quiet btn-sm">
                          {t.writeView}
                        </Link>
                      ) : null}
                      <button
                        type="button"
                        className="btn btn-danger btn-sm ms-auto"
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
        </>
      )}

      {pendingDelete ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4">
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-title"
            aria-describedby="delete-body"
            className="card w-full max-w-sm p-5"
          >
            <p id="delete-title" className="font-bold">
              {t.writeDeleteTitle}
            </p>
            <p id="delete-body" className="mt-1 text-sm text-muted">
              {t.writeDeleteBody}
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setPendingDelete(null)}
              >
                {t.writeDeleteKeep}
              </button>
              <button
                type="button"
                className="btn btn-danger btn-sm"
                disabled={busy}
                onClick={() => {
                  const target = pendingDelete;
                  setPendingDelete(null);
                  void act(() => deleteArticle(target.id));
                }}
              >
                {t.writeDeleteConfirm}
              </button>
            </div>
          </div>
        </div>
      ) : null}
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
    <section className="mt-8 max-w-3xl">
      <button type="button" className="btn btn-quiet btn-sm -ms-3" onClick={onClose}>
        ← {t.writeMine}
      </button>

      {article?.review_note ? (
        <p className="notice notice-warn mt-4">
          <span className="block text-xs font-semibold">{t.writeReviewNote}</span>
          {article.review_note}
        </p>
      ) : null}

      <div className="mt-5 space-y-5">
        <div>
          <label htmlFor={ids.title} className="label">
            {t.fieldArticleTitle}
          </label>
          <input
            id={ids.title}
            className="field text-lg font-bold"
            value={draft.title}
            maxLength={limits.title_max + 40}
            onChange={(event) => onChange({ ...draft, title: event.target.value })}
          />
          <p className={`hint ${draft.title && !titleOk ? "text-danger" : ""}`}>
            {t.lengthRange(draft.title.trim().length, limits.title_min, limits.title_max)}
          </p>
        </div>

        <div>
          <label htmlFor={ids.summary} className="label">
            {t.fieldArticleSummary}
          </label>
          <textarea
            id={ids.summary}
            className="field"
            rows={2}
            value={draft.summary}
            onChange={(event) => onChange({ ...draft, summary: event.target.value })}
          />
          <p className={`hint ${draft.summary && !summaryOk ? "text-danger" : ""}`}>
            {t.fieldArticleSummaryHint}{" "}
            {t.lengthRange(draft.summary.trim().length, limits.summary_min, limits.summary_max)}
          </p>
        </div>

        <div>
          <div className="flex items-end justify-between gap-3">
            <label htmlFor={ids.body} className="label">
              {t.fieldArticleBody}
            </label>
            <div className="mb-1 flex gap-1" role="group">
              <button
                type="button"
                aria-pressed={!previewing}
                className={`btn btn-sm ${previewing ? "btn-secondary" : "btn-primary"}`}
                onClick={() => setPreviewing(false)}
              >
                {t.writeTabEdit}
              </button>
              <button
                type="button"
                aria-pressed={previewing}
                className={`btn btn-sm ${previewing ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setPreviewing(true)}
              >
                {t.writeTabPreview}
              </button>
            </div>
          </div>

          {previewing ? (
            <div className="card min-h-64 p-5">
              {draft.body.trim() ? (
                <Prose markdown={draft.body} fromReader />
              ) : (
                <p className="text-muted">{t.writePreviewEmpty}</p>
              )}
            </div>
          ) : (
            <textarea
              id={ids.body}
              className="field min-h-96 font-mono text-sm leading-relaxed"
              rows={20}
              value={draft.body}
              onChange={(event) => onChange({ ...draft, body: event.target.value })}
            />
          )}
          <p className={`hint ${draft.body && !bodyOk ? "text-danger" : ""}`}>
            {t.fieldArticleBodyHint}{" "}
            {t.lengthRange(draft.body.trim().length, limits.body_min, limits.body_max)}
          </p>
        </div>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-3">
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
          className="btn btn-primary"
          disabled={busy || !complete}
          onClick={onSubmit}
        >
          {publishesDirectly ? t.writePublish : t.writeSubmit}
        </button>
      </div>
      <p className="hint">{publishesDirectly ? t.writePublishNote : t.writeSubmitNote}</p>
    </section>
  );
}
