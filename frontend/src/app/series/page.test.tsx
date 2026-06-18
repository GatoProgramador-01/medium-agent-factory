import { render, screen, waitFor } from "@testing-library/react";
import SeriesPage from "./page";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: { listSeries: jest.fn() },
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
  beforeEach(() => jest.clearAllMocks());

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
});
