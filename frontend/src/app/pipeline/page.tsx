"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, type AgentLog, type PipelineRun, type Post } from "@/lib/api";

type RunPhase = "idle" | "running" | "done";
type Mode = "single" | "series";

// ── Agent pipeline steps (reviser is conditional, excluded from stepper) ──────
const PIPELINE_STEPS = [
  "orchestrator",
  "web_researcher",
  "content_generator",
  "fact_checker",
  "quality_analyzer",
  "formatter",
] as const;
type PipelineStep = (typeof PIPELINE_STEPS)[number];

const STEP_LABEL: Record<PipelineStep, string> = {
  orchestrator:      "Orchestrate",
  web_researcher:    "Research",
  content_generator: "Generate",
  fact_checker:      "Fact Check",
  quality_analyzer:  "Quality",
  formatter:         "Format",
};

const STEP_ICON: Record<string, string> = {
  orchestrator:      "◈",
  web_researcher:    "⌕",
  content_generator: "✎",
  fact_checker:      "⊛",
  quality_analyzer:  "⊛",
  formatter:         "⌥",
};

const LEVEL_COLOR: Record<string, string> = {
  info:    "var(--text-muted)",
  success: "var(--green)",
  warning: "var(--amber)",
  error:   "var(--red)",
};

// ── Derive stepper state from logs ─────────────────────────────────────────────
type StepState = "done" | "active" | "pending";

function getStepperState(logs: AgentLog[]): Record<PipelineStep, StepState> {
  const seenSteps = new Set<string>(logs.map((l) => l.step));
  let lastSeenIndex = -1;
  for (let i = PIPELINE_STEPS.length - 1; i >= 0; i--) {
    if (seenSteps.has(PIPELINE_STEPS[i])) {
      lastSeenIndex = i;
      break;
    }
  }

  const result = {} as Record<PipelineStep, StepState>;
  for (let i = 0; i < PIPELINE_STEPS.length; i++) {
    const step = PIPELINE_STEPS[i];
    if (lastSeenIndex === -1) {
      result[step] = "pending";
    } else if (i < lastSeenIndex) {
      result[step] = "done";
    } else if (i === lastSeenIndex) {
      result[step] = "active";
    } else {
      result[step] = "pending";
    }
  }
  return result;
}

// ── Agent stepper component ────────────────────────────────────────────────────
function AgentStepper({ logs, phase }: { logs: AgentLog[]; phase: RunPhase }) {
  const stepState = getStepperState(logs);
  const allDone = phase === "done";

  return (
    <div
      data-testid="agent-stepper"
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        padding: "16px 20px 14px",
        background: "var(--surface)",
        borderRadius: 10,
        border: "1px solid var(--border)",
      }}
    >
      {PIPELINE_STEPS.map((step, i) => {
        const state = allDone ? "done" : stepState[step];
        const circleColor =
          state === "done"
            ? "var(--green)"
            : state === "active"
            ? "var(--amber)"
            : "var(--text-dim)";
        const circleBg =
          state === "done"
            ? "rgba(34,197,94,0.15)"
            : state === "active"
            ? "rgba(245,158,11,0.15)"
            : "var(--surface-hover)";
        const labelColor =
          state === "done"
            ? "var(--text-muted)"
            : state === "active"
            ? "var(--amber)"
            : "var(--text-dim)";

        return (
          <div key={step} style={{ display: "flex", alignItems: "flex-start", flex: 1 }}>
            {/* Node + label */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", minWidth: 0 }}>
              <div
                data-testid={`step-node-${step}`}
                style={{
                  width: 20,
                  height: 20,
                  borderRadius: "50%",
                  border: `2px solid ${circleColor}`,
                  background: circleBg,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                  transition: "border-color 0.3s, background 0.3s",
                }}
              >
                {state === "done" && (
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <path d="M2 5l2 2 4-4" stroke="var(--green)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
                {state === "active" && (
                  <div
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: "50%",
                      background: "var(--amber)",
                      animation: "pulse-dot 1s ease-in-out infinite",
                    }}
                  />
                )}
              </div>
              <span
                style={{
                  fontSize: 10,
                  marginTop: 5,
                  color: labelColor,
                  fontFamily: "inherit",
                  fontWeight: state === "active" ? 600 : 400,
                  whiteSpace: "nowrap",
                  transition: "color 0.3s",
                  letterSpacing: "0.01em",
                }}
              >
                {STEP_LABEL[step]}
              </span>
            </div>

            {/* Connector line between nodes (not after last) */}
            {i < PIPELINE_STEPS.length - 1 && (
              <div
                style={{
                  flex: 1,
                  height: 2,
                  marginTop: 9,
                  marginLeft: 4,
                  marginRight: 4,
                  background:
                    stepState[step] === "done" || allDone
                      ? "var(--green)"
                      : "var(--border-light)",
                  borderRadius: 1,
                  transition: "background 0.3s",
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Log line with fade-in ──────────────────────────────────────────────────────
function LogLine({ log, index }: { log: AgentLog; index: number }) {
  const hasData = log.data && Object.keys(log.data).length > 0;
  const [expanded, setExpanded] = useState(false);
  const icon  = STEP_ICON[log.step] ?? "·";
  const time  = new Date(log.timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  const color = LEVEL_COLOR[log.level] ?? "var(--text-muted)";

  return (
    <div
      className="flex gap-2 py-0.5 leading-relaxed"
      style={{
        animationDelay: `${Math.min(index * 15, 200)}ms`,
        fontSize: 12,
        animation: "fadeIn 0.2s ease forwards",
        opacity: 0,
      }}
    >
      <span className="shrink-0 tabular-nums w-20" style={{ color: "var(--text-dim)" }}>
        {time}
      </span>
      <span
        className="shrink-0 w-36 truncate"
        style={{ color: "var(--orange)", fontFamily: "var(--mono)" }}
      >
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

// ── Score ring SVG ─────────────────────────────────────────────────────────────
function ScoreRing({
  score,
  color,
  size = 100,
}: {
  score: number;
  color: string;
  size?: number;
}) {
  const radius = 40;
  const strokeWidth = 6;
  const normalizedRadius = radius - strokeWidth / 2;
  const circumference = 2 * Math.PI * normalizedRadius;
  const strokeDashoffset = circumference - (score / 100) * circumference;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      style={{ transform: "rotate(-90deg)" }}
      aria-label={`Score: ${score}`}
    >
      {/* Track */}
      <circle
        cx="50"
        cy="50"
        r={normalizedRadius}
        fill="none"
        stroke="var(--border-light)"
        strokeWidth={strokeWidth}
      />
      {/* Progress */}
      <circle
        cx="50"
        cy="50"
        r={normalizedRadius}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={`${circumference} ${circumference}`}
        strokeDashoffset={strokeDashoffset}
        style={{ transition: "stroke-dashoffset 0.6s ease" }}
      />
    </svg>
  );
}

// ── Result card ────────────────────────────────────────────────────────────────
function ResultCard({ post }: { post: Post }) {
  const score    = post.quality_report?.score ?? 0;
  const ratio    = post.quality_report?.read_ratio_prediction ?? 0;
  const boost    = post.quality_report?.medium_boost_eligible ?? false;
  const issues   = post.quality_report?.issues ?? [];
  const scorePct = Math.round(score * 100);
  const scoreColor =
    scorePct >= 90 ? "var(--green)" : scorePct >= 75 ? "var(--amber)" : "var(--red)";

  // Build gate list: boost, ratio, score
  const gates = [
    {
      label: "Quality score ≥ 75",
      pass: scorePct >= 75,
    },
    {
      label: "Read ratio ≥ 50%",
      pass: Math.round(ratio * 100) >= 50,
    },
    {
      label: "Medium Boost eligible",
      pass: boost,
    },
    {
      label: `Zero critical issues (${issues.filter((i) => i.severity === "critical").length} found)`,
      pass: issues.filter((i) => i.severity === "critical").length === 0,
    },
  ];

  return (
    <div className="card p-6 space-y-5" data-testid="result-card">
      {/* Header */}
      <div className="flex items-center gap-2">
        <span style={{ color: "var(--orange)", fontSize: 18 }}>✓</span>
        <span className="font-semibold" style={{ color: "var(--orange)" }}>
          Pipeline complete
        </span>
      </div>

      <h2
        className="font-semibold text-lg leading-snug"
        style={{ color: "#fff" }}
      >
        {post.title}
      </h2>

      {post.pull_quote && (
        <p
          className="text-sm italic"
          style={{ color: "var(--text-muted)", fontFamily: "Georgia, serif" }}
        >
          &ldquo;{post.pull_quote}&rdquo;
        </p>
      )}

      {/* Score ring + metrics row */}
      <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
        {/* Ring */}
        <div style={{ position: "relative", width: 100, height: 100, flexShrink: 0 }}>
          <ScoreRing score={scorePct} color={scoreColor} size={100} />
          {/* Score label centered */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <span
              data-testid="result-score"
              style={{
                fontSize: "2rem",
                fontWeight: 700,
                lineHeight: 1,
                color: scoreColor,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {scorePct}
            </span>
            <span style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 2 }}>
              / 100
            </span>
          </div>
        </div>

        {/* Side metrics */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
              Read ratio
            </div>
            <div
              data-testid="result-ratio"
              style={{
                fontSize: "1.5rem",
                fontWeight: 700,
                color: "var(--green)",
                fontVariantNumeric: "tabular-nums",
                lineHeight: 1,
              }}
            >
              {Math.round(ratio * 100)}%
            </div>
          </div>
          <div>
            <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
              Boost
            </div>
            {boost ? (
              <span className="badge badge-green">Eligible</span>
            ) : (
              <span className="badge badge-muted">No</span>
            )}
          </div>
          {post.word_count && (
            <div>
              <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
                Words
              </div>
              <div style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-muted)" }}>
                {post.word_count.toLocaleString()}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Quality gates */}
      <div>
        <div
          className="text-xs font-medium mb-2"
          style={{ color: "var(--text-muted)", letterSpacing: "0.04em", textTransform: "uppercase" }}
        >
          Quality Gates
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {gates.map((gate) => (
            <div
              key={gate.label}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 13,
              }}
            >
              <span
                style={{
                  width: 18,
                  height: 18,
                  borderRadius: "50%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                  background: gate.pass
                    ? "rgba(34,197,94,0.15)"
                    : "rgba(239,68,68,0.12)",
                  color: gate.pass ? "var(--green)" : "var(--red)",
                  fontSize: 11,
                  fontWeight: 700,
                }}
              >
                {gate.pass ? "✓" : "✗"}
              </span>
              <span style={{ color: gate.pass ? "var(--text-muted)" : "var(--red)" }}>
                {gate.label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Tags */}
      {post.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {post.tags.map((t) => (
            <span
              key={t}
              className="text-xs px-2.5 py-1 rounded-full"
              style={{
                background: "var(--surface-hover)",
                color: "var(--text-muted)",
              }}
            >
              {t}
            </span>
          ))}
        </div>
      )}

      {/* Full-width CTA */}
      <Link
        href={`/posts/${post.run_id}`}
        className="btn btn-primary text-sm"
        data-testid="view-post-link"
        style={{
          textDecoration: "none",
          display: "block",
          textAlign: "center",
          width: "100%",
        }}
      >
        Read Full Post
      </Link>
    </div>
  );
}

// ── Series result card with skeleton placeholders ──────────────────────────────
function SeriesResultCard({ seriesId }: { seriesId: string }) {
  const posts = [1, 2, 3]; // 3-post series

  return (
    <div className="card p-6 space-y-4" data-testid="series-result-card">
      <div className="flex items-center gap-2">
        <span style={{ color: "var(--green)", fontSize: 18 }}>✓</span>
        <span className="font-semibold" style={{ color: "var(--green)" }}>
          Series started
        </span>
      </div>

      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        The pipeline is generating your series in the background. Each post is processed
        sequentially — check back in a few minutes.
      </p>

      {/* Post progress skeletons */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {posts.map((n) => (
          <div
            key={n}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "10px 14px",
              background: "var(--bg)",
              border: "1px solid var(--border)",
              borderRadius: 8,
            }}
          >
            {/* Number badge */}
            <div
              style={{
                width: 24,
                height: 24,
                borderRadius: "50%",
                background: "var(--surface-hover)",
                border: "1px solid var(--border-light)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                fontSize: 11,
                color: "var(--text-dim)",
                fontWeight: 600,
              }}
            >
              {n}
            </div>

            {/* Skeleton title */}
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
              <div
                className="skeleton"
                style={{
                  height: 10,
                  borderRadius: 4,
                  width: `${65 + n * 8}%`,
                  animationDelay: `${n * 120}ms`,
                }}
              />
              <div
                className="skeleton"
                style={{
                  height: 8,
                  borderRadius: 4,
                  width: "40%",
                  animationDelay: `${n * 120 + 80}ms`,
                }}
              />
            </div>

            {/* Pulsing status */}
            <span
              style={{
                fontSize: 11,
                color: "var(--text-dim)",
                fontFamily: "var(--mono)",
                animation: "pulse-dot 1.4s ease-in-out infinite",
                animationDelay: `${n * 200}ms`,
              }}
            >
              queued
            </span>
          </div>
        ))}
      </div>

      <div className="text-xs font-mono" style={{ color: "var(--text-dim)" }}>
        series_id: {seriesId}
      </div>

      <Link
        href="/series"
        data-testid="view-series-link"
        className="btn btn-primary text-sm"
        style={{ textDecoration: "none", display: "block", textAlign: "center", width: "100%" }}
      >
        View Series →
      </Link>
    </div>
  );
}

// ── Run history ────────────────────────────────────────────────────────────────
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
      <h2
        className="text-xs font-medium tracking-wide"
        style={{ color: "var(--text-muted)" }}
      >
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
            <span className="shrink-0 font-mono" style={{ color: "var(--text-dim)" }}>
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
              {new Date(run.created_at).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              })}
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

// ── Inject keyframe animations once ───────────────────────────────────────────
function GlobalAnimations() {
  useEffect(() => {
    const id = "pipeline-keyframes";
    if (document.getElementById(id)) return;
    const style = document.createElement("style");
    style.id = id;
    style.textContent = `
      @keyframes fadeIn {
        from { opacity: 0; transform: translateY(2px); }
        to   { opacity: 1; transform: translateY(0);   }
      }
      @keyframes pulse-dot {
        0%, 100% { opacity: 1; }
        50%       { opacity: 0.35; }
      }
    `;
    document.head.appendChild(style);
    return () => { document.getElementById(id)?.remove(); };
  }, []);
  return null;
}

// ── Page ───────────────────────────────────────────────────────────────────────
export default function PipelinePage() {
  const [mode, setMode] = useState<Mode>("single");

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
      if (data.__done__) {
        es.close();
        esRef.current = null;
        setPhase("done");
        return;
      }
      setLogs((prev) => [...prev, data as unknown as AgentLog]);
    };
    es.onerror = () => {
      es.close();
      esRef.current = null;
      setPhase("done");
    };
    return () => {
      es.close();
      esRef.current = null;
    };
  }, [phase, runId]);

  useEffect(() => {
    if (phase !== "done" || !runId) return;
    api.getPost(runId).then(setPost).catch(() => {});
    fetchRuns();
  }, [phase, runId]);

  async function handleRun() {
    if (esRef.current) { esRef.current.close(); esRef.current = null; }
    setPhase("running");
    setLogs([]);
    setPost(null);
    setError(null);
    try {
      const { run_id } = await api.triggerPipeline(topic.trim() || "trending topic");
      setRunId(run_id);
    } catch (e) {
      setError(String(e));
      setPhase("idle");
    }
  }

  function handleReset() {
    if (esRef.current) { esRef.current.close(); esRef.current = null; }
    setPhase("idle");
    setLogs([]);
    setPost(null);
    setError(null);
    setRunId(null);
  }

  async function handleSeriesRun() {
    setSeriesPhase("running");
    setSeriesId(null);
    setSeriesError(null);
    try {
      const { series_id } = await api.triggerSeries(
        theme.trim() || "AI trends",
        context.trim(),
      );
      setSeriesId(series_id);
      setSeriesPhase("done");
    } catch (e) {
      setSeriesError(String(e));
      setSeriesPhase("idle");
    }
  }

  const showStepper = mode === "single" && (logs.length > 0 || phase === "running");

  return (
    <div className="space-y-6 max-w-3xl">
      <GlobalAnimations />

      <div>
        <h1
          className="text-2xl font-bold mb-1"
          data-testid="page-heading"
          style={{ color: "#fff", letterSpacing: "-0.01em" }}
        >
          Run Pipeline
        </h1>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          Format → Quality → Revision loop (up to 3 cycles) · Live log via SSE
        </p>
      </div>

      {/* Mode tabs */}
      <div
        className="flex gap-1 p-1 rounded-lg w-fit"
        style={{ background: "var(--surface-hover)" }}
      >
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
      {mode === "single" && (
        <div className="card p-5 space-y-4">
          <label className="block">
            <span
              className="text-xs font-medium block mb-2"
              style={{ color: "var(--text-muted)" }}
            >
              Topic
            </span>
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
            <button
              data-testid="run-again-button"
              onClick={handleReset}
              className="btn w-full"
            >
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
                    style={{
                      borderColor: "rgba(15,17,23,0.3)",
                      borderTopColor: "#0f1117",
                    }}
                  />
                  Generating…
                </>
              ) : (
                "Generate Post"
              )}
            </button>
          )}
        </div>
      )}

      {/* Series form */}
      {mode === "series" && (
        <div className="card p-5 space-y-4">
          <label className="block">
            <span
              className="text-xs font-medium block mb-2"
              style={{ color: "var(--text-muted)" }}
            >
              Series Theme
            </span>
            <input
              data-testid="theme-input"
              value={theme}
              onChange={(e) => setTheme(e.target.value)}
              onKeyDown={(e) =>
                e.key === "Enter" && seriesPhase === "idle" && handleSeriesRun()
              }
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
            <span
              className="text-xs font-medium block mb-2"
              style={{ color: "var(--text-muted)" }}
            >
              Context{" "}
              <span style={{ color: "var(--text-dim)" }}>
                (optional — extra background for the planner)
              </span>
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
                  style={{
                    borderColor: "rgba(15,17,23,0.3)",
                    borderTopColor: "#0f1117",
                  }}
                />
                Planning Series…
              </>
            ) : (
              "Generate Series"
            )}
          </button>
        </div>
      )}

      {seriesError && mode === "series" && (
        <div
          className="rounded-lg p-4 text-sm"
          style={{
            background: "rgba(239,68,68,0.08)",
            border: "1px solid var(--red)",
            color: "var(--red)",
          }}
        >
          {seriesError}
        </div>
      )}

      {seriesPhase === "done" && seriesId && mode === "series" && (
        <SeriesResultCard seriesId={seriesId} />
      )}

      {/* Agent stepper — shown above log panel once a run starts */}
      {showStepper && <AgentStepper logs={logs} phase={phase} />}

      {/* Live log panel */}
      {(logs.length > 0 || phase === "running") && (
        <div className="log-panel" data-testid="log-terminal">
          <div className="log-panel-header">
            <span
              className="w-2 h-2 rounded-full"
              style={{
                background:
                  phase === "running" ? "var(--amber)" : "var(--green)",
                flexShrink: 0,
              }}
            />
            <span>Agent Logs</span>
            {runId && (
              <span style={{ color: "var(--text-dim)" }}>
                · {runId.slice(0, 8)}…
              </span>
            )}
            <span className="ml-auto text-xs">
              {phase === "running"
                ? "● live"
                : `✓ done · ${logs.length} lines`}
            </span>
          </div>
          <div className="p-3 max-h-96 overflow-y-auto">
            {logs.length === 0 && phase === "running" && (
              <p
                className="text-xs animate-pulse"
                style={{
                  color: "var(--text-dim)",
                  fontFamily: "var(--mono)",
                }}
              >
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

      {error && (
        <div
          className="rounded-lg p-4 text-sm"
          style={{
            background: "rgba(239,68,68,0.08)",
            border: "1px solid var(--red)",
            color: "var(--red)",
          }}
        >
          {error}
        </div>
      )}

      {phase === "done" && post && <ResultCard post={post} />}

      <RunHistory runs={runs} />
    </div>
  );
}
