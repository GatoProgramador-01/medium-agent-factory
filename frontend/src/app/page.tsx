"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Summary } from "@/lib/api";

function SkeletonCard() {
  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5 space-y-3">
      <div className="skeleton h-3 w-24" />
      <div className="skeleton h-8 w-16" />
      <div className="skeleton h-3 w-32" />
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  icon,
  accent,
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`bg-[var(--surface)] border rounded-xl p-5 space-y-2 ${
        accent ? "border-[var(--accent)]/30" : "border-[var(--border)]"
      }`}
      data-testid={`stat-${label.toLowerCase().replace(/\s+/g, "-")}`}
    >
      <div className="flex items-center justify-between">
        <p className="text-[var(--muted)] text-xs uppercase tracking-widest">{label}</p>
        <span className="text-base opacity-60">{icon}</span>
      </div>
      <p className="text-3xl font-bold tabular-nums">{value}</p>
      {sub && <p className="text-[var(--muted)] text-xs">{sub}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.summary()
      .then(setSummary)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold" data-testid="page-heading">Dashboard</h1>
        <p className="text-[var(--muted)] mt-1 text-sm">
          Automated Medium post pipeline — LangChain · LangGraph · Claude
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {loading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : summary ? (
          <>
            <StatCard
              label="Pipeline Runs"
              value={summary.pipeline_runs}
              sub={`${summary.completed_runs} completed`}
              icon="◈"
            />
            <StatCard
              label="Posts Generated"
              value={summary.total_posts}
              sub={`${summary.published_posts} published`}
              icon="✎"
            />
            <StatCard
              label="Total API Cost"
              value={`$${summary.total_cost_usd.toFixed(4)}`}
              sub={`${summary.total_tokens.toLocaleString()} tokens`}
              icon="⊛"
              accent
            />
          </>
        ) : null}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Link
          href="/pipeline"
          data-testid="cta-run-pipeline"
          className="group bg-[var(--accent)] hover:opacity-90 transition-opacity text-white rounded-xl p-6 block"
        >
          <div className="flex items-center justify-between">
            <p className="font-bold text-lg">Run New Pipeline</p>
            <span className="text-xl group-hover:translate-x-1 transition-transform">→</span>
          </div>
          <p className="text-sm opacity-75 mt-2">
            Research trends → Generate → Analyze → Approve
          </p>
        </Link>

        <Link
          href="/posts"
          data-testid="cta-view-posts"
          className="group bg-[var(--surface)] border border-[var(--border)] hover:border-[var(--accent)]/50 hover:bg-[var(--surface-hover)] transition-colors rounded-xl p-6 block"
        >
          <div className="flex items-center justify-between">
            <p className="font-bold text-lg">View Posts</p>
            <span className="text-xl text-[var(--muted)] group-hover:text-[var(--accent)] group-hover:translate-x-1 transition-all">→</span>
          </div>
          <p className="text-[var(--muted)] text-sm mt-2">
            Browse drafts, quality scores, and approved posts
          </p>
        </Link>
      </div>
    </div>
  );
}
