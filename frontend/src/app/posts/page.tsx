"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Post } from "@/lib/api";

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 75
      ? "text-[var(--green)] bg-green-950/40"
      : pct >= 50
      ? "text-[var(--yellow)] bg-yellow-950/40"
      : "text-[var(--red)] bg-red-950/40";
  return (
    <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${color}`}>
      {pct}/100
    </span>
  );
}

function PostCard({ post }: { post: Post }) {
  const [expanded, setExpanded] = useState(false);
  const qr = post.quality_report;

  return (
    <div
      className="bg-[var(--surface)] border border-[var(--border)] hover:border-[var(--accent)]/30 transition-colors rounded-xl p-5 space-y-3"
      data-testid="post-card"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-semibold leading-snug">{post.title}</p>
          <p className="text-[var(--muted)] text-xs mt-1">
            {new Date(post.created_at).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
              year: "numeric",
            })}{" "}
            · {post.revision_count} revision{post.revision_count !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {qr && <ScoreBadge score={qr.score} />}
          <span className="text-[10px] text-[var(--muted)] border border-[var(--border)] rounded px-2 py-0.5 capitalize">
            {post.status}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {post.tags.map((t) => (
          <span
            key={t}
            className="text-[11px] bg-[var(--bg)] border border-[var(--border)] rounded px-2 py-0.5"
          >
            {t}
          </span>
        ))}
      </div>

      {qr && (
        <p className="text-xs text-[var(--muted)]">
          Predicted read ratio:{" "}
          <span className="text-[var(--text)] font-medium">
            {Math.round(qr.read_ratio_prediction * 100)}%
          </span>
          <span className="ml-1 opacity-50">(baseline 12%)</span>
        </p>
      )}

      <div className="flex items-center gap-3 pt-1">
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-[var(--accent)] hover:underline transition-colors"
        >
          {expanded ? "Hide content" : "Show content"}
        </button>
        {post.medium_url && (
          <a
            href={post.medium_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-[var(--muted)] hover:text-[var(--text)] underline transition-colors"
          >
            View on Medium ↗
          </a>
        )}
      </div>

      {expanded && (
        <div className="space-y-3">
          <pre className="text-xs bg-[var(--bg)] rounded-lg p-4 overflow-auto max-h-96 whitespace-pre-wrap leading-relaxed">
            {post.content}
          </pre>
          {qr && qr.issues.length > 0 && (
            <div className="space-y-2">
              <p className="text-[10px] font-semibold text-[var(--muted)] uppercase tracking-widest">
                Quality Issues
              </p>
              {qr.issues.slice(0, 5).map((issue, i) => (
                <div key={i} className="text-xs bg-[var(--bg)] rounded-lg p-3 flex gap-2">
                  <span
                    className={`font-bold shrink-0 ${
                      issue.severity === "high"
                        ? "text-[var(--red)]"
                        : issue.severity === "medium"
                        ? "text-[var(--yellow)]"
                        : "text-[var(--muted)]"
                    }`}
                  >
                    {issue.severity.toUpperCase()}
                  </span>
                  <span className="text-[var(--muted)]">
                    {issue.category}: {issue.suggestion}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2 flex-1">
          <div className="skeleton h-4 w-3/4" />
          <div className="skeleton h-3 w-40" />
        </div>
        <div className="skeleton h-5 w-12 rounded-full" />
      </div>
      <div className="flex gap-1.5">
        <div className="skeleton h-5 w-16 rounded" />
        <div className="skeleton h-5 w-20 rounded" />
        <div className="skeleton h-5 w-14 rounded" />
      </div>
    </div>
  );
}

const STATUSES = ["", "draft", "revised", "approved", "published"];

export default function PostsPage() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .listPosts(filter || undefined)
      .then(setPosts)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [filter]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold" data-testid="page-heading">Posts</h1>
        <div className="flex gap-1.5 flex-wrap" data-testid="filter-bar">
          {STATUSES.map((s) => (
            <button
              key={s}
              data-testid={`filter-${s || "all"}`}
              onClick={() => setFilter(s)}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                filter === s
                  ? "border-[var(--accent)] text-[var(--accent)] bg-[var(--accent-dim)]"
                  : "border-[var(--border)] text-[var(--muted)] hover:text-[var(--text)] hover:border-[var(--muted)]"
              }`}
            >
              {s || "All"}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="space-y-4">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : posts.length === 0 ? (
        <div className="text-center py-16 space-y-4" data-testid="empty-state">
          <p className="text-4xl opacity-30">✎</p>
          <p className="text-[var(--muted)] text-sm">
            {filter ? `No ${filter} posts yet.` : "No posts yet."}
          </p>
          <Link
            href="/pipeline"
            data-testid="empty-cta"
            className="inline-block bg-[var(--accent)] text-white text-sm px-4 py-2 rounded-lg hover:opacity-90 transition-opacity"
          >
            Run your first pipeline →
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          {posts.map((p) => (
            <PostCard key={p.run_id} post={p} />
          ))}
        </div>
      )}
    </div>
  );
}
