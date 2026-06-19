import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ExemplarsPage from "./page";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: {
    listExemplars: jest.fn(),
    deleteExemplar: jest.fn(),
  },
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

const fakeExemplar2 = { ...fakeExemplar, run_id: "run-xyz", title: "Second Exemplar" };

describe("ExemplarsPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.deleteExemplar as jest.Mock).mockResolvedValue(undefined);
  });

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

  it("shows a remove button on each exemplar card", async () => {
    (api.listExemplars as jest.Mock).mockResolvedValue([fakeExemplar]);
    render(<ExemplarsPage />);
    await waitFor(() => screen.getByTestId("exemplar-card-run-abc"));
    expect(screen.getByTestId("remove-exemplar-run-abc")).toBeInTheDocument();
  });

  it("clicking remove calls api.deleteExemplar with the run_id", async () => {
    const user = userEvent.setup();
    (api.listExemplars as jest.Mock).mockResolvedValue([fakeExemplar]);
    render(<ExemplarsPage />);
    await waitFor(() => screen.getByTestId("remove-exemplar-run-abc"));
    await user.click(screen.getByTestId("remove-exemplar-run-abc"));
    expect(api.deleteExemplar).toHaveBeenCalledWith("run-abc");
  });

  it("removed exemplar card disappears from the list", async () => {
    const user = userEvent.setup();
    (api.listExemplars as jest.Mock).mockResolvedValue([fakeExemplar, fakeExemplar2]);
    render(<ExemplarsPage />);
    await waitFor(() => expect(screen.getAllByTestId(/exemplar-card-/)).toHaveLength(2));
    await user.click(screen.getByTestId("remove-exemplar-run-abc"));
    await waitFor(() => expect(screen.queryByTestId("exemplar-card-run-abc")).not.toBeInTheDocument());
    expect(screen.getByTestId("exemplar-card-run-xyz")).toBeInTheDocument();
  });
});
