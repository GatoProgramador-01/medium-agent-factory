import React from "react";
import type { VerifiedSource } from "@/lib/api";

// Matches: **bold**, *em*, `code`, [text](url), inline backtick
const INLINE_RE =
  /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)]+\))/g;

function makeRenderInline(urlToIndex: Map<string, number>) {
  return function renderInline(text: string): React.ReactNode[] {
    const parts = text.split(INLINE_RE);
    return parts.map((part, i) => {
      // **bold**
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={i}>{part.slice(2, -2)}</strong>;
      }
      // *em* (single asterisk, not **)
      if (
        part.startsWith("*") &&
        part.endsWith("*") &&
        !part.startsWith("**")
      ) {
        return <em key={i}>{part.slice(1, -1)}</em>;
      }
      // `code`
      if (part.startsWith("`") && part.endsWith("`")) {
        return (
          <code key={i} className="post-code">
            {part.slice(1, -1)}
          </code>
        );
      }
      // [text](url)
      const linkMatch = part.match(/^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/);
      if (linkMatch) {
        const [, linkText, url] = linkMatch;
        const idx = urlToIndex.get(url);
        if (idx !== undefined) {
          return (
            <a key={i} href={url} target="_blank" rel="noopener noreferrer">
              {linkText}
              <sup className="cite-ref">[{idx}]</sup>
            </a>
          );
        }
        return (
          <a key={i} href={url} target="_blank" rel="noopener noreferrer">
            {linkText}
          </a>
        );
      }
      return <React.Fragment key={i}>{part}</React.Fragment>;
    });
  };
}

function ImagePlaceholder({ raw }: { raw: string }) {
  const match = raw.match(
    /\[IMAGE:\s*([^|[\]]+?)(?:\s*\|\s*alt:\s*(.+?))?\s*\]/
  );
  const description = match?.[1]?.trim() ?? "Image";
  const altText = match?.[2]?.trim() ?? description;
  return (
    <figure className="image-placeholder">
      <span className="img-icon">🖼</span>
      <figcaption className="img-label">{altText || description}</figcaption>
    </figure>
  );
}

function isListItem(block: string): boolean {
  return block.startsWith("- ") || block.startsWith("* ");
}

export function PostContent({
  content,
  sources,
}: {
  content: string;
  sources?: VerifiedSource[];
}) {
  // Build url → 1-based index map from sources
  const urlToIndex = new Map<string, number>();
  if (sources) {
    sources.forEach((src, i) => {
      urlToIndex.set(src.source_url, i + 1);
    });
  }

  const renderInline = makeRenderInline(urlToIndex);

  const blocks = content
    .split(/\n{2,}/)
    .map((b) => b.trim())
    .filter(Boolean);

  let firstParaRendered = false;
  const rendered: React.ReactNode[] = [];
  let i = 0;

  while (i < blocks.length) {
    const block = blocks[i];
    const key = i;

    // Horizontal rule
    if (block === "---") {
      rendered.push(<hr key={key} />);
      i++;
      continue;
    }

    // ## h2
    if (block.startsWith("## ")) {
      rendered.push(<h2 key={key}>{renderInline(block.slice(3))}</h2>);
      i++;
      continue;
    }

    // ### h3
    if (block.startsWith("### ")) {
      rendered.push(<h3 key={key}>{renderInline(block.slice(4))}</h3>);
      i++;
      continue;
    }

    // [IMAGE:...]
    if (block.startsWith("[IMAGE:")) {
      rendered.push(<ImagePlaceholder key={key} raw={block} />);
      i++;
      continue;
    }

    // > blockquote
    if (block.startsWith("> ")) {
      rendered.push(
        <blockquote key={key} className="post-blockquote">
          {renderInline(block.slice(2))}
        </blockquote>
      );
      i++;
      continue;
    }

    // List: group consecutive list-item blocks into a single <ul>
    if (isListItem(block)) {
      const listItems: React.ReactNode[] = [];
      while (i < blocks.length && isListItem(blocks[i])) {
        const itemText = blocks[i].slice(2); // strip leading "- " or "* "
        listItems.push(<li key={i}>{renderInline(itemText)}</li>);
        i++;
      }
      rendered.push(
        <ul key={key} className="post-list">
          {listItems}
        </ul>
      );
      continue;
    }

    // Regular paragraph
    const paraClass = !firstParaRendered ? "post-first-para" : undefined;
    firstParaRendered = true;
    rendered.push(
      <p key={key} className={paraClass}>
        {renderInline(block)}
      </p>
    );
    i++;
  }

  return (
    <div className="post-body">
      {rendered}
      {sources && sources.length > 0 && (
        <footer className="post-footnotes">
          <h4 className="footnotes-heading">References</h4>
          <ol className="footnotes-list">
            {sources.map((src, idx) => (
              <li key={idx} id={`ref-${idx + 1}`}>
                <span className="footnote-num">[{idx + 1}]</span>
                <span className="footnote-claim">
                  &ldquo;
                  {src.claim_text.slice(0, 100)}
                  {src.claim_text.length > 100 ? "…" : ""}
                  &rdquo;
                </span>
                {" — "}
                <a
                  href={src.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="footnote-link"
                >
                  {src.source_title} ↗
                </a>
              </li>
            ))}
          </ol>
        </footer>
      )}
    </div>
  );
}
