"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Exemplar, type Post, type Summary } from "@/lib/api";

const PIPELINE_STEPS = [
  "Research",
  "Generate",
  "Fact-check",
  "Quality",
  "Revise",
  "Format",
  "Finalize",
];

function MetricCard({
  label,
  value,
  sub,
  testId,
  accent,
}: {
  label: string;
  value: string | number;
  sub?: string;
  testId?: string;
  accent?: boolean;
}) {
  return (
    <div className="metric-card" data-testid={testId}>
      <div className="metric-card-label">{label}</div>
      <div
        className="metric-card-value"
        style={accent ? { color: "var(--orange)" } : undefined}
      >
        {value}
      </div>
      {sub && <div className="metric-card-sub">{sub}</div>}
    </div>
  );
}

function scoreColor(score: number) {
  if (score >= 0.9) return "var(--green)";
  if (score >= 0.75) return "var(--amber)";
  return "var(--red)";
}

export default function DashboardPage() {
  const [summary, setSummary]     = useState<Summary | null>(null);
  const [posts, setPosts]         = useState<Post[]>([]);
  const [exemplars, setExemplars] = useState<Exemplar[]>([]);
  const [loading, setLoading]     = useState(true);

  useEffect(() => {
    Promise.all([api.summary(), api.listPosts(), api.listExemplars()])
      .then(([s, p, e]) => {
        setSummary(s);
        setPosts(p);
        setExemplars(e);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-10">

      {/* ── Hero ── */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <span className="section-label">Medium Agent Factory</span>
        </div>

        <h1
          data-testid="page-heading"
          className="text-5xl font-bold leading-tight"
          style={{ color: "#fff", letterSpacing: "-0.03em" }}
        >
          Research. Write.<br />
          <span style={{ color: "var(--orange)" }}>Publish.</span>
        </h1>

        <p
          className="text-sm mt-4"
          style={{ color: "var(--text-muted)", maxWidth: "52ch", lineHeight: 1.75 }}
        >
          Multi-agent pipeline that researches, writes, fact-checks, and revises
          until quality gates pass — then formats for Medium.
        </p>

        {/* Pipeline step chips */}
        <div className="flex items-center gap-1 flex-wrap mt-5">
          {PIPELINE_STEPS.map((step, i) => (
            <div key={step} className="flex items-center gap-1">
              <div className="pipeline-step">
                <div className="pipeline-step-dot" />
                {step}
              </div>
              {i < PIPELINE_STEPS.length - 1 && (
                <div className="pipeline-connector" />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── Stats grid ── */}
      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {Array.from({ length: 7 }).map((_, i) => (
            <div key={i} className="metric-card space-y-3">
              <div className="skeleton h-2 w-20" />
              <div className="skeleton h-8 w-16" />
            </div>
          ))}
        </div>
      ) : summary ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <MetricCard
            label="Pipeline runs"
            value={summary.pipeline_runs}
            testId="stat-pipeline-runs"
          />
          <MetricCard
            label="Completed"
            value={summary.completed_runs}
            testId="stat-completed"
          />
          <MetricCard
            label="Posts generated"
            value={summary.total_posts}
            testId="stat-total-posts"
          />
          <MetricCard
            label="Published"
            value={summary.published_posts}
            testId="stat-published"
          />
          <MetricCard
            label="Total tokens"
            value={summary.total_tokens.toLocaleString()}
            testId="stat-total-tokens"
          />
          <MetricCard
            label="Total cost"
            value={`$${summary.total_cost_usd.toFixed(4)}`}
            sub="USD"
            testId="stat-total-cost"
            accent
          />
          <MetricCard
            label="Exemplars saved"
            value={exemplars.length}
            testId="stat-exemplars"
          />
        </div>
      ) : (
        <div
          className="card p-8 text-center text-sm"
          style={{ color: "var(--text-muted)" }}
        >
          No data yet — run the pipeline to get started.
        </div>
      )}

      {/* ── Actions ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Link
          href="/pipeline"
          data-testid="cta-run-pipeline"
          className="panel flex flex-col gap-2 p-5 group"
          style={{ textDecoration: "none", cursor: "pointer" }}
        >
          <div className="flex items-center justify-between">
            <span className="section-label">Action</span>
            <span
              className="text-xs font-medium"
              style={{ color: "var(--orange)" }}
            >
              Open →
            </span>
          </div>
          <span
            className="text-base font-semibold"
            style={{ color: "#fff" }}
          >
            Run Pipeline
          </span>
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            Trigger the 7-agent writing loop on a custom topic
          </span>
        </Link>

        <Link
          href="/posts"
          data-testid="cta-view-posts"
          className="panel flex flex-col gap-2 p-5 group"
          style={{ textDecoration: "none", cursor: "pointer" }}
        >
          <div className="flex items-center justify-between">
            <span className="section-label">Library</span>
            <span
              className="text-xs font-medium"
              style={{ color: "var(--orange)" }}
            >
              Browse →
            </span>
          </div>
          <span
            className="text-base font-semibold"
            style={{ color: "#fff" }}
          >
            View Posts
          </span>
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            Browse generated articles, quality scores, and publish status
          </span>
        </Link>
      </div>

      {/* ── Recent Posts ── */}
      {!loading && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              Recent Posts
            </h2>
            <Link
              href="/posts"
              className="text-xs"
              style={{ color: "var(--orange)", textDecoration: "none" }}
            >
              View all →
            </Link>
          </div>

          {posts.length === 0 ? (
            <div
              className="panel p-8 text-center text-sm"
              data-testid="recent-posts-empty"
              style={{ color: "var(--text-muted)" }}
            >
              No posts yet — run the pipeline to get started.
            </div>
          ) : (
            <div className="space-y-2" data-testid="recent-posts">
              {posts.slice(0, 3).map((p) => {
                const score = p.quality_report?.score ?? p.quality_score ?? null;
                const borderColor =
                  score !== null ? scoreColor(score) : "var(--border)";

                return (
                  <Link
                    key={p.run_id}
                    href={`/posts/${p.run_id}`}
                    data-testid={`recent-post-${p.run_id}`}
                    className="panel post-card flex items-start justify-between gap-4 block"
                    style={{
                      textDecoration: "none",
                      borderLeft: `3px solid ${borderColor}`,
                      padding: "1rem 1.25rem 1rem calc(1.25rem - 3px)",
                      borderRadius: "16px",
                    }}
                  >
                    <div className="flex-1 min-w-0">
                      <p
                        className="text-sm font-medium truncate"
                        style={{ color: "var(--text)" }}
                      >
                        {p.title}
                      </p>

                      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                        {p.word_count != null && (
                          <span
                            className="badge badge-muted"
                            style={{ fontSize: "10px" }}
                          >
                            {p.word_count.toLocaleString()} words
                          </span>
                        )}
                        {p.medium_boost_eligible && (
                          <span className="badge badge-amber" style={{ fontSize: "10px" }}>
                            Boost-eligible
                          </span>
                        )}
                        {p.medium_url && (
                          <span className="badge badge-green" style={{ fontSize: "10px" }}>
                            Published
                          </span>
                        )}
                      </div>

                      <p
                        className="text-xs mt-1.5"
                        style={{ color: "var(--text-dim)" }}
                      >
                        {new Date(p.created_at).toLocaleDateString("en-US", {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                        })}
                        {" · "}
                        {p.status}
                      </p>
                    </div>

                    {score !== null && (
                      <div className="shrink-0 flex flex-col items-end gap-1">
                        <span
                          className="text-lg font-bold tabular-nums leading-none"
                          style={{ color: scoreColor(score) }}
                        >
                          {Math.round(score * 100)}
                        </span>
                        <span className="text-xs" style={{ color: "var(--text-dim)" }}>
                          score
                        </span>
                      </div>
                    )}
                  </Link>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
