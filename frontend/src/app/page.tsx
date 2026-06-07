"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Summary } from "@/lib/api";

function Row({ label, value, accent }: { label: string; value: string | number; accent?: boolean }) {
  return (
    <div className="flex gap-4 py-0.5">
      <span className="text-[var(--muted)] w-36 shrink-0">{label}</span>
      <span className={accent ? "text-[var(--accent)] font-semibold" : "text-[var(--text)]"}>{value}</span>
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
    <div className="space-y-6">
      {/* Prompt heading */}
      <div>
        <p className="text-[var(--muted)] text-xs mb-1">user@factory:~$</p>
        <h1 className="text-[var(--accent)] text-xl font-bold tracking-tight" data-testid="page-heading">
          Dashboard<span className="cursor" />
        </h1>
        <p className="text-[var(--muted)] text-xs mt-1">
          Multi-agent Medium post pipeline · LangGraph · Claude · MongoDB
        </p>
      </div>

      {/* Stats */}
      <div className="term-box">
        <div className="term-box-header">
          <span className="text-[var(--accent)]">●</span>
          <span>system status</span>
        </div>
        <div className="p-4 space-y-0.5 text-sm">
          {loading ? (
            <>
              <div className="flex gap-4 py-0.5"><div className="skeleton h-3 w-28" /><div className="skeleton h-3 w-8" /></div>
              <div className="flex gap-4 py-0.5"><div className="skeleton h-3 w-28" /><div className="skeleton h-3 w-8" /></div>
              <div className="flex gap-4 py-0.5"><div className="skeleton h-3 w-28" /><div className="skeleton h-3 w-16" /></div>
            </>
          ) : summary ? (
            <>
              <Row label="pipeline_runs" value={summary.pipeline_runs} />
              <Row label="completed_runs" value={summary.completed_runs} accent />
              <Row label="total_posts" value={summary.total_posts} />
              <Row label="published_posts" value={summary.published_posts} accent />
              <Row label="total_tokens" value={summary.total_tokens.toLocaleString()} />
              <Row label="total_cost_usd" value={`$${summary.total_cost_usd.toFixed(6)}`} accent />
            </>
          ) : (
            <p className="text-[var(--muted)]">no data — run a pipeline first</p>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="space-y-2">
        <p className="text-[var(--muted)] text-xs">available commands:</p>
        <div className="flex flex-col sm:flex-row gap-3">
          <Link
            href="/pipeline"
            data-testid="cta-run-pipeline"
            className="term-btn term-btn-solid flex-1 text-center py-3 text-sm tracking-widest"
          >
            ❯ run_pipeline
          </Link>
          <Link
            href="/posts"
            data-testid="cta-view-posts"
            className="term-btn flex-1 text-center py-3 text-sm tracking-widest"
          >
            ❯ list_posts
          </Link>
        </div>
      </div>
    </div>
  );
}
