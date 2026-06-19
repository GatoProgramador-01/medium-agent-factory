import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useParams, useRouter } from "next/navigation";
import PostReaderPage from "./page";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: {
    getPost: jest.fn(),
    getSeries: jest.fn(),
    deletePost: jest.fn(),
    updateStatus: jest.fn(),
    setMediumUrl: jest.fn(),
    updateTags: jest.fn(),
  },
}));

// DownloadButton uses URL.createObjectURL — stub it for jsdom
beforeAll(() => {
  URL.createObjectURL = jest.fn().mockReturnValue("blob:fake");
  URL.revokeObjectURL = jest.fn();
  jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});

const MOCK_POST = {
  run_id: "run-1",
  title: "How I Saved $2,000 on LLM Inference",
  subtitle: "A real cost breakdown",
  content: "This is the full post content with enough words here.",
  tags: ["ai", "cost", "llm"],
  status: "approved",
  revision_count: 2,
  pull_quote: "The cheapest model that passes quality gates wins.",
  medium_url: "https://medium.com/@user/article-slug",
  created_at: "2026-06-18T10:00:00Z",
  quality_report: {
    score: 0.95,
    read_ratio_prediction: 0.84,
    medium_boost_eligible: true,
    issues: [],
    strengths: ["Strong hook", "Clear takeaways"],
  },
  verified_sources: [],
  quality_history: [],
};

const POST_NO_QUALITY = {
  ...MOCK_POST,
  run_id: "run-2",
  pull_quote: undefined,
  medium_url: undefined,
  quality_report: undefined,
  verified_sources: [],
  quality_history: [],
};

const MOCK_POST_WITH_ISSUES = {
  ...MOCK_POST,
  quality_report: {
    score: 0.78,
    read_ratio_prediction: 0.65,
    medium_boost_eligible: false,
    issues: [
      { category: "Hook Weakness", severity: "HIGH",   suggestion: "Rewrite the hook" },
      { category: "Structure",     severity: "MEDIUM", suggestion: "Add subheadings" },
    ],
    strengths: ["Clear data points"],
  },
};

const MOCK_POST_WITH_SERIES = {
  ...MOCK_POST,
  series_id: "series-abc",
  series_position: 2,
};

describe("PostReaderPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (useParams as jest.Mock).mockReturnValue({ run_id: "run-1" });
    (api.getSeries as jest.Mock).mockResolvedValue(null);
    (api.deletePost as jest.Mock).mockResolvedValue(undefined);
    (api.updateStatus as jest.Mock).mockResolvedValue({ ...MOCK_POST, status: "approved" });
    (api.setMediumUrl as jest.Mock).mockResolvedValue({ ...MOCK_POST });
    (api.updateTags as jest.Mock).mockResolvedValue({ ...MOCK_POST });
  });

  it("shows a loading skeleton before data arrives", () => {
    (api.getPost as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<PostReaderPage />);
    // skeletons are rendered via className, check for the back nav absence and skeleton presence
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
    const skeletons = document.querySelectorAll(".skeleton");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders post title after data loads", async () => {
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: MOCK_POST.title })).toBeInTheDocument()
    );
  });

  it("back link points to /posts", async () => {
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    expect(screen.getByRole("link", { name: /all posts/i })).toHaveAttribute("href", "/posts");
  });

  it("renders post tags", async () => {
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    expect(screen.getByText("ai")).toBeInTheDocument();
    expect(screen.getByText("cost")).toBeInTheDocument();
    expect(screen.getByText("llm")).toBeInTheDocument();
  });

  it("renders pull quote when present", async () => {
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    expect(screen.getByText(/cheapest model/i)).toBeInTheDocument();
  });

  it("shows Copy Markdown button in footer", async () => {
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    expect(screen.getByRole("button", { name: /copy markdown/i })).toBeInTheDocument();
  });

  it("shows Save as Exemplar button in footer", async () => {
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    expect(screen.getByRole("button", { name: /save as exemplar/i })).toBeInTheDocument();
  });

  it("shows Download .md button in footer", async () => {
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    expect(screen.getByRole("button", { name: /download/i })).toBeInTheDocument();
  });

  it("shows View on Medium link when medium_url is present", async () => {
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    const mediumLink = screen.getByRole("link", { name: /view on medium/i });
    expect(mediumLink).toHaveAttribute("href", MOCK_POST.medium_url);
  });

  it("renders quality score when quality_report is present", async () => {
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    // quality score = 0.95 → 95
    expect(screen.getByText("95")).toBeInTheDocument();
  });

  it("sidebar is not shown when post has no quality data", async () => {
    (api.getPost as jest.Mock).mockResolvedValue(POST_NO_QUALITY);
    (useParams as jest.Mock).mockReturnValue({ run_id: "run-2" });
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    // Quality score text (95) should not appear
    expect(screen.queryByText("95")).not.toBeInTheDocument();
  });

  it("shows not-found message when API returns null", async () => {
    (api.getPost as jest.Mock).mockRejectedValue(new Error("404"));
    render(<PostReaderPage />);
    await waitFor(() =>
      expect(screen.getByText(/post not found/i)).toBeInTheDocument()
    );
  });

  it("shows a status select in the meta row", async () => {
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    expect(screen.getByTestId("status-picker")).toBeInTheDocument();
  });

  it("status select shows the current post status", async () => {
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    expect(screen.getByTestId("status-picker")).toHaveValue("approved");
  });

  it("changing status calls api.updateStatus with run_id and new status", async () => {
    const user = userEvent.setup();
    (api.getPost as jest.Mock).mockResolvedValue({ ...MOCK_POST, status: "draft" });
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    await user.selectOptions(screen.getByTestId("status-picker"), "approved");
    expect(api.updateStatus).toHaveBeenCalledWith("run-1", "approved");
  });

  it("shows Delete button in footer", async () => {
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    expect(screen.getByRole("button", { name: /^delete$/i })).toBeInTheDocument();
  });

  it("clicking Delete shows confirmation UI", async () => {
    const user = userEvent.setup();
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    await user.click(screen.getByRole("button", { name: /^delete$/i }));
    expect(screen.getByRole("button", { name: /confirm/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
  });

  it("confirming Delete calls api.deletePost with the run_id", async () => {
    const user = userEvent.setup();
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    await user.click(screen.getByRole("button", { name: /^delete$/i }));
    await user.click(screen.getByRole("button", { name: /confirm/i }));
    expect(api.deletePost).toHaveBeenCalledWith("run-1");
  });

  it("renders existing post tags", async () => {
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    expect(screen.getByTestId("tag-pill-ai")).toBeInTheDocument();
    expect(screen.getByTestId("tag-pill-cost")).toBeInTheDocument();
    expect(screen.getByTestId("tag-pill-llm")).toBeInTheDocument();
  });

  it("each tag pill has a remove button", async () => {
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByTestId("tag-pill-ai"));
    expect(screen.getByTestId("remove-tag-ai")).toBeInTheDocument();
  });

  it("clicking × on a tag removes it and calls api.updateTags", async () => {
    const user = userEvent.setup();
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByTestId("remove-tag-ai"));
    await user.click(screen.getByTestId("remove-tag-ai"));
    expect(api.updateTags).toHaveBeenCalledWith("run-1", ["cost", "llm"]);
    expect(screen.queryByTestId("tag-pill-ai")).not.toBeInTheDocument();
  });

  it("shows an add-tag input field", async () => {
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    expect(screen.getByTestId("add-tag-input")).toBeInTheDocument();
  });

  it("typing a tag and pressing Enter adds it and calls api.updateTags", async () => {
    const user = userEvent.setup();
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByTestId("add-tag-input"));
    await user.type(screen.getByTestId("add-tag-input"), "python{Enter}");
    expect(api.updateTags).toHaveBeenCalledWith("run-1", ["ai", "cost", "llm", "python"]);
    expect(screen.getByTestId("tag-pill-python")).toBeInTheDocument();
  });

  it("shows Add Medium link button when medium_url is not set", async () => {
    (api.getPost as jest.Mock).mockResolvedValue({ ...MOCK_POST, medium_url: undefined });
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    expect(screen.getByTestId("add-medium-link")).toBeInTheDocument();
  });

  it("clicking Add Medium link shows a URL input", async () => {
    const user = userEvent.setup();
    (api.getPost as jest.Mock).mockResolvedValue({ ...MOCK_POST, medium_url: undefined });
    render(<PostReaderPage />);
    await waitFor(() => screen.getByTestId("add-medium-link"));
    await user.click(screen.getByTestId("add-medium-link"));
    expect(screen.getByTestId("medium-url-input")).toBeInTheDocument();
  });

  it("clicking Save calls api.setMediumUrl with the run_id and URL", async () => {
    const user = userEvent.setup();
    (api.getPost as jest.Mock).mockResolvedValue({ ...MOCK_POST, medium_url: undefined });
    render(<PostReaderPage />);
    await waitFor(() => screen.getByTestId("add-medium-link"));
    await user.click(screen.getByTestId("add-medium-link"));
    await user.type(screen.getByTestId("medium-url-input"), "https://medium.com/@user/my-post");
    await user.click(screen.getByTestId("save-medium-link"));
    expect(api.setMediumUrl).toHaveBeenCalledWith("run-1", "https://medium.com/@user/my-post");
  });

  it("after saving medium URL the link appears in the footer", async () => {
    const user = userEvent.setup();
    const savedUrl = "https://medium.com/@user/saved-post";
    (api.getPost as jest.Mock).mockResolvedValue({ ...MOCK_POST, medium_url: undefined });
    (api.setMediumUrl as jest.Mock).mockResolvedValue({ ...MOCK_POST, medium_url: savedUrl });
    render(<PostReaderPage />);
    await waitFor(() => screen.getByTestId("add-medium-link"));
    await user.click(screen.getByTestId("add-medium-link"));
    await user.type(screen.getByTestId("medium-url-input"), savedUrl);
    await user.click(screen.getByTestId("save-medium-link"));
    await waitFor(() => expect(screen.getByRole("link", { name: /view on medium/i })).toBeInTheDocument());
  });

  it("after successful delete redirects to /posts", async () => {
    const push = jest.fn();
    (useRouter as jest.Mock).mockReturnValue({ push, replace: jest.fn(), back: jest.fn() });
    const user = userEvent.setup();
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    await user.click(screen.getByRole("button", { name: /^delete$/i }));
    await user.click(screen.getByRole("button", { name: /confirm/i }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/posts"));
  });

  it("clicking Cancel on delete confirmation returns to idle state", async () => {
    const user = userEvent.setup();
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
    render(<PostReaderPage />);
    await waitFor(() => screen.getByRole("heading", { name: MOCK_POST.title }));
    await user.click(screen.getByRole("button", { name: /^delete$/i }));
    expect(screen.getByRole("button", { name: /confirm/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.getByRole("button", { name: /^delete$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /confirm/i })).not.toBeInTheDocument();
  });

  it("calls api.getSeries with the series_id when post has series_id", async () => {
    (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST_WITH_SERIES);
    (api.getSeries as jest.Mock).mockResolvedValue({ series_id: "series-abc", theme: "AI Series", status: "completed", posts: [] });
    render(<PostReaderPage />);
    await waitFor(() => expect(api.getSeries).toHaveBeenCalledWith("series-abc"));
  });

  describe("QualityPanel content", () => {
    it("shows read_ratio_prediction in the sidebar", async () => {
      (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
      render(<PostReaderPage />);
      // read_ratio_prediction: 0.84 → 84%
      await waitFor(() => expect(screen.getByTestId("quality-read-ratio")).toBeInTheDocument());
      expect(screen.getByTestId("quality-read-ratio")).toHaveTextContent("84%");
    });

    it("shows boost_eligible Yes badge when eligible", async () => {
      (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
      render(<PostReaderPage />);
      await waitFor(() => expect(screen.getByTestId("quality-boost-eligible")).toBeInTheDocument());
      expect(screen.getByTestId("quality-boost-eligible")).toHaveTextContent("Yes");
    });

    it("shows boost_eligible No badge when not eligible", async () => {
      (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST_WITH_ISSUES);
      render(<PostReaderPage />);
      await waitFor(() => expect(screen.getByTestId("quality-boost-eligible")).toBeInTheDocument());
      expect(screen.getByTestId("quality-boost-eligible")).toHaveTextContent("No");
    });

    it("renders quality issue items with category and severity", async () => {
      (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST_WITH_ISSUES);
      render(<PostReaderPage />);
      await waitFor(() => expect(screen.getByTestId("quality-issue-0")).toBeInTheDocument());
      expect(screen.getByTestId("quality-issue-0")).toHaveTextContent("HIGH");
      expect(screen.getByTestId("quality-issue-0")).toHaveTextContent("Hook Weakness");
      expect(screen.getByTestId("quality-issue-1")).toHaveTextContent("MEDIUM");
      expect(screen.getByTestId("quality-issue-1")).toHaveTextContent("Structure");
    });

    it("renders quality strengths text", async () => {
      (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
      render(<PostReaderPage />);
      await waitFor(() => expect(screen.getByTestId("quality-strength-0")).toBeInTheDocument());
      expect(screen.getByTestId("quality-strength-0")).toHaveTextContent("Strong hook");
      expect(screen.getByTestId("quality-strength-1")).toHaveTextContent("Clear takeaways");
    });
  });

  describe("post meta row", () => {
    it("shows word count in the meta row", async () => {
      (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
      render(<PostReaderPage />);
      await waitFor(() => expect(screen.getByTestId("word-count")).toBeInTheDocument());
      expect(screen.getByTestId("word-count")).toHaveTextContent("words");
    });

    it("shows reading time estimate in the meta row", async () => {
      (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST);
      render(<PostReaderPage />);
      await waitFor(() => expect(screen.getByTestId("read-time")).toBeInTheDocument());
      expect(screen.getByTestId("read-time")).toHaveTextContent("min read");
    });

    it("shows series position badge when post is part of a series", async () => {
      (api.getPost as jest.Mock).mockResolvedValue(MOCK_POST_WITH_SERIES);
      render(<PostReaderPage />);
      await waitFor(() => expect(screen.getByTestId("series-position-badge")).toBeInTheDocument());
      expect(screen.getByTestId("series-position-badge")).toHaveTextContent("Series Part 2");
    });
  });
});
