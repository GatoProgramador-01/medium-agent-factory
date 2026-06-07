import { test, expect } from "@playwright/test";

test.describe("Navigation", () => {
  test("dashboard loads with heading and CTAs", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("page-heading")).toHaveText("Dashboard");
    await expect(page.getByTestId("cta-run-pipeline")).toBeVisible();
    await expect(page.getByTestId("cta-view-posts")).toBeVisible();
  });

  test("nav link Run Pipeline navigates to /pipeline", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("nav-pipeline").click();
    await expect(page).toHaveURL("/pipeline");
    await expect(page.getByTestId("page-heading")).toHaveText("Run Pipeline");
  });

  test("nav link Posts navigates to /posts", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("nav-posts").click();
    await expect(page).toHaveURL("/posts");
    await expect(page.getByTestId("page-heading")).toHaveText("Posts");
  });

  test("nav link Analytics navigates to /analytics", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("nav-analytics").click();
    await expect(page).toHaveURL("/analytics");
    await expect(page.getByTestId("page-heading")).toHaveText("Analytics");
  });

  test("logo link returns to dashboard", async ({ page }) => {
    await page.goto("/pipeline");
    await page.getByRole("link", { name: "~/factory" }).first().click();
    await expect(page).toHaveURL("/");
  });

  test("dashboard CTA Run Pipeline navigates to /pipeline", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("cta-run-pipeline").click();
    await expect(page).toHaveURL("/pipeline");
  });

  test("dashboard CTA View Posts navigates to /posts", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("cta-view-posts").click();
    await expect(page).toHaveURL("/posts");
  });
});
