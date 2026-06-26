"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, type AgentLog, type PipelineRun, type Post } from "@/lib/api";

type RunPhase = "idle" | "running" | "done";
type Mode = "single" | "series";

const STEP_ICON: Record<string, string> = {
  orchestrator:      "◈",
  web_researcher:    "⌕",
  content_generator: "✎",
  quality_analyzer:  "⊛",
  formatter:         "⌥",
};

const LEVEL_COLOR: Record<string, string> = {
  info:    "var(--text-muted)",
  success: "var(--green)",
  warning: "var(--amber)",
  error:   "var(--red)",
};

function LogLine({ log, index }: { log: AgentLog; index: number }) {
  const hasData = log.data && Object.keys(log.data).length > 0;
  const [expanded, setExpanded] = useState(false);
  const icon  = STEP_ICON[log.step] ?? "·";
  const time  = new Date(log.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const color = LEVEL_COLOR[log.level] ?? "var(--text-muted)";

  return (
    <div
      className="flex gap-2 py-0.5 leading-relaxed"
      style={{ animationDelay: `${Math.min(index * 15, 200)}ms`, fontSize: 12 }}
    >
      <span className="shrink-0 tabular-nums w-20" style={{ color: "var(--text-dim)" }}>{time}</span>
      <span className="shrink-0 w-36 truncate" style={{ color: "var(--orange)", fontFamily: "var(--mono)" }}>
        {icon} {log.step}
      </span>
      <span className="flex-1 min-w-0" style={{ color, fontFamily: "var(--mono)" }}>
        {log.message}
        {hasData && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="ml-2 text-xs"
            style={{ color: "var(--text-dim)" }}
          >
            [{expanded ? "−" : "+"}]
          </button>
        )}
      </span>
    </div>
  );
}

function ResultCard({ post }: { post: Post }) {
  const score    = post.quality_report?.score ?? 0;
  const ratio    = post.quality_report?.read_ratio_prediction ?? 0;
  const boost    = post.quality_report?.medium_boost_eligible ?? false;
  const scorePct = Math.round(score * 100);
  const scoreColor = scorePct >= 90 ? "var(--green)" : scorePct >= 75 ? "var(--amber)" : "var(--red)";

  return (
    <div className="card p-6 space-y-4" data-testid="result-card">
      <div className="flex items-center gap-2">
        <span style={{ color: "var(--orange)", fontSize: 18 }}>✓</span>
        <span className="font-semibold" style={{ color: "var(--orange)" }}>Pipeline complete</span>
      </div>

      <h2 className="font-semibold text-lg leading-snug" style={{ color: "#fff" }}>{post.title}</h2>

      {post.pull_quote && (
        <p className="text-sm italic" style={{ color: "var(--text-muted)", fontFamily: "Georgia, serif" }}>
          &ldquo;{post.pull_quote}&rdquo;
        </p>
      )}

      <div className="grid grid-cols-3 gap-4">
        <div>
          <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>Quality</div>
          <div data-testid="result-score" className="text-2xl font-bold tabular-nums" style={{ color: scoreColor }}>{scorePct}</div>
        </div>
        <div>
          <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>Read ratio</div>
          <div data-testid="result-ratio" className="text-2xl font-bold tabular-nums" style={{ color: "var(--green)" }}>
            {Math.round(ratio * 100)}%
          </div>
        </div>
        <div>
          <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>Boost</div>
          <div className="mt-1">
            {boost
              ? <span className="badge badge-green">Eligible</span>
              : <span className="badge badge-muted">No</span>
            }
          </div>
        </div>
      </div>

      {post.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {post.tags.map((t) => (
            <span
              key={t}
              className="text-xs px-2.5 py-1 rounded-full"
              style={{ background: "var(--surface-hover)", color: "var(--text-muted)" }}
            >
              {t}
            </span>
          ))}
        </div>
      )}

      <Link
        href={`/posts/${post.run_id}`}
        className="inline-block btn btn-primary text-sm"
        data-testid="view-post-link"
        style={{ textDecoration: "none" }}
      >
        Read Full Post
      </Link>
    </div>
  );
}

function SeriesResultCard({ seriesId }: { seriesId: string }) {
  return (
    <div className="card p-6 space-y-4" data-testid="series-result-card">
      <div className="flex items-center gap-2">
        <span style={{ color: "var(--green)", fontSize: 18 }}>✓</span>
        <span className="font-semibold" style={{ color: "var(--green)" }}>Series started</span>
      </div>
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        The pipeline is generating your series in the background. Each post is processed
        sequentially — check back in a few minutes.
      </p>
      <div className="text-xs font-mono" style={{ color: "var(--text-dim)" }}>
        series_id: {seriesId}
      </div>
      <Link
        href="/series"
        data-testid="view-series-link"
        className="inline-block btn btn-primary text-sm"
        style={{ textDecoration: "none" }}
      >
        View Series →
      </Link>
    </div>
  );
}

const STATUS_COLOR: Record<string, string> = {
  completed: "var(--green)",
  failed:    "var(--red)",
  running:   "var(--amber)",
  queued:    "var(--text-dim)",
};

function RunHistory({ runs }: { runs: PipelineRun[] }) {
  if (runs.length === 0) return null;
  return (
    <div data-testid="run-history" className="space-y-2">
      <h2 className="text-xs font-medium tracking-wide" style={{ color: "var(--text-muted)" }}>
        Recent Runs
      </h2>
      <div className="card overflow-hidden">
        {runs.slice(0, 5).map((run, i) => (
          <div
            key={run.run_id}
            data-testid={`run-row-${run.run_id}`}
            className="flex items-center gap-3 px-4 py-2.5 text-xs"
            style={{
              borderTop: i > 0 ? "1px solid var(--border)" : "none",
            }}
          >
            <span
              className="shrink-0 font-mono"
              style={{ color: "var(--text-dim)" }}
            >
              {run.run_id.slice(0, 8)}
            </span>
            <span className="flex-1 truncate" style={{ color: "var(--text-muted)" }}>
              {run.custom_topic || "—"}
            </span>
            <span
              className="shrink-0 font-medium"
              style={{ color: STATUS_COLOR[run.status] ?? "var(--text-dim)" }}
            >
              {run.status}
            </span>
            <span className="shrink-0" style={{ color: "var(--text-dim)" }}>
              {new Date(run.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
            </span>
            {run.status === "completed" && (
              <Link
                href={`/posts/${run.run_id}`}
                data-testid={`run-post-link-${run.run_id}`}
                className="shrink-0 text-xs"
                style={{ color: "var(--orange)", textDecoration: "none" }}
              >
                View →
              </Link>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function PipelinePage() {
  const [mode,  setMode]  = useState<Mode>("single");

  // Single-post state
  const [topic, setTopic] = useState("");
  const [phase, setPhase] = useState<RunPhase>("idle");
  const [runId, setRunId] = useState<string | null>(null);
  const [logs,  setLogs]  = useState<AgentLog[]>([]);
  const [post,  setPost]  = useState<Post | null>(null);
  const [error, setError] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const esRef     = useRef<EventSource | null>(null);

  // Series state
  const [theme,       setTheme]       = useState("");
  const [context,     setContext]     = useState("");
  const [seriesPhase, setSeriesPhase] = useState<"idle" | "running" | "done">("idle");
  const [seriesId,    setSeriesId]    = useState<string | null>(null);
  const [seriesError, setSeriesError] = useState<string | null>(null);

  // Run history
  const [runs, setRuns] = useState<PipelineRun[]>([]);

  function fetchRuns() {
    api.listRuns().then(setRuns).catch(() => {});
  }

  useEffect(() => { fetchRuns(); }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  useEffect(() => {
    if (phase !== "running" || !runId) return;
    const es = api.streamLogs(runId);
    esRef.current = es;
    es.onmessage = (event: MessageEvent<string>) => {
      const data = JSON.parse(event.data) as Record<string, unknown>;
      if (data.__done__) { es.close(); esRef.current = null; setPhase("done"); return; }
      setLogs((prev) => [...prev, data as unknown as AgentLog]);
    };
    es.onerror = () => { es.close(); esRef.current = null; setPhase("done"); };
    return () => { es.close(); esRef.current = null; };
  }, [phase, runId]);

  useEffect(() => {
    if (phase !== "done" || !runId) return;
    api.getPost(runId).then(setPost).catch(() => {});
    fetchRuns();
  }, [phase, runId]);

  async function handleRun() {
    if (esRef.current) { esRef.current.close(); esRef.current = null; }
    setPhase("running"); setLogs([]); setPost(null); setError(null);
    try {
      const { run_id } = await api.triggerPipeline(topic.trim() || "trending topic");
      setRunId(run_id);
    } catch (e) {
      setError(String(e)); setPhase("idle");
    }
  }

  function handleReset() {
    if (esRef.current) { esRef.current.close(); esRef.current = null; }
    setPhase("idle"); setLogs([]); setPost(null); setError(null); setRunId(null);
  }

  async function handleSeriesRun() {
    setSeriesPhase("running"); setSeriesId(null); setSeriesError(null);
    try {
      const { series_id } = await api.triggerSeries(theme.trim() || "AI trends", context.trim());
      setSeriesId(series_id);
      setSeriesPhase("done");
    } catch (e) {
      setSeriesError(String(e)); setSeriesPhase("idle");
    }
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold mb-1" data-testid="page-heading" style={{ color: "#fff", letterSpacing: "-0.01em" }}>
          Run Pipeline
        </h1>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          Format → Quality → Revision loop (up to 3 cycles) · Live log via SSE
        </p>
      </div>

      {/* Mode tabs */}
      <div className="flex gap-1 p-1 rounded-lg w-fit" style={{ background: "var(--surface-hover)" }}>
        {(["single", "series"] as Mode[]).map((m) => (
          <button
            key={m}
            data-testid={`tab-${m}`}
            onClick={() => setMode(m)}
            className="px-4 py-1.5 rounded-md text-sm transition-colors"
            style={{
              background: mode === m ? "var(--bg)" : "transparent",
              color:      mode === m ? "var(--text)" : "var(--text-muted)",
              fontWeight: mode === m ? 500 : 400,
              border:     mode === m ? "1px solid var(--border)" : "1px solid transparent",
            }}
          >
            {m === "single" ? "Single Post" : "Series"}
          </button>
        ))}
      </div>

      {/* Single-post input card */}
      {mode === "single" && <div className="card p-5 space-y-4">
        <label className="block">
          <span className="text-xs font-medium block mb-2" style={{ color: "var(--text-muted)" }}>Topic</span>
          <input
            data-testid="topic-input"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && phase === "idle" && handleRun()}
            disabled={phase === "running"}
            maxLength={500}
            placeholder="e.g. I spent 90 days tracking every dollar my AI pipeline made on Medium"
            className="w-full rounded-lg px-4 py-2.5 text-sm outline-none transition-colors"
            style={{
              background: "var(--bg)",
              border: "1px solid var(--border)",
              color: "var(--text)",
              fontFamily: "inherit",
            }}
            onFocus={(e) => (e.target.style.borderColor = "var(--orange)")}
            onBlur={(e)  => (e.target.style.borderColor = "var(--border)")}
          />
        </label>

        {phase === "done" ? (
          <button data-testid="run-again-button" onClick={handleReset} className="btn w-full">
            Run Again
          </button>
        ) : (
          <button
            data-testid="run-button"
            onClick={handleRun}
            disabled={phase === "running"}
            className="btn btn-primary w-full flex items-center justify-center gap-2"
          >
            {phase === "running" ? (
              <>
                <span
                  className="inline-block w-3.5 h-3.5 rounded-full border-2 animate-spin"
                  style={{ borderColor: "rgba(15,17,23,0.3)", borderTopColor: "#0f1117" }}
                />
                Generating…
              </>
            ) : "Generate Post"}
          </button>
        )}
      </div>}

      {/* Series form */}
      {mode === "series" && (
        <div className="card p-5 space-y-4">
          <label className="block">
            <span className="text-xs font-medium block mb-2" style={{ color: "var(--text-muted)" }}>Series Theme</span>
            <input
              data-testid="theme-input"
              value={theme}
              onChange={(e) => setTheme(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && seriesPhase === "idle" && handleSeriesRun()}
              disabled={seriesPhase === "running"}
              maxLength={500}
              placeholder="e.g. The real cost of running LLMs in production"
              className="w-full rounded-lg px-4 py-2.5 text-sm outline-none transition-colors"
              style={{
                background: "var(--bg)",
                border: "1px solid var(--border)",
                color: "var(--text)",
                fontFamily: "inherit",
              }}
              onFocus={(e) => (e.target.style.borderColor = "var(--orange)")}
              onBlur={(e)  => (e.target.style.borderColor = "var(--border)")}
            />
          </label>

          <label className="block">
            <span className="text-xs font-medium block mb-2" style={{ color: "var(--text-muted)" }}>
              Context <span style={{ color: "var(--text-dim)" }}>(optional — extra background for the planner)</span>
            </span>
            <textarea
              data-testid="context-input"
              value={context}
              onChange={(e) => setContext(e.target.value)}
              disabled={seriesPhase === "running"}
              maxLength={1000}
              placeholder="e.g. Focus on Anthropic, OpenAI and DeepSeek; avoid Gemini"
              rows={3}
              className="w-full rounded-lg px-4 py-2.5 text-sm outline-none transition-colors resize-none"
              style={{
                background: "var(--bg)",
                border: "1px solid var(--border)",
                color: "var(--text)",
                fontFamily: "inherit",
              }}
              onFocus={(e) => (e.target.style.borderColor = "var(--orange)")}
              onBlur={(e)  => (e.target.style.borderColor = "var(--border)")}
            />
          </label>

          <button
            data-testid="run-series-button"
            onClick={handleSeriesRun}
            disabled={seriesPhase === "running"}
            className="btn btn-primary w-full flex items-center justify-center gap-2"
          >
            {seriesPhase === "running" ? (
              <>
                <span
                  className="inline-block w-3.5 h-3.5 rounded-full border-2 animate-spin"
                  style={{ borderColor: "rgba(15,17,23,0.3)", borderTopColor: "#0f1117" }}
                />
                Planning Series…
              </>
            ) : "Generate Series"}
          </button>
        </div>
      )}

      {seriesError && mode === "series" && (
        <div
          className="rounded-lg p-4 text-sm"
          style={{ background: "rgba(239,68,68,0.08)", border: "1px solid var(--red)", color: "var(--red)" }}
        >
          {seriesError}
        </div>
      )}

      {seriesPhase === "done" && seriesId && mode === "series" && (
        <SeriesResultCard seriesId={seriesId} />
      )}

      {/* Live log */}
      {(logs.length > 0 || phase === "running") && (
        <div className="log-panel" data-testid="log-terminal">
          <div className="log-panel-header">
            <span
              className="w-2 h-2 rounded-full"
              style={{ background: phase === "running" ? "var(--amber)" : "var(--green)", flexShrink: 0 }}
            />
            <span>Agent Logs</span>
            {runId && <span style={{ color: "var(--text-dim)" }}>· {runId.slice(0, 8)}…</span>}
            <span className="ml-auto text-xs">
              {phase === "running" ? "● live" : `✓ done · ${logs.length} lines`}
            </span>
          </div>
          <div className="p-3 max-h-96 overflow-y-auto">
            {logs.length === 0 && phase === "running" && (
              <p className="text-xs animate-pulse" style={{ color: "var(--text-dim)", fontFamily: "var(--mono)" }}>
                Waiting for first log entry…
              </p>
            )}
            {logs.map((log, i) => <LogLine key={`${log.timestamp}-${i}`} log={log} index={i} />)}
            <div ref={logEndRef} />
          </div>
        </div>
      )}

      {error && (
        <div
          className="rounded-lg p-4 text-sm"
          style={{ background: "rgba(239,68,68,0.08)", border: "1px solid var(--red)", color: "var(--red)" }}
        >
          {error}
        </div>
      )}

      {phase === "done" && post && <ResultCard post={post} />}

      <RunHistory runs={runs} />
    </div>
  );
}
