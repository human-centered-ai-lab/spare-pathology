import { test, expect } from "@playwright/test";
import { login, loginAsParticipant } from "../helpers/auth";

test.describe("Participant Submission", () => {
  test("incomplete evaluation keeps submit disabled", async ({ page }) => {
    await loginAsParticipant(page);
    await page.locator("a[href*='/evaluate']").first().click();
    await expect(page).toHaveURL(/\/studies\/\d+\/evaluate/);

    await expect(page.getByRole("button", { name: "Submit" })).toBeDisabled();
  });

  test("submitted participant sees read-only state", async ({ page }) => {
    // Login as a seeded submitted participant (Amara)
    await login(page, "amara.test@example.com", "password123");
    await expect(page).toHaveURL(/\/studies/);

    // The study card should show "Submitted" badge
    await expect(page.getByText("Submitted").first()).toBeVisible();
  });

  test("test user reset button is visible", async ({ page }) => {
    await loginAsParticipant(page);
    await page.locator("a[href*='/evaluate']").first().click();
    await expect(page).toHaveURL(/\/studies\/\d+\/evaluate/);

    // Test user should see a Reset button
    await expect(
      page.getByRole("button", { name: "Reset" })
    ).toBeVisible();
  });
});
