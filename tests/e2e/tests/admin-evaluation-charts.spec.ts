import { test, expect } from "@playwright/test";
import { loginAsAdmin } from "../helpers/auth";

test.describe("Admin Evaluation Charts", () => {
  test("evaluation tab shows summary and chart data with seeded data", async ({
    page,
  }) => {
    await loginAsAdmin(page);

    // Navigate to Demo Evaluation Study
    await page
      .getByRole("link", { name: "Demo Evaluation Study" })
      .first()
      .click();
    await expect(page).toHaveURL(/\/admin\/studies\/\d+/);

    // Click Evaluation tab
    await page.getByRole("tab", { name: "Evaluation" }).click();

    // Wait for "Submitted only" toggle to confirm filter bar loaded
    await expect(page.getByText("Submitted only")).toBeVisible({
      timeout: 10_000,
    });

    // Wait for the Summary card to appear (this means evaluation data has loaded)
    await expect(page.getByText("Summary").first()).toBeVisible({
      timeout: 15_000,
    });

    // Verify statistics metrics are visible (ICC, Fleiss' Kappa, Mann-Whitney)
    await expect(page.getByText("ICC").first()).toBeVisible();
    await expect(page.getByText("Fleiss' Kappa").first()).toBeVisible();

    // Verify chart cards are present (conditionally rendered based on data).
    // Score Distribution should be available with seeded data.
    await expect(
      page.getByText("Score Distribution").first()
    ).toBeVisible({ timeout: 10_000 });
  });
});
