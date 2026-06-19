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
  tags: ["writing"],
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
      expect(api.listPosts).toHaveBeenCalledWith("draft", 0)
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
      expect(api.listPosts).toHaveBeenLastCalledWith(undefined, 0)
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

  describe("Tag filter", () => {
    const AI_POST   = { ...MOCK_POST, run_id: "run-ai",   title: "AI Post",   tags: ["ai", "llm"]       };
    const COST_POST = { ...MOCK_POST, run_id: "run-cost",  title: "Cost Post",  tags: ["cost", "llm"]     };
    const MISC_POST = { ...MOCK_POST, run_id: "run-misc",  title: "Misc Post",  tags: ["writing"]          };

    it("clicking a tag pill filters posts to those sharing that tag", async () => {
      const user = userEvent.setup();
      (api.listPosts as jest.Mock).mockResolvedValue([AI_POST, COST_POST, MISC_POST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(3));
      await user.click(screen.getAllByTestId("tag-llm")[0]);
      expect(screen.getAllByTestId("post-card")).toHaveLength(2);
      expect(screen.getByText("AI Post")).toBeInTheDocument();
      expect(screen.getByText("Cost Post")).toBeInTheDocument();
    });

    it("hides posts that do not have the selected tag", async () => {
      const user = userEvent.setup();
      (api.listPosts as jest.Mock).mockResolvedValue([AI_POST, MISC_POST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(2));
      await user.click(screen.getByTestId("tag-ai"));
      expect(screen.queryByText("Misc Post")).not.toBeInTheDocument();
    });

    it("shows active tag chip in the filter bar", async () => {
      const user = userEvent.setup();
      (api.listPosts as jest.Mock).mockResolvedValue([AI_POST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getByTestId("post-card")).toBeInTheDocument());
      await user.click(screen.getByTestId("tag-ai"));
      expect(screen.getByTestId("active-tag-filter")).toBeInTheDocument();
    });

    it("clicking the clear-tag button removes the tag filter", async () => {
      const user = userEvent.setup();
      (api.listPosts as jest.Mock).mockResolvedValue([AI_POST, MISC_POST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(2));
      await user.click(screen.getByTestId("tag-ai"));
      expect(screen.getAllByTestId("post-card")).toHaveLength(1);
      await user.click(screen.getByTestId("clear-tag-filter"));
      expect(screen.getAllByTestId("post-card")).toHaveLength(2);
    });

    it("tag filter combines with title search", async () => {
      const user = userEvent.setup();
      const SECOND_LLM = { ...MOCK_POST, run_id: "run-llm2", title: "Second LLM Post", tags: ["llm"] };
      (api.listPosts as jest.Mock).mockResolvedValue([AI_POST, COST_POST, SECOND_LLM]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(3));
      await user.click(screen.getAllByTestId("tag-llm")[0]);
      await user.type(screen.getByTestId("search-input"), "Cost");
      expect(screen.getAllByTestId("post-card")).toHaveLength(1);
      expect(screen.getByText("Cost Post")).toBeInTheDocument();
    });
  });

  describe("Sort", () => {
    const OLD_POST  = { ...MOCK_POST, run_id: "run-old",  title: "Oldest Post",       created_at: "2026-05-01T00:00:00Z", quality_report: { ...MOCK_POST.quality_report, score: 0.72 } };
    const MID_POST  = { ...MOCK_POST, run_id: "run-mid",  title: "Middle Post",        created_at: "2026-05-15T00:00:00Z", quality_report: { ...MOCK_POST.quality_report, score: 0.88 } };
    const NEW_POST  = { ...MOCK_POST, run_id: "run-new",  title: "Newest Post",        created_at: "2026-06-01T00:00:00Z", quality_report: { ...MOCK_POST.quality_report, score: 0.95 } };

    it("renders a sort select control", async () => {
      (api.listPosts as jest.Mock).mockResolvedValue([]);
      render(<PostsPage />);
      expect(screen.getByTestId("sort-select")).toBeInTheDocument();
    });

    it("default order is newest first", async () => {
      (api.listPosts as jest.Mock).mockResolvedValue([OLD_POST, NEW_POST, MID_POST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(3));
      const cards = screen.getAllByTestId("post-card");
      expect(cards[0]).toHaveTextContent("Newest Post");
      expect(cards[2]).toHaveTextContent("Oldest Post");
    });

    it("sort oldest shows oldest post first", async () => {
      const user = userEvent.setup();
      (api.listPosts as jest.Mock).mockResolvedValue([OLD_POST, NEW_POST, MID_POST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(3));
      await user.selectOptions(screen.getByTestId("sort-select"), "oldest");
      const cards = screen.getAllByTestId("post-card");
      expect(cards[0]).toHaveTextContent("Oldest Post");
      expect(cards[2]).toHaveTextContent("Newest Post");
    });

    it("sort score-desc shows highest score first", async () => {
      const user = userEvent.setup();
      (api.listPosts as jest.Mock).mockResolvedValue([OLD_POST, NEW_POST, MID_POST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(3));
      await user.selectOptions(screen.getByTestId("sort-select"), "score-desc");
      const cards = screen.getAllByTestId("post-card");
      expect(cards[0]).toHaveTextContent("Newest Post");   // score 0.95
      expect(cards[2]).toHaveTextContent("Oldest Post");   // score 0.72
    });

    it("sort score-asc shows lowest score first", async () => {
      const user = userEvent.setup();
      (api.listPosts as jest.Mock).mockResolvedValue([OLD_POST, NEW_POST, MID_POST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(3));
      await user.selectOptions(screen.getByTestId("sort-select"), "score-asc");
      const cards = screen.getAllByTestId("post-card");
      expect(cards[0]).toHaveTextContent("Oldest Post");   // score 0.72
      expect(cards[2]).toHaveTextContent("Newest Post");   // score 0.95
    });

    it("sort composes with boost filter", async () => {
      const user = userEvent.setup();
      const BOOST_A = { ...OLD_POST, run_id: "ba", title: "Boost Old",  quality_report: { ...OLD_POST.quality_report,  score: 0.72, medium_boost_eligible: true } };
      const BOOST_B = { ...NEW_POST, run_id: "bb", title: "Boost New",  quality_report: { ...NEW_POST.quality_report,  score: 0.95, medium_boost_eligible: true } };
      const NO_BOOST = { ...MID_POST, run_id: "nb", title: "No Boost",  quality_report: { ...MID_POST.quality_report, score: 0.88, medium_boost_eligible: false } };
      (api.listPosts as jest.Mock).mockResolvedValue([BOOST_A, BOOST_B, NO_BOOST]);
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(3));
      await user.click(screen.getByTestId("filter-boost"));
      await user.selectOptions(screen.getByTestId("sort-select"), "score-asc");
      const cards = screen.getAllByTestId("post-card");
      expect(cards).toHaveLength(2);
      expect(cards[0]).toHaveTextContent("Boost Old");
      expect(cards[1]).toHaveTextContent("Boost New");
    });
  });

  describe("Word count badge", () => {
    const wcPost = (wordCount: number) => ({
      ...MOCK_POST,
      run_id: "run-wc",
      word_count: wordCount,
    });

    it("displays word count on a post card", async () => {
      (api.listPosts as jest.Mock).mockResolvedValue([wcPost(1700)]);
      render(<PostsPage />);
      await waitFor(() => screen.getByTestId("word-count-run-wc"));
      expect(screen.getByTestId("word-count-run-wc")).toHaveTextContent("1,700");
    });

    it("shows green when word count >= 1700", async () => {
      (api.listPosts as jest.Mock).mockResolvedValue([wcPost(1700)]);
      render(<PostsPage />);
      await waitFor(() => screen.getByTestId("word-count-run-wc"));
      expect(screen.getByTestId("word-count-run-wc")).toHaveStyle({ color: "var(--green)" });
    });

    it("shows amber when word count is 1300–1699", async () => {
      (api.listPosts as jest.Mock).mockResolvedValue([wcPost(1450)]);
      render(<PostsPage />);
      await waitFor(() => screen.getByTestId("word-count-run-wc"));
      expect(screen.getByTestId("word-count-run-wc")).toHaveStyle({ color: "var(--amber)" });
    });

    it("shows red when word count < 1300", async () => {
      (api.listPosts as jest.Mock).mockResolvedValue([wcPost(1100)]);
      render(<PostsPage />);
      await waitFor(() => screen.getByTestId("word-count-run-wc"));
      expect(screen.getByTestId("word-count-run-wc")).toHaveStyle({ color: "var(--red)" });
    });

    it("prefers post.word_count over content-computed count", async () => {
      const post = { ...wcPost(1800), content: "just five words here" };
      (api.listPosts as jest.Mock).mockResolvedValue([post]);
      render(<PostsPage />);
      await waitFor(() => screen.getByTestId("word-count-run-wc"));
      expect(screen.getByTestId("word-count-run-wc")).toHaveTextContent("1,800");
      expect(screen.getByTestId("word-count-run-wc")).toHaveStyle({ color: "var(--green)" });
    });

    it("falls back to computed count when word_count field is absent", async () => {
      const post = { ...MOCK_POST, run_id: "run-wc", content: Array(1700).fill("word").join(" "), word_count: undefined };
      (api.listPosts as jest.Mock).mockResolvedValue([post]);
      render(<PostsPage />);
      await waitFor(() => screen.getByTestId("word-count-run-wc"));
      expect(screen.getByTestId("word-count-run-wc")).toHaveTextContent("1,700");
    });
  });

  describe("Load more", () => {
    function makePosts(count: number, startId = 0) {
      return Array.from({ length: count }, (_, i) => ({
        ...MOCK_POST,
        run_id: `run-p${startId + i}`,
        title: `Post ${startId + i}`,
        tags: [],
      }));
    }

    it("shows Load more button when a full page is returned", async () => {
      (api.listPosts as jest.Mock).mockResolvedValue(makePosts(20));
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(20));
      expect(screen.getByTestId("load-more")).toBeInTheDocument();
    });

    it("hides Load more when fewer than 20 posts are returned", async () => {
      (api.listPosts as jest.Mock).mockResolvedValue(makePosts(5));
      render(<PostsPage />);
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(5));
      expect(screen.queryByTestId("load-more")).not.toBeInTheDocument();
    });

    it("clicking Load more fetches next page with offset 20", async () => {
      const user = userEvent.setup();
      (api.listPosts as jest.Mock)
        .mockResolvedValueOnce(makePosts(20))
        .mockResolvedValueOnce(makePosts(5, 20));
      render(<PostsPage />);
      await waitFor(() => screen.getByTestId("load-more"));
      await user.click(screen.getByTestId("load-more"));
      expect(api.listPosts).toHaveBeenNthCalledWith(2, undefined, 20);
    });

    it("appended posts are shown after clicking Load more", async () => {
      const user = userEvent.setup();
      (api.listPosts as jest.Mock)
        .mockResolvedValueOnce(makePosts(20))
        .mockResolvedValueOnce(makePosts(5, 20));
      render(<PostsPage />);
      await waitFor(() => screen.getByTestId("load-more"));
      await user.click(screen.getByTestId("load-more"));
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(25));
    });

    it("hides Load more after last page has fewer than 20 posts", async () => {
      const user = userEvent.setup();
      (api.listPosts as jest.Mock)
        .mockResolvedValueOnce(makePosts(20))
        .mockResolvedValueOnce(makePosts(3, 20));
      render(<PostsPage />);
      await waitFor(() => screen.getByTestId("load-more"));
      await user.click(screen.getByTestId("load-more"));
      await waitFor(() => expect(screen.getAllByTestId("post-card")).toHaveLength(23));
      expect(screen.queryByTestId("load-more")).not.toBeInTheDocument();
    });
  });
});
