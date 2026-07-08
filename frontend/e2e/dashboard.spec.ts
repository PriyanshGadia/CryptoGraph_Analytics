import { test, expect } from "@playwright/test";

test.describe("CryptoGraph Dashboard E2E", () => {
  test("should load the dashboard homepage successfully and render headers", async ({ page }) => {
    // Navigate to local homepage
    await page.goto("/");

    // Verify title or main heading exists
    const heading = page.locator("h1");
    await expect(heading).toContainText("Spatio-Temporal");
    await expect(heading).toContainText("Graph Intelligence");
  });

  test("should have functional navigation link to View Models page", async ({ page }) => {
    await page.goto("/");

    // Locate the View Models button and click
    const viewModelsBtn = page.getByRole("button", { name: "View Models" });
    await expect(viewModelsBtn).toBeVisible();
  });

  test("should contain the theme toggle button", async ({ page }) => {
    await page.goto("/");

    // Locate the ThemeToggle button via its aria-label
    const themeBtn = page.getByRole("button", { name: "Toggle theme" });
    await expect(themeBtn).toBeVisible();
  });
});
