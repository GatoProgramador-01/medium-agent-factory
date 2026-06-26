"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Exemplar } from "@/lib/api";

function scoreColor(score: number) {
  if (score >= 0.90) return "var(--green)";
  if (score >= 0.75) return "var(--amber)";
  return "var(--red)";
}

function ExemplarCard({ ex, onRemove }: { ex: Exemplar; onRemove: () => void }) {
  const pct = Math.round(ex.score * 100);
  const color = scoreColor(ex.score);

  return (
    <div className="card p-5 space-y-3" data-testid={`exemplar-card-${ex.run_id}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0 space-y-1">

          <Link
            href={`/posts/${ex.run_id}`}
            data-testid={`exemplar-link-${ex.run_id}`}
            className="font-semibold text-base hover:text-white transition-colors block"
            style={{ color: "var(--text)", textDecoration: "none" }}
          >
            {ex.title}
          </Link>
          <div className="text-xs" style={{ color: "var(--text-dim)" }}>
            {new Date(ex.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
            {" · "}{ex.word_count.toLocaleString()} words
          </div>
        </div>

        <div className="shrink-0 text-right space-y-1">
          <div data-testid={`exemplar-score-${ex.run_id}`} className="text-2xl font-bold tabular-nums" style={{ color }}>{pct}</div>
          <div data-testid={`exemplar-ratio-${ex.run_id}`} className="text-xs" style={{ color: "var(--text-dim)" }}>
            {Math.round(ex.read_ratio * 100)}% ratio
          </div>
        </div>
      </div>

      {/* Hook text */}
      <blockquote
        className="text-sm italic pl-3"
        style={{
          borderLeft: "2px solid rgba(139,92,246,0.4)",
          color: "var(--text-muted)",
          fontFamily: "Georgia, serif",
        }}
      >
        &ldquo;{ex.hook}&rdquo;
      </blockquote>

      {/* Tags */}
      {ex.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {ex.tags.map((t) => (
            <span
              key={t}
              className="text-xs px-2 py-0.5 rounded-full"
              style={{
                background: "rgba(139,92,246,0.07)",
                color: "var(--text-dim)",
                border: "1px solid rgba(139,92,246,0.15)",
              }}
            >
              {t}
            </span>
          ))}
        </div>
      )}

      {/* Hook score bar */}
      <div className="space-y-1">
        <div className="text-xs" style={{ color: "var(--text-dim)" }}>
          Hook score: {Math.round(ex.hook_score * 100)}%
        </div>
        <div className="score-bar-track">
          <div
            className="score-bar-fill"
            style={{ width: `${Math.round(ex.hook_score * 100)}%`, background: color }}
          />
        </div>
      </div>

      <div className="flex justify-end pt-1" style={{ borderTop: "1px solid var(--border)" }}>
        <button
          data-testid={`remove-exemplar-${ex.run_id}`}
          onClick={async () => { await api.deleteExemplar(ex.run_id); onRemove(); }}
          className="text-xs px-2 py-0.5 rounded transition-colors"
          style={{ color: "var(--text-dim)", border: "1px solid var(--border)", cursor: "pointer" }}
        >
          Remove
        </button>
      </div>
    </div>
  );
}

export default function ExemplarsPage() {
  const [exemplars, setExemplars] = useState<Exemplar[]>([]);
  const [loading, setLoading]     = useState(true);

  useEffect(() => {
    api.listExemplars()
      .then(setExemplars)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1
          className="text-2xl font-bold"
          data-testid="page-heading"
          style={{ color: "#fff" }}
        >
          Exemplars
        </h1>
        <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
          High-scoring posts (≥ 0.95) saved as few-shot references for the content generator.
        </p>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="card p-5 space-y-3">
              <div className="skeleton h-4 w-2/3" />
              <div className="skeleton h-3 w-full" />
              <div className="skeleton h-3 w-3/4" />
            </div>
          ))}
        </div>
      ) : exemplars.length === 0 ? (
        <div className="card p-12 text-center space-y-3" data-testid="empty-state">
          <p className="text-lg" style={{ color: "var(--text-muted)" }}>No exemplars yet</p>
          <p className="text-sm" style={{ color: "var(--text-dim)" }}>
            Posts scoring ≥ 0.95 are auto-saved. You can also promote any post manually from
            the post reader.
          </p>
          <Link
            href="/posts"
            className="btn btn-primary inline-block mt-2"
            style={{ textDecoration: "none" }}
          >
            Browse Posts
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          {exemplars.map((ex) => (
            <ExemplarCard
              key={ex.run_id}
              ex={ex}
              onRemove={() => setExemplars((prev) => prev.filter((e) => e.run_id !== ex.run_id))}
            />
          ))}
        </div>
      )}
    </div>
  );
}
