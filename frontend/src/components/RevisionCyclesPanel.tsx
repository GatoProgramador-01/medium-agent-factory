"use client";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface RevisionSnapshot {
  run_id: string;
  iteration: number;
  score: number;
  read_ratio: number;
  word_count: number;
  medium_boost_eligible: boolean;
  passed: boolean;
  gate_failures: string[];
  issue_summary: { high: number; medium: number; low: number; total: number };
  strengths: string[];
  topic?: string;
}

interface RevisionCyclesPanelProps {
  snapshots: RevisionSnapshot[];
  loading: boolean;
}

// ─── Colour helpers ───────────────────────────────────────────────────────────

function scoreColor(score: number): string {
  if (score >= 0.9) return "text-green-400";
  if (score >= 0.85) return "text-yellow-400";
  return "text-red-400";
}

function wordCountColor(wc: number): string {
  if (wc >= 1700) return "text-green-400";
  if (wc >= 1300) return "text-yellow-400";
  return "text-red-400";
}

function sparkColor(score: number): string {
  if (score >= 0.9) return "bg-green-400";
  if (score >= 0.85) return "bg-yellow-400";
  return "bg-red-400";
}

// ─── Score sparkline (Tailwind divs only) ─────────────────────────────────────

function ScoreSparkline({ iterations }: { iterations: RevisionSnapshot[] }) {
  if (iterations.length === 0) return null;

  const sorted = [...iterations].sort((a, b) => a.iteration - b.iteration);
  const maxScore = 1.0;
  const minScore = 0.6;

  return (
    <div className="mt-4 pt-4" style={{ borderTop: "1px solid var(--border)" }}>
      <div
        className="text-xs font-medium mb-2"
        style={{ color: "var(--text-muted)", letterSpacing: "0.05em", textTransform: "uppercase" }}
      >
        Score progression · most recent run
      </div>
      <div className="flex items-end gap-1.5" style={{ height: "3rem" }}>
        {sorted.map((snap) => {
          const heightPct = Math.max(
            5,
            Math.round(((snap.score - minScore) / (maxScore - minScore)) * 100),
          );
          return (
            <div
              key={snap.iteration}
              className="flex flex-col items-center gap-1"
              title={`Iteration ${snap.iteration}: ${(snap.score * 100).toFixed(1)}%`}
            >
              <div
                className={`w-6 rounded-sm ${sparkColor(snap.score)}`}
                style={{ height: `${heightPct}%`, minHeight: "4px" }}
              />
              <span
                className="text-xs tabular-nums"
                style={{ color: "var(--text-dim)", fontSize: "10px" }}
              >
                i{snap.iteration}
              </span>
            </div>
          );
        })}
      </div>
      <div className="flex gap-4 mt-2">
        {sorted.map((snap) => (
          <span
            key={snap.iteration}
            className={`text-xs tabular-nums font-semibold ${scoreColor(snap.score)}`}
            style={{ fontSize: "10px", width: "1.5rem", textAlign: "center" }}
          >
            {(snap.score * 100).toFixed(0)}
          </span>
        ))}
      </div>
    </div>
  );
}

// ─── Skeleton ────────────────────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Revision Cycles</span>
      </div>
      <div className="panel-body space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex gap-4">
            <div className="skeleton h-3 w-32" />
            <div className="skeleton h-3 w-8" />
            <div className="skeleton h-3 w-12" />
            <div className="skeleton h-3 w-12" />
            <div className="skeleton h-3 w-8" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function RevisionCyclesPanel({ snapshots, loading }: RevisionCyclesPanelProps) {
  if (loading) return <LoadingSkeleton />;

  // Group snapshots by run_id, preserving insertion order of first encounter
  const grouped = new Map<string, RevisionSnapshot[]>();
  for (const snap of snapshots) {
    const bucket = grouped.get(snap.run_id) ?? [];
    bucket.push(snap);
    grouped.set(snap.run_id, bucket);
  }

  // Most recent run = last key in the map
  const runIds = Array.from(grouped.keys());
  const mostRecentRunId = runIds[runIds.length - 1] ?? null;
  const mostRecentIterations = mostRecentRunId ? (grouped.get(mostRecentRunId) ?? []) : [];

  return (
    <div className="panel" data-testid="revision-cycles-panel">
      <div className="panel-header">
        <span className="panel-title">Revision Cycles</span>
        {snapshots.length > 0 && (
          <span className="section-label">{runIds.length} runs · {snapshots.length} snapshots</span>
        )}
      </div>

      {snapshots.length === 0 ? (
        <div className="panel-body">
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            No revision snapshots yet — run a pipeline to start tracking quality cycles.
          </p>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="data-table" data-testid="revision-cycles-table">
              <thead>
                <tr>
                  {[
                    "Topic",
                    "Run ID",
                    "Iter",
                    "Score",
                    "Words",
                    "Read ratio",
                    "Passed",
                    "Boost",
                    "Gate failures",
                    "Issues",
                  ].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {snapshots.map((snap) => {
                  const truncatedFailures =
                    snap.gate_failures.length === 0
                      ? "—"
                      : snap.gate_failures.join(", ").length > 40
                        ? `${snap.gate_failures.join(", ").slice(0, 37)}…`
                        : snap.gate_failures.join(", ");

                  const issueSummary =
                    snap.issue_summary.total === 0
                      ? "—"
                      : `H:${snap.issue_summary.high} M:${snap.issue_summary.medium} L:${snap.issue_summary.low}`;

                  return (
                    <tr key={`${snap.run_id}-${snap.iteration}`}>
                      {/* Topic */}
                      <td
                        className="td-muted"
                        style={{
                          maxWidth: "8rem",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                        title={snap.topic ?? "—"}
                      >
                        {snap.topic ?? "—"}
                      </td>

                      {/* Run ID (truncated) */}
                      <td
                        className="td-muted"
                        style={{
                          fontFamily: "var(--mono)",
                          maxWidth: "6rem",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                        title={snap.run_id}
                      >
                        {snap.run_id.slice(0, 8)}…
                      </td>

                      {/* Iteration */}
                      <td className="td-mono text-center">
                        {snap.iteration === 0 ? (
                          <span style={{ color: "var(--text-muted)" }}>0</span>
                        ) : (
                          snap.iteration
                        )}
                      </td>

                      {/* Score — colour coded */}
                      <td className={`td-mono font-semibold ${scoreColor(snap.score)}`}>
                        {(snap.score * 100).toFixed(1)}%
                      </td>

                      {/* Word count — colour coded */}
                      <td className={`td-mono ${wordCountColor(snap.word_count)}`}>
                        {snap.word_count.toLocaleString()}
                      </td>

                      {/* Read ratio */}
                      <td className="td-mono">
                        {(snap.read_ratio * 100).toFixed(1)}%
                      </td>

                      {/* Passed */}
                      <td className="text-center">
                        {snap.passed ? (
                          <span className="text-green-400 font-bold">✓</span>
                        ) : (
                          <span className="text-red-400 font-bold">✗</span>
                        )}
                      </td>

                      {/* Boost eligible */}
                      <td className="text-center">
                        {snap.medium_boost_eligible ? (
                          <span className="text-green-400 font-bold">✓</span>
                        ) : (
                          <span className="text-red-400 font-bold">✗</span>
                        )}
                      </td>

                      {/* Gate failures */}
                      <td
                        className="text-xs"
                        style={{
                          color:
                            snap.gate_failures.length > 0
                              ? "var(--red, #f87171)"
                              : "var(--text-dim)",
                          maxWidth: "10rem",
                        }}
                        title={snap.gate_failures.join(", ")}
                      >
                        {truncatedFailures}
                      </td>

                      {/* Issue summary */}
                      <td
                        className="td-mono text-xs"
                        style={{
                          color:
                            snap.issue_summary.high > 0
                              ? "#f87171"
                              : snap.issue_summary.medium > 0
                                ? "#facc15"
                                : "var(--text-muted)",
                        }}
                      >
                        {issueSummary}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Sparkline for the most recent run */}
          {mostRecentIterations.length > 1 && (
            <div className="panel-body">
              <ScoreSparkline iterations={mostRecentIterations} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
