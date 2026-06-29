"use client";

import type { CostComparison } from "@/lib/api";

interface CostComparisonPanelProps {
  data: CostComparison | null;
  loading: boolean;
}

function fmtUSD(n: number) {
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
          <span className="panel-title">DeepSeek V3 · Cost Dashboard</span>
        </div>
        <div className="panel-body">
          <div className="space-y-3">
            <div className="skeleton h-12 w-48" />
            <div className="skeleton h-3 w-64" />
            <div className="skeleton h-4 w-full" style={{ maxWidth: "320px" }} />
          </div>
        </div>
      </div>
    );
  }

  if (!data || !data.has_deepseek_data) {
    return (
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">DeepSeek V3 · Cost Dashboard</span>
        </div>
        <div className="panel-body">
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            No DeepSeek runs yet — trigger the pipeline to start tracking costs.
          </p>
          <p
            className="text-xs mt-2"
            style={{
              color: "var(--text-dim)",
              borderTop: "1px solid var(--border)",
              paddingTop: "0.75rem",
              marginTop: "0.75rem",
            }}
          >
            Note: LangSmith shows $0 for DeepSeek runs — it does not include DeepSeek V3 in
            its pricing catalog. This dashboard reads directly from MongoDB and is the
            source of truth.
          </p>
        </div>
      </div>
    );
  }

  const savingsPct = Math.min(Math.max(data.savings_pct, 0), 100);
  const totalTokens = data.deepseek_tokens_in + data.deepseek_tokens_out;

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">DeepSeek V3 · Cost Dashboard</span>
        {savingsPct > 0 && (
          <span className="badge badge-green" style={{ fontSize: "11px" }}>
            {savingsPct.toFixed(1)}% cheaper than Sonnet
          </span>
        )}
      </div>
      <div className="panel-body space-y-5">

        {/* Hero cost number */}
        <div>
          <div
            className="provider-cost provider-deepseek"
            style={{ fontSize: "3rem" }}
          >
            {fmtUSD(data.deepseek_cost_usd)}
          </div>
          <div className="provider-meta mt-1">
            {fmtTokens(totalTokens)} tokens &middot; {data.deepseek_runs} agent calls &middot; DeepSeek V3
          </div>
        </div>

        {/* Savings bar */}
        {savingsPct > 0 && (
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="section-label">Savings vs Claude Sonnet rates</span>
              <span
                className="text-sm font-semibold tabular-nums"
                style={{ color: "var(--green)" }}
              >
                {fmtUSD(data.savings_usd)} saved
              </span>
            </div>
            <div className="savings-bar-track">
              <div className="savings-bar-fill" style={{ width: `${savingsPct}%` }} />
            </div>
            <p className="text-xs mt-1.5" style={{ color: "var(--text-muted)" }}>
              Equivalent cost at Sonnet $3/$15M rates would have been{" "}
              <span style={{ color: "var(--text)", fontWeight: 600 }}>
                {fmtUSD(data.equivalent_claude_cost_usd)}
              </span>
            </p>
          </div>
        )}

        {/* Breakdown row */}
        <div
          className="grid grid-cols-3 gap-3"
          style={{ borderTop: "1px solid var(--border)", paddingTop: "1rem" }}
        >
          <div>
            <div className="metric-card-label">Tokens in</div>
            <div className="text-sm font-semibold tabular-nums" style={{ color: "var(--text)" }}>
              {fmtTokens(data.deepseek_tokens_in)}
            </div>
          </div>
          <div>
            <div className="metric-card-label">Tokens out</div>
            <div className="text-sm font-semibold tabular-nums" style={{ color: "var(--text)" }}>
              {fmtTokens(data.deepseek_tokens_out)}
            </div>
          </div>
          <div>
            <div className="metric-card-label">Agent calls</div>
            <div className="text-sm font-semibold tabular-nums" style={{ color: "var(--text)" }}>
              {data.deepseek_runs}
            </div>
          </div>
        </div>

        {/* LangSmith note */}
        <p
          className="text-xs"
          style={{
            color: "var(--text-dim)",
            borderTop: "1px solid var(--border)",
            paddingTop: "0.75rem",
          }}
        >
          LangSmith shows $0 for DeepSeek runs — it lacks DeepSeek V3 pricing in its catalog.
          Costs above are calculated from token counts × DeepSeek V3 rates ($0.27/$1.10 per 1M)
          and stored directly in MongoDB. This is the source of truth.
          {data.has_claude_data && (
            <> &nbsp;&middot;&nbsp; Claude historical spend: {fmtUSD(data.claude_cost_usd)}</>
          )}
        </p>
      </div>
    </div>
  );
}
