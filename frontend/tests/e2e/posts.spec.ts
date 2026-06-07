import { test, expect } from "@playwright/test";

const MOCK_POSTS = [
  {
    run_id: "run-1",
    title: "How to Make $500/Month on Ko-fi",
    content: "Lorem ipsum content...",
    tags: ["monetization", "ko-fi"],
    status: "approved",
    revision_count: 1,
    created_at: "2026-06-06T22:00:00Z",
    quality_report: {
      score: 0.82,
      read_ratio_prediction: 0.74,
      issues: [],
      strengths: ["Good hook"],
    },
  },
  {
    run_id: "run-2",
    title: "Substack Growth Secrets",
    content: "Content here...",
    tags: ["substack", "newsletter"],
    status: "draft",
    revision_count: 0,
    created_at: "2026-06-05T18:00:00Z",
    quality_report: null,
  },
];

// Scope mocks to the backend port only — avoids intercepting the /posts HTML navigation
const API_POSTS = "http://localhost:8000/posts";
const API_POSTS_GLOB = "http://localhost:8000/posts**";

test.describe("Posts page", () => {
  test("shows all posts by default", async ({ page }) => {
    await page.route(API_POSTS, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_POSTS),
      })
    );

    await page.goto("/posts");
    await expect(page.getByTestId("page-heading")).toHaveText("Posts");
    await expect(page.getByTestId("post-card").first()).toBeVisible();
    expect(await page.getByTestId("post-card").count()).toBe(2);
  });

  test("filter bar renders all status buttons", async ({ page }) => {
    await page.route(API_POSTS_GLOB, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "[]",
      })
    );

    await page.goto("/posts");
    await expect(page.getByTestId("filter-all")).toBeVisible();
    await expect(page.getByTestId("filter-draft")).toBeVisible();
    await expect(page.getByTestId("filter-revised")).toBeVisible();
    await expect(page.getByTestId("filter-approved")).toBeVisible();
    await expect(page.getByTestId("filter-published")).toBeVisible();
  });

  test("clicking a filter button updates active state", async ({ page }) => {
    await page.route(API_POSTS_GLOB, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "[]",
      })
    );

    await page.goto("/posts");
    const draftBtn = page.getByTestId("filter-draft");
    await draftBtn.click();
    await expect(draftBtn).toHaveClass(/text-\[var\(--accent\)\]/);
  });

  test("empty state shows CTA linking to pipeline", async ({ page }) => {
    await page.route(API_POSTS_GLOB, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "[]",
      })
    );

    await page.goto("/posts");
    await expect(page.getByTestId("empty-state")).toBeVisible();
    await expect(page.getByTestId("empty-cta")).toBeVisible();

    await page.getByTestId("empty-cta").click();
    await expect(page).toHaveURL("/pipeline");
  });

  test("post card shows title and score badge", async ({ page }) => {
    await page.route(API_POSTS, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([MOCK_POSTS[0]]),
      })
    );

    await page.goto("/posts");
    const card = page.getByTestId("post-card").first();
    await expect(card).toContainText("How to Make $500/Month on Ko-fi");
    await expect(card).toContainText("82");
  });
});
