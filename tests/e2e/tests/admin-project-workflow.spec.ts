import { test, expect } from "@playwright/test";
import { loginAsAdmin } from "../helpers/auth";

test.describe("Admin Study Workflow", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test("studies list shows seeded study", async ({ page }) => {
    // Navigate to studies via sidebar
    await page.getByRole("link", { name: "Studies" }).first().click();
    await expect(page).toHaveURL(/\/admin\/studies$/);
    await expect(
      page.getByRole("heading", { name: "Studies" })
    ).toBeVisible();
    // Seeded "Demo Evaluation Study" should be visible as a card title.
    await expect(
      page.getByText("Demo Evaluation Study").first()
    ).toBeVisible();
  });

  test("study detail shows all tabs", async ({ page }) => {
    // Click the seeded study in sidebar.
    await page
      .getByRole("link", { name: "Demo Evaluation Study" })
      .first()
      .click();
    await expect(page).toHaveURL(/\/admin\/studies\/\d+/);

    // Should see tab navigation with all 6 tabs.
    await expect(page.getByRole("tab", { name: "General" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Questions" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Images" })).toBeVisible();
    await expect(
      page.getByRole("tab", { name: "Participants" })
    ).toBeVisible();
    await expect(page.getByRole("tab", { name: "Evaluation" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Export" })).toBeVisible();
  });

  test("create new study", async ({ page }) => {
    await page.getByRole("link", { name: "Studies" }).first().click();
    await expect(page).toHaveURL(/\/admin\/studies$/);

    await page.getByRole("button", { name: "New Study" }).click();

    // Creating routes directly into the new study page.
    await expect(page).toHaveURL(/\/admin\/studies\/\d+\/settings/);
    await expect(page.getByRole("tab", { name: "General" })).toBeVisible();
  });

  test("study settings tab shows general settings", async ({ page }) => {
    await page
      .getByRole("link", { name: "Demo Evaluation Study" })
      .first()
      .click();
    await expect(page).toHaveURL(/\/admin\/studies\/\d+/);

    // General tab should be default or clickable.
    await page.getByRole("tab", { name: "General" }).click();
    // Should see the "General Settings" card and Description label.
    await expect(page.getByText("General Settings")).toBeVisible();
    await expect(page.getByLabel("Description")).toBeVisible();
  });

  test("questions tab shows rating questions", async ({ page }) => {
    await page
      .getByRole("link", { name: "Demo Evaluation Study" })
      .first()
      .click();
    await page.getByRole("tab", { name: "Questions" }).click();

    // Question names are rendered as Input values in the schema builder
    await expect(
      page.locator('input[value="Nuclear detail & cytology"]')
    ).toBeVisible();
    await expect(
      page.locator('input[value="Tissue architecture"]')
    ).toBeVisible();
  });

  test("images tab shows images", async ({ page }) => {
    await page
      .getByRole("link", { name: "Demo Evaluation Study" })
      .first()
      .click();
    await page.getByRole("tab", { name: "Images" }).click();

    // Should show image count info (80 images in seed)
    await expect(page.getByText(/80 images/).first()).toBeVisible();
  });

  test("participants tab shows assigned users", async ({ page }) => {
    await page
      .getByRole("link", { name: "Demo Evaluation Study" })
      .first()
      .click();
    await page.getByRole("tab", { name: "Participants" }).click();

    // Should see seeded participants (Amara, Carlos, Yuki, Eleanor + test user)
    await expect(page.getByText(/Amara/).first()).toBeVisible();
  });

  test("evaluation tab shows summary", async ({ page }) => {
    await page
      .getByRole("link", { name: "Demo Evaluation Study" })
      .first()
      .click();
    await page.getByRole("tab", { name: "Evaluation" }).click();

    // Should show the "Submitted only" toggle (appears in the filter bar)
    await expect(page.getByText("Submitted only")).toBeVisible({
      timeout: 10_000,
    });
  });
});
