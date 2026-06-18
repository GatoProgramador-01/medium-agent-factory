import { render, screen } from "@testing-library/react";
import { SeriesNav } from "./SeriesNav";
import type { SeriesPost } from "@/lib/api";

function makePost(overrides: Partial<SeriesPost> = {}): SeriesPost {
  return {
    run_id: "run-1",
    title: "Post Title",
    series_position: 1,
    status: "approved",
    ...overrides,
  };
}

const three = [
  makePost({ run_id: "run-1", series_position: 1, title: "Part One" }),
  makePost({ run_id: "run-2", series_position: 2, title: "Part Two" }),
  makePost({ run_id: "run-3", series_position: 3, title: "Part Three" }),
];

describe("SeriesNav", () => {
  it("returns null when fewer than 2 posts", () => {
    const { container } = render(
      <SeriesNav posts={[makePost()]} currentRunId="run-1" theme="AI Costs" />
    );
    expect(container.firstChild).toBeNull();
  });

  it("returns null when currentRunId is not in posts", () => {
    const { container } = render(
      <SeriesNav posts={three} currentRunId="run-99" theme="AI Costs" />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders part indicator showing position and total", () => {
    render(<SeriesNav posts={three} currentRunId="run-2" theme="AI Costs" />);
    expect(screen.getByTestId("series-position")).toHaveTextContent("Part 2 of 3");
  });

  it("shows the series theme", () => {
    render(<SeriesNav posts={three} currentRunId="run-2" theme="AI Costs" />);
    expect(screen.getByTestId("series-theme")).toHaveTextContent("AI Costs");
  });

  it("shows prev link when not the first post", () => {
    render(<SeriesNav posts={three} currentRunId="run-2" theme="AI Costs" />);
    const prev = screen.getByTestId("series-prev");
    expect(prev).toBeInTheDocument();
    expect(prev).toHaveAttribute("href", "/posts/run-1");
  });

  it("hides prev link on the first post", () => {
    render(<SeriesNav posts={three} currentRunId="run-1" theme="AI Costs" />);
    expect(screen.queryByTestId("series-prev")).toBeNull();
  });

  it("shows next link when not the last post", () => {
    render(<SeriesNav posts={three} currentRunId="run-2" theme="AI Costs" />);
    const next = screen.getByTestId("series-next");
    expect(next).toBeInTheDocument();
    expect(next).toHaveAttribute("href", "/posts/run-3");
  });

  it("hides next link on the last post", () => {
    render(<SeriesNav posts={three} currentRunId="run-3" theme="AI Costs" />);
    expect(screen.queryByTestId("series-next")).toBeNull();
  });

  it("shows the prev post title", () => {
    render(<SeriesNav posts={three} currentRunId="run-2" theme="AI Costs" />);
    expect(screen.getByTestId("series-prev")).toHaveTextContent("Part One");
  });

  it("shows the next post title", () => {
    render(<SeriesNav posts={three} currentRunId="run-2" theme="AI Costs" />);
    expect(screen.getByTestId("series-next")).toHaveTextContent("Part Three");
  });
});
