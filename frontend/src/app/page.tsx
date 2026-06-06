"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Summary } from "@/lib/api";

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
      <p className="text-[var(--muted)] text-xs uppercase tracking-widest mb-1">{label}</p>
      <p className="text-3xl font-bold">{value}</p>
      {sub && <p className="text-[var(--muted)] text-sm mt-1">{sub}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    api.summary().then(setSummary).catch(console.error);
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-[var(--muted)] mt-1 text-sm">
          Automated Medium post pipeline — LangChain · LangGraph · Claude
        </p>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <StatCard label="Pipeline Runs" value={summary.pipeline_runs} sub={`${summary.completed_runs} completed`} />
          <StatCard label="Posts Generated" value={summary.total_posts} sub={`${summary.published_posts} published`} />
          <StatCard label="Total API Cost" value={`$${summary.total_cost_usd.toFixed(4)}`} sub={`${summary.total_tokens.toLocaleString()} tokens`} />
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Link
          href="/pipeline"
          className="bg-[var(--accent)] hover:opacity-90 transition-opacity text-white rounded-xl p-6 block"
        >
          <p className="font-bold text-lg">Run New Pipeline</p>
          <p className="text-sm opacity-80 mt-1">Research trends → Generate → Analyze → Publish</p>
        </Link>
        <Link
          href="/posts"
          className="bg-[var(--surface)] border border-[var(--border)] hover:border-[var(--accent)] transition-colors rounded-xl p-6 block"
        >
          <p className="font-bold text-lg">View Posts</p>
          <p className="text-[var(--muted)] text-sm mt-1">Browse drafts, quality scores, and published posts</p>
        </Link>
      </div>
    </div>
  );
}
