"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { api, type AgentUsage, type RunUsage, type CostComparison } from "@/lib/api";
import CostComparisonPanel from "@/components/CostComparisonPanel";

const AgentCharts = dynamic(() => import("@/components/AgentCharts"), { ssr: false });

function MetricCard({
  label,
  value,
  accent,
  testId,
}: {
  label: string;
  value: string | number;
  accent?: boolean;
  testId?: string;
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
    </div>
  );
}

export default function AnalyticsPage() {
  const [usage, setUsage]                       = useState<AgentUsage[]>([]);
  const [byRun, setByRun]                       = useState<RunUsage[]>([]);
  const [costComparison, setCostComparison]     = useState<CostComparison | null>(null);
  const [loading, setLoading]                   = useState(true);

  useEffect(() => {
    Promise.all([api.tokenUsage(), api.tokenUsageByRun(), api.costComparison()])
      .then(([u, r, c]) => {
        setUsage(u);
        setByRun(r);
        setCostComparison(c);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const totalCost  = usage.reduce((a, u) => a + u.total_cost_usd, 0);
  const totalCalls = usage.reduce((a, u) => a + u.call_count, 0);
  const totalIn    = usage.reduce((a, u) => a + u.total_tokens_in, 0);
  const totalOut   = usage.reduce((a, u) => a + u.total_tokens_out, 0);

  return (
    <div className="space-y-6">

      {/* ── Page heading ── */}
      <div>
        <span className="section-label">Overview</span>
        <h1
          className="text-3xl font-bold mt-1"
          data-testid="page-heading"
          style={{ color: "#fff", letterSpacing: "-0.025em" }}
        >
          Analytics
        </h1>
        <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
          LLM cost &amp; performance breakdown
        </p>
      </div>

      {/* ── Cost Comparison Panel ── */}
      <CostComparisonPanel data={costComparison} loading={loading} />

      {/* ── Summary stat grid ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="metric-card space-y-3">
              <div className="skeleton h-2 w-20" />
              <div className="skeleton h-8 w-14" />
            </div>
          ))
        ) : (
          <>
            <MetricCard
              label="Total cost (USD)"
              value={`$${totalCost.toFixed(4)}`}
              accent
              testId="stat-cost"
            />
            <MetricCard
              label="LLM calls"
              value={totalCalls}
              testId="stat-calls"
            />
            <MetricCard
              label="Tokens in"
              value={totalIn.toLocaleString()}
              testId="stat-tokens-in"
            />
            <MetricCard
              label="Tokens out"
              value={totalOut.toLocaleString()}
              testId="stat-tokens-out"
            />
          </>
        )}
      </div>

      {/* ── Charts ── */}
      {!loading && usage.length > 0 && <AgentCharts usage={usage} />}

      {/* ── Agent breakdown table ── */}
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Agent Breakdown</span>
          {!loading && (
            <span className="section-label">{usage.length} agents</span>
          )}
        </div>

        {loading ? (
          <div className="panel-body space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="flex gap-6">
                <div className="skeleton h-3 w-32" />
                <div className="skeleton h-3 w-12" />
                <div className="skeleton h-3 w-20" />
                <div className="skeleton h-3 w-20" />
              </div>
            ))}
          </div>
        ) : usage.length === 0 ? (
          <div className="panel-body">
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              No data — run a pipeline to see metrics.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  {["Agent", "Calls", "Tokens in", "Tokens out", "Avg ms", "Cost (USD)"].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {usage.map((u) => (
                  <tr key={u.agent_name}>
                    <td className="td-accent">{u.agent_name}</td>
                    <td className="td-mono">{u.call_count}</td>
                    <td className="td-mono">{u.total_tokens_in.toLocaleString()}</td>
                    <td className="td-mono">{u.total_tokens_out.toLocaleString()}</td>
                    <td className="td-mono">{u.avg_duration_ms}ms</td>
                    <td className="td-mono td-accent">${u.total_cost_usd.toFixed(6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Cost by run table ── */}
      <div className="panel" data-testid="by-run-table">
        <div className="panel-header">
          <span className="panel-title">Cost by Run</span>
          {!loading && (
            <span className="section-label">{byRun.length} runs</span>
          )}
        </div>

        {loading ? (
          <div className="panel-body space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex gap-6">
                <div className="skeleton h-3 w-32" />
                <div className="skeleton h-3 w-12" />
                <div className="skeleton h-3 w-20" />
              </div>
            ))}
          </div>
        ) : byRun.length === 0 ? (
          <div className="panel-body">
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              No data — run a pipeline to see per-run costs.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  {["Run ID", "Agent calls", "Tokens in", "Tokens out", "Cost (USD)"].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {byRun.map((r) => (
                  <tr
                    key={r.run_id}
                    data-testid={`by-run-row-${r.run_id}`}
                  >
                    <td
                      className="td-muted"
                      style={{ fontFamily: "var(--mono)", maxWidth: "10rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                    >
                      {r.run_id}
                    </td>
                    <td className="td-mono">{r.agent_calls}</td>
                    <td className="td-mono">{r.total_tokens_in.toLocaleString()}</td>
                    <td className="td-mono">{r.total_tokens_out.toLocaleString()}</td>
                    <td className="td-mono td-accent">${r.total_cost_usd.toFixed(6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
