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

async function closeInstructionDialogIfOpen(page: Page) {
  const dialog = page.getByRole("dialog", { name: /Session Instructions/i });
  if (await dialog.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await dialog.getByRole("button", { name: /^Continue$/ }).click();
    await expect(dialog).toBeHidden({ timeout: 10_000 });
  }
}

async function getDemoStudyId(page: Page): Promise<number> {
  const studiesRes = await page.request.get("/api/studies");
  expect(studiesRes.ok()).toBeTruthy();
  const studies = (await studiesRes.json()) as Array<{ id: number; name: string }>;
  const demoStudy = studies.find((study) => study.name === "Demo Evaluation Study");
  expect(demoStudy).toBeTruthy();
  return demoStudy!.id;
}

function imageSidebarViewport(page: Page) {
  return page.locator('[data-image-sidebar="true"] [data-slot="scroll-area-viewport"]').first();
}

test.describe("Participant Evaluation", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsParticipant(page);
    await expect(page).toHaveURL(/\/studies/);
  });

  test("studies page shows Demo Evaluation Study", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "My Studies" })
    ).toBeVisible();
    await expect(page.getByText("Demo Evaluation Study")).toBeVisible();
  });

  test("click evaluation button navigates to evaluate page", async ({
    page,
  }) => {
    // Navigate to the Demo project's evaluation (use the card containing the project name)
    const demoCard = page.locator("a[href*='/evaluate']").first();
    await demoCard.click();
    await expect(page).toHaveURL(/\/studies\/\d+\/evaluate/);
    // Should see the study name in the header
    await expect(page.getByText("Demo Evaluation Study")).toBeVisible();
  });

  test("evaluation page shows image sidebar with images", async ({ page }) => {
    await page.locator("a[href*='/evaluate']").first().click();
    await expect(page).toHaveURL(/\/studies\/\d+\/evaluate/);

    await expect(positionIndicator(page)).toBeVisible();
  });

  test("navigate between images with arrow buttons", async ({ page }) => {
    await page.locator("a[href*='/evaluate']").first().click();
    await expect(page).toHaveURL(/\/studies\/\d+\/evaluate/);

    const start = await getCurrentPosition(page);
    if (start < 80) {
      await page.getByRole("button", { name: /Next image/ }).click();
      await expect(positionIndicator(page)).toHaveText(new RegExp(`${start + 1}\\s*\\/\\s*80`));

      await page.getByRole("button", { name: /Previous image/ }).click();
      await expect(positionIndicator(page)).toHaveText(new RegExp(`${start}\\s*\\/\\s*80`));
    } else {
      await page.getByRole("button", { name: /Previous image/ }).click();
      await expect(positionIndicator(page)).toHaveText(/79\s*\/\s*80/);

      await page.getByRole("button", { name: /Next image/ }).click();
      await expect(positionIndicator(page)).toHaveText(/80\s*\/\s*80/);
    }
  });

  test("navigate between images with keyboard arrow keys", async ({
    page,
  }) => {
    await page.locator("a[href*='/evaluate']").first().click();
    await expect(page).toHaveURL(/\/studies\/\d+\/evaluate/);

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
  });

  test("rating form shows schema questions", async ({ page }) => {
    await page.locator("a[href*='/evaluate']").first().click();
    await expect(page).toHaveURL(/\/studies\/\d+\/evaluate/);

    // Wait for rating form to load — should show the seeded schema questions
    await expect(page.getByText("Nuclear detail & cytology")).toBeVisible();
    await expect(page.getByText("Tissue architecture")).toBeVisible();
  });

  test("progress bar reflects completion", async ({ page }) => {
    await page.locator("a[href*='/evaluate']").first().click();
    await expect(page).toHaveURL(/\/studies\/\d+\/evaluate/);

    // Progress percentage should be visible in footer
    await expect(page.getByText(/%/).first()).toBeVisible();
  });

  test("submit button is visible for non-submitted evaluation", async ({
    page,
  }) => {
    await page.locator("a[href*='/evaluate']").first().click();
    await expect(page).toHaveURL(/\/studies\/\d+\/evaluate/);

    await expect(
      page.getByRole("button", { name: "Submit" })
    ).toBeVisible();
  });

  test("hover prefetch does not reset the resume position", async ({ page }) => {
    const resetResponse = await page.request.post("/api/auth/test-user-reset");
    expect(resetResponse.ok()).toBeTruthy();

    const studyId = await getDemoStudyId(page);
    const evaluateLink = page.locator(`a[href="/studies/${studyId}/evaluate"]`).first();

    await page.goto("/studies");
    await evaluateLink.click();
    await expect(page).toHaveURL(new RegExp(`/studies/${studyId}/evaluate`));
    await closeInstructionDialogIfOpen(page);

    await expect(positionIndicator(page)).toHaveText(/1\s*\/\s*80/);
    await page.getByRole("button", { name: /Next image/ }).click();
    await expect(positionIndicator(page)).toHaveText(/2\s*\/\s*80/);

    await page.goto("/studies");
    const resumedLink = page.locator(`a[href="/studies/${studyId}/evaluate"]`).first();
    await resumedLink.hover();
    await page.waitForTimeout(500);
    await resumedLink.click();

    await expect(page).toHaveURL(new RegExp(`/studies/${studyId}/evaluate`));
    await closeInstructionDialogIfOpen(page);
    await expect(positionIndicator(page)).toHaveText(/2\s*\/\s*80/);
  });

  test("sidebar scroll reveals the resumed image", async ({ page }) => {
    const resetResponse = await page.request.post("/api/auth/test-user-reset");
    expect(resetResponse.ok()).toBeTruthy();

    const studyId = await getDemoStudyId(page);
    const resumeResponse = await page.request.get(`/api/studies/${studyId}/image/25`);
    expect(resumeResponse.ok()).toBeTruthy();

    await page.goto("/studies");
    await page.locator(`a[href="/studies/${studyId}/evaluate"]`).first().click();

    await expect(page).toHaveURL(new RegExp(`/studies/${studyId}/evaluate`));
    await closeInstructionDialogIfOpen(page);
    await expect(positionIndicator(page)).toHaveText(/25\s*\/\s*80/);

    await expect
      .poll(async () => imageSidebarViewport(page).evaluate((el) => el.scrollTop))
      .toBeGreaterThan(0);
    await expect(page.getByRole("row", { name: "Image 25", exact: true })).toBeVisible();
  });
});
