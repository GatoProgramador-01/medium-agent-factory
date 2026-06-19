import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SeriesPage from "./page";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: {
    listSeries: jest.fn(),
    deleteSeries: jest.fn(),
  },
}));

const mockListSeries = api.listSeries as jest.MockedFunction<typeof api.listSeries>;

const fakeSeries = [
  {
    series_id: "series-abc",
    theme: "LLM Cost Breakdown",
    status: "completed",
    created_at: "2026-06-18T10:00:00Z",
    posts: [
      { run_id: "run-1", title: "Part One Title", series_position: 1, status: "approved", quality_score: 0.93 },
      { run_id: "run-2", title: "Part Two Title", series_position: 2, status: "approved", quality_score: 0.97 },
    ],
  },
];

describe("SeriesPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.deleteSeries as jest.Mock).mockResolvedValue(undefined);
  });

  it("renders page heading", async () => {
    mockListSeries.mockResolvedValue(fakeSeries);
    render(<SeriesPage />);
    expect(screen.getByTestId("page-heading")).toBeInTheDocument();
  });

  it("shows series theme after load", async () => {
    mockListSeries.mockResolvedValue(fakeSeries);
    render(<SeriesPage />);
    await waitFor(() => screen.getByTestId("series-card-series-abc"));
    expect(screen.getByTestId("series-card-series-abc")).toHaveTextContent("LLM Cost Breakdown");
  });

  it("shows post count for each series", async () => {
    mockListSeries.mockResolvedValue(fakeSeries);
    render(<SeriesPage />);
    await waitFor(() => screen.getByTestId("series-card-series-abc"));
    expect(screen.getByTestId("series-card-series-abc")).toHaveTextContent("2");
  });

  it("renders a link for each post part", async () => {
    mockListSeries.mockResolvedValue(fakeSeries);
    render(<SeriesPage />);
    await waitFor(() => screen.getByTestId("series-part-run-1"));
    expect(screen.getByTestId("series-part-run-1")).toHaveAttribute("href", "/posts/run-1");
    expect(screen.getByTestId("series-part-run-2")).toHaveAttribute("href", "/posts/run-2");
  });

  it("shows empty state when no series exist", async () => {
    mockListSeries.mockResolvedValue([]);
    render(<SeriesPage />);
    await waitFor(() => screen.getByTestId("empty-state"));
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
  });

  it("shows a delete button on each series card", async () => {
    mockListSeries.mockResolvedValue(fakeSeries);
    render(<SeriesPage />);
    await waitFor(() => screen.getByTestId("series-card-series-abc"));
    expect(screen.getByTestId("delete-series-series-abc")).toBeInTheDocument();
  });

  it("clicking delete calls api.deleteSeries with the series_id", async () => {
    const user = userEvent.setup();
    mockListSeries.mockResolvedValue(fakeSeries);
    render(<SeriesPage />);
    await waitFor(() => screen.getByTestId("delete-series-series-abc"));
    await user.click(screen.getByTestId("delete-series-series-abc"));
    expect(api.deleteSeries).toHaveBeenCalledWith("series-abc");
  });

  it("shows quality score for each post part", async () => {
    mockListSeries.mockResolvedValue(fakeSeries);
    render(<SeriesPage />);
    await waitFor(() => screen.getByTestId("series-part-run-1"));
    // quality_score: 0.93 → 93; 0.97 → 97
    expect(screen.getByTestId("series-part-run-1")).toHaveTextContent("93");
    expect(screen.getByTestId("series-part-run-2")).toHaveTextContent("97");
  });

  it("shows series position number (#1, #2) for each post part", async () => {
    mockListSeries.mockResolvedValue(fakeSeries);
    render(<SeriesPage />);
    await waitFor(() => screen.getByTestId("series-part-run-1"));
    expect(screen.getByTestId("series-part-run-1")).toHaveTextContent("#1");
    expect(screen.getByTestId("series-part-run-2")).toHaveTextContent("#2");
  });

  it("shows the series status badge text", async () => {
    mockListSeries.mockResolvedValue(fakeSeries);
    render(<SeriesPage />);
    await waitFor(() => screen.getByTestId("series-card-series-abc"));
    expect(screen.getByTestId("series-card-series-abc")).toHaveTextContent("completed");
  });

  it("shows '1 part' (singular) when series has exactly one post", async () => {
    const singlePostSeries = [{ ...fakeSeries[0], posts: [fakeSeries[0].posts[0]] }];
    mockListSeries.mockResolvedValue(singlePostSeries);
    render(<SeriesPage />);
    await waitFor(() => screen.getByTestId("series-card-series-abc"));
    expect(screen.getByTestId("series-card-series-abc")).toHaveTextContent("1 part");
    expect(screen.getByTestId("series-card-series-abc")).not.toHaveTextContent("1 parts");
  });

  it("shows '2 parts' plural for a series with 2 posts", async () => {
    mockListSeries.mockResolvedValue(fakeSeries);
    render(<SeriesPage />);
    await waitFor(() => screen.getByTestId("series-card-series-abc"));
    expect(screen.getByTestId("series-card-series-abc")).toHaveTextContent("2 parts");
  });

  it("shows '0 parts' for a series with no posts", async () => {
    const emptySeries = [{ ...fakeSeries[0], posts: [] }];
    mockListSeries.mockResolvedValue(emptySeries);
    render(<SeriesPage />);
    await waitFor(() => screen.getByTestId("series-card-series-abc"));
    expect(screen.getByTestId("series-card-series-abc")).toHaveTextContent("0 parts");
  });

  it("shows loading skeletons before data arrives", () => {
    mockListSeries.mockReturnValue(new Promise(() => {}));
    render(<SeriesPage />);
    const skeletons = document.querySelectorAll(".skeleton");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("deleted series card disappears from the list", async () => {
    const user = userEvent.setup();
    const twoSeries = [
      ...fakeSeries,
      { series_id: "series-xyz", theme: "Second Series", status: "completed", created_at: "2026-06-17T10:00:00Z", posts: [] },
    ];
    mockListSeries.mockResolvedValue(twoSeries);
    render(<SeriesPage />);
    await waitFor(() => expect(screen.getAllByTestId(/series-card-/)).toHaveLength(2));
    await user.click(screen.getByTestId("delete-series-series-abc"));
    await waitFor(() => expect(screen.queryByTestId("series-card-series-abc")).not.toBeInTheDocument());
    expect(screen.getByTestId("series-card-series-xyz")).toBeInTheDocument();
  });
});
