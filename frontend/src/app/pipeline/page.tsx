"use client";

import { useEffect, useRef, useState } from "react";
import { api, type AgentLog } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

type RunResult = {
  run_id: string;
  status: string;
  title?: string;
  quality_score?: number;
  read_ratio_prediction?: number;
  revision_count?: number;
  medium_url?: string;
  errors?: string[];
  steps?: string[];
};

// ── Step icon + colour ────────────────────────────────────────────────────────

const STEP_ICON: Record<string, string> = {
  orchestrator:       "◈",
  trend_researcher:   "⌖",
  content_generator:  "✎",
  quality_analyzer:   "⊛",
  publisher:          "⇪",
};

const LEVEL_COLOR: Record<string, string> = {
  info:    "text-[var(--muted)]",
  success: "text-[var(--green)]",
  warning: "text-[var(--yellow)]",
  error:   "text-[var(--red)]",
};

const LEVEL_DOT: Record<string, string> = {
  info:    "bg-[var(--muted)]",
  success: "bg-[var(--green)]",
  warning: "bg-[var(--yellow)]",
  error:   "bg-[var(--red)]",
};

// ── LogLine ───────────────────────────────────────────────────────────────────

function LogLine({ log, index }: { log: AgentLog; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const hasData = log.data && Object.keys(log.data).length > 0;
  const icon = STEP_ICON[log.step] ?? "·";
  const time = new Date(log.timestamp).toLocaleTimeString([], {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });

  return (
    <div
      className="group flex gap-3 py-1.5 border-b border-[var(--border)]/40 last:border-0 animate-in fade-in slide-in-from-bottom-1 duration-200"
      style={{ animationDelay: `${Math.min(index * 30, 300)}ms` }}
    >
      {/* dot */}
      <div className="mt-1.5 flex-shrink-0">
        <span className={`inline-block w-1.5 h-1.5 rounded-full ${LEVEL_DOT[log.level] ?? "bg-[var(--muted)]"}`} />
      </div>

      {/* content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="text-[var(--accent)] font-mono text-[11px] select-none">
            {icon} {log.step}
          </span>
          <span className={`text-sm ${LEVEL_COLOR[log.level] ?? "text-[var(--muted)]"}`}>
            {log.message}
          </span>
          {hasData && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-[10px] text-[var(--muted)] hover:text-[var(--accent)] ml-auto flex-shrink-0"
            >
              {expanded ? "hide" : "details ›"}
            </button>
          )}
        </div>

        {expanded && hasData && (
          <pre className="mt-1.5 text-[11px] text-[var(--muted)] bg-[var(--bg)] rounded p-2 overflow-auto">
            {JSON.stringify(log.data, null, 2)}
          </pre>
        )}
      </div>

      {/* timestamp */}
      <span className="text-[10px] text-[var(--muted)]/50 flex-shrink-0 mt-0.5 font-mono">
        {time}
      </span>
    </div>
  );
}

// ── ResultCard ────────────────────────────────────────────────────────────────

function ResultCard({ result }: { result: RunResult }) {
  const score = result.quality_score ?? 0;
  const ratio = result.read_ratio_prediction ?? 0;
  const scorePct = Math.round(score * 100);
  const ratioPct = Math.round(ratio * 100);

  const scoreColor =
    scorePct >= 75 ? "text-[var(--green)]" : scorePct >= 50 ? "text-[var(--yellow)]" : "text-[var(--red)]";

  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <p className="font-semibold truncate pr-4">{result.title ?? "Untitled"}</p>
        <span
          className={`text-xs px-2.5 py-1 rounded-full flex-shrink-0 ${
            result.status === "completed"
              ? "bg-green-950/50 text-[var(--green)]"
              : "bg-red-950/50 text-[var(--red)]"
          }`}
        >
          {result.status}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        <div className="bg-[var(--bg)] rounded-lg p-3">
          <p className={`text-2xl font-bold ${scoreColor}`}>{scorePct}</p>
          <p className="text-[var(--muted)] text-xs mt-0.5">Quality /100</p>
        </div>
        <div className="bg-[var(--bg)] rounded-lg p-3">
          <p className="text-2xl font-bold text-[var(--accent)]">{ratioPct}%</p>
          <p className="text-[var(--muted)] text-xs mt-0.5">Predicted Read Ratio</p>
          <p className="text-[10px] text-[var(--muted)]/60 mt-0.5">was 12%</p>
        </div>
        <div className="bg-[var(--bg)] rounded-lg p-3">
          <p className="text-2xl font-bold">{result.revision_count ?? 0}</p>
          <p className="text-[var(--muted)] text-xs mt-0.5">Revisions</p>
        </div>
      </div>

      {result.steps && result.steps.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {result.steps.map((s) => (
            <span key={s} className="text-[11px] bg-[var(--bg)] border border-[var(--border)] rounded px-2 py-0.5">
              {s}
            </span>
          ))}
        </div>
      )}

      {result.medium_url && (
        <a
          href={result.medium_url}
          target="_blank"
          rel="noopener noreferrer"
          className="block text-[var(--accent)] text-sm underline"
        >
          View on Medium →
        </a>
      )}

      {result.errors && result.errors.length > 0 && (
        <div className="space-y-1">
          {result.errors.map((e, i) => (
            <p key={i} className="text-sm text-[var(--red)]">{e}</p>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

type RunPhase = "idle" | "running" | "done";

export default function PipelinePage() {
  const [topic, setTopic] = useState("");
  const [publishLive, setPublishLive] = useState(false);
  const [phase, setPhase] = useState<RunPhase>("idle");
  const [runId, setRunId] = useState<string | null>(null);
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Auto-scroll log terminal
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Poll logs while running
  useEffect(() => {
    if (phase !== "running" || !runId) return;

    const poll = async () => {
      try {
        const newLogs = await api.getLogs(runId);
        setLogs(newLogs);

        // Check if pipeline is done
        const run = await api.getRun(runId);
        if (run.status === "completed" || run.status === "failed") {
          clearInterval(pollRef.current!);
          pollRef.current = null;
          setPhase("done");
        }
      } catch {
        // ignore transient fetch errors
      }
    };

    poll();
    pollRef.current = setInterval(poll, 2000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [phase, runId]);

  async function handleRun() {
    setPhase("running");
    setLogs([]);
    setResult(null);
    setError(null);

    try {
      // Use sync endpoint so we get the full result back when done
      const res = await api.triggerPipeline(topic.trim() || null, publishLive) as unknown as RunResult & { run_id: string };
      setRunId(res.run_id);

      // If triggerPipeline returns immediately (async endpoint), we'll poll.
      // If it returns a full result (sync), set result directly.
      if (res.status && res.status !== "queued") {
        const finalLogs = await api.getLogs(res.run_id);
        setLogs(finalLogs);
        setResult(res);
        setPhase("done");
      }
    } catch (e) {
      setError(String(e));
      setPhase("idle");
    }
  }

  // Trigger using async endpoint for background run + live logs
  async function handleRunAsync() {
    setPhase("running");
    setLogs([]);
    setResult(null);
    setError(null);

    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/pipeline/run`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ custom_topic: topic.trim() || null, publish_live: publishLive }),
        }
      );
      const { run_id } = await res.json();
      setRunId(run_id);
    } catch (e) {
      setError(String(e));
      setPhase("idle");
    }
  }

  // When phase becomes "done", fetch final result
  useEffect(() => {
    if (phase !== "done" || !runId) return;
    api.getRun(runId).then((run) => {
      if ((run as any).title) setResult(run as unknown as RunResult);
    }).catch(() => {});
  }, [phase, runId]);

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold">Run Pipeline</h1>
        <p className="text-[var(--muted)] text-sm mt-1">
          Cost strategy: Haiku → Haiku revision → Sonnet (last resort only)
        </p>
      </div>

      {/* Controls */}
      <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5 space-y-4">
        <div>
          <label className="text-xs text-[var(--muted)] block mb-1.5 uppercase tracking-widest">
            Custom Topic (optional)
          </label>
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            disabled={phase === "running"}
            placeholder="e.g. How to make $500/month on Ko-fi in 2025"
            className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-[var(--accent)] disabled:opacity-40"
          />
          <p className="text-[10px] text-[var(--muted)] mt-1">
            Leave blank → Trend Research Agent picks the best opportunity automatically
          </p>
        </div>

        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={publishLive}
            onChange={(e) => setPublishLive(e.target.checked)}
            disabled={phase === "running"}
            className="accent-[var(--accent)]"
          />
          <span className="text-sm">Publish live to Medium after pipeline</span>
        </label>

        <button
          onClick={handleRunAsync}
          disabled={phase === "running"}
          className="w-full bg-[var(--accent)] text-white rounded-lg py-2.5 font-medium disabled:opacity-50 hover:opacity-90 transition-opacity flex items-center justify-center gap-2"
        >
          {phase === "running" ? (
            <>
              <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Pipeline running…
            </>
          ) : (
            "Run Pipeline"
          )}
        </button>
      </div>

      {/* Live log terminal */}
      {(logs.length > 0 || phase === "running") && (
        <div className="bg-[#0a0a0d] border border-[var(--border)] rounded-xl overflow-hidden">
          {/* terminal header */}
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[var(--border)] bg-[var(--surface)]">
            <span className="w-2.5 h-2.5 rounded-full bg-[var(--red)]" />
            <span className="w-2.5 h-2.5 rounded-full bg-[var(--yellow)]" />
            <span className="w-2.5 h-2.5 rounded-full bg-[var(--green)]" />
            <span className="ml-2 text-xs text-[var(--muted)] font-mono">
              agent-logs {runId ? `· ${runId.slice(0, 8)}…` : ""}
            </span>
            {phase === "running" && (
              <span className="ml-auto flex items-center gap-1.5 text-xs text-[var(--yellow)]">
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--yellow)] animate-pulse" />
                live
              </span>
            )}
            {phase === "done" && (
              <span className="ml-auto text-xs text-[var(--green)]">done</span>
            )}
          </div>

          {/* log entries */}
          <div className="p-4 max-h-[480px] overflow-y-auto font-mono space-y-0">
            {logs.length === 0 && phase === "running" && (
              <p className="text-xs text-[var(--muted)] animate-pulse">Waiting for first log entry…</p>
            )}
            {logs.map((log, i) => (
              <LogLine key={`${log.timestamp}-${i}`} log={log} index={i} />
            ))}
            <div ref={logEndRef} />
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-950/30 border border-[var(--red)] rounded-xl p-4 text-sm text-[var(--red)]">
          {error}
        </div>
      )}

      {/* Result */}
      {phase === "done" && result && <ResultCard result={result} />}
    </div>
  );
}
