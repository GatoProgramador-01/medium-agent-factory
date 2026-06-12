"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Post } from "@/lib/api";

const STATUSES = ["", "draft", "revised", "approved"];

const STATUS_COLOR: Record<string, string> = {
  approved: "text-[var(--accent)]",
  revised:  "text-[var(--yellow)]",
  draft:    "text-[var(--muted)]",
  failed:   "text-[var(--red)]",
};

function ScoreBar({ score }: { score: number }) {
  const pct  = Math.round(score * 100);
  const fill = pct >= 75 ? "bg-[var(--accent)]" : pct >= 50 ? "bg-[var(--yellow)]" : "bg-[var(--red)]";
  const text = pct >= 75 ? "text-[var(--accent)]" : pct >= 50 ? "text-[var(--yellow)]" : "text-[var(--red)]";
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className={`tabular-nums w-7 ${text}`}>{pct}</span>
      <div className="flex-1 h-1 bg-[var(--border)] rounded-full overflow-hidden">
        <div className={`h-full ${fill} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function PostCard({ post }: { post: Post }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied]     = useState(false);
  const statusColor = STATUS_COLOR[post.status] ?? "text-[var(--muted)]";

  async function handleCopy() {
    const text = `# ${post.title}\n\n${post.subtitle ? `*${post.subtitle}*\n\n` : ""}${post.content}`;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div
      className="border-b border-[var(--border)] last:border-0 py-3 px-4 hover:bg-[var(--surface2)] transition-colors"
      data-testid="post-card"
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs shrink-0 ${statusColor}`}>[{post.status}]</span>
            <p className="text-sm font-medium truncate text-[var(--text)]">{post.title}</p>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-[var(--muted)]">
            <span>{new Date(post.created_at).toISOString().slice(0, 10)}</span>
            <span>{post.revision_count} rev</span>
            {post.tags.map((t) => (
              <span key={t} className="text-[var(--border2)]">#{t}</span>
            ))}
          </div>
        </div>
        <div className="shrink-0 w-32">
          {post.quality_report
            ? <ScoreBar score={post.quality_report.score} />
            : <span className="text-[10px] text-[var(--muted)]">no score</span>
          }
        </div>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="mt-3 space-y-2">
          {post.subtitle && (
            <p className="text-xs text-[var(--muted)] italic">{post.subtitle}</p>
          )}
          {post.quality_report && (
            <div className="text-xs text-[var(--muted)] flex flex-wrap gap-4">
              <span>
                read_ratio:{" "}
                <span className="text-[var(--accent)]">
                  {Math.round(post.quality_report.read_ratio_prediction * 100)}%
                </span>
              </span>
              {post.quality_report.strengths.length > 0 && (
                <span>
                  strengths:{" "}
                  <span className="text-[var(--text)]">
                    {post.quality_report.strengths.slice(0, 2).join(", ")}
                  </span>
                </span>
              )}
              {post.quality_report.issues.length > 0 && (
                <span>
                  top issue:{" "}
                  <span className="text-[var(--yellow)]">
                    {post.quality_report.issues[0].category}
                  </span>
                </span>
              )}
            </div>
          )}
          <pre className="text-[11px] bg-[var(--bg)] p-3 overflow-auto max-h-64 text-[var(--muted)] leading-relaxed whitespace-pre-wrap">
            {post.content.slice(0, 1200)}{post.content.length > 1200 ? "\n…" : ""}
          </pre>
        </div>
      )}

      {/* Footer controls */}
      <div className="flex gap-4 mt-2 items-center">
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-[10px] text-[var(--muted)] hover:text-[var(--accent)] transition-colors"
        >
          [{expanded ? "collapse" : "expand"}]
        </button>
        <button
          onClick={handleCopy}
          className="text-[10px] text-[var(--muted)] hover:text-[var(--accent)] transition-colors"
        >
          {copied ? "[✓ copied]" : "[copy_markdown]"}
        </button>
      </div>
    </div>
  );
}

export default function PostsPage() {
  const [posts, setPosts]   = useState<Post[]>([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.listPosts(filter || undefined)
      .then(setPosts)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [filter]);

  return (
    <div className="space-y-5">
      <div>
        <p className="text-[var(--muted)] text-xs mb-1">user@factory:~/factory$</p>
        <h1 className="text-[var(--accent)] text-xl font-bold" data-testid="page-heading">
          Posts
        </h1>
        <p className="text-[var(--muted)] text-xs mt-1">ls -la ./posts --filter=status</p>
      </div>

      {/* Status filter */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[var(--muted)] text-xs">--status:</span>
        {STATUSES.map((s) => (
          <button
            key={s}
            data-testid={`filter-${s || "all"}`}
            onClick={() => setFilter(s)}
            className={`text-[10px] px-2.5 py-1 border transition-colors tracking-wider ${
              filter === s
                ? "border-[var(--accent)] text-[var(--accent)] bg-[var(--accent-dim)]"
                : "border-[var(--border)] text-[var(--muted)] hover:border-[var(--border2)] hover:text-[var(--text)]"
            }`}
          >
            {s || "all"}
          </button>
        ))}
      </div>

      {/* Post list */}
      <div className="term-box">
        <div className="term-box-header">
          <span>output</span>
          {!loading && (
            <span className="ml-auto text-[var(--accent)]">{posts.length} results</span>
          )}
        </div>

        {loading ? (
          <div className="p-4 space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex gap-4">
                <div className="skeleton h-3 w-16" />
                <div className="skeleton h-3 flex-1" />
                <div className="skeleton h-3 w-24" />
              </div>
            ))}
          </div>
        ) : posts.length === 0 ? (
          <div className="p-8 text-center space-y-4" data-testid="empty-state">
            <p className="text-[var(--muted)] text-xs">no posts found</p>
            <p className="text-[var(--border2)] text-[10px]">
              {filter
                ? `no posts with status "${filter}"`
                : "run the pipeline to generate your first post"}
            </p>
            <Link
              href="/pipeline"
              data-testid="empty-cta"
              className="inline-block term-btn term-btn-solid px-6 py-2 text-xs tracking-widest"
            >
              ❯ run_pipeline
            </Link>
          </div>
        ) : (
          <div>
            {posts.map((p) => <PostCard key={p.run_id} post={p} />)}
          </div>
        )}
      </div>
    </div>
  );
}
