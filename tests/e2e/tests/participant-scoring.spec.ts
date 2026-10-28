import { test, expect, type Page } from "@playwright/test";
import { loginAsParticipant } from "../helpers/auth";

function positionIndicator(page: Page) {
  return page.locator("footer span").filter({ hasText: "/" }).first();
}

async function getCurrentPosition(page: Page) {
  const text = await positionIndicator(page).textContent();
  const match = text?.match(/(\d+)\s*\/\s*80/);
  if (!match) {
    throw new Error(`Could not parse image position from: ${text}`);
  }
  return Number(match[1]);
}

test.describe("Participant Scoring", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsParticipant(page);
    await page.locator("a[href*='/evaluate']").first().click();
    await expect(page).toHaveURL(/\/studies\/\d+\/evaluate/);
    // Wait for rating form to load
    await expect(page.getByText("Nuclear detail & cytology")).toBeVisible();
  });

  test("score an image and verify persistence across navigation", async ({
    page,
  }) => {
    // The schema has 0-2 scale: "0 inconsistent", "1 borderline", "2 consistent"
    // Click the first "2 consistent" button (belongs to "Nuclear detail & cytology")
    await page
      .getByRole("button", { name: "2 consistent" })
      .first()
      .click();

    // Wait for auto-save
    await page.waitForTimeout(500);

    const start = await getCurrentPosition(page);
    if (start < 80) {
      await page.keyboard.press("ArrowRight");
      await expect(positionIndicator(page)).toHaveText(new RegExp(`${start + 1}\\s*\\/\\s*80`));

      await page.keyboard.press("ArrowLeft");
      await expect(positionIndicator(page)).toHaveText(new RegExp(`${start}\\s*\\/\\s*80`));
    } else {
      await page.keyboard.press("ArrowLeft");
      await expect(positionIndicator(page)).toHaveText(/79\s*\/\s*80/);

      await page.keyboard.press("ArrowRight");
      await expect(positionIndicator(page)).toHaveText(/80\s*\/\s*80/);
    }

    // Verify score "2" is still selected (button should have bg-primary class)
    const selectedButton = page
      .getByRole("button", { name: "2 consistent" })
      .first();
    await expect(selectedButton).toHaveClass(/bg-primary/);
  });

  test("scores persist after browser refresh", async ({ page }) => {
    // Click the first "1 borderline" button (Nuclear detail & cytology)
    await page
      .getByRole("button", { name: "1 borderline" })
      .first()
      .click();

    // Wait for auto-save
    await page.waitForTimeout(500);

    // Refresh the page
    await page.reload();

    // Wait for rating form to load again
    await expect(page.getByText("Nuclear detail & cytology")).toBeVisible();

    // Verify score "1" is still selected (has bg-primary class)
    const selectedButton = page
      .getByRole("button", { name: "1 borderline" })
      .first();
    await expect(selectedButton).toHaveClass(/bg-primary/);
  });
});
