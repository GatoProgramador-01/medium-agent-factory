/**
 * Sprint UI Demo — Visual walkthrough of all UI changes from the UX/UI sprint.
 *
 * Run headed to watch live:
 *   npx playwright test sprint-ui-demo --headed --project=chromium
 *
 * View screenshots after:
 *   npx playwright show-report
 */

import { test, expect, type Page } from "@playwright/test";
import * as path from "path";
import * as fs from "fs";

const SCREENSHOT_DIR = path.join(__dirname, "../../playwright-report/sprint-ui");

async function shot(page: Page, name: string) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, `${name}.png`),
    fullPage: true,
  });
}

// ── 1. HOME PAGE ─────────────────────────────────────────────────────────────

test("home — hero pill badges and stat icons", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector('[data-testid="page-heading"]');

  // Wait for stats to load (skeleton disappears)
  await page.waitForSelector('[data-testid="stat-pipeline-runs"]', { timeout: 10000 });

  // Assert pill badges exist
  const pills = page.locator("text=LangGraph");
  await expect(pills.first()).toBeVisible();

  const claudePill = page.locator("text=/Claude/");
  await expect(claudePill.first()).toBeVisible();

  const mongoPill = page.locator("text=MongoDB");
  await expect(mongoPill.first()).toBeVisible();

  await shot(page, "01-home-hero-pills");

  // Scroll to CTAs
  await page.locator('[data-testid="cta-run-pipeline"]').scrollIntoViewIfNeeded();
  await shot(page, "02-home-cta-cards");
});

test("home — recent posts with color-coded borders and score bars", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector('[data-testid="page-heading"]');

  // Wait for posts section or empty state
  await page.waitForTimeout(2000);

  const hasRecentPosts = await page.locator('[data-testid="recent-posts"]').isVisible().catch(() => false);

  if (hasRecentPosts) {
    // Score bar should exist inside each recent post card
    const scoreBars = page.locator(".score-bar-track");
    const count = await scoreBars.count();
    expect(count).toBeGreaterThan(0);

    await shot(page, "03-home-recent-posts-score-bars");
  } else {
    await shot(page, "03-home-empty-state");
  }
});

// ── 2. PIPELINE PAGE ─────────────────────────────────────────────────────────

test("pipeline — mode tabs and input form", async ({ page }) => {
  await page.goto("/pipeline");
  await page.waitForSelector('[data-testid="page-heading"]');

  // Mode tabs
  await expect(page.locator('[data-testid="tab-single"]')).toBeVisible();
  await expect(page.locator('[data-testid="tab-series"]')).toBeVisible();

  await shot(page, "04-pipeline-idle-single");

  // Switch to series tab
  await page.click('[data-testid="tab-series"]');
  await expect(page.locator('[data-testid="theme-input"]')).toBeVisible();
  await shot(page, "05-pipeline-series-tab");
});

test("pipeline — agent stepper appears when run starts", async ({ page }) => {
  await page.goto("/pipeline");
  await page.waitForSelector('[data-testid="topic-input"]');

  // Fill topic
  await page.fill('[data-testid="topic-input"]', "How Claude Code parallel agents cut development time by 60%");

  // Start run
  await page.click('[data-testid="run-button"]');

  // Stepper should appear
  const stepper = page.locator('[data-testid="agent-stepper"]');
  await expect(stepper).toBeVisible({ timeout: 15000 });

  await shot(page, "06-pipeline-stepper-visible");

  // Wait a moment and capture the stepper with active node
  await page.waitForTimeout(3000);
  await shot(page, "07-pipeline-stepper-active");

  // Log terminal
  const logPanel = page.locator('[data-testid="log-terminal"]');
  const hasLogs = await logPanel.isVisible().catch(() => false);
  if (hasLogs) {
    await shot(page, "08-pipeline-log-lines");
  }
});

// ── 3. POSTS LIST ─────────────────────────────────────────────────────────────

test("posts — filter toolbar and PostCard left borders", async ({ page }) => {
  await page.goto("/posts");
  await page.waitForSelector('[data-testid="page-heading"]');
  await page.waitForTimeout(1500);

  // Filter bar with toolbar container
  await expect(page.locator('[data-testid="filter-all"]')).toBeVisible();
  await expect(page.locator('[data-testid="search-input"]')).toBeVisible();

  await shot(page, "09-posts-filter-toolbar");

  // Wait for loading to finish — either posts or empty state will appear
  await page.waitForSelector('[data-testid="post-card"], [data-testid="empty-state"]', { timeout: 15000 });

  const hasPosts = await page.locator('[data-testid="post-card"]').first().isVisible().catch(() => false);

  if (hasPosts) {
    // Hover first card to see arrow animation
    await page.locator('[data-testid="post-card"]').first().hover();
    await shot(page, "10-posts-card-hover-arrow");

    // Check score bar exists on cards
    const scoreBars = page.locator(".score-bar-track");
    const count = await scoreBars.count();
    expect(count).toBeGreaterThan(0);
    await shot(page, "11-posts-cards-with-score-bars");
  } else {
    // Empty state with ◈ symbol
    await shot(page, "10-posts-empty-state-symbol");
  }
});

test("posts — boost filter", async ({ page }) => {
  await page.goto("/posts");
  await page.waitForSelector('[data-testid="filter-boost"]');

  await page.click('[data-testid="filter-boost"]');
  await page.waitForTimeout(500);
  await shot(page, "12-posts-boost-filter-active");
});

// ── 4. POST READER ────────────────────────────────────────────────────────────

test("post reader — quality panel score ring and issue breakdown", async ({ page }) => {
  // First get a real post from the API
  const response = await page.request.get("http://localhost:8000/posts");
  const posts = await response.json().catch(() => []);

  if (!Array.isArray(posts) || posts.length === 0) {
    test.skip(true, "No posts in DB — skipping post reader test");
    return;
  }

  const runId = posts[0].run_id as string;
  await page.goto(`/posts/${runId}`);
  await page.waitForSelector('[data-testid="read-time"]', { timeout: 15000 });

  await shot(page, "13-post-reader-full");

  // Score ring SVG
  const scoreRing = page.locator("svg circle").first();
  const hasRing = await scoreRing.isVisible().catch(() => false);
  if (hasRing) {
    await shot(page, "14-post-reader-score-ring");
  }

  // Quality panel in sidebar
  const boostBadge = page.locator('[data-testid="quality-boost-eligible"]');
  await expect(boostBadge).toBeVisible();

  // Read ratio label (Exceptional / Strong / Weak)
  const readRatio = page.locator('[data-testid="quality-read-ratio"]');
  await expect(readRatio).toBeVisible();
  await shot(page, "15-post-reader-sidebar");

  // Footer actions with icon labels
  await page.locator("text=/Copy/").first().scrollIntoViewIfNeeded();
  await shot(page, "16-post-reader-footer-actions");
});

test("post reader — revision history panel with deltas", async ({ page }) => {
  const response = await page.request.get("http://localhost:8000/posts");
  const posts = await response.json().catch(() => []);

  if (!Array.isArray(posts) || posts.length === 0) {
    test.skip(true, "No posts in DB");
    return;
  }

  // Find a post with multiple revision cycles
  const multiRevPost = (posts as Array<{ run_id: string; revision_count: number }>)
    .find((p) => p.revision_count > 1);

  if (!multiRevPost) {
    test.skip(true, "No multi-revision posts to demo revision history");
    return;
  }

  await page.goto(`/posts/${multiRevPost.run_id}`);
  await page.waitForSelector('[data-testid="read-time"]', { timeout: 15000 });

  const revPanel = page.locator('[data-testid="revision-history-heading"]');
  const hasRevPanel = await revPanel.isVisible().catch(() => false);

  if (hasRevPanel) {
    await revPanel.scrollIntoViewIfNeeded();
    await shot(page, "17-revision-history-delta-indicators");
  }
});

// ── 5. SERIES PAGE ────────────────────────────────────────────────────────────

test("series — cards with progress bars or empty state", async ({ page }) => {
  await page.goto("/series");
  await page.waitForSelector('[data-testid="page-heading"]');
  await page.waitForTimeout(1500);

  // Wait for skeleton to clear — series page loads from API
  await page.waitForFunction(
    () => document.querySelectorAll(".skeleton").length === 0,
    { timeout: 20000 }
  ).catch(() => {}); // proceed even if skeleton doesn't clear

  await shot(page, "18-series-page-loaded");

  const hasSeries = await page.locator('[data-testid^="series-card-"]').first().isVisible().catch(() => false);

  if (hasSeries) {
    // Progress bar should be inside each series card
    const progressBars = page.locator(".score-bar-track");
    const count = await progressBars.count();
    expect(count).toBeGreaterThan(0);
    await shot(page, "18-series-progress-bars");

    // Score circles (small filled divs next to post titles)
    await shot(page, "19-series-post-score-circles");
  } else {
    await shot(page, "18-series-empty-state-symbol");
  }
});

// ── 6. ANALYTICS ─────────────────────────────────────────────────────────────

test("analytics — terminal stat boxes and agent table", async ({ page }) => {
  await page.goto("/analytics");
  await page.waitForSelector('[data-testid="page-heading"]');
  await page.waitForTimeout(2000);

  await expect(page.locator('[data-testid="stat-cost"]')).toBeVisible();
  await expect(page.locator('[data-testid="stat-calls"]')).toBeVisible();

  await shot(page, "20-analytics-stat-boxes");

  await shot(page, "21-analytics-agent-table");
});

// ── 7. NAVIGATION ACTIVE STATE ───────────────────────────────────────────────

test("nav — active route indicator per page", async ({ page }) => {
  const routes = [
    { path: "/", label: "Home" },
    { path: "/pipeline", label: "Pipeline" },
    { path: "/posts", label: "Posts" },
    { path: "/analytics", label: "Analytics" },
    { path: "/series", label: "Series" },
  ];

  for (const route of routes) {
    await page.goto(route.path);
    await page.waitForSelector("header");
    // Orange underline on active nav link — check border-bottom style
    await shot(page, `22-nav-active-${route.label.toLowerCase()}`);
  }
});

// ── 8. SOURCES PANEL ─────────────────────────────────────────────────────────

test("sources panel — claim type badges and truncated claims", async ({ page }) => {
  const response = await page.request.get("http://localhost:8000/posts");
  const posts = await response.json().catch(() => []);

  if (!Array.isArray(posts) || posts.length === 0) {
    test.skip(true, "No posts in DB");
    return;
  }

  // Find a post with verified sources
  const withSources = (posts as Array<{ run_id: string; verified_sources?: unknown[] }>)
    .find((p) => p.verified_sources && p.verified_sources.length > 0);

  if (!withSources) {
    test.skip(true, "No posts with verified sources to demo sources panel");
    return;
  }

  await page.goto(`/posts/${withSources.run_id}`);
  await page.waitForSelector('[data-testid="read-time"]', { timeout: 15000 });

  const sourcesPanel = page.locator('[data-testid="sources-heading"]');
  const hasPanel = await sourcesPanel.isVisible().catch(() => false);

  if (hasPanel) {
    await sourcesPanel.scrollIntoViewIfNeeded();
    await shot(page, "23-sources-panel-claim-badges");
  }
});
