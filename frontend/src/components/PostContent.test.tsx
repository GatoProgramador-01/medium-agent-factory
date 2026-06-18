import { render, screen } from "@testing-library/react";
import { PostContent } from "./PostContent";

describe("PostContent — markdown hyperlinks", () => {
  it("renders [text](url) as an anchor tag", () => {
    render(<PostContent content="See [the report](https://example.com/report) for details." />);
    const link = screen.getByRole("link", { name: /the report/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "https://example.com/report");
  });

  it("link text is exactly the bracketed portion", () => {
    render(<PostContent content="We achieved [73% reduction](https://source.com)." />);
    const link = screen.getByRole("link", { name: "73% reduction" });
    expect(link).toBeInTheDocument();
  });

  it("hyperlink opens in a new tab", () => {
    render(<PostContent content="Read [this](https://example.com)." />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("preserves surrounding plain text", () => {
    render(<PostContent content="Costs dropped from $12,400 to [73% less](https://ex.com) per month." />);
    const para = screen.getByText(/Costs dropped from/);
    expect(para).toHaveTextContent("Costs dropped from $12,400 to 73% less per month.");
  });

  it("renders multiple hyperlinks in the same paragraph", () => {
    const content = "See [Source A](https://a.com) and [Source B](https://b.com).";
    render(<PostContent content={content} />);
    expect(screen.getByRole("link", { name: "Source A" })).toHaveAttribute("href", "https://a.com");
    expect(screen.getByRole("link", { name: "Source B" })).toHaveAttribute("href", "https://b.com");
  });

  it("does not render plain text as a link", () => {
    render(<PostContent content="No links here, just plain text." />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("handles bold and hyperlink in the same paragraph", () => {
    render(<PostContent content="This is **bold** and [a link](https://ex.com)." />);
    expect(screen.getByRole("link", { name: "a link" })).toBeInTheDocument();
    expect(screen.getByText("bold")).toBeInTheDocument();
  });
});
