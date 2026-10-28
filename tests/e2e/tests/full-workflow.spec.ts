import path from "node:path";
import { test, expect, type Page } from "@playwright/test";
import { login, loginAsAdmin } from "../helpers/auth";

async function logoutViaApi(page: Page): Promise<void> {
  const response = await page.request.post("/api/auth/logout");
  expect(response.status()).toBe(204);
  await page.goto("/login");
  await expect(page).toHaveURL(/\/login/);
}

async function closeInstructionDialogIfOpen(page: Page): Promise<void> {
  const dialog = page.getByRole("dialog", { name: /Session Instructions/i });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const isOpen = await dialog.isVisible({ timeout: 2_000 }).catch(() => false);
    if (!isOpen) return;

    const continueButton = dialog.getByRole("button", { name: /^Continue$/ });
    const closeButton = dialog.getByRole("button", { name: /^Close$/ });

    if (await continueButton.isVisible().catch(() => false)) {
      await continueButton.click({ force: true });
    } else if (await closeButton.isVisible().catch(() => false)) {
      await closeButton.click({ force: true });
    } else {
      await page.keyboard.press("Escape");
    }

    await page.waitForTimeout(250);
  }

  await expect(dialog).toBeHidden({ timeout: 10_000 });
}

async function scoreCurrentImageAllOrdinalsAsTwo(page: Page, expectedCount: number): Promise<void> {
  const scoreTwoButtons = page.getByRole("button", { name: /^2\b/ });
  await expect(scoreTwoButtons).toHaveCount(expectedCount, { timeout: 10_000 });
  for (let i = 0; i < expectedCount; i += 1) {
    await scoreTwoButtons.nth(i).click();
  }
}

test.describe("Full Workflow", () => {
  test("admin setup to participant submission to admin evaluation/export", async ({ page }) => {
    test.setTimeout(180_000);

    const runId = Date.now();
    const datasetName = `e2e_workflow_${runId}`;
    const participantFirstName = "Workflow";
    const participantLastName = "Participant";
    const participantFullName = `${participantFirstName} ${participantLastName}`;
    const participantEmail = `workflow_${runId}@example.com`;
    const participantPassword = "workflow-pass-123";
    const fixtureDatasetDir = path.resolve(process.cwd(), "fixtures", "mini_dataset");

    // 1) Admin logs in and uploads a tiny dataset via the real UI.
    await loginAsAdmin(page);
    await page.goto("/admin/images");
    await expect(page).toHaveURL(/\/admin\/images/);

    await page
      .locator('input[type="file"][webkitdirectory]')
      .setInputFiles(fixtureDatasetDir);

    await page.getByLabel("Dataset Name").fill(datasetName);
    await expect(page.getByText("Name is available")).toBeVisible({ timeout: 10_000 });

    await page.getByRole("button", { name: "Upload" }).click();
    await expect(page.getByText("Upload completed successfully").first()).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByRole("cell", { name: datasetName })).toBeVisible({
      timeout: 10_000,
    });

    // 2) Admin creates a participant account.
    await page.goto("/admin/users/create");
    await expect(page).toHaveURL(/\/admin\/users\/create/);
    await page.getByLabel("First Name").fill(participantFirstName);
    await page.getByLabel("Last Name").fill(participantLastName);
    await page.getByLabel("Institution").fill("E2E Test Center");
    await page.getByLabel("Email").fill(participantEmail);
    await page.getByLabel("Password").fill(participantPassword);
    await page.getByRole("button", { name: "Create User" }).click();
    await expect(page).toHaveURL(/\/admin\/users$/);
    await expect(page.getByRole("cell", { name: participantFullName })).toBeVisible();

    // 3) Admin creates a study and configures settings.
    await page.goto("/admin/studies");
    await page.getByRole("button", { name: "New Study" }).click();
    await expect(page).toHaveURL(/\/admin\/studies\/\d+\/settings/);

    const match = page.url().match(/\/admin\/studies\/(\d+)\/settings/);
    expect(match).not.toBeNull();
    const studyId = Number(match![1]);

    await page.getByLabel("Description").fill("E2E full workflow study");
    await page.getByRole("button", { name: "Save Settings" }).click();
    await expect(page.getByText("Settings saved.").first()).toBeVisible({ timeout: 10_000 });

    // 4) Questions tab: verify schema is present.
    await page.getByRole("tab", { name: "Questions" }).click();
    await expect(
      page.locator('input[value="Nuclear detail & cytology"]'),
    ).toBeVisible();
    await expect(page.locator('input[value="Tissue architecture"]')).toBeVisible();

    // 5) Images tab: select uploaded dataset and add all images to the study.
    await page.getByRole("tab", { name: "Images" }).click();
    await page.getByRole("button", { name: "Select dataset..." }).click();
    await page.getByRole("menuitemradio", { name: `${datasetName} (2)`, exact: true }).click();
    await expect(page.getByText("Dataset updated.").first()).toBeVisible({ timeout: 10_000 });

    for (const filename of ["img_a.png", "img_b.png"]) {
      await page.locator("[data-select-id]").filter({
        has: page.getByAltText(filename, { exact: true }),
      }).click();
      await expect(page.locator("button").filter({
        has: page.getByAltText(filename, { exact: true }),
      })).toBeVisible();
    }
    await expect(page.getByRole("heading", { name: "Study Images", exact: true })
      .locator("..").getByText("2 images", { exact: true })).toBeVisible();

    // 6) Participants tab: assign the new participant.
    await page.getByRole("tab", { name: "Participants" }).click();
    const availableUser = page
      .locator("div.rounded-md.px-3.py-2")
      .filter({ hasText: participantEmail });
    await expect(availableUser).toBeVisible({ timeout: 10_000 });
    await availableUser.getByRole("button", { name: "Assign" }).click();
    await expect(page.getByText("User assigned successfully").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      page.getByRole("row").filter({ hasText: participantFullName }),
    ).toBeVisible({ timeout: 10_000 });

    // 7) Activate study.
    await page.goto(`/admin/studies/${studyId}`);
    const activateButton = page.getByRole("button", { name: "Activate" });
    await expect(activateButton).toBeEnabled({ timeout: 15_000 });
    await activateButton.click();
    await page.getByRole("dialog").getByRole("button", { name: "Activate" }).click();
    await expect(page.getByText("Study activated.").first()).toBeVisible({ timeout: 10_000 });

    // 8) Participant logs in and completes the full evaluation.
    await logoutViaApi(page);
    await login(page, participantEmail, participantPassword);
    await expect(page).toHaveURL(/\/studies/);

    await page.goto(`/studies/${studyId}/evaluate`);
    await expect(page).toHaveURL(new RegExp(`/studies/${studyId}/evaluate`));
    await closeInstructionDialogIfOpen(page);

    await expect(page.getByText("Nuclear detail & cytology")).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText(/1\s*\/\s*2/)).toBeVisible();

    // Determine required ordinal count from live participant study payload.
    const studiesRes = await page.request.get("/api/studies");
    expect(studiesRes.ok()).toBeTruthy();
    const studiesJson = (await studiesRes.json()) as Array<{
      id: number;
      rating_schema?: { questions?: Array<{ type?: string }> };
    }>;
    const thisStudy = studiesJson.find((s) => s.id === studyId);
    expect(thisStudy).toBeTruthy();
    const ordinalCount =
      thisStudy?.rating_schema?.questions?.filter((q) => q.type === "ordinal").length ?? 0;
    expect(ordinalCount).toBeGreaterThan(0);

    // Image 1: answer all ordinal questions.
    await closeInstructionDialogIfOpen(page);
    await scoreCurrentImageAllOrdinalsAsTwo(page, ordinalCount);
    await closeInstructionDialogIfOpen(page);
    await page.keyboard.press("ArrowRight");

    // Image 2: answer all ordinal questions.
    await expect(page.getByText(/2\s*\/\s*2/)).toBeVisible();
    await closeInstructionDialogIfOpen(page);
    await scoreCurrentImageAllOrdinalsAsTwo(page, ordinalCount);
    await closeInstructionDialogIfOpen(page);

    // Submit should now be enabled.
    await expect(page.getByRole("contentinfo").getByText("100%", { exact: true })).toBeVisible({ timeout: 10_000 });
    const submitButton = page.getByRole("button", { name: /^Submit$/ }).first();
    await expect(submitButton).toBeEnabled({ timeout: 10_000 });
    await submitButton.click();
    await page
      .getByRole("alertdialog")
      .getByRole("button", { name: /^Submit$/ })
      .click();

    await expect(page.getByText("Evaluation submitted successfully.").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      page.getByText("This evaluation has been submitted and is read-only."),
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Submitted").first()).toBeVisible();

    // 9) Admin verifies finished state, evaluation visibility, and export contents.
    await logoutViaApi(page);
    await loginAsAdmin(page);
    await page.goto(`/admin/studies/${studyId}/participants`);

    await expect(
      page.getByText("All participants submitted. Permanently locked."),
    ).toBeVisible({ timeout: 15_000 });

    const participantRow = page.getByRole("row").filter({ hasText: participantFullName });
    await expect(participantRow).toContainText("Submitted");
    await expect(participantRow).toContainText("100%");

    await page.getByRole("tab", { name: "Evaluation" }).click();
    await expect(page.getByText("Summary").first()).toBeVisible({ timeout: 15_000 });

    await page.getByRole("tab", { name: "Export" }).click();
    await expect(page.getByText("1 of 1 users submitted")).toBeVisible({
      timeout: 10_000,
    });

    const exportResponse = await page.request.get(`/api/admin/studies/${studyId}/export`);
    expect(exportResponse.ok()).toBeTruthy();
    const csv = await exportResponse.text();
    const lines = csv.trim().split(/\r?\n/);

    // 2 images rated by 1 non-test participant => 1 header + 2 data rows.
    expect(lines.length).toBe(3);
    expect(csv).toContain("user_id,user_name");
    expect(csv).toContain(participantFullName);
    expect(csv).not.toContain("Test User");
  });
});
