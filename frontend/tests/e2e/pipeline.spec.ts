import { test, expect } from "@playwright/test";

const API = "http://localhost:8000";

// Reusable SSE mock body — sends two log events then signals completion
function sseBody(runId: string, extraEvents: string[] = []) {
  const base = [
    `data: ${JSON.stringify({ run_id: runId, step: "orchestrator", level: "info", message: "Pipeline started.", data: {}, timestamp: new Date().toISOString() })}\n\n`,
    ...extraEvents,
    'data: {"__done__": true}\n\n',
  ];
  return base.join("");
}

const FAKE_POST = {
  run_id: "test-run-id",
  title: "Generated Test Post",
  subtitle: "A subtitle",
  content: "Post content",
  tags: ["ai", "writing"],
  status: "approved",
  revision_count: 0,
  created_at: new Date().toISOString(),
  image_suggestions: [],
  quality_report: {
    score: 0.85,
    read_ratio_prediction: 0.72,
    issues: [],
    strengths: ["Good hook"],
    revision_prompt: "",
  },
};

test.describe("Pipeline page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/pipeline");
  });

  test("renders form controls", async ({ page }) => {
    await expect(page.getByTestId("topic-input")).toBeVisible();
    await expect(page.getByTestId("run-button")).toBeVisible();
    await expect(page.getByTestId("run-button")).toBeEnabled();
  });

  test("run button is disabled while pipeline POST is in-flight", async ({ page }) => {
    // Hold the POST for 400 ms so we can observe the disabled state
    await page.route(`${API}/pipeline/run`, async (route) => {
      await new Promise((r) => setTimeout(r, 400));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ run_id: "test-run-id", message: "Pipeline started" }),
      });
    });
    // Mock SSE so onerror doesn't immediately fire and end the run
    await page.route(`${API}/pipeline/runs/test-run-id/stream`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sseBody("test-run-id"),
      })
    );
    await page.route(`${API}/posts/test-run-id`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(FAKE_POST) })
    );

    await page.getByTestId("run-button").click();
    // Immediately after click React sets phase="running" → button disabled
    await expect(page.getByTestId("run-button")).toBeDisabled();
  });

  test("topic input accepts text", async ({ page }) => {
    const input = page.getByTestId("topic-input");
    await input.fill("How to earn on Ko-fi in 2025");
    await expect(input).toHaveValue("How to earn on Ko-fi in 2025");
  });

  test("SSE stream — log terminal receives live events", async ({ page }) => {
    const runId = "sse-run-001";

    await page.route(`${API}/pipeline/run`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ run_id: runId, message: "Pipeline started" }),
      })
    );
    await page.route(`${API}/pipeline/runs/${runId}/stream`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sseBody(runId, [
          `data: ${JSON.stringify({ run_id: runId, step: "content_generator", level: "success", message: 'Draft generated: "Test Post" (~1800 words)', data: {}, timestamp: new Date().toISOString() })}\n\n`,
          `data: ${JSON.stringify({ run_id: runId, step: "quality_analyzer", level: "success", message: "Quality score: 0.85/1.0 — Passed threshold.", data: {}, timestamp: new Date().toISOString() })}\n\n`,
        ]),
      })
    );
    await page.route(`${API}/posts/${runId}`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...FAKE_POST, run_id: runId }) })
    );

    await page.getByTestId("run-button").click();

    // Terminal becomes visible and shows log content
    await expect(page.getByTestId("log-terminal")).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId("log-terminal")).toContainText("Pipeline started.");
  });

  test("SSE __done__ event completes the pipeline and shows result card", async ({ page }) => {
    const runId = "sse-done-run";

    await page.route(`${API}/pipeline/run`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ run_id: runId, message: "Pipeline started" }),
      })
    );
    await page.route(`${API}/pipeline/runs/${runId}/stream`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sseBody(runId),
      })
    );
    await page.route(`${API}/posts/${runId}`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...FAKE_POST, run_id: runId }),
      })
    );

    await page.getByTestId("run-button").click();

    await expect(page.getByTestId("result-card")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("view-post-link")).toBeVisible();
    await expect(page.getByTestId("run-again-button")).toBeVisible();
  });

  test("Enter key on topic input triggers the pipeline", async ({ page }) => {
    const runId = "enter-key-run";

    await page.route(`${API}/pipeline/run`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ run_id: runId, message: "Pipeline started" }),
      })
    );
    await page.route(`${API}/pipeline/runs/${runId}/stream`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sseBody(runId),
      })
    );
    await page.route(`${API}/posts/${runId}`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...FAKE_POST, run_id: runId }) })
    );

    await page.getByTestId("topic-input").fill("LLMOps for beginners");
    await page.getByTestId("topic-input").press("Enter");

    // Button becomes disabled — pipeline started
    await expect(page.getByTestId("run-button")).toBeDisabled();
  });
});
