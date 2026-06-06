import { test, expect } from "@playwright/test";

const API = "http://localhost:8000";

test.describe("Pipeline page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/pipeline");
  });

  test("renders form controls", async ({ page }) => {
    await expect(page.getByTestId("topic-input")).toBeVisible();
    await expect(page.getByTestId("run-button")).toBeVisible();
    await expect(page.getByTestId("run-button")).toBeEnabled();
  });

  test("run button is disabled while running", async ({ page }) => {
    // Intercept the POST to avoid a real API call
    await page.route(`${API}/pipeline/run`, async (route) => {
      // Delay so we can observe the disabled state
      await new Promise((r) => setTimeout(r, 300));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ run_id: "test-run-id", message: "Pipeline started" }),
      });
    });
    // Also stub the polling endpoints so the run never "completes"
    await page.route(`${API}/pipeline/runs/test-run-id`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ run_id: "test-run-id", status: "running" }),
      })
    );
    await page.route(`${API}/pipeline/runs/test-run-id/logs`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );

    await page.getByTestId("run-button").click();
    await expect(page.getByTestId("run-button")).toBeDisabled();
  });

  test("topic input accepts text", async ({ page }) => {
    const input = page.getByTestId("topic-input");
    await input.fill("How to earn on Ko-fi in 2025");
    await expect(input).toHaveValue("How to earn on Ko-fi in 2025");
  });

  test("log terminal appears after run starts", async ({ page }) => {
    await page.route(`${API}/pipeline/run`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ run_id: "abc123", message: "Pipeline started" }),
      })
    );
    await page.route(`${API}/pipeline/runs/abc123`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ run_id: "abc123", status: "running" }),
      })
    );
    await page.route(`${API}/pipeline/runs/abc123/logs`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            run_id: "abc123",
            step: "orchestrator",
            level: "info",
            message: "Pipeline started.",
            data: {},
            timestamp: new Date().toISOString(),
          },
        ]),
      })
    );

    await page.getByTestId("run-button").click();
    await expect(page.getByTestId("log-terminal")).toBeVisible();
  });

  test("result card shows View Post link after completion", async ({ page }) => {
    const fakePost = {
      run_id: "done-run",
      title: "Test Post Title",
      content: "content",
      tags: ["writing"],
      status: "approved",
      revision_count: 0,
      created_at: new Date().toISOString(),
      quality_report: {
        score: 0.85,
        read_ratio_prediction: 0.7,
        issues: [],
        strengths: ["Good"],
      },
    };

    await page.route(`${API}/pipeline/run`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ run_id: "done-run", message: "Pipeline started" }),
      })
    );
    await page.route(`${API}/pipeline/runs/done-run/logs`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
    );
    await page.route(`${API}/pipeline/runs/done-run`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ run_id: "done-run", status: "completed" }),
      })
    );
    await page.route(`${API}/posts/done-run`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(fakePost),
      })
    );

    await page.getByTestId("run-button").click();

    await expect(page.getByTestId("result-card")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("view-post-link")).toBeVisible();
  });
});
