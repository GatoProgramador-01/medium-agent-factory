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

  describe("Search", () => {
    it("renders a search input", async () => {
      (api.listPosts as jest.Mock).mockResolvedValue([MOCK_POST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getByTestId("post-card")).toBeInTheDocument());
      expect(screen.getByTestId("search-input")).toBeInTheDocument();
    });

    it("filters post cards by title substring", async () => {
      const user = userEvent.setup();
      (api.listPosts as jest.Mock).mockResolvedValue([MOCK_POST, DRAFT_POST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(2));
      await user.type(screen.getByTestId("search-input"), "Draft");
      expect(screen.getAllByTestId("post-card")).toHaveLength(1);
      expect(screen.getByText("Draft Post")).toBeInTheDocument();
    });

    it("search is case-insensitive", async () => {
      const user = userEvent.setup();
      (api.listPosts as jest.Mock).mockResolvedValue([MOCK_POST, DRAFT_POST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(2));
      await user.type(screen.getByTestId("search-input"), "pipeline");
      expect(screen.getAllByTestId("post-card")).toHaveLength(1);
      expect(screen.getByText(MOCK_POST.title)).toBeInTheDocument();
    });

    it("shows empty state when search matches no posts", async () => {
      const user = userEvent.setup();
      (api.listPosts as jest.Mock).mockResolvedValue([MOCK_POST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getByTestId("post-card")).toBeInTheDocument());
      await user.type(screen.getByTestId("search-input"), "xyznotfound");
      expect(screen.queryByTestId("post-card")).not.toBeInTheDocument();
      expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    });

    it("clearing search restores all posts", async () => {
      const user = userEvent.setup();
      (api.listPosts as jest.Mock).mockResolvedValue([MOCK_POST, DRAFT_POST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(2));
      await user.type(screen.getByTestId("search-input"), "Draft");
      expect(screen.getAllByTestId("post-card")).toHaveLength(1);
      await user.clear(screen.getByTestId("search-input"));
      expect(screen.getAllByTestId("post-card")).toHaveLength(2);
    });
  });

  describe("Boost filter", () => {
    const BOOST_POST = {
      ...MOCK_POST,
      run_id: "run-boost",
      title: "Boost Eligible Post",
      quality_report: {
        score: 0.96,
        read_ratio_prediction: 0.88,
        medium_boost_eligible: true,
        issues: [],
        strengths: ["Excellent hook"],
      },
    };
    const NO_BOOST_POST = {
      ...DRAFT_POST,
      run_id: "run-noboost",
      title: "Not Boost Eligible",
      quality_report: {
        score: 0.72,
        read_ratio_prediction: 0.55,
        medium_boost_eligible: false,
        issues: [],
        strengths: [],
      },
    };

    it("renders a Boost filter button", async () => {
      (api.listPosts as jest.Mock).mockResolvedValue([]);
      render(<PostsPage />);
      expect(screen.getByTestId("filter-boost")).toBeInTheDocument();
    });

    it("clicking Boost shows only boost-eligible posts", async () => {
      const user = userEvent.setup();
      (api.listPosts as jest.Mock).mockResolvedValue([BOOST_POST, NO_BOOST_POST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(2));
      await user.click(screen.getByTestId("filter-boost"));
      expect(screen.getAllByTestId("post-card")).toHaveLength(1);
      expect(screen.getByText("Boost Eligible Post")).toBeInTheDocument();
    });

    it("hides non-boost-eligible posts when Boost filter is active", async () => {
      const user = userEvent.setup();
      (api.listPosts as jest.Mock).mockResolvedValue([BOOST_POST, NO_BOOST_POST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(2));
      await user.click(screen.getByTestId("filter-boost"));
      expect(screen.queryByText("Not Boost Eligible")).not.toBeInTheDocument();
    });

    it("clicking Boost again toggles it off and restores all posts", async () => {
      const user = userEvent.setup();
      (api.listPosts as jest.Mock).mockResolvedValue([BOOST_POST, NO_BOOST_POST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(2));
      await user.click(screen.getByTestId("filter-boost"));
      expect(screen.getAllByTestId("post-card")).toHaveLength(1);
      await user.click(screen.getByTestId("filter-boost"));
      expect(screen.getAllByTestId("post-card")).toHaveLength(2);
    });

    it("Boost filter combines with title search", async () => {
      const user = userEvent.setup();
      const ANOTHER_BOOST = { ...BOOST_POST, run_id: "run-boost2", title: "Another Boost Post" };
      (api.listPosts as jest.Mock).mockResolvedValue([BOOST_POST, ANOTHER_BOOST, NO_BOOST_POST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(3));
      await user.click(screen.getByTestId("filter-boost"));
      await user.type(screen.getByTestId("search-input"), "Another");
      expect(screen.getAllByTestId("post-card")).toHaveLength(1);
      expect(screen.getByText("Another Boost Post")).toBeInTheDocument();
    });
  });
});
