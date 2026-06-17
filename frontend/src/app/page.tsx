"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Summary } from "@/lib/api";

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="card p-5">
      <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>{label}</div>
      <div className="text-2xl font-bold tabular-nums" style={{ color: "#fff" }}>{value}</div>
      {sub && <div className="text-xs mt-0.5" style={{ color: "var(--text-dim)" }}>{sub}</div>}
    </div>
  );
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.summary().then(setSummary).catch(console.error).finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-8">
      {/* Hero */}
      <div>
        <h1 className="text-3xl font-bold mb-2" data-testid="page-heading" style={{ color: "#fff", letterSpacing: "-0.02em" }}>
          Agent Factory
        </h1>
        <p className="text-base" style={{ color: "var(--text-muted)" }}>
          Multi-agent AI writing pipeline · LangGraph · Claude · MongoDB
        </p>
      </div>

      {/* Stats grid */}
      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {[1,2,3,4,5,6].map(i => (
            <div key={i} className="card p-5 space-y-2">
              <div className="skeleton h-3 w-20" />
              <div className="skeleton h-7 w-12" />
            </div>
          ))}
        </div>
      ) : summary ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <StatCard label="Pipeline runs"    value={summary.pipeline_runs} />
          <StatCard label="Completed"        value={summary.completed_runs} />
          <StatCard label="Posts generated"  value={summary.total_posts} />
          <StatCard label="Published"        value={summary.published_posts} />
          <StatCard label="Total tokens"     value={summary.total_tokens.toLocaleString()} />
          <StatCard label="Total cost"       value={`$${summary.total_cost_usd.toFixed(4)}`} sub="USD" />
        </div>
      ) : (
        <div className="card p-8 text-center" style={{ color: "var(--text-muted)" }}>
          No data yet — run the pipeline to get started.
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-3">
        <Link
          href="/pipeline"
          data-testid="cta-run-pipeline"
          className="btn btn-primary"
          style={{ textDecoration: "none" }}
        >
          Run Pipeline
        </Link>
        <Link
          href="/posts"
          data-testid="cta-view-posts"
          className="btn"
          style={{ textDecoration: "none" }}
        >
          View Posts
        </Link>
      </div>
    </div>
  );
}
