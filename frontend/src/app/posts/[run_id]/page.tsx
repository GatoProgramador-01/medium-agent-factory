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

type QualityReport = {
  score: number;
  read_ratio_prediction: number;
  medium_boost_eligible: boolean;
  issues: { category: string; severity: string; suggestion: string }[];
  strengths: string[];
};

function ScoreRing({ pct, color }: { pct: number; color: string }) {
  const r = 25;
  const strokeWidth = 4;
  const circumference = 2 * Math.PI * r;
  const filled = circumference * (pct / 100);

  return (
    <svg
      width={60}
      height={60}
      viewBox="0 0 60 60"
      style={{ flexShrink: 0 }}
      aria-hidden="true"
    >
      {/* Track */}
      <circle
        cx={30}
        cy={30}
        r={r}
        fill="none"
        stroke="var(--border)"
        strokeWidth={strokeWidth}
      />
      {/* Filled arc — starts at top (rotate -90deg) */}
      <circle
        cx={30}
        cy={30}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeDasharray={`${filled} ${circumference - filled}`}
        strokeDashoffset={0}
        strokeLinecap="round"
        transform="rotate(-90 30 30)"
        style={{ transition: "stroke-dasharray 0.5s ease" }}
      />
    </svg>
  );
}

function ReadRatioLabel({ ratio }: { ratio: number }) {
  const pct = Math.round(ratio * 100);
  if (pct > 80) {
    return (
      <span className="text-xs font-medium" style={{ color: "var(--green)" }}>
        Exceptional
      </span>
    );
  }
  if (pct >= 65) {
    return (
      <span className="text-xs font-medium" style={{ color: "var(--amber)" }}>
        Strong
      </span>
    );
  }
  return (
    <span className="text-xs font-medium" style={{ color: "var(--red)" }}>
      Weak
    </span>
  );
}

function QualityPanel({ qr }: { qr: QualityReport }) {
  const [showAllStrengths, setShowAllStrengths] = useState(false);

  const pct = Math.round(qr.score * 100);
  const scoreColor =
    pct >= 90 ? "var(--green)" : pct >= 75 ? "var(--amber)" : "var(--red)";

  // Group issues by category, max 5 categories
  const categoryMap = qr.issues.reduce<
    Record<string, { count: number; topSeverity: string }>
  >((acc, iss) => {
    const existing = acc[iss.category];
    const severityRank = (s: string) =>
      s === "HIGH" ? 2 : s === "MEDIUM" ? 1 : 0;
    if (!existing) {
      acc[iss.category] = { count: 1, topSeverity: iss.severity };
    } else {
      acc[iss.category] = {
        count: existing.count + 1,
        topSeverity:
          severityRank(iss.severity) > severityRank(existing.topSeverity)
            ? iss.severity
            : existing.topSeverity,
      };
    }
    return acc;
  }, {});

  const categoryRows = Object.entries(categoryMap)
    .sort(([, a], [, b]) => {
      const rank = (s: string) => (s === "HIGH" ? 2 : s === "MEDIUM" ? 1 : 0);
      return rank(b.topSeverity) - rank(a.topSeverity);
    })
    .slice(0, 5);

  const severityBadgeStyle = (severity: string) => ({
    background:
      severity === "HIGH"
        ? "rgba(239,68,68,0.15)"
        : severity === "MEDIUM"
        ? "rgba(245,158,11,0.15)"
        : "rgba(124,133,162,0.12)",
    color:
      severity === "HIGH"
        ? "var(--red)"
        : severity === "MEDIUM"
        ? "var(--amber)"
        : "var(--text-muted)",
  });

  const visibleStrengths = showAllStrengths
    ? qr.strengths
    : qr.strengths.slice(0, 1);

  return (
    <aside
      className="card p-5 space-y-4 text-sm"
      style={{
        minWidth: 200,
        maxWidth: 240,
        background: "linear-gradient(170deg, #1e1409 0%, #180f06 100%)",
        border: "1px solid rgba(249,115,22,0.2)",
      }}
    >
      {/* Score + ring */}
      <div>
        <div className="text-xs mb-2" style={{ color: "var(--text-muted)" }}>
          Quality Score
        </div>
        <div className="flex items-center gap-3">
          <ScoreRing pct={pct} color={scoreColor} />
          <div>
            <div
              className="text-3xl font-bold tabular-nums"
              style={{ color: scoreColor }}
            >
              {pct}
              <span
                className="text-base font-normal"
                style={{ color: "var(--text-muted)" }}
              >
                /100
              </span>
            </div>
            <div className="score-bar-track mt-2">
              <div
                className="score-bar-fill"
                style={{ width: `${pct}%`, background: scoreColor }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Read ratio */}
      <div className="space-y-1">
        <div className="text-xs" style={{ color: "var(--text-muted)" }}>
          Predicted read ratio
        </div>
        <div className="flex items-center gap-2">
          <span
            className="font-semibold"
            data-testid="quality-read-ratio"
            style={{ color: "var(--green)" }}
          >
            {Math.round(qr.read_ratio_prediction * 100)}%
          </span>
          <ReadRatioLabel ratio={qr.read_ratio_prediction} />
        </div>
      </div>

      {/* Boost eligible */}
      <div className="space-y-1">
        <div className="text-xs" style={{ color: "var(--text-muted)" }}>
          Boost eligible
        </div>
        <div data-testid="quality-boost-eligible">
          {qr.medium_boost_eligible ? (
            <span className="badge badge-green">Yes</span>
          ) : (
            <span className="badge badge-muted">No</span>
          )}
        </div>
      </div>

      {/* Issue category breakdown */}
      {categoryRows.length > 0 && (
        <div
          className="space-y-2 pt-2"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <div
            className="text-xs font-medium"
            style={{ color: "var(--text-muted)" }}
          >
            Issues
          </div>
          {categoryRows.map(([category, { count, topSeverity }], i) => (
            <div
              key={category}
              data-testid={`quality-issue-${i}`}
              className="flex items-center justify-between gap-2"
            >
              <span
                className="text-xs leading-snug truncate"
                style={{ color: "var(--text-muted)", flex: 1 }}
                title={category}
              >
                {category}
              </span>
              <div className="flex items-center gap-1.5 shrink-0">
                <span className="badge" style={severityBadgeStyle(topSeverity)}>
                  {topSeverity}
                </span>
                {count > 1 && (
                  <span
                    className="text-xs tabular-nums"
                    style={{ color: "var(--text-dim)" }}
                  >
                    ×{count}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Strengths — expandable */}
      {qr.strengths.length > 0 && (
        <div
          className="space-y-2 pt-2"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <div
            className="text-xs font-medium"
            style={{ color: "var(--text-muted)" }}
          >
            Strengths
          </div>
          {visibleStrengths.map((s, i) => (
            <p
              key={i}
              data-testid={`quality-strength-${i}`}
              className="text-xs leading-snug"
              style={{ color: "var(--text-muted)" }}
            >
              {s.slice(0, 120)}
              {s.length > 120 ? "…" : ""}
            </p>
          ))}
          {qr.strengths.length > 1 && (
            <button
              onClick={() => setShowAllStrengths((v) => !v)}
              className="text-xs"
              style={{ color: "var(--orange)", cursor: "pointer", background: "none", border: "none", padding: 0 }}
            >
              {showAllStrengths
                ? "Show less"
                : `Show ${qr.strengths.length - 1} more`}
            </button>
          )}
        </div>
      )}
    </aside>
  );
}

function TagsEditor({ runId, initialTags }: { runId: string; initialTags: string[] }) {
  const [tags, setTags]     = useState(initialTags);
  const [newTag, setNewTag] = useState("");

  async function removeTag(tag: string) {
    const next = tags.filter((t) => t !== tag);
    setTags(next);
    await api.updateTags(runId, next);
  }

  async function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key !== "Enter") return;
    const trimmed = newTag.trim();
    if (!trimmed || tags.includes(trimmed)) return;
    const next = [...tags, trimmed];
    setTags(next);
    setNewTag("");
    await api.updateTags(runId, next);
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5 mb-8">
      {tags.map((t) => (
        <span
          key={t}
          data-testid={`tag-pill-${t}`}
          className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-full"
          style={{ background: "rgba(249,115,22,0.08)", color: "var(--text-muted)", border: "1px solid rgba(249,115,22,0.18)" }}
        >
          {t}
          <button
            data-testid={`remove-tag-${t}`}
            onClick={() => removeTag(t)}
            style={{ color: "var(--text-dim)", lineHeight: 1, cursor: "pointer" }}
          >
            ×
          </button>
        </span>
      ))}
      <input
        data-testid="add-tag-input"
        type="text"
        value={newTag}
        onChange={(e) => setNewTag(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="add tag…"
        className="text-xs px-2 py-0.5 rounded"
        style={{ background: "transparent", border: "1px solid var(--border)", color: "var(--text-muted)", width: 90, outline: "none" }}
      />
    </div>
  );
}

function MediumUrlInput({ runId, initialUrl, onSave }: { runId: string; initialUrl?: string; onSave: (url: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue]     = useState(initialUrl ?? "");
  const [saving, setSaving]   = useState(false);
  const [url, setUrl]         = useState(initialUrl);

  async function handleSave() {
    setSaving(true);
    await api.setMediumUrl(runId, value);
    setUrl(value);
    onSave(value);
    setEditing(false);
    setSaving(false);
  }

  if (!editing && !url) {
    return (
      <button
        data-testid="add-medium-link"
        onClick={() => setEditing(true)}
        className="btn text-sm"
      >
        Add Medium link
      </button>
    );
  }

  if (!editing && url) {
    return (
      <span className="flex items-center gap-2">
        <a href={url} target="_blank" rel="noopener noreferrer" className="btn text-sm" style={{ textDecoration: "none" }}>
          View on Medium ↗
        </a>
        <button onClick={() => { setValue(url); setEditing(true); }} className="text-xs" style={{ color: "var(--text-dim)" }}>
          edit
        </button>
      </span>
    );
  }

  return (
    <span className="flex items-center gap-2">
      <input
        data-testid="medium-url-input"
        type="url"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="https://medium.com/@you/article"
        className="text-xs px-2 py-1 rounded"
        style={{ background: "var(--card-bg)", border: "1px solid var(--border)", color: "var(--text)", minWidth: 260 }}
      />
      <button
        data-testid="save-medium-link"
        onClick={handleSave}
        disabled={saving}
        className="btn text-sm"
      >
        {saving ? "Saving…" : "Save"}
      </button>
      <button onClick={() => setEditing(false)} className="btn text-sm">Cancel</button>
    </span>
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
    <button
      data-testid="copy-markdown-btn"
      onClick={handleCopy}
      className="btn text-sm"
    >
      {copied ? "Copied!" : "✦ Copy"}
    </button>
  );
}

const VALID_STATUSES = ["draft", "revised", "approved", "published"] as const;

function StatusPicker({ runId, status, onChange }: { runId: string; status: string; onChange: (s: string) => void }) {
  async function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const next = e.target.value;
    await api.updateStatus(runId, next);
    onChange(next);
  }

  return (
    <select
      data-testid="status-picker"
      value={status}
      onChange={handleChange}
      className="text-xs px-2 py-0.5 rounded"
      style={{
        background: status === "approved" ? "rgba(16,185,129,0.12)" : "rgba(124,133,162,0.12)",
        color: status === "approved" ? "var(--green)" : "var(--text-muted)",
        border: "1px solid var(--border)",
        cursor: "pointer",
      }}
    >
      {VALID_STATUSES.map((s) => (
        <option key={s} value={s}>{s}</option>
      ))}
    </select>
  );
}

export default function PostReaderPage() {
  const params = useParams();
  const runId  = params.run_id as string;
  const [post, setPost]       = useState<Post | null>(null);
  const [series, setSeries]   = useState<SeriesDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState(0);

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

  useEffect(() => {
    function handleScroll() {
      const scrollY = window.scrollY;
      const documentHeight = document.documentElement.scrollHeight;
      const windowHeight = window.innerHeight;
      const total = documentHeight - windowHeight;
      if (total <= 0) {
        setProgress(0);
        return;
      }
      setProgress((scrollY / total) * 100);
    }

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

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

  const qr = post.quality_report;
  const scorePct = qr ? Math.round(qr.score * 100) : null;
  const scoreColor = scorePct != null
    ? scorePct >= 90 ? "var(--green)" : scorePct >= 75 ? "var(--amber)" : "var(--red)"
    : "var(--text-muted)";

  return (
    <div>
      {/* Reading progress bar */}
      <div
        className="reading-progress"
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          height: "3px",
          background: "var(--orange)",
          zIndex: 9999,
          width: `${progress}%`,
          transition: "width 0.1s linear",
        }}
      />

      {/* Back nav */}
      <Link
        href="/posts"
        className="inline-flex items-center gap-1.5 text-sm mb-8 transition-colors"
        style={{ color: "var(--orange)", textDecoration: "none" }}
      >
        ← All Posts
      </Link>

      <div className="post-reader-layout flex gap-10 items-start">
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

          {/* Meta row */}
          <div
            className="post-meta-bar flex flex-wrap items-center gap-2 text-xs"
            style={{ color: "var(--text-dim)" }}
          >
            <StatusPicker
              runId={runId}
              status={post.status}
              onChange={(s) => setPost((p) => p ? { ...p, status: s } : p)}
            />
            {post.series_position && (
              <span className="badge badge-purple" data-testid="series-position-badge">Series Part {post.series_position}</span>
            )}
            <span>·</span>
            <span data-testid="read-time">{readMin} min read</span>
            <span>·</span>
            <span data-testid="word-count">{wordCount.toLocaleString()} words</span>
            <span>·</span>
            <span>{new Date(post.created_at).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}</span>
          </div>

          {/* Mobile quality bar — hidden on desktop, shown on mobile */}
          {qr && scorePct != null && (
            <div className="mobile-quality-bar">
              <span
                className="font-bold tabular-nums"
                style={{ color: scoreColor, fontSize: "1rem" }}
              >
                {scorePct}
                <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.75rem" }}>/100</span>
              </span>
              {qr.medium_boost_eligible ? (
                <span className="badge badge-green" style={{ fontSize: "10px" }}>Boost</span>
              ) : (
                <span className="badge badge-muted" style={{ fontSize: "10px" }}>No Boost</span>
              )}
            </div>
          )}

          {/* Title */}
          <h1
            className="font-bold mb-4 leading-tight"
            style={{ fontSize: "2.4rem", color: "#f5e8d0", letterSpacing: "-0.02em" }}
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

          {/* Subtitle */}
          {post.subtitle && (
            <p className="post-subtitle">{post.subtitle}</p>
          )}

          {/* Tags */}
          <TagsEditor runId={runId} initialTags={post.tags} />

          {/* Divider */}
          <div style={{ height: "1px", background: "rgba(249,115,22,0.18)", marginBottom: "2.5rem" }} />

          {/* Full post content */}
          <PostContent content={post.content} sources={post.verified_sources} />

          {/* Footer actions */}
          <div
            className="flex items-center gap-3 mt-12 pt-6"
            style={{ borderTop: "1px solid var(--border)" }}
          >
            <CopyButton content={post.content} title={post.title} />
            <DownloadButton
              title={post.title}
              content={post.content}
              label="⊡ Download"
            />
            <PromoteExemplarButton runId={runId} label="★ Save as Exemplar" />
            <MediumUrlInput
              runId={runId}
              initialUrl={post.medium_url}
              onSave={(url) => setPost((p) => p ? { ...p, medium_url: url } : p)}
            />
            <DeleteButton runId={runId} />
          </div>
        </article>

        {/* Sidebar — sticky; quality + revision history (sources moved below) */}
        {(qr || (post.quality_history && post.quality_history.length >= 2)) && (
          <div
            className="post-sidebar shrink-0 sticky top-6 space-y-4"
            style={{
              maxHeight: "calc(100vh - 3rem)",
              overflowY: "auto",
            }}
          >
            {qr && <QualityPanel qr={qr} />}
            <RevisionHistoryPanel history={post.quality_history} />
          </div>
        )}
      </div>

      {/* Sources — full-width below article */}
      {post.verified_sources && post.verified_sources.length > 0 && (
        <div className="sources-below">
          <SourcesPanel sources={post.verified_sources} />
        </div>
      )}
    </div>
  );
}
