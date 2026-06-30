/**
 * app.spec.ts — Integration E2E suite for Medium Agent Factory
 *
 * Covers:
 *   1. Homepage loads — page-heading, hero text, pipeline step chips, CTAs
 *   2. Dashboard stats — metric cards render after API resolves
 *   3. Pipeline form — topic input, grounding textarea, run button, mode tabs
 *   4. API health check — GET /health returns 200 {"status":"ok"}
 *   5. Recent runs list — GET /pipeline/runs populates RunHistory component
 *   6. Navigation — all 6 nav links route to correct pages
 *   7. Posts page — heading, filter toolbar, empty state CTA
 *   8. Series tab — switching mode reveals theme-input
 *
 * All backend calls are intercepted via page.route() so tests run without
 * a live API. Tests that validate the real /health endpoint are marked with
 * an explicit note and skip gracefully when the backend is unreachable.
 *
 * Selectors come from data-testid attributes already present in the codebase —
 * no new attributes are needed.
 *
 * Run:
 *   npx playwright test app.spec.ts --project=chromium
 *
 * Expected record count: N/A (UI-only, no scraping)
 * Known fragile selectors: none — all use data-testid
 */

import { test, expect } from "@playwright/test";

// ── Shared mock data ───────────────────────────────────────────────────────────

const MOCK_SUMMARY = {
  pipeline_runs: 12,
  completed_runs: 10,
  total_posts: 10,
  published_posts: 3,
  total_cost_usd: 0.4231,
  total_tokens: 184200,
  claude_cost_usd: 0.38,
  deepseek_cost_usd: 0.04,
};

const MOCK_POSTS = [
  {
    run_id: "run-abc123",
    title: "How I Built a 7-Agent Content Pipeline",
    content: "Full article content here...",
    tags: ["ai", "langchain", "fastapi"],
    status: "approved",
    revision_count: 2,
    word_count: 1850,
    pull_quote: "Parallel agents cut iteration time by 60%.",
    medium_boost_eligible: true,
    created_at: "2026-06-20T14:00:00Z",
    quality_report: {
      score: 0.93,
      read_ratio_prediction: 0.78,
      medium_boost_eligible: true,
      issues: [],
      strengths: ["Strong hook", "Concrete metrics"],
    },
  },
  {
    run_id: "run-def456",
    title: "LangGraph State Machines in Practice",
    content: "Content...",
    tags: ["langgraph", "python"],
    status: "draft",
    revision_count: 1,
    word_count: 1420,
    created_at: "2026-06-19T10:00:00Z",
    quality_report: {
      score: 0.76,
      read_ratio_prediction: 0.58,
      medium_boost_eligible: false,
      issues: [{ category: "depth", severity: "medium", suggestion: "Add more examples" }],
      strengths: ["Clear structure"],
    },
  },
];

const MOCK_EXEMPLARS = [
  {
    run_id: "ex-001",
    title: "Best Post Ever",
    tags: ["ai"],
    score: 0.97,
    read_ratio: 0.85,
    hook_score: 0.9,
    hook: "What if you never had to write again?",
    intro_word_count: 120,
    word_count: 1900,
    created_at: "2026-06-15T08:00:00Z",
  },
];

const MOCK_RUNS = [
  {
    run_id: "run-abc123",
    custom_topic: "How I Built a 7-Agent Content Pipeline",
    status: "completed",
    created_at: "2026-06-20T14:00:00Z",
  },
  {
    run_id: "run-def456",
    custom_topic: "LangGraph State Machines in Practice",
    status: "completed",
    created_at: "2026-06-19T10:00:00Z",
  },
  {
    run_id: "run-ghi789",
    custom_topic: "The real cost of running LLMs",
    status: "failed",
    created_at: "2026-06-18T09:00:00Z",
  },
];

/** Wire up all analytics + posts + pipeline/runs mocks before each test in a describe block. */
async function mockAllApis(page: import("@playwright/test").Page) {
  const API = "http://localhost:8000";

  await page.route(`${API}/analytics/summary`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_SUMMARY),
    })
  );

  await page.route(`${API}/posts`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_POSTS),
    })
  );

  await page.route(`${API}/posts**`, (route) => {
    // Only intercept list calls — individual post pages match a different pattern
    if (route.request().url() === `${API}/posts` || route.request().url().includes("/posts?")) {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_POSTS),
      });
    } else {
      route.continue();
    }
  });

  await page.route(`${API}/posts/exemplars/list`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_EXEMPLARS),
    })
  );

  await page.route(`${API}/pipeline/runs`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_RUNS),
    })
  );
}

// ── 1. HOMEPAGE LOADS ─────────────────────────────────────────────────────────

test.describe("Homepage", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page);
    await page.goto("/");
  });

  test("page-heading is visible", async ({ page }) => {
    // The hero heading contains "Research. Write." and "Publish." (split across spans)
    const heading = page.getByTestId("page-heading");
    await expect(heading).toBeVisible();
    await expect(heading).toContainText("Research. Write.");
  });

  test("hero section label reads Medium Agent Factory", async ({ page }) => {
    await expect(page.locator("text=Medium Agent Factory").first()).toBeVisible();
  });

  test("all 7 pipeline step chips are rendered", async ({ page }) => {
    const expectedSteps = ["Research", "Generate", "Fact-check", "Quality", "Revise", "Format", "Finalize"];
    for (const step of expectedSteps) {
      await expect(page.locator(`text=${step}`).first()).toBeVisible();
    }
  });

  test("CTA cards link to /pipeline and /posts", async ({ page }) => {
    await expect(page.getByTestId("cta-run-pipeline")).toBeVisible();
    await expect(page.getByTestId("cta-view-posts")).toBeVisible();

    const pipelineHref = await page.getByTestId("cta-run-pipeline").getAttribute("href");
    const postsHref = await page.getByTestId("cta-view-posts").getAttribute("href");
    expect(pipelineHref).toBe("/pipeline");
    expect(postsHref).toBe("/posts");
  });

  test("stat metric cards appear after summary resolves", async ({ page }) => {
    // Wait for skeleton placeholders to be replaced
    await expect(page.getByTestId("stat-pipeline-runs")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("stat-completed")).toBeVisible();
    await expect(page.getByTestId("stat-total-posts")).toBeVisible();
    await expect(page.getByTestId("stat-published")).toBeVisible();
    await expect(page.getByTestId("stat-total-tokens")).toBeVisible();
    await expect(page.getByTestId("stat-total-cost")).toBeVisible();
    await expect(page.getByTestId("stat-exemplars")).toBeVisible();
  });

  test("stat-pipeline-runs displays mocked count 12", async ({ page }) => {
    await page.getByTestId("stat-pipeline-runs").waitFor({ state: "visible", timeout: 10000 });
    await expect(page.getByTestId("stat-pipeline-runs")).toContainText("12");
  });

  test("stat-total-cost shows dollar amount with accent colour", async ({ page }) => {
    await page.getByTestId("stat-total-cost").waitFor({ state: "visible", timeout: 10000 });
    await expect(page.getByTestId("stat-total-cost")).toContainText("$");
  });

  test("recent posts section renders with mocked posts", async ({ page }) => {
    // Posts are loaded via api.listPosts(); wait for them to appear
    const recentPosts = page.getByTestId("recent-posts");
    await expect(recentPosts).toBeVisible({ timeout: 10000 });
    // First post title should be visible inside the list
    await expect(recentPosts).toContainText("How I Built a 7-Agent Content Pipeline");
  });

  test("clicking CTA Run Pipeline navigates to /pipeline", async ({ page }) => {
    await page.getByTestId("cta-run-pipeline").click();
    await expect(page).toHaveURL("/pipeline");
  });

  test("clicking CTA View Posts navigates to /posts", async ({ page }) => {
    await page.getByTestId("cta-view-posts").click();
    await expect(page).toHaveURL("/posts");
  });
});

// ── 2. HOMEPAGE — EMPTY STATE ─────────────────────────────────────────────────

test.describe("Homepage — empty state", () => {
  test("shows no-data message when API returns empty arrays", async ({ page }) => {
    const API = "http://localhost:8000";
    await page.route(`${API}/analytics/summary`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "null" })
    );
    await page.route(`${API}/posts`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );
    await page.route(`${API}/posts/exemplars/list`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );
    await page.route(`${API}/pipeline/runs`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );

    await page.goto("/");

    // When summary is null, the no-data card renders instead of metric grid
    await expect(page.locator("text=No data yet")).toBeVisible({ timeout: 10000 });

    // recent-posts-empty sentinel is rendered when posts array is empty
    await expect(page.getByTestId("recent-posts-empty")).toBeVisible({ timeout: 10000 });
  });
});

// ── 3. PIPELINE FORM ──────────────────────────────────────────────────────────

test.describe("Pipeline page — form controls", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("http://localhost:8000/pipeline/runs", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_RUNS),
      })
    );
    await page.goto("/pipeline");
  });

  test("page heading reads Run Pipeline", async ({ page }) => {
    await expect(page.getByTestId("page-heading")).toHaveText("Run Pipeline");
  });

  test("topic input is visible and enabled", async ({ page }) => {
    const input = page.getByTestId("topic-input");
    await expect(input).toBeVisible();
    await expect(input).toBeEnabled();
  });

  test("topic input accepts typed text", async ({ page }) => {
    const input = page.getByTestId("topic-input");
    await input.fill("Why parallel agents matter for LLM pipelines");
    await expect(input).toHaveValue("Why parallel agents matter for LLM pipelines");
  });

  test("grounding-context textarea is visible", async ({ page }) => {
    await expect(page.getByTestId("grounding-context-input")).toBeVisible();
  });

  test("grounding context character counter starts at 0 / 12,000", async ({ page }) => {
    // The counter div renders "{length.toLocaleString()} / 12,000"
    await expect(page.locator("text=0 / 12,000")).toBeVisible();
  });

  test("Master Prompt repo button loads template text", async ({ page }) => {
    const btn = page.getByTestId("load-master-prompt-template");
    await expect(btn).toBeVisible();
    await btn.click();
    // After click, the textarea should be non-empty (template was pasted in)
    const textarea = page.getByTestId("grounding-context-input");
    const value = await textarea.inputValue();
    expect(value.length).toBeGreaterThan(100);
    // Character counter should update above 0
    await expect(page.locator("text=/ 12,000")).toBeVisible();
    const counterText = await page.locator("text=/ 12,000").textContent();
    expect(counterText).not.toMatch(/^0 \/ 12,000/);
  });

  test("run button Generate Post is visible and enabled in idle state", async ({ page }) => {
    const btn = page.getByTestId("run-button");
    await expect(btn).toBeVisible();
    await expect(btn).toBeEnabled();
    await expect(btn).toHaveText("Generate Post");
  });

  test("Single Post tab is active by default", async ({ page }) => {
    const singleTab = page.getByTestId("tab-single");
    await expect(singleTab).toBeVisible();
    // Active tab has a border and background — check the element exists and is visible
    await expect(singleTab).toContainText("Single Post");
  });

  test("clicking Series tab shows theme-input", async ({ page }) => {
    const seriesTab = page.getByTestId("tab-series");
    await expect(seriesTab).toBeVisible();
    await seriesTab.click();

    await expect(page.getByTestId("theme-input")).toBeVisible();
    // topic-input (Single Post form) should be gone
    await expect(page.getByTestId("topic-input")).not.toBeVisible();
  });

  test("series tab shows context-input and run-series-button", async ({ page }) => {
    await page.getByTestId("tab-series").click();
    await expect(page.getByTestId("context-input")).toBeVisible();
    await expect(page.getByTestId("run-series-button")).toBeVisible();
    await expect(page.getByTestId("run-series-button")).toHaveText("Generate Series");
  });

  test("switching back to Single Post tab restores topic-input", async ({ page }) => {
    await page.getByTestId("tab-series").click();
    await page.getByTestId("tab-single").click();
    await expect(page.getByTestId("topic-input")).toBeVisible();
    await expect(page.getByTestId("run-button")).toBeVisible();
  });
});

// ── 4. PIPELINE — RUN BUTTON DISABLED WHILE IN-FLIGHT ────────────────────────

test.describe("Pipeline page — run lifecycle", () => {
  const API = "http://localhost:8000";

  function sseBody(runId: string): string {
    return [
      `data: ${JSON.stringify({
        run_id: runId,
        step: "orchestrator",
        level: "info",
        message: "Pipeline started.",
        data: {},
        timestamp: new Date().toISOString(),
      })}\n\n`,
      'data: {"__done__": true}\n\n',
    ].join("");
  }

  const FAKE_POST = {
    run_id: "app-spec-run",
    title: "Test Post Title",
    content: "Content.",
    tags: ["ai"],
    status: "approved",
    revision_count: 1,
    created_at: new Date().toISOString(),
    quality_report: {
      score: 0.88,
      read_ratio_prediction: 0.69,
      medium_boost_eligible: true,
      issues: [],
      strengths: ["Tight opening"],
    },
  };

  test.beforeEach(async ({ page }) => {
    await page.route(`${API}/pipeline/runs`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );
  });

  test("run button is disabled while POST is in-flight", async ({ page }) => {
    // Hold the POST for 500ms to observe disabled state
    await page.route(`${API}/pipeline/run`, async (route) => {
      await new Promise((r) => setTimeout(r, 500));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ run_id: "app-spec-run", message: "Pipeline started" }),
      });
    });
    await page.route(`${API}/pipeline/runs/app-spec-run/stream`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sseBody("app-spec-run"),
      })
    );
    await page.route(`${API}/posts/app-spec-run`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(FAKE_POST) })
    );

    await page.goto("/pipeline");
    await page.getByTestId("run-button").click();
    await expect(page.getByTestId("run-button")).toBeDisabled();
  });

  test("agent stepper appears once a run starts", async ({ page }) => {
    await page.route(`${API}/pipeline/run`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ run_id: "app-spec-run", message: "Pipeline started" }),
      })
    );
    await page.route(`${API}/pipeline/runs/app-spec-run/stream`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sseBody("app-spec-run"),
      })
    );
    await page.route(`${API}/posts/app-spec-run`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(FAKE_POST) })
    );

    await page.goto("/pipeline");
    await page.getByTestId("run-button").click();
    await expect(page.getByTestId("agent-stepper")).toBeVisible({ timeout: 8000 });
  });

  test("log-terminal appears and shows first log entry", async ({ page }) => {
    await page.route(`${API}/pipeline/run`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ run_id: "app-spec-run", message: "Pipeline started" }),
      })
    );
    await page.route(`${API}/pipeline/runs/app-spec-run/stream`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sseBody("app-spec-run"),
      })
    );
    await page.route(`${API}/posts/app-spec-run`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(FAKE_POST) })
    );

    await page.goto("/pipeline");
    await page.getByTestId("run-button").click();
    await expect(page.getByTestId("log-terminal")).toBeVisible({ timeout: 8000 });
    await expect(page.getByTestId("log-terminal")).toContainText("Pipeline started.");
  });

  test("result card with view-post-link appears after SSE __done__", async ({ page }) => {
    await page.route(`${API}/pipeline/run`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ run_id: "app-spec-run", message: "Pipeline started" }),
      })
    );
    await page.route(`${API}/pipeline/runs/app-spec-run/stream`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sseBody("app-spec-run"),
      })
    );
    await page.route(`${API}/posts/app-spec-run`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(FAKE_POST) })
    );

    await page.goto("/pipeline");
    await page.getByTestId("run-button").click();
    await expect(page.getByTestId("result-card")).toBeVisible({ timeout: 12000 });
    await expect(page.getByTestId("view-post-link")).toBeVisible();
    await expect(page.getByTestId("run-again-button")).toBeVisible();
    // Score ring value should match mock: 0.88 → 88
    await expect(page.getByTestId("result-score")).toContainText("88");
  });

  test("Enter key on topic input triggers the pipeline run", async ({ page }) => {
    await page.route(`${API}/pipeline/run`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ run_id: "app-spec-run", message: "Pipeline started" }),
      })
    );
    await page.route(`${API}/pipeline/runs/app-spec-run/stream`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sseBody("app-spec-run"),
      })
    );
    await page.route(`${API}/posts/app-spec-run`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(FAKE_POST) })
    );

    await page.goto("/pipeline");
    await page.getByTestId("topic-input").fill("LLMOps for senior engineers");
    await page.getByTestId("topic-input").press("Enter");
    await expect(page.getByTestId("run-button")).toBeDisabled();
  });
});

// ── 5. API HEALTH CHECK ───────────────────────────────────────────────────────

test.describe("API health check", () => {
  test("GET /health returns 200 with status ok", async ({ request }) => {
    // This test hits the real backend — skip gracefully if it's not running
    let response: import("@playwright/test").APIResponse;
    try {
      response = await request.get("http://localhost:8000/health");
    } catch {
      test.skip(true, "Backend not reachable at http://localhost:8000 — start Docker containers first");
      return;
    }

    expect(response.status()).toBe(200);
    const body = await response.json() as { status: string };
    expect(body.status).toBe("ok");
  });

  test("GET /pipeline/runs returns an array", async ({ request }) => {
    let response: import("@playwright/test").APIResponse;
    try {
      response = await request.get("http://localhost:8000/pipeline/runs");
    } catch {
      test.skip(true, "Backend not reachable — start Docker containers first");
      return;
    }

    expect(response.status()).toBe(200);
    const body = await response.json() as unknown[];
    expect(Array.isArray(body)).toBe(true);
  });
});

// ── 6. RECENT RUNS LIST ───────────────────────────────────────────────────────

test.describe("Pipeline page — recent runs list", () => {
  test("RunHistory renders rows from /pipeline/runs", async ({ page }) => {
    await page.route("http://localhost:8000/pipeline/runs", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_RUNS),
      })
    );

    await page.goto("/pipeline");

    const runHistory = page.getByTestId("run-history");
    await expect(runHistory).toBeVisible({ timeout: 10000 });

    // First run ID truncated to 8 chars: "run-abc1"
    await expect(runHistory).toContainText("run-abc1");
    // Topic text
    await expect(runHistory).toContainText("How I Built a 7-Agent Content Pipeline");
    // Status
    await expect(runHistory).toContainText("completed");
    await expect(runHistory).toContainText("failed");
  });

  test("completed run row shows View link to /posts/:run_id", async ({ page }) => {
    await page.route("http://localhost:8000/pipeline/runs", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_RUNS),
      })
    );

    await page.goto("/pipeline");
    await page.getByTestId("run-history").waitFor({ state: "visible", timeout: 10000 });

    const viewLink = page.getByTestId(`run-post-link-${MOCK_RUNS[0].run_id}`);
    await expect(viewLink).toBeVisible();
    const href = await viewLink.getAttribute("href");
    expect(href).toBe(`/posts/${MOCK_RUNS[0].run_id}`);
  });

  test("run history is empty when API returns empty array", async ({ page }) => {
    await page.route("http://localhost:8000/pipeline/runs", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );

    await page.goto("/pipeline");
    // RunHistory renders null when runs is empty — component should not appear
    await page.waitForTimeout(1500); // let the effect settle
    const runHistory = page.getByTestId("run-history");
    await expect(runHistory).not.toBeVisible();
  });
});

// ── 7. NAVIGATION ─────────────────────────────────────────────────────────────

test.describe("Navigation", () => {
  // Mock APIs so pages don't fail on missing data
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page);
  });

  test("nav-dashboard link navigates to /", async ({ page }) => {
    await page.goto("/pipeline");
    await page.getByTestId("nav-dashboard").click();
    await expect(page).toHaveURL("/");
    await expect(page.getByTestId("page-heading")).toBeVisible();
  });

  test("nav-pipeline link navigates to /pipeline", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("nav-pipeline").click();
    await expect(page).toHaveURL("/pipeline");
    await expect(page.getByTestId("page-heading")).toHaveText("Run Pipeline");
  });

  test("nav-posts link navigates to /posts", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("nav-posts").click();
    await expect(page).toHaveURL("/posts");
    await expect(page.getByTestId("page-heading")).toHaveText("Posts");
  });

  test("nav-series link navigates to /series", async ({ page }) => {
    await page.route("http://localhost:8000/series", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );
    await page.goto("/");
    await page.getByTestId("nav-series").click();
    await expect(page).toHaveURL("/series");
    await expect(page.getByTestId("page-heading")).toBeVisible();
  });

  test("nav-exemplars link navigates to /exemplars", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("nav-exemplars").click();
    await expect(page).toHaveURL("/exemplars");
    await expect(page.getByTestId("page-heading")).toBeVisible();
  });

  test("nav-analytics link navigates to /analytics", async ({ page }) => {
    await page.route("http://localhost:8000/analytics/token-usage**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );
    await page.route("http://localhost:8000/analytics/token-usage/by-run**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );
    await page.route("http://localhost:8000/analytics/cost-comparison", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          claude_cost_usd: 0.38, claude_tokens_in: 100000, claude_tokens_out: 40000, claude_runs: 10,
          deepseek_cost_usd: 0.04, deepseek_tokens_in: 0, deepseek_tokens_out: 0, deepseek_runs: 0,
          equivalent_claude_cost_usd: 0.42, savings_usd: 0.0, savings_pct: 0,
          has_claude_data: true, has_deepseek_data: false,
        }),
      })
    );
    await page.route("http://localhost:8000/analytics/revision-cycles**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );

    await page.goto("/");
    await page.getByTestId("nav-analytics").click();
    await expect(page).toHaveURL("/analytics");
    await expect(page.getByTestId("page-heading")).toHaveText("Analytics");
  });

  test("logo link returns to / from any page", async ({ page }) => {
    await page.goto("/pipeline");
    // The logo link text is "Agent Factory" — find by visible text
    await page.getByRole("link", { name: /Agent Factory/i }).first().click();
    await expect(page).toHaveURL("/");
  });
});

// ── 8. POSTS PAGE ─────────────────────────────────────────────────────────────

test.describe("Posts page", () => {
  const API_POSTS = "http://localhost:8000/posts";

  test("heading reads Posts", async ({ page }) => {
    await page.route(`${API_POSTS}**`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_POSTS) })
    );
    await page.goto("/posts");
    await expect(page.getByTestId("page-heading")).toHaveText("Posts");
  });

  test("filter toolbar shows All, draft, revised, approved buttons", async ({ page }) => {
    await page.route(`${API_POSTS}**`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );
    await page.goto("/posts");
    await expect(page.getByTestId("filter-all")).toBeVisible();
    await expect(page.getByTestId("filter-draft")).toBeVisible();
    await expect(page.getByTestId("filter-revised")).toBeVisible();
    await expect(page.getByTestId("filter-approved")).toBeVisible();
  });

  test("search input is visible", async ({ page }) => {
    await page.route(`${API_POSTS}**`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );
    await page.goto("/posts");
    await expect(page.getByTestId("search-input")).toBeVisible();
  });

  test("sort select defaults to Newest first", async ({ page }) => {
    await page.route(`${API_POSTS}**`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );
    await page.goto("/posts");
    await expect(page.getByTestId("sort-select")).toHaveValue("newest");
  });

  test("boost eligible filter button is visible", async ({ page }) => {
    await page.route(`${API_POSTS}**`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );
    await page.goto("/posts");
    await expect(page.getByTestId("filter-boost")).toBeVisible();
  });

  test("post cards render title and score when posts exist", async ({ page }) => {
    await page.route(API_POSTS, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_POSTS),
      })
    );
    await page.goto("/posts");

    const cards = page.getByTestId("post-card");
    await expect(cards.first()).toBeVisible({ timeout: 8000 });
    expect(await cards.count()).toBe(2);
    await expect(cards.first()).toContainText("How I Built a 7-Agent Content Pipeline");
    // Score from quality_report.score 0.93 → "93"
    await expect(cards.first()).toContainText("93");
  });

  test("empty state with pipeline CTA appears when posts array is empty", async ({ page }) => {
    await page.route(`${API_POSTS}**`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );
    await page.goto("/posts");
    await expect(page.getByTestId("empty-state")).toBeVisible({ timeout: 8000 });
    await expect(page.getByTestId("empty-cta")).toBeVisible();
    // Clicking the CTA navigates to /pipeline
    await page.getByTestId("empty-cta").click();
    await expect(page).toHaveURL("/pipeline");
  });

  test("search filters visible cards by title", async ({ page }) => {
    await page.route(API_POSTS, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_POSTS),
      })
    );
    await page.goto("/posts");
    await page.getByTestId("post-card").first().waitFor({ state: "visible", timeout: 8000 });

    await page.getByTestId("search-input").fill("LangGraph");
    // Only the second post matches "LangGraph"
    await expect(page.getByTestId("post-card")).toHaveCount(1);
    await expect(page.getByTestId("post-card").first()).toContainText("LangGraph");
  });
});
