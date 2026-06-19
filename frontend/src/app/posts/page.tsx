"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Post } from "@/lib/api";

function CopyMarkdownButton({ content, title }: { content: string; title: string }) {
  const [copied, setCopied] = useState(false);

  async function handleClick(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    await navigator.clipboard.writeText(`# ${title}\n\n${content}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }

  return (
    <button
      onClick={handleClick}
      className="text-xs px-2 py-0.5 rounded transition-colors"
      style={{
        background: "rgba(124,133,162,0.1)",
        color: copied ? "var(--green)" : "var(--text-dim)",
        border: "1px solid var(--border)",
        fontFamily: "monospace",
        cursor: "pointer",
      }}
    >
      {copied ? "copied!" : "copy_markdown"}
    </button>
  );
}

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

function wcColor(n: number) {
  if (n >= 1700) return "var(--green)";
  if (n >= 1300) return "var(--amber)";
  return "var(--red)";
}

function PostCard({ post, onTagClick }: { post: Post; onTagClick: (tag: string) => void }) {
  const qr = post.quality_report;
  const wordCount = post.word_count ?? (post.content ? post.content.split(/\s+/).length : 0);
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
            <span
              data-testid={`word-count-${post.run_id}`}
              style={{ color: wcColor(wordCount), fontWeight: 500 }}
            >
              {wordCount.toLocaleString()} words
            </span>
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
            <div className="flex flex-wrap gap-1.5 mt-3" onClick={(e) => e.preventDefault()}>
              {post.tags.map((t) => (
                <button
                  key={t}
                  data-testid={`tag-${t}`}
                  onClick={(e) => { e.preventDefault(); e.stopPropagation(); onTagClick(t); }}
                  className="text-xs px-2 py-0.5 rounded-full transition-colors"
                  style={{
                    background: "rgba(249,115,22,0.07)",
                    color: "var(--text-muted)",
                    border: "1px solid rgba(249,115,22,0.14)",
                    cursor: "pointer",
                  }}
                >
                  {t}
                </button>
              ))}
            </div>
          )}

          {/* Quick actions */}
          <div className="flex items-center gap-2 mt-3" onClick={(e) => e.stopPropagation()}>
            <CopyMarkdownButton content={post.content} title={post.title} />
            {post.verified_sources && post.verified_sources.length > 0 && (
              <span className="text-xs" style={{ color: "var(--green)", fontFamily: "monospace" }}>
                {post.verified_sources.length} source{post.verified_sources.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>
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

const PAGE_SIZE = 20;

export default function PostsPage() {
  type SortKey = "newest" | "oldest" | "score-desc" | "score-asc";

  const [posts, setPosts]             = useState<Post[]>([]);
  const [filter, setFilter]           = useState("");
  const [search, setSearch]           = useState("");
  const [boostOnly, setBoostOnly]     = useState(false);
  const [tagFilter, setTagFilter]     = useState<string | null>(null);
  const [sort, setSort]               = useState<SortKey>("newest");
  const [loading, setLoading]         = useState(true);
  const [offset, setOffset]           = useState(0);
  const [hasMore, setHasMore]         = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    setLoading(true);
    setOffset(0);
    api.listPosts(filter || undefined, 0)
      .then((p) => {
        setPosts(p);
        setHasMore(p.length === PAGE_SIZE);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [filter]);

  async function handleLoadMore() {
    setLoadingMore(true);
    const nextOffset = offset + PAGE_SIZE;
    try {
      const more = await api.listPosts(filter || undefined, nextOffset);
      setPosts((prev) => [...prev, ...more]);
      setOffset(nextOffset);
      setHasMore(more.length === PAGE_SIZE);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingMore(false);
    }
  }

  const visible = posts
    .filter((p) => {
      if (boostOnly && !p.quality_report?.medium_boost_eligible) return false;
      if (search.trim() && !p.title.toLowerCase().includes(search.toLowerCase())) return false;
      if (tagFilter && !p.tags.includes(tagFilter)) return false;
      return true;
    })
    .sort((a, b) => {
      if (sort === "newest") return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      if (sort === "oldest") return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      const sa = a.quality_report?.score ?? -1;
      const sb = b.quality_report?.score ?? -1;
      if (sort === "score-desc") return sb - sa;
      if (sort === "score-asc")  return sa - sb;
      return 0;
    });

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

      {/* Filter + search bar */}
      <div className="flex flex-wrap items-center gap-3">
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
        <button
          data-testid="filter-boost"
          onClick={() => setBoostOnly((b) => !b)}
          className="text-xs px-3 py-1.5 rounded-md transition-colors"
          style={{
            background: boostOnly ? "rgba(16,185,129,0.12)" : "transparent",
            color:      boostOnly ? "var(--green)"           : "var(--text-muted)",
            border:     `1px solid ${boostOnly ? "var(--green)" : "var(--border)"}`,
            fontWeight: boostOnly ? 500 : 400,
          }}
        >
          Boost eligible
        </button>
        {tagFilter && (
          <div
            data-testid="active-tag-filter"
            className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-md"
            style={{
              background: "rgba(139,92,246,0.1)",
              border: "1px solid rgba(139,92,246,0.3)",
              color: "#a78bfa",
            }}
          >
            #{tagFilter}
            <button
              data-testid="clear-tag-filter"
              onClick={() => setTagFilter(null)}
              className="ml-1 leading-none"
              style={{ color: "#a78bfa", cursor: "pointer" }}
            >
              ×
            </button>
          </div>
        )}
        <input
          data-testid="search-input"
          type="text"
          placeholder="Search titles…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="text-xs px-3 py-1.5 rounded-md"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
            color: "var(--text)",
            outline: "none",
            minWidth: 180,
          }}
        />
        <select
          data-testid="sort-select"
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          className="text-xs px-3 py-1.5 rounded-md ml-auto"
          style={{
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
            color: "var(--text-muted)",
            outline: "none",
            cursor: "pointer",
          }}
        >
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="score-desc">Best score</option>
          <option value="score-asc">Worst score</option>
        </select>
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
      ) : visible.length === 0 ? (
        <div className="card p-12 text-center space-y-4" data-testid="empty-state">
          <p className="text-lg" style={{ color: "var(--text-muted)" }}>No posts yet</p>
          <p className="text-sm" style={{ color: "var(--text-dim)" }}>
            {boostOnly && !search ? "No Boost-eligible posts yet." : search ? `No posts matching "${search}"` : filter ? `No posts with status "${filter}"` : "Run the pipeline to generate your first post."}
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
        <>
          <div className="space-y-3">
            {visible.map((p) => <PostCard key={p.run_id} post={p} onTagClick={setTagFilter} />)}
          </div>
          {hasMore && (
            <div className="text-center pt-4">
              <button
                data-testid="load-more"
                onClick={handleLoadMore}
                disabled={loadingMore}
                className="btn text-sm"
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
