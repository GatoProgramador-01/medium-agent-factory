import Link from "next/link";
import type { SeriesPost } from "@/lib/api";

export function SeriesNav({
  posts,
  currentRunId,
  theme,
}: {
  posts: SeriesPost[];
  currentRunId: string;
  theme: string;
}) {
  const idx = posts.findIndex((p) => p.run_id === currentRunId);
  if (idx < 0 || posts.length < 2) return null;

  const prev = idx > 0 ? posts[idx - 1] : null;
  const next = idx < posts.length - 1 ? posts[idx + 1] : null;
  const position = idx + 1;

  return (
    <div
      className="flex items-center justify-between gap-4 mb-6 px-4 py-3 rounded-lg text-sm"
      style={{
        background: "rgba(139,92,246,0.06)",
        border: "1px solid rgba(139,92,246,0.18)",
      }}
    >
      {/* Prev */}
      <div className="w-1/3">
        {prev && (
          <Link
            href={`/posts/${prev.run_id}`}
            data-testid="series-prev"
            className="flex items-center gap-1.5 transition-colors group"
            style={{ color: "#a78bfa", textDecoration: "none" }}
          >
            <span>←</span>
            <span
              className="truncate text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              {prev.title}
            </span>
          </Link>
        )}
      </div>

      {/* Centre — position + theme */}
      <div className="text-center shrink-0 space-y-0.5">
        <div
          className="text-xs font-semibold"
          data-testid="series-position"
          style={{ color: "#a78bfa" }}
        >
          Part {position} of {posts.length}
        </div>
        <div
          className="text-xs truncate max-w-[180px]"
          data-testid="series-theme"
          style={{ color: "var(--text-dim)" }}
        >
          {theme}
        </div>
      </div>

      {/* Next */}
      <div className="w-1/3 flex justify-end">
        {next && (
          <Link
            href={`/posts/${next.run_id}`}
            data-testid="series-next"
            className="flex items-center gap-1.5 transition-colors group"
            style={{ color: "#a78bfa", textDecoration: "none" }}
          >
            <span
              className="truncate text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              {next.title}
            </span>
            <span>→</span>
          </Link>
        )}
      </div>
    </div>
  );
}
