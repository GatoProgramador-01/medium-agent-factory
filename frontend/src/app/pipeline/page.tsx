"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, type AgentLog, type Post } from "@/lib/api";

type RunPhase = "idle" | "running" | "done";

const STEP_ICON: Record<string, string> = {
  orchestrator:      "◈",
  trend_researcher:  "⌖",
  content_generator: "✎",
  quality_analyzer:  "⊛",
  publisher:         "⇪",
};

const LEVEL_COLOR: Record<string, string> = {
  info:    "text-[var(--muted)]",
  success: "text-[var(--accent)]",
  warning: "text-[var(--yellow)]",
  error:   "text-[var(--red)]",
};

function LogLine({ log, index }: { log: AgentLog; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const hasData = log.data && Object.keys(log.data).length > 0;
  const icon = STEP_ICON[log.step] ?? "·";
  const time = new Date(log.timestamp).toLocaleTimeString([], {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
  const color = LEVEL_COLOR[log.level] ?? "text-[var(--muted)]";

  return (
    <div className="flex gap-2 py-0.5 text-xs leading-relaxed" style={{ animationDelay: `${Math.min(index * 15, 200)}ms` }}>
      <span className="text-[var(--muted)] shrink-0 tabular-nums w-20">{time}</span>
      <span className="text-[var(--accent)] shrink-0 w-32 truncate">{icon} {log.step}</span>
      <span className={`flex-1 min-w-0 ${color}`}>
        {log.message}
        {hasData && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="ml-2 text-[var(--muted)] hover:text-[var(--accent)] transition-colors"
          >
            [{expanded ? "−" : "+"}]
          </button>
        )}
      </span>
    </div>
  );
}

function ResultCard({ post }: { post: Post }) {
  const score = post.quality_report?.score ?? 0;
  const ratio = post.quality_report?.read_ratio_prediction ?? 0;
  const scorePct = Math.round(score * 100);

  return (
    <div className="term-box" data-testid="result-card">
      <div className="term-box-header">
        <span className="text-[var(--accent)]">✓</span>
        <span className="text-[var(--accent)]">pipeline completed</span>
      </div>
      <div className="p-4 space-y-3 text-sm">
        <div>
          <p className="text-[var(--muted)] text-xs mb-1">title</p>
          <p className="text-[var(--text)] font-semibold">{post.title}</p>
        </div>
        <div className="grid grid-cols-3 gap-4 text-xs">
          <div>
            <p className="text-[var(--muted)]">quality_score</p>
            <p className={`text-lg font-bold tabular-nums mt-0.5 ${scorePct >= 75 ? "text-[var(--accent)]" : scorePct >= 50 ? "text-[var(--yellow)]" : "text-[var(--red)]"}`}>
              {scorePct}/100
            </p>
          </div>
          <div>
            <p className="text-[var(--muted)]">read_ratio</p>
            <p className="text-lg font-bold tabular-nums mt-0.5 text-[var(--accent)]">
              {Math.round(ratio * 100)}%
            </p>
          </div>
          <div>
            <p className="text-[var(--muted)]">revisions</p>
            <p className="text-lg font-bold tabular-nums mt-0.5">{post.revision_count}</p>
          </div>
        </div>
        {post.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {post.tags.map((t) => (
              <span key={t} className="text-[10px] border border-[var(--border2)] px-2 py-0.5 text-[var(--muted)]">
                #{t}
              </span>
            ))}
          </div>
        )}
        <div className="flex gap-4 pt-1">
          <Link href="/posts" className="text-xs text-[var(--accent)] hover:underline" data-testid="view-post-link">
            ❯ view_post
          </Link>
          {post.medium_url && (
            <a href={post.medium_url} target="_blank" rel="noopener noreferrer" className="text-xs text-[var(--muted)] hover:text-[var(--text)] underline">
              open_medium ↗
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

export default function PipelinePage() {
  const [topic, setTopic]         = useState("");
  const [publishLive, setPublishLive] = useState(false);
  const [phase, setPhase]         = useState<RunPhase>("idle");
  const [runId, setRunId]         = useState<string | null>(null);
  const [logs, setLogs]           = useState<AgentLog[]>([]);
  const [post, setPost]           = useState<Post | null>(null);
  const [error, setError]         = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const pollRef   = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs]);

  useEffect(() => {
    if (phase !== "running" || !runId) return;
    const poll = async () => {
      try {
        const [newLogs, run] = await Promise.all([api.getLogs(runId), api.getRun(runId)]);
        setLogs(newLogs);
        if (run.status === "completed" || run.status === "failed") {
          clearInterval(pollRef.current!);
          pollRef.current = null;
          setPhase("done");
        }
      } catch { /* ignore */ }
    };
    poll();
    pollRef.current = setInterval(poll, 2000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [phase, runId]);

  useEffect(() => {
    if (phase !== "done" || !runId) return;
    api.getPost(runId).then(setPost).catch(() => {});
  }, [phase, runId]);

  async function handleRun() {
    setPhase("running"); setLogs([]); setPost(null); setError(null);
    try {
      const { run_id } = await api.triggerPipeline(topic.trim() || null, publishLive);
      setRunId(run_id);
    } catch (e) { setError(String(e)); setPhase("idle"); }
  }

  function handleReset() {
    setPhase("idle"); setLogs([]); setPost(null); setError(null); setRunId(null);
  }

  return (
    <div className="space-y-5 max-w-3xl">
      <div>
        <p className="text-[var(--muted)] text-xs mb-1">user@factory:~/factory$</p>
        <h1 className="text-[var(--accent)] text-xl font-bold" data-testid="page-heading">
          Run Pipeline
        </h1>
        <p className="text-[var(--muted)] text-xs mt-1">
          strategy: haiku → haiku-revision → sonnet (last resort)
        </p>
      </div>

      {/* Input */}
      <div className="term-box">
        <div className="term-box-header">
          <span className="text-[var(--accent)]">$</span>
          <span>pipeline.run --topic &lt;query&gt;</span>
        </div>
        <div className="p-4 space-y-4">
          <div>
            <label className="text-[var(--muted)] text-xs block mb-1.5">
              --topic  <span className="text-[var(--border2)]">(optional, auto-detected if blank)</span>
            </label>
            <div className="flex items-center gap-2 border border-[var(--border)] bg-[var(--bg)] px-3 py-2 focus-within:border-[var(--accent)] transition-colors">
              <span className="text-[var(--accent)] shrink-0">❯</span>
              <input
                data-testid="topic-input"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                disabled={phase === "running"}
                placeholder="e.g. how to make $500/month on Ko-fi in 2025"
                className="flex-1 bg-transparent text-sm text-[var(--text)] placeholder:text-[var(--muted)] focus:outline-none disabled:opacity-40"
              />
            </div>
          </div>

          <label className="flex items-center gap-3 cursor-pointer select-none text-xs">
            <input
              type="checkbox"
              checked={publishLive}
              onChange={(e) => setPublishLive(e.target.checked)}
              disabled={phase === "running"}
              className="accent-[var(--accent)]"
            />
            <span className="text-[var(--muted)]">--publish-live</span>
            <span className="text-[var(--border2)]">publish to Medium on completion</span>
          </label>

          {phase === "done" ? (
            <button data-testid="run-again-button" onClick={handleReset} className="term-btn w-full py-2.5 text-xs tracking-widest">
              ❯ run --again
            </button>
          ) : (
            <button
              data-testid="run-button"
              onClick={handleRun}
              disabled={phase === "running"}
              className="term-btn term-btn-solid w-full py-2.5 text-xs tracking-widest flex items-center justify-center gap-2"
            >
              {phase === "running" ? (
                <>
                  <span className="w-2.5 h-2.5 border border-[#0b0b0b]/40 border-t-[#0b0b0b] rounded-full animate-spin" />
                  running…
                </>
              ) : "❯ run_pipeline"}
            </button>
          )}
        </div>
      </div>

      {/* Live log */}
      {(logs.length > 0 || phase === "running") && (
        <div className="term-box" data-testid="log-terminal">
          <div className="term-box-header">
            <span className={`w-2 h-2 rounded-full ${phase === "running" ? "bg-[var(--yellow)] animate-pulse" : "bg-[var(--accent)]"}`} />
            <span className="font-mono">agent-logs</span>
            {runId && <span className="text-[var(--border2)]">· {runId.slice(0, 8)}…</span>}
            <span className="ml-auto">{phase === "running" ? "● live" : "✓ done"}</span>
          </div>
          <div className="p-3 max-h-[420px] overflow-y-auto font-mono">
            {logs.length === 0 && phase === "running" && (
              <p className="text-[var(--muted)] text-xs animate-pulse">waiting for first log entry…</p>
            )}
            {logs.map((log, i) => <LogLine key={`${log.timestamp}-${i}`} log={log} index={i} />)}
            <div ref={logEndRef} />
          </div>
        </div>
      )}

      {error && (
        <div className="border border-[var(--red)] bg-[var(--red)]/5 p-3 text-xs text-[var(--red)]">
          error: {error}
        </div>
      )}

      {phase === "done" && post && <ResultCard post={post} />}
    </div>
  );
}
