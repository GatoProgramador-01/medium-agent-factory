"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { api, type AgentUsage } from "@/lib/api";

const AgentCharts = dynamic(() => import("@/components/AgentCharts"), { ssr: false });

export default function AnalyticsPage() {
  const [usage, setUsage]   = useState<AgentUsage[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.tokenUsage().then(setUsage).catch(console.error).finally(() => setLoading(false));
  }, []);

  const totalCost  = usage.reduce((a, u) => a + u.total_cost_usd, 0);
  const totalCalls = usage.reduce((a, u) => a + u.call_count, 0);
  const totalIn    = usage.reduce((a, u) => a + u.total_tokens_in, 0);
  const totalOut   = usage.reduce((a, u) => a + u.total_tokens_out, 0);

  return (
    <div className="space-y-5">
      <div>
        <p className="text-[var(--text-muted)] text-xs mb-1">user@factory:~/factory$</p>
        <h1 className="text-[var(--orange)] text-xl font-bold" data-testid="page-heading">Analytics</h1>
        <p className="text-[var(--text-muted)] text-xs mt-1">top -n 1 --agents --sort=cost</p>
      </div>

      {/* Summary row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {loading ? (
          Array.from({length: 4}).map((_, i) => (
            <div key={i} className="term-box p-3 space-y-2">
              <div className="skeleton h-2 w-20" />
              <div className="skeleton h-5 w-12" />
            </div>
          ))
        ) : (
          <>
            <StatBox label="total_cost_usd" value={`$${totalCost.toFixed(4)}`} accent testId="stat-cost" />
            <StatBox label="llm_calls" value={totalCalls} testId="stat-calls" />
            <StatBox label="tokens_in" value={totalIn.toLocaleString()} testId="stat-tokens-in" />
            <StatBox label="tokens_out" value={totalOut.toLocaleString()} testId="stat-tokens-out" />
          </>
        )}
      </div>

      {/* Charts */}
      {!loading && usage.length > 0 && <AgentCharts usage={usage} />}

      {/* Table */}
      <div className="term-box overflow-hidden">
        <div className="term-box-header">
          <span>agent breakdown</span>
          {!loading && <span className="ml-auto text-[var(--orange)]">{usage.length} agents</span>}
        </div>

        {loading ? (
          <div className="p-4 space-y-2">
            {[1,2,3,4].map((i) => (
              <div key={i} className="flex gap-6">
                <div className="skeleton h-3 w-32" />
                <div className="skeleton h-3 w-12" />
                <div className="skeleton h-3 w-20" />
                <div className="skeleton h-3 w-20" />
              </div>
            ))}
          </div>
        ) : usage.length === 0 ? (
          <p className="p-4 text-xs text-[var(--text-muted)]">no data — run a pipeline to see metrics</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[var(--border)] text-[var(--text-muted)]">
                  {["agent", "calls", "tok_in", "tok_out", "avg_ms", "cost_usd"].map((h) => (
                    <th key={h} className="px-4 py-2 text-left font-normal tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {usage.map((u) => (
                  <tr key={u.agent_name} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--surface-hover)] transition-colors">
                    <td className="px-4 py-2 text-[var(--orange)]">{u.agent_name}</td>
                    <td className="px-4 py-2 tabular-nums">{u.call_count}</td>
                    <td className="px-4 py-2 tabular-nums">{u.total_tokens_in.toLocaleString()}</td>
                    <td className="px-4 py-2 tabular-nums">{u.total_tokens_out.toLocaleString()}</td>
                    <td className="px-4 py-2 tabular-nums">{u.avg_duration_ms}ms</td>
                    <td className="px-4 py-2 tabular-nums text-[var(--orange)]">${u.total_cost_usd.toFixed(6)}</td>
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

function StatBox({ label, value, accent, testId }: { label: string; value: string | number; accent?: boolean; testId?: string }) {
  return (
    <div className="term-box p-3 space-y-1" data-testid={testId}>
      <p className="text-[10px] text-[var(--text-muted)] tracking-wider">{label}</p>
      <p className={`text-lg font-bold tabular-nums ${accent ? "text-[var(--orange)]" : "text-[var(--text)]"}`}>
        {value}
      </p>
    </div>
  );
}
