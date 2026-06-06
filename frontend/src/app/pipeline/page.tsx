"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, type AgentLog, type Post } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

type RunPhase = "idle" | "running" | "done";

// ── Step icon + colour ────────────────────────────────────────────────────────

const STEP_ICON: Record<string, string> = {
  orchestrator:      "◈",
  trend_researcher:  "⌖",
  content_generator: "✎",
  quality_analyzer:  "⊛",
  publisher:         "⇪",
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
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <div
      className="group flex gap-3 py-1.5 border-b border-[var(--border)]/40 last:border-0 animate-in fade-in slide-in-from-bottom-1 duration-200"
      style={{ animationDelay: `${Math.min(index * 20, 200)}ms` }}
    >
      <div className="mt-1.5 shrink-0">
        <span className={`inline-block w-1.5 h-1.5 rounded-full ${LEVEL_DOT[log.level] ?? "bg-[var(--muted)]"}`} />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="text-[var(--accent)] font-mono text-[11px] select-none shrink-0">
            {icon} {log.step}
          </span>
          <span className={`text-sm ${LEVEL_COLOR[log.level] ?? "text-[var(--muted)]"}`}>
            {log.message}
          </span>
          {hasData && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-[10px] text-[var(--muted)] hover:text-[var(--accent)] ml-auto shrink-0 transition-colors"
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

      <span className="text-[10px] text-[var(--muted)]/50 shrink-0 mt-0.5 font-mono">{time}</span>
    </div>
  );
}

// ── ResultCard ────────────────────────────────────────────────────────────────

function ResultCard({ post, runId }: { post: Post; runId: string }) {
  const score = post.quality_report?.score ?? 0;
  const ratio = post.quality_report?.read_ratio_prediction ?? 0;
  const scorePct = Math.round(score * 100);
  const ratioPct = Math.round(ratio * 100);

  const scoreColor =
    scorePct >= 75 ? "text-[var(--green)]" : scorePct >= 50 ? "text-[var(--yellow)]" : "text-[var(--red)]";

  return (
    <div
      className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5 space-y-4"
      data-testid="result-card"
    >
      <div className="flex items-start justify-between gap-4">
        <p className="font-semibold leading-snug pr-4">{post.title}</p>
        <span className="text-xs px-2.5 py-1 rounded-full shrink-0 bg-green-950/50 text-[var(--green)]">
          completed
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        <div className="bg-[var(--bg)] rounded-lg p-3">
          <p className={`text-2xl font-bold tabular-nums ${scoreColor}`}>{scorePct}</p>
          <p className="text-[var(--muted)] text-xs mt-0.5">Quality /100</p>
        </div>
        <div className="bg-[var(--bg)] rounded-lg p-3">
          <p className="text-2xl font-bold tabular-nums text-[var(--accent)]">{ratioPct}%</p>
          <p className="text-[var(--muted)] text-xs mt-0.5">Predicted Read Ratio</p>
          <p className="text-[10px] text-[var(--muted)]/60 mt-0.5">baseline 12%</p>
        </div>
        <div className="bg-[var(--bg)] rounded-lg p-3">
          <p className="text-2xl font-bold tabular-nums">{post.revision_count}</p>
          <p className="text-[var(--muted)] text-xs mt-0.5">Revisions</p>
        </div>
      </div>

      {post.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {post.tags.map((t) => (
            <span key={t} className="text-[11px] bg-[var(--bg)] border border-[var(--border)] rounded px-2 py-0.5">
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center gap-3 pt-1">
        <Link
          href={`/posts`}
          className="text-sm text-[var(--accent)] hover:underline"
          data-testid="view-post-link"
        >
          View post →
        </Link>
        {post.medium_url && (
          <a
            href={post.medium_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-[var(--muted)] hover:text-[var(--text)] underline transition-colors"
          >
            Open on Medium ↗
          </a>
        )}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PipelinePage() {
  const [topic, setTopic] = useState("");
  const [publishLive, setPublishLive] = useState(false);
  const [phase, setPhase] = useState<RunPhase>("idle");
  const [runId, setRunId] = useState<string | null>(null);
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [post, setPost] = useState<Post | null>(null);
  const [error, setError] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Auto-scroll log terminal
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Poll logs + status while running
  useEffect(() => {
    if (phase !== "running" || !runId) return;

    const poll = async () => {
      try {
        const [newLogs, run] = await Promise.all([
          api.getLogs(runId),
          api.getRun(runId),
        ]);
        setLogs(newLogs);
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

  // Fetch post result when done
  useEffect(() => {
    if (phase !== "done" || !runId) return;
    api.getPost(runId).then(setPost).catch(() => {});
  }, [phase, runId]);

  async function handleRun() {
    setPhase("running");
    setLogs([]);
    setPost(null);
    setError(null);

    try {
      const { run_id } = await api.triggerPipeline(topic.trim() || null, publishLive);
      setRunId(run_id);
    } catch (e) {
      setError(String(e));
      setPhase("idle");
    }
  }

  function handleReset() {
    setPhase("idle");
    setLogs([]);
    setPost(null);
    setError(null);
    setRunId(null);
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold" data-testid="page-heading">Run Pipeline</h1>
        <p className="text-[var(--muted)] text-sm mt-1">
          Cost strategy: Haiku → Haiku revision → Sonnet (last resort only)
        </p>
      </div>

      {/* Controls */}
      <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5 space-y-4">
        <div>
          <label className="text-xs text-[var(--muted)] block mb-1.5 uppercase tracking-widest">
            Custom Topic <span className="normal-case">(optional)</span>
          </label>
          <input
            data-testid="topic-input"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            disabled={phase === "running"}
            placeholder="e.g. How to make $500/month on Ko-fi in 2025"
            className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-[var(--accent)] disabled:opacity-40 transition-colors"
          />
          <p className="text-[10px] text-[var(--muted)] mt-1.5">
            Leave blank → Trend Research Agent picks the best opportunity automatically
          </p>
        </div>

        <label className="flex items-center gap-3 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={publishLive}
            onChange={(e) => setPublishLive(e.target.checked)}
            disabled={phase === "running"}
            className="accent-[var(--accent)]"
          />
          <span className="text-sm">Publish live to Medium after pipeline</span>
        </label>

        {phase === "done" ? (
          <button
            data-testid="run-again-button"
            onClick={handleReset}
            className="w-full border border-[var(--border)] hover:border-[var(--accent)] text-[var(--muted)] hover:text-[var(--text)] rounded-lg py-2.5 font-medium transition-colors text-sm"
          >
            Run Again
          </button>
        ) : (
          <button
            data-testid="run-button"
            onClick={handleRun}
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
        )}
      </div>

      {/* Live log terminal */}
      {(logs.length > 0 || phase === "running") && (
        <div
          className="bg-[#0a0a0d] border border-[var(--border)] rounded-xl overflow-hidden"
          data-testid="log-terminal"
        >
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
              <span className="ml-auto text-xs text-[var(--green)]">done ✓</span>
            )}
          </div>

          <div className="p-4 max-h-[480px] overflow-y-auto font-mono space-y-0">
            {logs.length === 0 && phase === "running" && (
              <p className="text-xs text-[var(--muted)] animate-pulse">
                Waiting for first log entry…
              </p>
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
      {phase === "done" && post && <ResultCard post={post} runId={runId!} />}
    </div>
  );
}
