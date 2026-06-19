import { render, screen, waitFor } from "@testing-library/react";
import AnalyticsPage from "./page";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: { tokenUsage: jest.fn(), tokenUsageByRun: jest.fn() },
}));

// AgentCharts uses Recharts/SVG which doesn't render in jsdom — stub it out.
jest.mock("@/components/AgentCharts", () => ({
  __esModule: true,
  default: ({ usage }: { usage: unknown[] }) => (
    <div data-testid="agent-charts" data-count={usage.length} />
  ),
}));

const MOCK_USAGE = [
  {
    agent_name: "content_generator",
    total_tokens_in: 12000,
    total_tokens_out: 3000,
    total_cost_usd: 0.004512,
    avg_duration_ms: 8200,
    call_count: 5,
  },
  {
    agent_name: "quality_analyzer",
    total_tokens_in: 4500,
    total_tokens_out: 900,
    total_cost_usd: 0.001134,
    avg_duration_ms: 3100,
    call_count: 3,
  },
];

const MOCK_RUN_USAGE = [
  { run_id: "run-abc", total_cost_usd: 0.0123, total_tokens_in: 5000, total_tokens_out: 1200, total_duration_ms: 4000, agent_calls: 3 },
  { run_id: "run-def", total_cost_usd: 0.0087, total_tokens_in: 3000, total_tokens_out: 800,  total_duration_ms: 2500, agent_calls: 2 },
];

describe("AnalyticsPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.tokenUsageByRun as jest.Mock).mockResolvedValue([]);
  });

  it("renders page heading", () => {
    (api.tokenUsage as jest.Mock).mockResolvedValue([]);
    render(<AnalyticsPage />);
    expect(screen.getByTestId("page-heading")).toHaveTextContent("Analytics");
  });

  it("shows loading skeletons before data arrives", () => {
    (api.tokenUsage as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<AnalyticsPage />);
    const skeletons = document.querySelectorAll(".skeleton");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows total cost stat after data loads", async () => {
    (api.tokenUsage as jest.Mock).mockResolvedValue(MOCK_USAGE);
    render(<AnalyticsPage />);
    // total cost = 0.004512 + 0.001134 = 0.005646
    await waitFor(() => expect(screen.getByText("$0.0056")).toBeInTheDocument());
  });

  it("shows llm_calls stat after data loads", async () => {
    (api.tokenUsage as jest.Mock).mockResolvedValue(MOCK_USAGE);
    render(<AnalyticsPage />);
    // total calls = 5 + 3 = 8
    await waitFor(() => expect(screen.getByText("8")).toBeInTheDocument());
  });

  it("renders agent name in the breakdown table", async () => {
    (api.tokenUsage as jest.Mock).mockResolvedValue(MOCK_USAGE);
    render(<AnalyticsPage />);
    await waitFor(() => expect(screen.getByText("content_generator")).toBeInTheDocument());
    expect(screen.getByText("quality_analyzer")).toBeInTheDocument();
  });

  it("renders cost_usd for each agent row", async () => {
    (api.tokenUsage as jest.Mock).mockResolvedValue(MOCK_USAGE);
    render(<AnalyticsPage />);
    await waitFor(() => expect(screen.getByText("$0.004512")).toBeInTheDocument());
    expect(screen.getByText("$0.001134")).toBeInTheDocument();
  });

  it("shows agent count in the table header", async () => {
    (api.tokenUsage as jest.Mock).mockResolvedValue(MOCK_USAGE);
    render(<AnalyticsPage />);
    await waitFor(() => expect(screen.getByText("2 agents")).toBeInTheDocument());
  });

  it("shows no-data message when usage list is empty", async () => {
    (api.tokenUsage as jest.Mock).mockResolvedValue([]);
    render(<AnalyticsPage />);
    await waitFor(() =>
      expect(screen.getByText(/no data — run a pipeline to see metrics/i)).toBeInTheDocument()
    );
  });

  it("renders AgentCharts when data is loaded", async () => {
    (api.tokenUsage as jest.Mock).mockResolvedValue(MOCK_USAGE);
    render(<AnalyticsPage />);
    await waitFor(() => expect(screen.getByTestId("agent-charts")).toBeInTheDocument());
    expect(screen.getByTestId("agent-charts")).toHaveAttribute("data-count", "2");
  });

  it("shows tokens_in total in stat box", async () => {
    (api.tokenUsage as jest.Mock).mockResolvedValue(MOCK_USAGE);
    render(<AnalyticsPage />);
    // total: 12000 + 4500 = 16500
    await waitFor(() => expect(screen.getByTestId("stat-tokens-in")).toBeInTheDocument());
    expect(screen.getByTestId("stat-tokens-in")).toHaveTextContent("16,500");
  });

  it("shows tokens_out total in stat box", async () => {
    (api.tokenUsage as jest.Mock).mockResolvedValue(MOCK_USAGE);
    render(<AnalyticsPage />);
    // total: 3000 + 900 = 3900
    await waitFor(() => expect(screen.getByTestId("stat-tokens-out")).toBeInTheDocument());
    expect(screen.getByTestId("stat-tokens-out")).toHaveTextContent("3,900");
  });

  it("shows total cost in stat-cost box", async () => {
    (api.tokenUsage as jest.Mock).mockResolvedValue(MOCK_USAGE);
    render(<AnalyticsPage />);
    // 0.004512 + 0.001134 = 0.005646 → toFixed(4) = $0.0056
    await waitFor(() => expect(screen.getByTestId("stat-cost")).toBeInTheDocument());
    expect(screen.getByTestId("stat-cost")).toHaveTextContent("$0.0056");
  });

  it("shows llm_calls count in stat-calls box", async () => {
    (api.tokenUsage as jest.Mock).mockResolvedValue(MOCK_USAGE);
    render(<AnalyticsPage />);
    // 5 + 3 = 8
    await waitFor(() => expect(screen.getByTestId("stat-calls")).toBeInTheDocument());
    expect(screen.getByTestId("stat-calls")).toHaveTextContent("8");
  });

  describe("by-run breakdown", () => {
    beforeEach(() => {
      (api.tokenUsage as jest.Mock).mockResolvedValue(MOCK_USAGE);
      (api.tokenUsageByRun as jest.Mock).mockResolvedValue(MOCK_RUN_USAGE);
    });

    it("renders the by-run table section", async () => {
      render(<AnalyticsPage />);
      await waitFor(() => expect(screen.getByTestId("by-run-table")).toBeInTheDocument());
    });

    it("shows a row for each run", async () => {
      render(<AnalyticsPage />);
      await waitFor(() => expect(screen.getByTestId("by-run-row-run-abc")).toBeInTheDocument());
      expect(screen.getByTestId("by-run-row-run-def")).toBeInTheDocument();
    });

    it("by-run row shows total cost", async () => {
      render(<AnalyticsPage />);
      await waitFor(() => expect(screen.getByTestId("by-run-row-run-abc")).toBeInTheDocument());
      expect(screen.getByTestId("by-run-row-run-abc")).toHaveTextContent("$0.012300");
    });

    it("by-run row shows agent call count", async () => {
      render(<AnalyticsPage />);
      await waitFor(() => expect(screen.getByTestId("by-run-row-run-abc")).toBeInTheDocument());
      expect(screen.getByTestId("by-run-row-run-abc")).toHaveTextContent("3");
    });

    it("by-run row shows tokens_in", async () => {
      render(<AnalyticsPage />);
      await waitFor(() => expect(screen.getByTestId("by-run-row-run-abc")).toBeInTheDocument());
      expect(screen.getByTestId("by-run-row-run-abc")).toHaveTextContent("5,000");
    });

    it("shows run count in the table header", async () => {
      render(<AnalyticsPage />);
      await waitFor(() =>
        expect(screen.getByTestId("by-run-table")).toHaveTextContent("2 runs")
      );
    });

    it("shows empty state when no run data exists", async () => {
      (api.tokenUsageByRun as jest.Mock).mockResolvedValue([]);
      render(<AnalyticsPage />);
      await waitFor(() =>
        expect(screen.getByTestId("by-run-table")).toHaveTextContent(/no data/i)
      );
    });
  });
});
