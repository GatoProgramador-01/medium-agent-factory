import { render, screen, waitFor } from "@testing-library/react";
import DashboardPage from "./page";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: {
    summary: jest.fn(),
    listPosts: jest.fn(),
    listExemplars: jest.fn(),
  },
}));

const MOCK_SUMMARY = {
  pipeline_runs: 12,
  completed_runs: 10,
  total_posts: 8,
  published_posts: 3,
  total_tokens: 450000,
  total_cost_usd: 0.0842,
};

const MOCK_POSTS = [
  {
    run_id: "run-1",
    title: "How I Cut LLM Costs by 80%",
    status: "approved",
    revision_count: 2,
    tags: ["ai", "cost"],
    content: "some content",
    created_at: "2026-06-18T10:00:00Z",
    quality_report: { score: 0.97, read_ratio_prediction: 0.82, medium_boost_eligible: true, issues: [], strengths: [] },
  },
  {
    run_id: "run-2",
    title: "LangGraph in Production",
    status: "approved",
    revision_count: 1,
    tags: ["langchain"],
    content: "other content",
    created_at: "2026-06-17T09:00:00Z",
    quality_report: { score: 0.88, read_ratio_prediction: 0.75, medium_boost_eligible: false, issues: [], strengths: [] },
  },
];

describe("DashboardPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.summary as jest.Mock).mockResolvedValue(MOCK_SUMMARY);
    (api.listPosts as jest.Mock).mockResolvedValue(MOCK_POSTS);
    (api.listExemplars as jest.Mock).mockResolvedValue([]);
  });

  it("renders page heading", () => {
    render(<DashboardPage />);
    expect(screen.getByTestId("page-heading")).toBeInTheDocument();
  });

  it("renders CTA buttons", () => {
    render(<DashboardPage />);
    expect(screen.getByTestId("cta-run-pipeline")).toBeInTheDocument();
    expect(screen.getByTestId("cta-view-posts")).toBeInTheDocument();
  });

  it("shows stat cards after data loads", async () => {
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByText("12")).toBeInTheDocument());
    expect(screen.getByText("10")).toBeInTheDocument();
  });

  it("shows recent-posts section after load", async () => {
    render(<DashboardPage />);
    await waitFor(() => screen.getByTestId("recent-posts"));
    expect(screen.getByTestId("recent-posts")).toBeInTheDocument();
  });

  it("renders a card for each recent post", async () => {
    render(<DashboardPage />);
    await waitFor(() => screen.getByTestId("recent-post-run-1"));
    expect(screen.getByTestId("recent-post-run-1")).toBeInTheDocument();
    expect(screen.getByTestId("recent-post-run-2")).toBeInTheDocument();
  });

  it("shows post title in each recent-post card", async () => {
    render(<DashboardPage />);
    await waitFor(() => screen.getByTestId("recent-post-run-1"));
    expect(screen.getByTestId("recent-post-run-1")).toHaveTextContent("How I Cut LLM Costs by 80%");
  });

  it("recent-post card links to the post reader", async () => {
    render(<DashboardPage />);
    await waitFor(() => screen.getByTestId("recent-post-run-1"));
    expect(screen.getByTestId("recent-post-run-1").closest("a")).toHaveAttribute("href", "/posts/run-1");
  });

  it("shows quality score inside recent-post card", async () => {
    render(<DashboardPage />);
    await waitFor(() => screen.getByTestId("recent-post-run-1"));
    expect(screen.getByTestId("recent-post-run-1")).toHaveTextContent("97");
  });

  it("shows empty recent-posts message when no posts exist", async () => {
    (api.listPosts as jest.Mock).mockResolvedValue([]);
    render(<DashboardPage />);
    await waitFor(() => screen.getByTestId("recent-posts-empty"));
    expect(screen.getByTestId("recent-posts-empty")).toBeInTheDocument();
  });

  it("shows exemplars saved stat card after data loads", async () => {
    const MOCK_EXEMPLARS = [
      { run_id: "e-1", title: "Exemplar One", tags: [], score: 0.97, read_ratio: 0.82,
        hook_score: 0.95, hook: "hook", intro_word_count: 90, word_count: 1720, created_at: "2026-06-18T10:00:00Z" },
      { run_id: "e-2", title: "Exemplar Two", tags: [], score: 0.96, read_ratio: 0.80,
        hook_score: 0.93, hook: "hook2", intro_word_count: 85, word_count: 1650, created_at: "2026-06-17T10:00:00Z" },
    ];
    (api.listExemplars as jest.Mock).mockResolvedValue(MOCK_EXEMPLARS);
    render(<DashboardPage />);
    await waitFor(() => screen.getByTestId("stat-exemplars"));
    expect(screen.getByTestId("stat-exemplars")).toHaveTextContent("2");
  });
});
