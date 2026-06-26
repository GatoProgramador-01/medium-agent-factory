"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Exemplar, type Post, type Summary } from "@/lib/api";

const STAT_ICONS: Record<string, string> = {
  "Pipeline runs":   "⟳",
  "Completed":       "✓",
  "Posts generated": "✎",
  "Published":       "↗",
  "Total tokens":    "◈",
  "Total cost":      "$",
  "Exemplars saved": "★",
};

function StatCard({
  label,
  value,
  sub,
  testId,
}: {
  label: string;
  value: string | number;
  sub?: string;
  testId?: string;
}) {
  const icon = STAT_ICONS[label];
  return (
    <div className="card p-5" data-testid={testId}>
      {icon && (
        <div
          className="text-lg mb-1 leading-none"
          style={{ color: "var(--text-dim)" }}
          aria-hidden="true"
        >
          {icon}
        </div>
      )}
      <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
        {label}
      </div>
      <div
        className="text-2xl font-bold tabular-nums"
        style={{ color: "#fff" }}
      >
        {value}
      </div>
      {sub && (
        <div className="text-xs mt-0.5" style={{ color: "var(--text-dim)" }}>
          {sub}
        </div>
      )}
    </div>
  );
}

function scoreColor(score: number) {
  if (score >= 0.9) return "var(--green)";
  if (score >= 0.75) return "var(--amber)";
  return "var(--red)";
}

function scoreBorderColor(score: number) {
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
    <div className="space-y-8">
      {/* Hero */}
      <div>
        <h1
          className="text-4xl font-bold leading-tight"
          data-testid="page-heading"
          style={{ color: "#fff", letterSpacing: "-0.03em" }}
        >
          Agent Factory
        </h1>

        {/* Tech stack pill badges */}
        <div className="flex flex-wrap gap-2 mt-3">
          {["LangGraph", "Claude Haiku/Sonnet", "MongoDB"].map((tech) => (
            <span
              key={tech}
              className="text-xs font-medium px-2.5 py-1 rounded-full"
              style={{
                background: "var(--orange-dim)",
                color: "var(--orange)",
              }}
            >
              {tech}
            </span>
          ))}
        </div>

        <p
          className="text-sm mt-3"
          style={{ color: "var(--text-muted)", maxWidth: "42ch" }}
        >
          Research → Write → Fact-check → Revise until quality gates pass.
        </p>
      </div>

      {/* Stats grid */}
      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="card p-5 space-y-2">
              <div className="skeleton h-3 w-20" />
              <div className="skeleton h-7 w-12" />
            </div>
          ))}
        </div>
      ) : summary ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <StatCard
            label="Pipeline runs"
            value={summary.pipeline_runs}
            testId="stat-pipeline-runs"
          />
          <StatCard
            label="Completed"
            value={summary.completed_runs}
            testId="stat-completed"
          />
          <StatCard
            label="Posts generated"
            value={summary.total_posts}
            testId="stat-total-posts"
          />
          <StatCard
            label="Published"
            value={summary.published_posts}
            testId="stat-published"
          />
          <StatCard
            label="Total tokens"
            value={summary.total_tokens.toLocaleString()}
            testId="stat-total-tokens"
          />
          <StatCard
            label="Total cost"
            value={`$${summary.total_cost_usd.toFixed(4)}`}
            sub="USD"
            testId="stat-total-cost"
          />
          <StatCard
            label="Exemplars saved"
            value={exemplars.length}
            testId="stat-exemplars"
          />
        </div>
      ) : (
        <div
          className="card p-8 text-center"
          style={{ color: "var(--text-muted)" }}
        >
          No data yet — run the pipeline to get started.
        </div>
      )}

      {/* Actions */}
      <div
        className="card p-5 flex flex-col sm:flex-row gap-4"
        style={{ background: "var(--surface)" }}
      >
        <div className="flex flex-col gap-1">
          <Link
            href="/pipeline"
            data-testid="cta-run-pipeline"
            className="btn btn-primary"
            style={{ textDecoration: "none" }}
          >
            Run Pipeline
          </Link>
          <span
            className="text-xs"
            style={{ color: "var(--text-dim)", paddingLeft: "2px" }}
          >
            Trigger the 5-agent writing loop
          </span>
        </div>

        <div className="flex flex-col gap-1">
          <Link
            href="/posts"
            data-testid="cta-view-posts"
            className="btn"
            style={{ textDecoration: "none" }}
          >
            View Posts
          </Link>
          <span
            className="text-xs"
            style={{ color: "var(--text-dim)", paddingLeft: "2px" }}
          >
            Browse generated articles
          </span>
        </div>
      </div>

      {/* Recent Posts */}
      {!loading && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2
              className="text-sm font-semibold"
              style={{ color: "var(--text-muted)" }}
            >
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
              className="card p-6 text-center text-sm"
              data-testid="recent-posts-empty"
              style={{ color: "var(--text-muted)" }}
            >
              No posts yet — run the pipeline to get started.
            </div>
          ) : (
            <div className="space-y-2" data-testid="recent-posts">
              {posts.slice(0, 3).map((p) => {
                const score = p.quality_report?.score ?? null;
                const borderColor =
                  score !== null ? scoreBorderColor(score) : "var(--border)";

                return (
                  <Link
                    key={p.run_id}
                    href={`/posts/${p.run_id}`}
                    data-testid={`recent-post-${p.run_id}`}
                    className="card p-4 flex items-start justify-between gap-4 group block"
                    style={{
                      textDecoration: "none",
                      borderLeft: `3px solid ${borderColor}`,
                      paddingLeft: "calc(1rem - 3px)",
                    }}
                  >
                    <div className="flex-1 min-w-0">
                      <p
                        className="text-sm font-medium truncate group-hover:text-white transition-colors"
                        style={{ color: "var(--text)" }}
                      >
                        {p.title}
                      </p>

                      {/* Score bar */}
                      {score !== null && (
                        <div
                          className="score-bar-track mt-1.5"
                          style={{ width: "120px", height: "3px" }}
                        >
                          <div
                            className="score-bar-fill"
                            style={{
                              width: `${Math.round(score * 100)}%`,
                              height: "3px",
                              background: scoreColor(score),
                            }}
                          />
                        </div>
                      )}

                      <p
                        className="text-xs mt-1"
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
                      <span
                        className="shrink-0 text-sm font-bold tabular-nums"
                        style={{ color: scoreColor(score) }}
                      >
                        {Math.round(score * 100)}
                      </span>
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
