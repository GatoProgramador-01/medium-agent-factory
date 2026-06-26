"use client";

import type { CostComparison } from "@/lib/api";

interface CostComparisonPanelProps {
  data: CostComparison | null;
  loading: boolean;
}

function fmt(n: number) {
  return `$${n.toFixed(6)}`;
}

function fmtTokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

export default function CostComparisonPanel({ data, loading }: CostComparisonPanelProps) {
  if (loading) {
    return (
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Cost Comparison &middot; Claude vs DeepSeek</span>
        </div>
        <div className="panel-body">
          <div className="flex gap-4 flex-col sm:flex-row">
            <div className="provider-card provider-card-claude flex-1 space-y-3">
              <div className="skeleton h-3 w-28" />
              <div className="skeleton h-10 w-36" />
              <div className="skeleton h-3 w-40" />
            </div>
            <div className="provider-card provider-card-deepseek flex-1 space-y-3">
              <div className="skeleton h-3 w-28" />
              <div className="skeleton h-10 w-36" />
              <div className="skeleton h-3 w-40" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!data || (!data.has_claude_data && !data.has_deepseek_data)) {
    return (
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Cost Comparison &middot; Claude vs DeepSeek</span>
        </div>
        <div className="panel-body">
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            Run the pipeline to see cost comparison.
          </p>
        </div>
      </div>
    );
  }

  const savingsPct = Math.min(Math.max(data.savings_pct, 0), 100);

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Cost Comparison &middot; Claude vs DeepSeek</span>
        {data.has_deepseek_data && (
          <span
            className="badge badge-green"
            style={{ fontSize: "11px" }}
          >
            {savingsPct.toFixed(1)}% cheaper with DeepSeek
          </span>
        )}
      </div>
      <div className="panel-body space-y-4">

        {/* Provider cards */}
        <div className="flex gap-4 flex-col sm:flex-row">
          {/* Claude card */}
          <div className="provider-card provider-card-claude">
            <div className="provider-name provider-claude">Claude (historical)</div>
            <div
              className="provider-cost provider-claude"
              style={{ opacity: data.has_claude_data ? 1 : 0.35 }}
            >
              {data.has_claude_data ? fmt(data.claude_cost_usd) : "$—"}
            </div>
            <div className="provider-meta">
              {data.has_claude_data
                ? `${fmtTokens(data.claude_tokens_in + data.claude_tokens_out)} tokens · ${data.claude_runs} calls`
                : "No Claude data yet"}
            </div>
          </div>

          {/* DeepSeek card */}
          <div className="provider-card provider-card-deepseek">
            <div className="provider-name provider-deepseek">DeepSeek V3 (current)</div>
            <div
              className="provider-cost provider-deepseek"
              style={{ opacity: data.has_deepseek_data ? 1 : 0.35 }}
            >
              {data.has_deepseek_data ? fmt(data.deepseek_cost_usd) : "$—"}
            </div>
            <div className="provider-meta">
              {data.has_deepseek_data
                ? `${fmtTokens(data.deepseek_tokens_in + data.deepseek_tokens_out)} tokens · ${data.deepseek_runs} calls`
                : "No DeepSeek data yet"}
            </div>
          </div>
        </div>

        {/* Savings section */}
        {data.has_deepseek_data && (
          <div
            style={{
              borderTop: "1px solid var(--border)",
              paddingTop: "1rem",
            }}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="section-label">Savings vs Sonnet rates</span>
              <span
                className="text-sm font-semibold tabular-nums"
                style={{ color: "var(--green)" }}
              >
                {fmt(data.savings_usd)} saved
              </span>
            </div>

            <div className="savings-bar-track">
              <div
                className="savings-bar-fill"
                style={{ width: `${savingsPct}%` }}
              />
            </div>

            <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
              You saved{" "}
              <span style={{ color: "var(--green)", fontWeight: 600 }}>
                {fmt(data.savings_usd)}
              </span>{" "}
              vs running the same tokens at Sonnet rates (equivalent cost:{" "}
              {fmt(data.equivalent_claude_cost_usd)})
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
