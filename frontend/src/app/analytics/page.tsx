"use client";

import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { api, type AgentUsage } from "@/lib/api";

export default function AnalyticsPage() {
  const [usage, setUsage] = useState<AgentUsage[]>([]);
  const [byRun, setByRun] = useState<AgentUsage[]>([]);

  useEffect(() => {
    api.tokenUsage().then(setUsage).catch(console.error);
    api.tokenUsageByRun().then(setByRun).catch(console.error);
  }, []);

  const totalCost = usage.reduce((acc, u) => acc + u.total_cost_usd, 0);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Analytics</h1>
        <p className="text-[var(--muted)] text-sm mt-1">
          Token usage, cost, and latency per agent.
        </p>
      </div>

      <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-6">
        <p className="text-xs text-[var(--muted)] uppercase tracking-widest mb-4">
          Cost per Agent (USD) — Total: ${totalCost.toFixed(4)}
        </p>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={usage} margin={{ top: 0, right: 0, left: 0, bottom: 60 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a32" />
            <XAxis
              dataKey="agent_name"
              tick={{ fill: "#6b6b7e", fontSize: 11 }}
              angle={-35}
              textAnchor="end"
            />
            <YAxis tick={{ fill: "#6b6b7e", fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: "#1a1a1f", border: "1px solid #2a2a32", borderRadius: 8 }}
              labelStyle={{ color: "#e8e8f0" }}
              formatter={(v: number) => [`$${v.toFixed(6)}`, "Cost USD"]}
            />
            <Bar dataKey="total_cost_usd" fill="#7c6af7" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-6">
        <p className="text-xs text-[var(--muted)] uppercase tracking-widest mb-4">
          Avg Latency per Agent (ms)
        </p>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={usage} margin={{ top: 0, right: 0, left: 0, bottom: 60 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a32" />
            <XAxis
              dataKey="agent_name"
              tick={{ fill: "#6b6b7e", fontSize: 11 }}
              angle={-35}
              textAnchor="end"
            />
            <YAxis tick={{ fill: "#6b6b7e", fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: "#1a1a1f", border: "1px solid #2a2a32", borderRadius: 8 }}
              labelStyle={{ color: "#e8e8f0" }}
              formatter={(v: number) => [`${v}ms`, "Avg Duration"]}
            />
            <Bar dataKey="avg_duration_ms" fill="#22c55e" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="border-b border-[var(--border)]">
            <tr className="text-xs text-[var(--muted)] uppercase tracking-widest">
              {["Agent", "Calls", "Tokens In", "Tokens Out", "Avg ms", "Cost USD"].map((h) => (
                <th key={h} className="px-4 py-3 text-left font-normal">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {usage.map((u) => (
              <tr key={u.agent_name} className="border-b border-[var(--border)] last:border-0">
                <td className="px-4 py-3 font-mono text-xs">{u.agent_name}</td>
                <td className="px-4 py-3">{u.call_count}</td>
                <td className="px-4 py-3">{u.total_tokens_in.toLocaleString()}</td>
                <td className="px-4 py-3">{u.total_tokens_out.toLocaleString()}</td>
                <td className="px-4 py-3">{u.avg_duration_ms}ms</td>
                <td className="px-4 py-3 text-[var(--accent)]">${u.total_cost_usd.toFixed(6)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
