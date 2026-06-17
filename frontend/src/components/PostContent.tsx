import React from "react";

function renderInline(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={i}>{part.slice(2, -2)}</strong>
      : <React.Fragment key={i}>{part}</React.Fragment>
  );
}

function ImagePlaceholder({ raw }: { raw: string }) {
  const match = raw.match(/\[IMAGE:\s*([^|[\]]+?)(?:\s*\|\s*alt:\s*(.+?))?\s*\]/);
  const description = match?.[1]?.trim() ?? "Image";
  const altText     = match?.[2]?.trim() ?? description;
  return (
    <figure className="image-placeholder">
      <span className="img-icon">🖼</span>
      <figcaption className="img-label">{altText || description}</figcaption>
    </figure>
  );
}

export function PostContent({ content }: { content: string }) {
  const blocks = content.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);

  return (
    <div className="post-body">
      {blocks.map((block, i) => {
        if (block === "---") {
          return <hr key={i} />;
        }
        if (block.startsWith("## ")) {
          return <h2 key={i}>{block.slice(3)}</h2>;
        }
        if (block.startsWith("### ")) {
          return <h3 key={i}>{block.slice(4)}</h3>;
        }
        if (block.startsWith("[IMAGE:")) {
          return <ImagePlaceholder key={i} raw={block} />;
        }
        // Regular paragraph — handle inline bold
        return <p key={i}>{renderInline(block)}</p>;
      })}
    </div>
  );
}
