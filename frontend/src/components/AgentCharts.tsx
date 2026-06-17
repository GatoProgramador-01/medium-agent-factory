"use client";

import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from "recharts";
import type { AgentUsage } from "@/lib/api";

const TOOLTIP_STYLE = {
  background: "#0d0a07",
  border: "1px solid #302821",
  borderRadius: 4,
  fontSize: 11,
  fontFamily: "var(--mono, monospace)",
};

const TICK_COLOR  = "#574940";   // --text-dim
const GRID_COLOR  = "#302821";   // --border
const LABEL_COLOR = "#ede0cf";   // --text

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
              <CartesianGrid strokeDasharray="2 2" stroke={GRID_COLOR} vertical={false} />
              <XAxis
                dataKey="agent_name"
                tick={{ fill: TICK_COLOR, fontSize: 10 }}
                angle={-30}
                textAnchor="end"
                axisLine={false}
                tickLine={false}
              />
              <YAxis tick={{ fill: TICK_COLOR, fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelStyle={{ color: LABEL_COLOR }}
                formatter={(v: number) => [`$${v.toFixed(6)}`, "cost"]}
              />
              <Bar dataKey="total_cost_usd" fill="#f97316" radius={[2, 2, 0, 0]} maxBarSize={40} />
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
              <CartesianGrid strokeDasharray="2 2" stroke={GRID_COLOR} vertical={false} />
              <XAxis
                dataKey="agent_name"
                tick={{ fill: TICK_COLOR, fontSize: 10 }}
                angle={-30}
                textAnchor="end"
                axisLine={false}
                tickLine={false}
              />
              <YAxis tick={{ fill: TICK_COLOR, fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelStyle={{ color: LABEL_COLOR }}
                formatter={(v: number) => [`${v}ms`, "avg_ms"]}
              />
              <Bar dataKey="avg_duration_ms" fill="#f59e0b" radius={[2, 2, 0, 0]} maxBarSize={40} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
