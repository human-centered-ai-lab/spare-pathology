import { test, expect } from "@playwright/test";
import { loginAsParticipant } from "../helpers/auth";

test.describe("Participant Reset", () => {
  test("reset test data clears all ratings", async ({ page }) => {
    // Login as test participant
    await loginAsParticipant(page);

    // Navigate to evaluate page and score an image
    await page.locator("a[href*='/evaluate']").first().click();
    await expect(page).toHaveURL(/\/studies\/\d+\/evaluate/);
    await expect(page.getByText("Nuclear detail & cytology")).toBeVisible();

    // Score the first question with "1 borderline"
    await page
      .getByRole("button", { name: "1 borderline" })
      .first()
      .click();

    // Wait for auto-save
    await page.waitForTimeout(500);

    // Click the "Reset" button in the evaluation footer
    await page.getByRole("button", { name: "Reset", exact: true }).click();

    // Confirm the reset in the "Reset Test Data?" dialog
    await expect(
      page.getByRole("heading", { name: "Reset Test Data?" })
    ).toBeVisible();
    await page.getByRole("button", { name: "Reset All Data" }).click();

    // Verify success toast and page reload (toast says "Test data reset. Reloading...")
    // After reload, progress should be 0%
    await expect(page.getByText(/0\s*%/).first()).toBeVisible({
      timeout: 10_000,
    });
  });
});
