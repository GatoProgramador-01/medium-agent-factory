import type { VerifiedSource } from "@/lib/api";

export function SourcesPanel({ sources }: { sources: VerifiedSource[] | undefined }) {
  if (!sources || sources.length === 0) return null;

  return (
    <aside
      className="card p-5 space-y-3 text-sm"
      style={{
        minWidth: 220,
        maxWidth: 260,
        background: "linear-gradient(170deg, #091418 0%, #060e12 100%)",
        border: "1px solid rgba(16,185,129,0.2)",
      }}
    >
      <div
        className="text-xs font-medium"
        data-testid="sources-heading"
        style={{ color: "var(--green)" }}
      >
        {sources.length} Verified Source{sources.length !== 1 ? "s" : ""}
      </div>

      <ul className="space-y-3 list-none p-0 m-0">
        {sources.map((src, i) => (
          <li key={i} data-testid={`source-item-${i}`} className="space-y-0.5">
            <p
              className="text-xs leading-snug"
              style={{ color: "var(--text-dim)", fontStyle: "italic" }}
            >
              "{src.claim_text}"
            </p>
            <a
              href={src.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs block truncate transition-colors"
              style={{ color: "var(--green)", textDecoration: "none" }}
              title={src.source_title}
            >
              ↗ {src.source_title}
            </a>
          </li>
        ))}
      </ul>
    </aside>
  );
}
