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

describe("PostReaderPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (useParams as jest.Mock).mockReturnValue({ run_id: "run-1" });
    (api.getSeries as jest.Mock).mockResolvedValue(null);
    (api.deletePost as jest.Mock).mockResolvedValue(undefined);
    (api.updateStatus as jest.Mock).mockResolvedValue({ ...MOCK_POST, status: "approved" });
    (api.setMediumUrl as jest.Mock).mockResolvedValue({ ...MOCK_POST });
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
});
