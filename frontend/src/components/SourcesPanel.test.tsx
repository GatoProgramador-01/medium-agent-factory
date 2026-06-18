import { render, screen } from "@testing-library/react";
import { SourcesPanel } from "./SourcesPanel";
import type { VerifiedSource } from "@/lib/api";

const SOURCES: VerifiedSource[] = [
  {
    claim_text: "73% reduction in inference costs",
    source_url: "https://deepseek.com/report",
    source_title: "DeepSeek Cost Analysis 2025",
    claim_type: "percentage",
  },
  {
    claim_text: "$0.25 per million input tokens",
    source_url: "https://anthropic.com/pricing",
    source_title: "Anthropic Pricing",
    claim_type: "dollar_amount",
  },
];

describe("SourcesPanel", () => {
  it("renders the 'Verified Sources' heading", () => {
    render(<SourcesPanel sources={SOURCES} />);
    expect(screen.getByText(/verified sources/i)).toBeInTheDocument();
  });

  it("renders one entry per source", () => {
    render(<SourcesPanel sources={SOURCES} />);
    expect(screen.getByTestId("source-item-0")).toBeInTheDocument();
    expect(screen.getByTestId("source-item-1")).toBeInTheDocument();
  });

  it("renders the source title as a link", () => {
    render(<SourcesPanel sources={SOURCES} />);
    const link = screen.getByRole("link", { name: /DeepSeek Cost Analysis 2025/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "https://deepseek.com/report");
  });

  it("source links open in a new tab", () => {
    render(<SourcesPanel sources={SOURCES} />);
    const links = screen.getAllByRole("link");
    links.forEach((link) => {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    });
  });

  it("renders the claim text for each source", () => {
    render(<SourcesPanel sources={SOURCES} />);
    expect(screen.getByText(/73% reduction in inference costs/i)).toBeInTheDocument();
    expect(screen.getByText(/\$0\.25 per million input tokens/i)).toBeInTheDocument();
  });

  it("shows source count in heading", () => {
    render(<SourcesPanel sources={SOURCES} />);
    // "2 Verified Sources" or "Verified Sources (2)"
    expect(screen.getByTestId("sources-heading")).toHaveTextContent("2");
  });

  it("returns null when sources array is empty", () => {
    const { container } = render(<SourcesPanel sources={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("returns null when sources is undefined", () => {
    // @ts-expect-error testing undefined path
    const { container } = render(<SourcesPanel sources={undefined} />);
    expect(container.firstChild).toBeNull();
  });
});
