import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PipelinePage from "./page";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: {
    triggerPipeline: jest.fn(),
    streamLogs: jest.fn(),
    getPost: jest.fn(),
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
    expect(api.triggerPipeline).toHaveBeenCalledWith("my topic");
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
});
