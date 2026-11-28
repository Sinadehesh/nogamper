"use client";

import { useCallback, useEffect, useState } from "react";

import { Prose } from "@/components/Prose";
import { getArticleQueue, reviewArticle } from "@/lib/api";
import { errorMessage, t } from "@/lib/copy";
import { timeAgo } from "@/lib/format";
import type { ArticleQueue, QueuedArticle, ReviewDecision } from "@/lib/types";

/**
 * The review queue: what readers have written, waiting to be read.
 *
 * An article opens in full, rendered exactly as the public page would render
 * it — a reviewer who approves from a title and a summary has not reviewed
 * anything. Saying no needs a reason, because the author is shown it.
 */

type Tab = keyof typeof t.adminArticleTabs;
type Flash = { ok: boolean; text: string } | null;

const TABS = Object.keys(t.adminArticleTabs) as Tab[];

export default function AdminArticlesPage() {
  const [tab, setTab] = useState<Tab>("SUBMITTED");
  const [queue, setQueue] = useState<ArticleQueue | null>(null);
  const [flash, setFlash] = useState<Flash>(null);

  const load = useCallback(async () => {
    const result = await getArticleQueue(tab);
    if (result.ok) setQueue(result.data);
    else {
      setFlash({
        ok: false,
        text: result.status === 404 ? t.adminDenied : errorMessage(result.code),
      });
    }
  }, [tab]);

  useEffect(() => {
    setQueue(null);
    void load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-black tracking-tight">
          {t.adminArticles}
          {queue ? (
            <span className="chip ms-3 align-middle">
              {t.adminArticlesCounts(queue.waiting, queue.live)}
            </span>
          ) : null}
        </h1>
        <div className="flex flex-wrap gap-1" role="group">
          {TABS.map((entry) => (
            <button
              key={entry}
              type="button"
              aria-pressed={tab === entry}
              className={`btn btn-sm ${tab === entry ? "btn-primary" : "btn-secondary"}`}
              onClick={() => {
                setFlash(null);
                setTab(entry);
              }}
            >
              {t.adminArticleTabs[entry]}
            </button>
          ))}
        </div>
      </div>

      {flash ? (
        <p
          role={flash.ok ? "status" : "alert"}
          className={`notice ${flash.ok ? "notice-ok" : "notice-error"}`}
        >
          {flash.text}
        </p>
      ) : null}

      {queue === null ? (
        <p className="text-muted">{t.loading}</p>
      ) : queue.articles.length === 0 ? (
        <p className="text-muted">{t.adminArticlesEmpty}</p>
      ) : (
        <ul className="space-y-3">
          {queue.articles.map((article) => (
            <li key={article.id}>
              <ReviewCard
                article={article}
                onDecided={(next) => {
                  setFlash(next);
                  void load();
                }}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ReviewCard({
  article,
  onDecided,
}: {
  article: QueuedArticle;
  onDecided: (flash: Flash) => void;
}) {
  // An article waiting for review opens already unfolded: reading it is the
  // job. The others are history and stay folded until asked for.
  const [reading, setReading] = useState(article.status === "SUBMITTED");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function decide(decision: ReviewDecision) {
    setBusy(true);
    const result = await reviewArticle(article.id, decision, note.trim());
    setBusy(false);
    onDecided(
      result.ok
        ? { ok: true, text: t.adminArticleDone[decision] }
        : { ok: false, text: errorMessage(result.code) },
    );
  }

  const when = article.submitted_at ?? article.edited_at;

  return (
    <article className="card space-y-3 p-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-bold leading-snug">{article.title}</h2>
          <p className="mt-1 text-xs text-muted">
            {t.adminArticleByline(article.author, article.author_code)} · {timeAgo(when)} ·{" "}
            {t.articleReading(article.reading_minutes)}
          </p>
        </div>
        <span className="chip">{t.articleStatus[article.status]}</span>
      </header>

      <p className="text-sm text-muted">{article.summary}</p>

      {article.review_note ? (
        <p className="border-s-2 border-accent ps-3 text-sm">
          <span className="block text-xs font-semibold text-accent">{t.writeReviewNote}</span>
          {article.review_note}
        </p>
      ) : null}

      <button
        type="button"
        className="btn btn-quiet btn-sm -ms-3 self-start"
        aria-expanded={reading}
        onClick={() => setReading((current) => !current)}
      >
        {reading ? t.adminArticleHide : t.adminArticleRead}
      </button>

      {reading ? (
        <div className="rounded-xl border border-line bg-bg p-4">
          <Prose markdown={article.body} fromReader />
        </div>
      ) : null}

      {article.status === "SUBMITTED" || article.status === "PUBLISHED" ? (
        <div className="space-y-2 border-t border-line pt-3">
          <label className="label" htmlFor={`note-${article.id}`}>
            {t.adminArticleNote}
          </label>
          <textarea
            id={`note-${article.id}`}
            className="field"
            rows={2}
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            {article.status === "SUBMITTED" ? (
              <>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={busy}
                  onClick={() => void decide("publish")}
                >
                  {t.adminArticlePublish}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={busy || !note.trim()}
                  onClick={() => void decide("reject")}
                >
                  {t.adminArticleReject}
                </button>
              </>
            ) : (
              <button
                type="button"
                className="btn btn-danger btn-sm"
                disabled={busy || !note.trim()}
                onClick={() => void decide("remove")}
              >
                {t.adminArticleRemove}
              </button>
            )}
          </div>
        </div>
      ) : null}
    </article>
  );
}
