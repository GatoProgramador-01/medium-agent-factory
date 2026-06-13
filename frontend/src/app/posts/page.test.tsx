import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PostsPage from "./page";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: { listPosts: jest.fn() },
}));

// next/link renders a plain <a> in test env — no extra mock needed

const MOCK_POST = {
  run_id: "run-1",
  title: "How I Built a Self-Evaluating Pipeline",
  subtitle: "A subtitle",
  content: "Content body here with enough words to test",
  tags: ["ai", "writing"],
  status: "approved",
  revision_count: 0,
  created_at: "2026-06-13T00:00:00.000Z",
  image_suggestions: [],
  quality_report: {
    score: 0.82,
    read_ratio_prediction: 0.71,
    issues: [{ category: "ai-pattern", severity: "high", location: "intro", suggestion: "Fix it" }],
    strengths: ["Good hook"],
    revision_prompt: "Rewrite the intro",
  },
};

const DRAFT_POST = {
  ...MOCK_POST,
  run_id: "run-2",
  title: "Draft Post",
  status: "draft",
  quality_report: null,
};

describe("PostsPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders the page heading", () => {
    (api.listPosts as jest.Mock).mockResolvedValue([]);
    render(<PostsPage />);
    expect(screen.getByTestId("page-heading")).toHaveTextContent("Posts");
  });

  it("renders all status filter buttons", async () => {
    (api.listPosts as jest.Mock).mockResolvedValue([]);
    render(<PostsPage />);
    expect(screen.getByTestId("filter-all")).toBeInTheDocument();
    expect(screen.getByTestId("filter-draft")).toBeInTheDocument();
    expect(screen.getByTestId("filter-revised")).toBeInTheDocument();
    expect(screen.getByTestId("filter-approved")).toBeInTheDocument();
  });

  it("shows a post card after data loads", async () => {
    (api.listPosts as jest.Mock).mockResolvedValue([MOCK_POST]);
    render(<PostsPage />);
    await waitFor(() => expect(screen.getByTestId("post-card")).toBeInTheDocument());
    expect(screen.getByText(MOCK_POST.title)).toBeInTheDocument();
  });

  it("ScoreBar displays the rounded score percentage", async () => {
    (api.listPosts as jest.Mock).mockResolvedValue([MOCK_POST]);
    render(<PostsPage />);
    await waitFor(() => expect(screen.getByTestId("post-card")).toBeInTheDocument());
    // 0.82 * 100 = 82
    expect(screen.getByText("82")).toBeInTheDocument();
  });

  it("post without quality_report shows 'no score' instead of ScoreBar", async () => {
    (api.listPosts as jest.Mock).mockResolvedValue([DRAFT_POST]);
    render(<PostsPage />);
    await waitFor(() => expect(screen.getByTestId("post-card")).toBeInTheDocument());
    expect(screen.getByText("no score")).toBeInTheDocument();
  });

  it("clicking draft filter calls api.listPosts with status='draft'", async () => {
    const user = userEvent.setup();
    (api.listPosts as jest.Mock).mockResolvedValue([]);
    render(<PostsPage />);
    await user.click(screen.getByTestId("filter-draft"));
    await waitFor(() =>
      expect(api.listPosts).toHaveBeenCalledWith("draft")
    );
  });

  it("clicking all filter calls api.listPosts with undefined", async () => {
    const user = userEvent.setup();
    (api.listPosts as jest.Mock).mockResolvedValue([]);
    render(<PostsPage />);
    // Click draft first to change filter, then click all
    await user.click(screen.getByTestId("filter-draft"));
    await user.click(screen.getByTestId("filter-all"));
    await waitFor(() =>
      expect(api.listPosts).toHaveBeenLastCalledWith(undefined)
    );
  });

  it("shows empty state when no posts match the filter", async () => {
    (api.listPosts as jest.Mock).mockResolvedValue([]);
    render(<PostsPage />);
    await waitFor(() => expect(screen.getByTestId("empty-state")).toBeInTheDocument());
    expect(screen.getByTestId("empty-cta")).toBeInTheDocument();
  });

  it("copy_markdown button is visible when card is present", async () => {
    (api.listPosts as jest.Mock).mockResolvedValue([MOCK_POST]);
    render(<PostsPage />);
    await waitFor(() => expect(screen.getByTestId("post-card")).toBeInTheDocument());
    expect(screen.getByText(/copy_markdown/)).toBeInTheDocument();
  });

  it("copy_markdown button writes markdown to clipboard", async () => {
    const user = userEvent.setup();
    // userEvent.setup() replaces navigator.clipboard with its own stub.
    // Spy on the replacement so we get a proper mock function to assert against.
    const writeTextSpy = jest
      .spyOn(navigator.clipboard, "writeText")
      .mockResolvedValue(undefined);

    (api.listPosts as jest.Mock).mockResolvedValue([MOCK_POST]);
    render(<PostsPage />);
    await waitFor(() => expect(screen.getByTestId("post-card")).toBeInTheDocument());

    await user.click(screen.getByText(/copy_markdown/));

    expect(writeTextSpy).toHaveBeenCalledWith(
      expect.stringContaining(MOCK_POST.title)
    );
  });
});
