"use client";

import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from "recharts";
import type { AgentUsage } from "@/lib/api";

const TOOLTIP_STYLE = {
  background: "#111111",
  border: "1px solid #1f1f1f",
  borderRadius: 0,
  fontSize: 11,
  fontFamily: "inherit",
};

export default function AgentCharts({ usage }: { usage: AgentUsage[] }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div className="term-box">
        <div className="term-box-header">
          <span>cost_usd per agent</span>
        </div>
        <div className="p-4">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={usage} margin={{ top: 4, right: 4, left: -20, bottom: 50 }}>
              <CartesianGrid strokeDasharray="2 2" stroke="#1f1f1f" vertical={false} />
              <XAxis dataKey="agent_name" tick={{ fill: "#4a5a4a", fontSize: 10 }} angle={-30} textAnchor="end" axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#4a5a4a", fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: "#d4f0d4" }} formatter={(v: number) => [`$${v.toFixed(6)}`, "cost"]} />
              <Bar dataKey="total_cost_usd" fill="#4ade80" radius={[2, 2, 0, 0]} maxBarSize={40} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="term-box">
        <div className="term-box-header">
          <span>avg_latency_ms per agent</span>
        </div>
        <div className="p-4">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={usage} margin={{ top: 4, right: 4, left: -20, bottom: 50 }}>
              <CartesianGrid strokeDasharray="2 2" stroke="#1f1f1f" vertical={false} />
              <XAxis dataKey="agent_name" tick={{ fill: "#4a5a4a", fontSize: 10 }} angle={-30} textAnchor="end" axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#4a5a4a", fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: "#d4f0d4" }} formatter={(v: number) => [`${v}ms`, "avg_ms"]} />
              <Bar dataKey="avg_duration_ms" fill="#60a5fa" radius={[2, 2, 0, 0]} maxBarSize={40} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
