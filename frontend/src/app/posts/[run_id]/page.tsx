"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, type Post, type SeriesDetail } from "@/lib/api";
import { PostContent } from "@/components/PostContent";
import { SourcesPanel } from "@/components/SourcesPanel";
import { RevisionHistoryPanel } from "@/components/RevisionHistoryPanel";
import { SeriesNav } from "@/components/SeriesNav";
import { PromoteExemplarButton } from "@/components/PromoteExemplarButton";
import { DownloadButton } from "@/components/DownloadButton";

function QualityPanel({ qr }: { qr: NonNullable<Post["quality_report"]> }) {
  const pct = Math.round(qr.score * 100);
  const scoreColor = pct >= 90 ? "var(--green)" : pct >= 75 ? "var(--amber)" : "var(--red)";

  return (
    <aside
      className="card p-5 space-y-4 text-sm"
      style={{
        minWidth: 220,
        maxWidth: 260,
        background: "linear-gradient(170deg, #1e1409 0%, #180f06 100%)",
        border: "1px solid rgba(249,115,22,0.2)",
      }}
    >
      <div>
        <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>Quality Score</div>
        <div className="text-3xl font-bold tabular-nums" style={{ color: scoreColor }}>
          {pct}
          <span className="text-base font-normal" style={{ color: "var(--text-muted)" }}>/100</span>
        </div>
        <div className="score-bar-track mt-2">
          <div className="score-bar-fill" style={{ width: `${pct}%`, background: scoreColor }} />
        </div>
      </div>

      <div className="space-y-1">
        <div className="text-xs" style={{ color: "var(--text-muted)" }}>Predicted read ratio</div>
        <div className="font-semibold" style={{ color: "var(--green)" }}>
          {Math.round(qr.read_ratio_prediction * 100)}%
        </div>
      </div>

      <div className="space-y-1">
        <div className="text-xs" style={{ color: "var(--text-muted)" }}>Boost eligible</div>
        <div>
          {qr.medium_boost_eligible ? (
            <span className="badge badge-green">Yes</span>
          ) : (
            <span className="badge badge-muted">No</span>
          )}
        </div>
      </div>

      {qr.issues.length > 0 && (
        <div className="space-y-2 pt-2" style={{ borderTop: "1px solid var(--border)" }}>
          <div className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>Issues</div>
          {qr.issues.slice(0, 4).map((iss, i) => (
            <div key={i} className="space-y-0.5">
              <span
                className="badge"
                style={{
                  background: iss.severity === "HIGH"   ? "rgba(239,68,68,0.15)"
                            : iss.severity === "MEDIUM" ? "rgba(245,158,11,0.15)"
                            : "rgba(124,133,162,0.12)",
                  color:      iss.severity === "HIGH"   ? "var(--red)"
                            : iss.severity === "MEDIUM" ? "var(--amber)"
                            : "var(--text-muted)",
                }}
              >
                {iss.severity}
              </span>
              <p className="text-xs leading-snug" style={{ color: "var(--text-muted)" }}>
                {iss.category}
              </p>
            </div>
          ))}
        </div>
      )}

      {qr.strengths.length > 0 && (
        <div className="space-y-2 pt-2" style={{ borderTop: "1px solid var(--border)" }}>
          <div className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>Strengths</div>
          {qr.strengths.slice(0, 2).map((s, i) => (
            <p key={i} className="text-xs leading-snug" style={{ color: "var(--text-muted)" }}>
              {s.slice(0, 120)}{s.length > 120 ? "…" : ""}
            </p>
          ))}
        </div>
      )}
    </aside>
  );
}

function DeleteButton({ runId }: { runId: string }) {
  const router = useRouter();
  type Phase = "idle" | "confirming" | "deleting";
  const [phase, setPhase] = useState<Phase>("idle");

  async function handleConfirm() {
    setPhase("deleting");
    await api.deletePost(runId);
    router.push("/posts");
  }

  if (phase === "idle") {
    return (
      <button
        onClick={() => setPhase("confirming")}
        className="btn text-sm"
        style={{ color: "var(--red)", borderColor: "var(--red)" }}
      >
        Delete
      </button>
    );
  }

  if (phase === "confirming") {
    return (
      <span className="flex items-center gap-2">
        <button
          onClick={handleConfirm}
          className="btn text-sm"
          style={{ color: "var(--red)", borderColor: "var(--red)" }}
        >
          Confirm
        </button>
        <button onClick={() => setPhase("idle")} className="btn text-sm">
          Cancel
        </button>
      </span>
    );
  }

  return (
    <button disabled className="btn text-sm" style={{ opacity: 0.5 }}>
      Deleting…
    </button>
  );
}

function CopyButton({ content, title }: { content: string; title: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(`# ${title}\n\n${content}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button onClick={handleCopy} className="btn text-sm">
      {copied ? "Copied!" : "Copy Markdown"}
    </button>
  );
}

export default function PostReaderPage() {
  const params = useParams();
  const runId  = params.run_id as string;
  const [post, setPost]           = useState<Post | null>(null);
  const [series, setSeries]       = useState<SeriesDetail | null>(null);
  const [loading, setLoading]     = useState(true);

  useEffect(() => {
    if (!runId) return;
    api.getPost(runId)
      .then((p) => {
        setPost(p);
        if (p.series_id) {
          api.getSeries(p.series_id).then(setSeries).catch(() => null);
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [runId]);

  if (loading) {
    return (
      <div className="space-y-6 max-w-3xl">
        <div className="skeleton h-4 w-20" />
        <div className="skeleton h-8 w-3/4" />
        <div className="space-y-3">
          {[1,2,3,4].map(i => <div key={i} className="skeleton h-4 w-full" />)}
        </div>
      </div>
    );
  }

  if (!post) {
    return (
      <div className="text-center py-20">
        <p style={{ color: "var(--text-muted)" }}>Post not found.</p>
        <Link href="/posts" className="text-sm mt-4 inline-block" style={{ color: "var(--orange)" }}>
          ← Back to posts
        </Link>
      </div>
    );
  }

  const wordCount = post.content.split(/\s+/).length;
  const readMin   = Math.ceil(wordCount / 220);

  return (
    <div>
      {/* Back nav */}
      <Link
        href="/posts"
        className="inline-flex items-center gap-1.5 text-sm mb-8 transition-colors"
        style={{ color: "var(--orange)", textDecoration: "none" }}
      >
        ← All Posts
      </Link>

      <div className="flex gap-10 items-start">
        {/* Article */}
        <article className="flex-1 min-w-0 reading-wrapper">
          {/* Series navigation */}
          {series && (
            <SeriesNav
              posts={series.posts}
              currentRunId={runId}
              theme={series.theme}
            />
          )}

          {/* Meta */}
          <div className="flex flex-wrap items-center gap-2 mb-4 text-xs" style={{ color: "var(--text-dim)" }}>
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
              <span className="badge badge-purple">Series Part {post.series_position}</span>
            )}
            <span>·</span>
            <span>{readMin} min read</span>
            <span>·</span>
            <span>{wordCount.toLocaleString()} words</span>
            <span>·</span>
            <span>{new Date(post.created_at).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}</span>
          </div>

          {/* Title */}
          <h1
            className="font-bold mb-4 leading-tight"
            style={{ fontSize: "2rem", color: "#f5e8d0", letterSpacing: "-0.02em" }}
          >
            {post.title}
          </h1>

          {/* Pull quote */}
          {post.pull_quote && (
            <blockquote
              className="mb-6 pl-5 italic text-lg"
              style={{
                borderLeft: "3px solid var(--orange)",
                color: "#c89a60",
                fontFamily: "Georgia, serif",
                lineHeight: 1.65,
                background: "rgba(249,115,22,0.05)",
                borderRadius: "0 8px 8px 0",
                padding: "0.75rem 1.25rem",
              }}
            >
              {post.pull_quote}
            </blockquote>
          )}

          {/* Tags */}
          {post.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-8">
              {post.tags.map((t) => (
                <span
                  key={t}
                  className="text-xs px-2.5 py-1 rounded-full"
                  style={{
                    background: "rgba(249,115,22,0.08)",
                    color: "var(--text-muted)",
                    border: "1px solid rgba(249,115,22,0.18)",
                  }}
                >
                  {t}
                </span>
              ))}
            </div>
          )}

          {/* Divider */}
          <div style={{ height: "1px", background: "rgba(249,115,22,0.18)", marginBottom: "2.5rem" }} />

          {/* Full post content */}
          <PostContent content={post.content} />

          {/* Footer actions */}
          <div
            className="flex items-center gap-3 mt-12 pt-6"
            style={{ borderTop: "1px solid var(--border)" }}
          >
            <CopyButton content={post.content} title={post.title} />
            <DownloadButton title={post.title} content={post.content} />
            <PromoteExemplarButton runId={runId} />
            <DeleteButton runId={runId} />
            {post.medium_url && (
              <a
                href={post.medium_url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn text-sm"
                style={{ textDecoration: "none" }}
              >
                View on Medium ↗
              </a>
            )}
          </div>
        </article>

        {/* Sidebar — sticky; quality + sources + revision history stacked */}
        {(post.quality_report || (post.verified_sources && post.verified_sources.length > 0) || (post.quality_history && post.quality_history.length >= 2)) && (
          <div className="shrink-0 sticky top-6 space-y-4">
            {post.quality_report && <QualityPanel qr={post.quality_report} />}
            <SourcesPanel sources={post.verified_sources} />
            <RevisionHistoryPanel history={post.quality_history} />
          </div>
        )}
      </div>
    </div>
  );
}
