"use client";

import { useEffect, useState } from "react";
import { api, type Post } from "@/lib/api";

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 75 ? "text-[var(--green)]" : pct >= 50 ? "text-[var(--yellow)]" : "text-[var(--red)]";
  return <span className={`font-bold ${color}`}>{pct}/100</span>;
}

function PostCard({ post }: { post: Post }) {
  const [expanded, setExpanded] = useState(false);
  const qr = post.quality_report;

  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-semibold">{post.title}</p>
          <p className="text-[var(--muted)] text-xs mt-0.5">
            {new Date(post.created_at).toLocaleDateString()} · {post.status} · {post.revision_count} revision(s)
          </p>
        </div>
        {qr && <ScoreBadge score={qr.score} />}
      </div>

      <div className="flex flex-wrap gap-1">
        {post.tags.map((t) => (
          <span key={t} className="text-xs bg-[var(--bg)] border border-[var(--border)] rounded px-2 py-0.5">
            {t}
          </span>
        ))}
      </div>

      {qr && (
        <div className="text-sm text-[var(--muted)]">
          Predicted read ratio:{" "}
          <span className="text-[var(--text)]">
            {Math.round(qr.read_ratio_prediction * 100)}%
          </span>
        </div>
      )}

      <button
        onClick={() => setExpanded(!expanded)}
        className="text-xs text-[var(--accent)] hover:underline"
      >
        {expanded ? "Hide content" : "Show content"}
      </button>

      {expanded && (
        <pre className="text-xs bg-[var(--bg)] rounded-lg p-4 overflow-auto max-h-96 whitespace-pre-wrap">
          {post.content}
        </pre>
      )}

      {qr && expanded && qr.issues.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-[var(--muted)] uppercase tracking-widest">
            Quality Issues
          </p>
          {qr.issues.slice(0, 5).map((issue, i) => (
            <div key={i} className="text-xs bg-[var(--bg)] rounded-lg p-3">
              <span
                className={`font-bold mr-2 ${
                  issue.severity === "high"
                    ? "text-[var(--red)]"
                    : issue.severity === "medium"
                    ? "text-[var(--yellow)]"
                    : "text-[var(--muted)]"
                }`}
              >
                {issue.severity.toUpperCase()}
              </span>
              {issue.category}: {issue.suggestion}
            </div>
          ))}
        </div>
      )}

      {post.medium_url && (
        <a
          href={post.medium_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[var(--accent)] text-xs underline"
        >
          View on Medium →
        </a>
      )}
    </div>
  );
}

export default function PostsPage() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [filter, setFilter] = useState<string>("");

  useEffect(() => {
    api.listPosts(filter || undefined).then(setPosts).catch(console.error);
  }, [filter]);

  const statuses = ["", "draft", "revised", "approved", "published"];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Posts</h1>
        <div className="flex gap-2">
          {statuses.map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                filter === s
                  ? "border-[var(--accent)] text-[var(--accent)]"
                  : "border-[var(--border)] text-[var(--muted)] hover:text-[var(--text)]"
              }`}
            >
              {s || "All"}
            </button>
          ))}
        </div>
      </div>

      {posts.length === 0 ? (
        <p className="text-[var(--muted)] text-sm">No posts yet. Run a pipeline to generate your first post.</p>
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
