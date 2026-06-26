import type { VerifiedSource } from "@/lib/api";

type ClaimType = "STATISTIC" | "QUOTE" | "FACT" | string;

function claimTypeBadgeStyle(claimType: ClaimType): React.CSSProperties {
  switch (claimType) {
    case "STATISTIC":
      return { background: "rgba(245,158,11,0.15)", color: "var(--amber)" };
    case "QUOTE":
      return { background: "rgba(167,139,250,0.15)", color: "var(--purple)" };
    case "FACT":
      return { background: "rgba(34,197,94,0.15)", color: "var(--green)" };
    default:
      return { background: "rgba(150,120,100,0.12)", color: "var(--text-muted)" };
  }
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen).trimEnd() + "…";
}

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
          <li
            key={i}
            data-testid={`source-item-${i}`}
            className="space-y-0.5"
            style={{
              borderRadius: "6px",
              padding: "4px 6px",
              margin: "-4px -6px",
              transition: "background 0.15s",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLLIElement).style.background = "var(--surface-hover)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLLIElement).style.background = "transparent";
            }}
          >
            {src.claim_type && (
              <span
                style={{
                  display: "inline-block",
                  fontSize: "10px",
                  fontWeight: 600,
                  padding: "1px 5px",
                  borderRadius: "4px",
                  letterSpacing: "0.03em",
                  marginBottom: "2px",
                  ...claimTypeBadgeStyle(src.claim_type),
                }}
              >
                {src.claim_type}
              </span>
            )}
            <p
              className="text-xs leading-snug"
              style={{ color: "var(--text-dim)", fontStyle: "italic" }}
            >
              &ldquo;{truncate(src.claim_text, 80)}&rdquo;
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
