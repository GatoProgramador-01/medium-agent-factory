import { chromium } from "@playwright/test";

// Pre-compiles all pages so individual tests don't hit cold-start timeouts
export default async function globalSetup() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const pages = ["/", "/pipeline", "/posts", "/analytics"];

  for (const route of pages) {
    try {
      await page.goto(`http://localhost:3000${route}`, {
        waitUntil: "domcontentloaded",
        timeout: 90000,
      });
    } catch {
      // Page may 404 or error on first compile — that's OK, we just want to trigger compilation
    }
  }

  await browser.close();
}
