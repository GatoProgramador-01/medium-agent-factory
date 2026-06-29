import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PipelinePage from "./page";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: {
    triggerPipeline: jest.fn(),
    triggerSeries: jest.fn(),
    streamLogs: jest.fn(),
    getPost: jest.fn(),
    listRuns: jest.fn(),
  },
}));

function makeFakeEventSource(events: Record<string, unknown>[]) {
  const listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  return {
    onmessage: null as ((e: MessageEvent) => void) | null,
    onerror: null as ((e: Event) => void) | null,
    close: jest.fn(),
    // Call this from tests to fire events
    _emit(data: Record<string, unknown>) {
      const event = new MessageEvent("message", { data: JSON.stringify(data) });
      if (this.onmessage) this.onmessage(event);
    },
    _close() {
      if (this.onerror) this.onerror(new Event("error"));
    },
  };
}

describe("PipelinePage", () => {
  let fakeEs: ReturnType<typeof makeFakeEventSource>;

  beforeEach(() => {
    jest.clearAllMocks();
    fakeEs = makeFakeEventSource([]);
    (api.streamLogs as jest.Mock).mockReturnValue(fakeEs);
    (api.listRuns as jest.Mock).mockResolvedValue([]);
  });

  it("renders the page heading and topic input", () => {
    render(<PipelinePage />);
    expect(screen.getByTestId("page-heading")).toHaveTextContent("Run Pipeline");
    expect(screen.getByTestId("topic-input")).toBeInTheDocument();
  });

  it("run button is enabled in idle state", () => {
    render(<PipelinePage />);
    expect(screen.getByTestId("run-button")).toBeEnabled();
  });

  it("run button becomes disabled immediately on click", async () => {
    const user = userEvent.setup();
    // triggerPipeline never resolves — keeps phase=running
    (api.triggerPipeline as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<PipelinePage />);
    await user.click(screen.getByTestId("run-button"));
    expect(screen.getByTestId("run-button")).toBeDisabled();
  });

  it("topic input accepts text", async () => {
    const user = userEvent.setup();
    render(<PipelinePage />);
    const input = screen.getByTestId("topic-input");
    await user.type(input, "how to build LLM pipelines");
    expect(input).toHaveValue("how to build LLM pipelines");
  });

  it("calls triggerPipeline with the typed topic", async () => {
    const user = userEvent.setup();
    (api.triggerPipeline as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<PipelinePage />);
    await user.type(screen.getByTestId("topic-input"), "my topic");
    await user.click(screen.getByTestId("run-button"));
    expect(api.triggerPipeline).toHaveBeenCalledWith("my topic", "");
  });

  it("renders a grounding brief textarea for source notes", () => {
    render(<PipelinePage />);
    expect(screen.getByTestId("grounding-context-input")).toBeInTheDocument();
  });

  it("calls triggerPipeline with the grounding brief", async () => {
    const user = userEvent.setup();
    (api.triggerPipeline as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<PipelinePage />);
    await user.type(screen.getByTestId("topic-input"), "my topic");
    await user.type(screen.getByTestId("grounding-context-input"), "repo metric: 53 tests");
    await user.click(screen.getByTestId("run-button"));
    expect(api.triggerPipeline).toHaveBeenCalledWith("my topic", "repo metric: 53 tests");
  });

  it("loads the master prompt repo template", async () => {
    const user = userEvent.setup();
    render(<PipelinePage />);
    await user.click(screen.getByTestId("load-master-prompt-template"));
    const textarea = screen.getByTestId("grounding-context-input") as HTMLTextAreaElement;
    expect(textarea.value).toContain("claude-code-master-prompt");
  });

  it("log terminal appears when SSE events arrive", async () => {
    (api.triggerPipeline as jest.Mock).mockResolvedValue({ run_id: "run-123" });
    (api.getPost as jest.Mock).mockResolvedValue(null);
    render(<PipelinePage />);

    await userEvent.click(screen.getByTestId("run-button"));

    // Trigger first SSE event
    await waitFor(() => expect(api.streamLogs).toHaveBeenCalled());
    fakeEs._emit({
      run_id: "run-123",
      step: "orchestrator",
      level: "info",
      message: "Pipeline started.",
      data: {},
      timestamp: new Date().toISOString(),
    });

    await waitFor(() =>
      expect(screen.getByTestId("log-terminal")).toBeInTheDocument()
    );
    expect(screen.getByTestId("log-terminal")).toHaveTextContent("Pipeline started.");
  });

  describe("Series tab", () => {
    it("renders a Single Post tab button", () => {
      render(<PipelinePage />);
      expect(screen.getByTestId("tab-single")).toBeInTheDocument();
    });

    it("renders a Series tab button", () => {
      render(<PipelinePage />);
      expect(screen.getByTestId("tab-series")).toBeInTheDocument();
    });

    it("clicking Series tab shows the theme input", async () => {
      const user = userEvent.setup();
      render(<PipelinePage />);
      await user.click(screen.getByTestId("tab-series"));
      expect(screen.getByTestId("theme-input")).toBeInTheDocument();
    });

    it("theme input accepts text", async () => {
      const user = userEvent.setup();
      render(<PipelinePage />);
      await user.click(screen.getByTestId("tab-series"));
      const input = screen.getByTestId("theme-input");
      await user.type(input, "LLM cost breakdown");
      expect(input).toHaveValue("LLM cost breakdown");
    });

    it("submitting series form calls triggerSeries with theme", async () => {
      const user = userEvent.setup();
      (api.triggerSeries as jest.Mock).mockReturnValue(new Promise(() => {}));
      render(<PipelinePage />);
      await user.click(screen.getByTestId("tab-series"));
      await user.type(screen.getByTestId("theme-input"), "LLM cost breakdown");
      await user.click(screen.getByTestId("run-series-button"));
      expect(api.triggerSeries).toHaveBeenCalledWith("LLM cost breakdown", "");
    });

    it("shows series result card after successful submit", async () => {
      const user = userEvent.setup();
      (api.triggerSeries as jest.Mock).mockResolvedValue({ series_id: "s-abc", message: "Series started" });
      render(<PipelinePage />);
      await user.click(screen.getByTestId("tab-series"));
      await user.type(screen.getByTestId("theme-input"), "AI agents");
      await user.click(screen.getByTestId("run-series-button"));
      await waitFor(() => screen.getByTestId("series-result-card"));
      expect(screen.getByTestId("series-result-card")).toBeInTheDocument();
    });

    it("series result card links to /series page", async () => {
      const user = userEvent.setup();
      (api.triggerSeries as jest.Mock).mockResolvedValue({ series_id: "s-abc", message: "Series started" });
      render(<PipelinePage />);
      await user.click(screen.getByTestId("tab-series"));
      await user.type(screen.getByTestId("theme-input"), "AI agents");
      await user.click(screen.getByTestId("run-series-button"));
      await waitFor(() => screen.getByTestId("view-series-link"));
      expect(screen.getByTestId("view-series-link")).toHaveAttribute("href", "/series");
    });

    it("shows context textarea in the series tab", async () => {
      const user = userEvent.setup();
      render(<PipelinePage />);
      await user.click(screen.getByTestId("tab-series"));
      expect(screen.getByTestId("context-input")).toBeInTheDocument();
    });

    it("context textarea accepts text", async () => {
      const user = userEvent.setup();
      render(<PipelinePage />);
      await user.click(screen.getByTestId("tab-series"));
      await user.type(screen.getByTestId("context-input"), "Focus on Anthropic and OpenAI");
      expect(screen.getByTestId("context-input")).toHaveValue("Focus on Anthropic and OpenAI");
    });

    it("submitting with context passes context value to triggerSeries", async () => {
      const user = userEvent.setup();
      (api.triggerSeries as jest.Mock).mockReturnValue(new Promise(() => {}));
      render(<PipelinePage />);
      await user.click(screen.getByTestId("tab-series"));
      await user.type(screen.getByTestId("theme-input"), "LLM costs 2026");
      await user.type(screen.getByTestId("context-input"), "Focus on Claude");
      await user.click(screen.getByTestId("run-series-button"));
      expect(api.triggerSeries).toHaveBeenCalledWith("LLM costs 2026", "Focus on Claude");
    });
  });

  describe("Run History", () => {
    const MOCK_RUNS = [
      {
        run_id: "run-aabbcc",
        custom_topic: "LLM cost tricks",
        status: "completed",
        created_at: "2026-06-18T10:00:00Z",
        completed_at: "2026-06-18T10:05:00Z",
      },
      {
        run_id: "run-ddeeff",
        custom_topic: "Prompting tips",
        status: "failed",
        created_at: "2026-06-17T09:00:00Z",
      },
    ];

    it("renders run history section when runs exist", async () => {
      (api.listRuns as jest.Mock).mockResolvedValue(MOCK_RUNS);
      render(<PipelinePage />);
      await waitFor(() => screen.getByTestId("run-history"));
      expect(screen.getByTestId("run-history")).toBeInTheDocument();
    });

    it("shows a row for each run", async () => {
      (api.listRuns as jest.Mock).mockResolvedValue(MOCK_RUNS);
      render(<PipelinePage />);
      await waitFor(() => screen.getByTestId("run-row-run-aabbcc"));
      expect(screen.getByTestId("run-row-run-aabbcc")).toBeInTheDocument();
      expect(screen.getByTestId("run-row-run-ddeeff")).toBeInTheDocument();
    });

    it("completed run row links to the post reader", async () => {
      (api.listRuns as jest.Mock).mockResolvedValue(MOCK_RUNS);
      render(<PipelinePage />);
      await waitFor(() => screen.getByTestId("run-post-link-run-aabbcc"));
      expect(screen.getByTestId("run-post-link-run-aabbcc")).toHaveAttribute("href", "/posts/run-aabbcc");
    });

    it("failed run row shows failed status", async () => {
      (api.listRuns as jest.Mock).mockResolvedValue(MOCK_RUNS);
      render(<PipelinePage />);
      await waitFor(() => screen.getByTestId("run-row-run-ddeeff"));
      expect(screen.getByTestId("run-row-run-ddeeff")).toHaveTextContent("failed");
    });

    it("no run history section when list is empty", async () => {
      (api.listRuns as jest.Mock).mockResolvedValue([]);
      render(<PipelinePage />);
      // give time for fetch to resolve
      await waitFor(() => expect(api.listRuns).toHaveBeenCalled());
      expect(screen.queryByTestId("run-history")).not.toBeInTheDocument();
    });
  });

  it("__done__ event transitions phase to done and shows run-again button", async () => {
    const fakePost = {
      run_id: "run-done",
      title: "Generated Title",
      content: "...",
      tags: [],
      status: "approved",
      revision_count: 0,
      created_at: new Date().toISOString(),
      image_suggestions: [],
      quality_report: { score: 0.82, read_ratio_prediction: 0.7, issues: [], strengths: [], revision_prompt: "" },
    };
    (api.triggerPipeline as jest.Mock).mockResolvedValue({ run_id: "run-done" });
    (api.getPost as jest.Mock).mockResolvedValue(fakePost);

    render(<PipelinePage />);
    await userEvent.click(screen.getByTestId("run-button"));

    await waitFor(() => expect(api.streamLogs).toHaveBeenCalled());
    fakeEs._emit({ __done__: true });

    await waitFor(() =>
      expect(screen.getByTestId("run-again-button")).toBeInTheDocument()
    );
    await waitFor(() =>
      expect(screen.getByTestId("result-card")).toBeInTheDocument()
    );
  });

  describe("result-card content after __done__", () => {
    const fakePost = {
      run_id: "run-done",
      title: "Generated Title",
      content: "...",
      tags: [],
      status: "approved",
      revision_count: 0,
      created_at: new Date().toISOString(),
      image_suggestions: [],
      quality_report: { score: 0.82, read_ratio_prediction: 0.7, issues: [], strengths: [], revision_prompt: "" },
    };

    async function renderAndFinish(fakeEsRef: ReturnType<typeof makeFakeEventSource>) {
      (api.triggerPipeline as jest.Mock).mockResolvedValue({ run_id: "run-done" });
      (api.getPost as jest.Mock).mockResolvedValue(fakePost);
      render(<PipelinePage />);
      await userEvent.click(screen.getByTestId("run-button"));
      await waitFor(() => expect(api.streamLogs).toHaveBeenCalled());
      fakeEsRef._emit({ __done__: true });
      await waitFor(() => screen.getByTestId("result-card"));
    }

    it("shows quality score", async () => {
      await renderAndFinish(fakeEs);
      expect(screen.getByTestId("result-score")).toHaveTextContent("82");
    });

    it("shows read ratio percentage", async () => {
      await renderAndFinish(fakeEs);
      expect(screen.getByTestId("result-ratio")).toHaveTextContent("70%");
    });

    it("view post link has correct href", async () => {
      await renderAndFinish(fakeEs);
      expect(screen.getByTestId("view-post-link")).toHaveAttribute("href", "/posts/run-done");
    });
  });
});
