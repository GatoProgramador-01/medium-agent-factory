"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Post } from "@/lib/api";

const STATUSES = ["", "draft", "revised", "approved"];

function scoreColor(score: number) {
  if (score >= 0.90) return "badge-green";
  if (score >= 0.75) return "badge-amber";
  return "badge-red";
}

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  return (
    <span className={`badge ${scoreColor(score)}`}>{pct}</span>
  );
}

function PostCard({ post }: { post: Post }) {
  const qr = post.quality_report;
  const wordCount = post.content ? post.content.split(/\s+/).length : 0;
  const readMin = Math.ceil(wordCount / 220);

  return (
    <Link
      href={`/posts/${post.run_id}`}
      data-testid="post-card"
      className="block card p-5 post-card group"
      style={{ textDecoration: "none" }}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          {/* Status + position */}
          <div className="flex items-center gap-2 mb-2">
            <span
              className="badge"
              style={{
                background: post.status === "approved" ? "rgba(16,185,129,0.12)" : "rgba(124,133,162,0.12)",
                color:      post.status === "approved" ? "var(--green)" : "var(--text-muted)",
              }}
            >
              {post.status}
            </span>
            {post.series_position && (
              <span className="badge badge-purple">Part {post.series_position}</span>
            )}
          </div>

          {/* Title */}
          <h2
            className="font-semibold text-base mb-1 group-hover:text-white transition-colors"
            style={{ color: "var(--text)", lineHeight: 1.4 }}
          >
            {post.title}
          </h2>

          {/* Pull quote */}
          {post.pull_quote && (
            <p className="text-sm italic mb-2" style={{ color: "var(--text-muted)" }}>
              &ldquo;{post.pull_quote}&rdquo;
            </p>
          )}

          {/* Meta row */}
          <div className="flex flex-wrap items-center gap-3 text-xs" style={{ color: "var(--text-dim)" }}>
            <span>{new Date(post.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}</span>
            <span>·</span>
            <span>{readMin} min read</span>
            <span>·</span>
            <span>{post.revision_count} revision{post.revision_count !== 1 ? "s" : ""}</span>
            {qr?.medium_boost_eligible && (
              <>
                <span>·</span>
                <span style={{ color: "var(--green)", fontWeight: 500 }}>Boost eligible</span>
              </>
            )}
          </div>

          {/* Tags */}
          {post.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {post.tags.map((t) => (
                <span
                  key={t}
                  className="text-xs px-2 py-0.5 rounded-full"
                  style={{
                    background: "rgba(249,115,22,0.07)",
                    color: "var(--text-muted)",
                    border: "1px solid rgba(249,115,22,0.14)",
                  }}
                >
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Score column */}
        <div className="shrink-0 flex flex-col items-end gap-2">
          {qr ? (
            <>
              <ScoreBadge score={qr.score} />
              <div className="text-xs text-right" style={{ color: "var(--text-dim)" }}>
                <div>{Math.round(qr.read_ratio_prediction * 100)}% ratio</div>
              </div>
              <div className="score-bar-track w-20">
                <div
                  className="score-bar-fill"
                  style={{
                    width: `${Math.round(qr.score * 100)}%`,
                    background: qr.score >= 0.90 ? "var(--green)" : qr.score >= 0.75 ? "var(--amber)" : "var(--red)",
                  }}
                />
              </div>
            </>
          ) : (
            <span className="text-xs" style={{ color: "var(--text-dim)" }}>no score</span>
          )}
        </div>
      </div>
    </Link>
  );
}

export default function PostsPage() {
  const [posts, setPosts]     = useState<Post[]>([]);
  const [filter, setFilter]   = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.listPosts(filter || undefined)
      .then(setPosts)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [filter]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold" data-testid="page-heading" style={{ color: "#fff" }}>
          Posts
        </h1>
        <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
          All generated articles — click any post to read the full version.
        </p>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-2">
        <span className="text-xs" style={{ color: "var(--text-dim)" }}>Status:</span>
        {STATUSES.map((s) => (
          <button
            key={s}
            data-testid={`filter-${s || "all"}`}
            onClick={() => setFilter(s)}
            className="text-xs px-3 py-1.5 rounded-md transition-colors"
            style={{
              background: filter === s ? "var(--orange-dim)" : "transparent",
              color:      filter === s ? "var(--orange)"     : "var(--text-muted)",
              border:     `1px solid ${filter === s ? "var(--orange)" : "var(--border)"}`,
              fontWeight: filter === s ? 500 : 400,
            }}
          >
            {s || "All"}
          </button>
        ))}
      </div>

      {/* Post list */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="card p-5 space-y-3">
              <div className="skeleton h-3 w-20" />
              <div className="skeleton h-5 w-3/4" />
              <div className="skeleton h-3 w-1/2" />
            </div>
          ))}
        </div>
      ) : posts.length === 0 ? (
        <div className="card p-12 text-center space-y-4" data-testid="empty-state">
          <p className="text-lg" style={{ color: "var(--text-muted)" }}>No posts yet</p>
          <p className="text-sm" style={{ color: "var(--text-dim)" }}>
            {filter ? `No posts with status "${filter}"` : "Run the pipeline to generate your first post."}
          </p>
          <Link
            href="/pipeline"
            data-testid="empty-cta"
            className="btn btn-primary inline-block mt-2"
            style={{ textDecoration: "none" }}
          >
            Run Pipeline
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {posts.map((p) => <PostCard key={p.run_id} post={p} />)}
        </div>
      )}
    </div>
  );
}
