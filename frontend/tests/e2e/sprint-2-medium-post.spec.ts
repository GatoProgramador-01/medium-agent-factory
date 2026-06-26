/**
 * Sprint 2 — Medium Post Reader Visual Demo
 *
 * Covers: reading progress bar, Medium typography (drop cap, blockquote, inline code),
 * inline citation superscripts, footnotes footer, sources below article,
 * sidebar (quality panel only), mobile responsive layout.
 *
 * Run headed to watch live:
 *   npx playwright test sprint-2-medium-post --headed --project=chromium
 *
 * View screenshots after:
 *   npx playwright show-report
 */

import { test, expect, type Page } from "@playwright/test";
import * as path from "path";
import * as fs from "fs";

const SCREENSHOT_DIR = path.join(__dirname, "../../playwright-report/sprint-2");

async function shot(page: Page, name: string) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, `${name}.png`),
    fullPage: true,
  });
}

type PostMeta = {
  run_id: string;
  verified_sources?: unknown[];
};

async function getPosts(page: Page): Promise<PostMeta[]> {
  const response = await page.request.get("http://localhost:8000/posts");
  return response.json().catch(() => []);
}

async function getFirstPost(page: Page): Promise<PostMeta | null> {
  const posts = await getPosts(page);
  if (!Array.isArray(posts) || posts.length === 0) return null;
  return posts[0];
}

// ── 1. READING PROGRESS BAR ───────────────────────────────────────────────────

test("post reader — reading progress bar exists in DOM", async ({ page }) => {
  const post = await getFirstPost(page);
  if (!post) {
    test.skip(true, "No posts in DB");
    return;
  }

  await page.goto(`/posts/${post.run_id}`);
  await page.waitForSelector('[data-testid="read-time"]', { timeout: 15000 });

  await shot(page, "01-progress-bar-top");

  // Scroll to bottom
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(300);
  await shot(page, "02-progress-bar-scrolled");

  // Reading progress bar must be in the DOM (always rendered regardless of scroll)
  const progressBar = page.locator(".reading-progress");
  const count = await progressBar.count();
  expect(count).toBeGreaterThan(0);

  // After scrolling to bottom, width should be close to 100%
  if (count > 0) {
    const width = await progressBar.evaluate((el) => (el as HTMLElement).style.width);
    const widthNum = parseFloat(width);
    expect(widthNum).toBeGreaterThan(50);
  }
});

// ── 2. MEDIUM TYPOGRAPHY — DROP CAP ──────────────────────────────────────────

test("post reader — article body renders (drop cap when first block is paragraph)", async ({ page }) => {
  const post = await getFirstPost(page);
  if (!post) {
    test.skip(true, "No posts in DB");
    return;
  }

  await page.goto(`/posts/${post.run_id}`);
  await page.waitForSelector('[data-testid="read-time"]', { timeout: 15000 });

  // .post-body must always be present
  const postBody = page.locator(".post-body");
  await expect(postBody).toBeVisible();
  await postBody.scrollIntoViewIfNeeded();

  // Drop cap: only if content starts with a regular paragraph (not heading)
  const firstPara = page.locator(".post-first-para").first();
  const count = await firstPara.count();
  if (count > 0) {
    await firstPara.scrollIntoViewIfNeeded();
    await shot(page, "03-drop-cap");
  } else {
    await shot(page, "03-post-body");
  }
});

// ── 3. BLOCKQUOTE & INLINE CODE ──────────────────────────────────────────────

test("post reader — blockquote and inline code styling", async ({ page }) => {
  const post = await getFirstPost(page);
  if (!post) {
    test.skip(true, "No posts in DB");
    return;
  }

  await page.goto(`/posts/${post.run_id}`);
  await page.waitForSelector('[data-testid="read-time"]', { timeout: 15000 });

  const articleBody = page.locator(".post-body");
  await expect(articleBody).toBeVisible();
  await articleBody.scrollIntoViewIfNeeded();
  await shot(page, "04-article-body");

  const blockquote = page.locator(".post-blockquote").first();
  if (await blockquote.count() > 0) {
    await blockquote.scrollIntoViewIfNeeded();
    await shot(page, "05-blockquote");
  }

  const inlineCode = page.locator(".post-code").first();
  if (await inlineCode.count() > 0) {
    await inlineCode.scrollIntoViewIfNeeded();
    await shot(page, "06-inline-code");
  }
});

// ── 4. INLINE CITATION SUPERSCRIPTS ──────────────────────────────────────────

test("post reader — citation superscripts when sources exist", async ({ page }) => {
  const posts = await getPosts(page);
  if (!Array.isArray(posts) || posts.length === 0) {
    test.skip(true, "No posts in DB");
    return;
  }

  const withSources = posts.find(
    (p) => p.verified_sources && (p.verified_sources as unknown[]).length > 0
  );

  if (!withSources) {
    test.skip(true, "No posts with verified sources");
    return;
  }

  await page.goto(`/posts/${withSources.run_id}`);
  await page.waitForSelector('[data-testid="read-time"]', { timeout: 15000 });

  const citations = page.locator(".cite-ref");
  if (await citations.count() > 0) {
    await citations.first().scrollIntoViewIfNeeded();
    await shot(page, "07-citation-superscripts");
  } else {
    await shot(page, "07-no-matched-citations");
  }
});

// ── 5. FOOTNOTES FOOTER ───────────────────────────────────────────────────────

test("post reader — footnotes footer when sources exist", async ({ page }) => {
  const posts = await getPosts(page);
  if (!Array.isArray(posts) || posts.length === 0) {
    test.skip(true, "No posts in DB");
    return;
  }

  const withSources = posts.find(
    (p) => p.verified_sources && (p.verified_sources as unknown[]).length > 0
  );

  if (!withSources) {
    test.skip(true, "No posts with verified sources");
    return;
  }

  await page.goto(`/posts/${withSources.run_id}`);
  await page.waitForSelector('[data-testid="read-time"]', { timeout: 15000 });

  const footnotes = page.locator(".post-footnotes");
  if (await footnotes.count() > 0) {
    await footnotes.scrollIntoViewIfNeeded();
    await shot(page, "08-footnotes-footer");
  } else {
    await shot(page, "08-no-footnotes");
  }
});

// ── 6. SOURCES BELOW ARTICLE ──────────────────────────────────────────────────

test("post reader — sources section below article body", async ({ page }) => {
  const posts = await getPosts(page);
  if (!Array.isArray(posts) || posts.length === 0) {
    test.skip(true, "No posts in DB");
    return;
  }

  const withSources = posts.find(
    (p) => p.verified_sources && (p.verified_sources as unknown[]).length > 0
  );

  if (!withSources) {
    test.skip(true, "No posts with verified sources");
    return;
  }

  await page.goto(`/posts/${withSources.run_id}`);
  await page.waitForSelector('[data-testid="read-time"]', { timeout: 15000 });

  const sourcesBelow = page.locator(".sources-below");
  if (await sourcesBelow.count() > 0) {
    await sourcesBelow.scrollIntoViewIfNeeded();
    await shot(page, "09-sources-below-article");
    await expect(page.locator('[data-testid="sources-heading"]')).toBeVisible();
  } else {
    await shot(page, "09-no-sources-section");
  }
});

// ── 7. SIDEBAR — QUALITY PANEL ────────────────────────────────────────────────

test("post reader — sidebar renders when quality report exists", async ({ page }) => {
  const post = await getFirstPost(page);
  if (!post) {
    test.skip(true, "No posts in DB");
    return;
  }

  await page.goto(`/posts/${post.run_id}`);
  await page.waitForSelector('[data-testid="read-time"]', { timeout: 15000 });

  // Sidebar renders only when quality_report exists on the full post object
  const sidebar = page.locator(".post-sidebar");
  const hasSidebar = await sidebar.count() > 0;

  if (hasSidebar) {
    const boostBadge = page.locator('[data-testid="quality-boost-eligible"]');
    await expect(boostBadge).toBeVisible();
    await shot(page, "10-sidebar-quality-panel");
  } else {
    // Post has no quality data yet — take screenshot of the article-only layout
    await shot(page, "10-no-quality-sidebar");
  }
});

// ── 8. POST META BAR ──────────────────────────────────────────────────────────

test("post reader — meta bar shows read time and word count", async ({ page }) => {
  const post = await getFirstPost(page);
  if (!post) {
    test.skip(true, "No posts in DB");
    return;
  }

  await page.goto(`/posts/${post.run_id}`);
  await expect(page.locator('[data-testid="read-time"]')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('[data-testid="word-count"]')).toBeVisible();

  const metaBar = page.locator(".post-meta-bar");
  if (await metaBar.count() > 0) {
    await metaBar.scrollIntoViewIfNeeded();
  }
  await shot(page, "11-post-meta-bar");
});

// ── 9. MOBILE RESPONSIVE — 390px viewport ─────────────────────────────────────

test("post reader — mobile layout: sidebar hidden at 390px", async ({ page }) => {
  const post = await getFirstPost(page);
  if (!post) {
    test.skip(true, "No posts in DB");
    return;
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/posts/${post.run_id}`);
  await page.waitForSelector('[data-testid="read-time"]', { timeout: 15000 });

  await shot(page, "12-mobile-top");

  // Sidebar must be hidden (CSS display:none at ≤768px)
  const sidebar = page.locator(".post-sidebar");
  if (await sidebar.count() > 0) {
    const sidebarVisible = await sidebar.isVisible();
    expect(sidebarVisible).toBe(false);
    await shot(page, "13-mobile-sidebar-hidden");
  } else {
    await shot(page, "13-mobile-no-sidebar");
  }

  // Mobile quality bar — visible at mobile when post has quality data
  const mobileBar = page.locator(".mobile-quality-bar");
  if (await mobileBar.count() > 0) {
    await shot(page, "14-mobile-quality-bar");
  }

  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight / 2));
  await page.waitForTimeout(300);
  await shot(page, "15-mobile-scrolled");
});

// ── 10. FULL PAGE DESKTOP VIEW ────────────────────────────────────────────────

test("post reader — full desktop view stitched", async ({ page }) => {
  const post = await getFirstPost(page);
  if (!post) {
    test.skip(true, "No posts in DB");
    return;
  }

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`/posts/${post.run_id}`);
  await page.waitForSelector('[data-testid="read-time"]', { timeout: 15000 });
  await page.waitForTimeout(500);
  await shot(page, "16-desktop-full-page");
});
