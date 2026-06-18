import { render, screen, waitFor } from "@testing-library/react";
import ExemplarsPage from "./page";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: { listExemplars: jest.fn() },
}));

const fakeExemplar = {
  run_id: "run-abc",
  title: "How I Cut LLM Costs by 83%",
  tags: ["ai", "cost", "llm"],
  score: 0.97,
  read_ratio: 0.81,
  hook_score: 0.95,
  hook: "My bill dropped from $2,800 to $178 when I swapped models.",
  intro_word_count: 94,
  word_count: 1720,
  created_at: "2026-06-18T10:00:00Z",
};

describe("ExemplarsPage", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders page heading", () => {
    (api.listExemplars as jest.Mock).mockResolvedValue([]);
    render(<ExemplarsPage />);
    expect(screen.getByTestId("page-heading")).toBeInTheDocument();
  });

  it("shows exemplar card after load", async () => {
    (api.listExemplars as jest.Mock).mockResolvedValue([fakeExemplar]);
    render(<ExemplarsPage />);
    await waitFor(() => screen.getByTestId("exemplar-card-run-abc"));
    expect(screen.getByTestId("exemplar-card-run-abc")).toHaveTextContent("How I Cut LLM Costs by 83%");
  });

  it("shows hook text for each exemplar", async () => {
    (api.listExemplars as jest.Mock).mockResolvedValue([fakeExemplar]);
    render(<ExemplarsPage />);
    await waitFor(() => screen.getByTestId("exemplar-card-run-abc"));
    expect(screen.getByTestId("exemplar-card-run-abc")).toHaveTextContent(
      "My bill dropped from $2,800 to $178"
    );
  });

  it("exemplar card links to the source post", async () => {
    (api.listExemplars as jest.Mock).mockResolvedValue([fakeExemplar]);
    render(<ExemplarsPage />);
    await waitFor(() => screen.getByTestId("exemplar-link-run-abc"));
    expect(screen.getByTestId("exemplar-link-run-abc")).toHaveAttribute("href", "/posts/run-abc");
  });

  it("shows quality score", async () => {
    (api.listExemplars as jest.Mock).mockResolvedValue([fakeExemplar]);
    render(<ExemplarsPage />);
    await waitFor(() => screen.getByTestId("exemplar-card-run-abc"));
    expect(screen.getByTestId("exemplar-card-run-abc")).toHaveTextContent("97");
  });

  it("shows empty state when no exemplars", async () => {
    (api.listExemplars as jest.Mock).mockResolvedValue([]);
    render(<ExemplarsPage />);
    await waitFor(() => screen.getByTestId("empty-state"));
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
  });
});
