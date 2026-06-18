import type { QualityHistoryEntry } from "@/lib/api";

export function RevisionHistoryPanel({ history }: { history: QualityHistoryEntry[] | undefined }) {
  if (!history || history.length < 2) return null;

  return (
    <aside
      className="card p-5 space-y-3 text-sm"
      style={{
        minWidth: 220,
        maxWidth: 260,
        background: "linear-gradient(170deg, #0e091a 0%, #090612 100%)",
        border: "1px solid rgba(139,92,246,0.2)",
      }}
    >
      <div
        className="text-xs font-medium"
        data-testid="revision-history-heading"
        style={{ color: "#a78bfa" }}
      >
        {history.length} Revision Cycle{history.length !== 1 ? "s" : ""}
      </div>

      <ul className="space-y-3 list-none p-0 m-0">
        {history.map((entry, i) => {
          const pct = Math.round(entry.score * 100);
          const color =
            pct >= 90 ? "var(--green)" : pct >= 75 ? "var(--amber)" : "var(--red)";
          return (
            <li key={i} data-testid={`cycle-item-${entry.cycle}`} className="space-y-1">
              <div className="flex items-center gap-2">
                <span
                  className="text-xs font-mono shrink-0"
                  style={{ color: "var(--text-dim)", minWidth: "1.5rem" }}
                >
                  #{entry.cycle}
                </span>
                <div className="flex-1 score-bar-track">
                  <div
                    className="score-bar-fill"
                    style={{ width: `${pct}%`, background: color }}
                  />
                </div>
                <span
                  className="text-xs tabular-nums font-semibold shrink-0"
                  style={{ color, minWidth: "2rem", textAlign: "right" }}
                >
                  {pct}
                </span>
                <span
                  className="badge shrink-0"
                  style={{
                    background: entry.passed
                      ? "rgba(16,185,129,0.15)"
                      : "rgba(239,68,68,0.15)",
                    color: entry.passed ? "var(--green)" : "var(--red)",
                    fontSize: "10px",
                    padding: "1px 5px",
                  }}
                >
                  {entry.passed ? "PASS" : "FAIL"}
                </span>
              </div>
              {!entry.passed && entry.gate_failures.length > 0 && (
                <p
                  className="text-xs leading-snug pl-6"
                  style={{ color: "var(--text-dim)" }}
                >
                  {entry.gate_failures[0]}
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
