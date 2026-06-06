"use client";

import { useState } from "react";
import { api, type PipelineRun } from "@/lib/api";

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

export default function PipelinePage() {
  const [topic, setTopic] = useState("");
  const [publishLive, setPublishLive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const res = await api.triggerPipeline(topic.trim() || null, publishLive) as unknown as RunResult;
      setResult(res);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-8 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold">Run Pipeline</h1>
        <p className="text-[var(--muted)] text-sm mt-1">
          Leave topic blank to let the Trend Research Agent pick the best opportunity.
        </p>
      </div>

      <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-6 space-y-4">
        <div>
          <label className="text-sm text-[var(--muted)] block mb-1">Custom Topic (optional)</label>
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g. How to make $500/month on Ko-fi in 2025"
            className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-[var(--accent)]"
          />
        </div>

        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={publishLive}
            onChange={(e) => setPublishLive(e.target.checked)}
            className="accent-[var(--accent)]"
          />
          <span className="text-sm">Publish live to Medium after pipeline</span>
        </label>

        <button
          onClick={handleRun}
          disabled={loading}
          className="w-full bg-[var(--accent)] text-white rounded-lg py-2.5 font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
        >
          {loading ? "Running pipeline… (this takes 1-2 min)" : "Run Pipeline"}
        </button>
      </div>

      {error && (
        <div className="bg-red-950/30 border border-[var(--red)] rounded-xl p-4 text-sm text-[var(--red)]">
          {error}
        </div>
      )}

      {result && (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <p className="font-semibold">{result.title ?? "Untitled"}</p>
            <span
              className={`text-xs px-2 py-1 rounded-full ${
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
              <p className="text-xl font-bold">
                {result.quality_score != null ? (result.quality_score * 100).toFixed(0) : "—"}
              </p>
              <p className="text-[var(--muted)] text-xs">Quality Score</p>
            </div>
            <div className="bg-[var(--bg)] rounded-lg p-3">
              <p className="text-xl font-bold">
                {result.read_ratio_prediction != null
                  ? `${(result.read_ratio_prediction * 100).toFixed(0)}%`
                  : "—"}
              </p>
              <p className="text-[var(--muted)] text-xs">Predicted Read Ratio</p>
            </div>
            <div className="bg-[var(--bg)] rounded-lg p-3">
              <p className="text-xl font-bold">{result.revision_count ?? 0}</p>
              <p className="text-[var(--muted)] text-xs">Revisions</p>
            </div>
          </div>

          {result.steps && result.steps.length > 0 && (
            <div>
              <p className="text-xs text-[var(--muted)] mb-2">Steps completed</p>
              <div className="flex flex-wrap gap-2">
                {result.steps.map((s) => (
                  <span key={s} className="text-xs bg-[var(--bg)] border border-[var(--border)] rounded px-2 py-1">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}

          {result.medium_url && (
            <a
              href={result.medium_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--accent)] text-sm underline"
            >
              View on Medium →
            </a>
          )}

          {result.errors && result.errors.length > 0 && (
            <div className="text-sm text-[var(--red)] space-y-1">
              {result.errors.map((e, i) => <p key={i}>{e}</p>)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
