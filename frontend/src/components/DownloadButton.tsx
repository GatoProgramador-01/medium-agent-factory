"use client";

import { useState } from "react";

function slugify(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function DownloadButton({ title, content }: { title: string; content: string }) {
  const [downloaded, setDownloaded] = useState(false);

  function handleDownload() {
    const markdown = `# ${title}\n\n${content}`;
    const blob = new Blob([markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${slugify(title)}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setDownloaded(true);
    setTimeout(() => setDownloaded(false), 2000);
  }

  return (
    <button onClick={handleDownload} className="btn text-sm">
      {downloaded ? "Downloaded!" : "Download .md"}
    </button>
  );
}
