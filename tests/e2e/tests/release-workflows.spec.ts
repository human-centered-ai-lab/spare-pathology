import { expect, test, type Page } from "@playwright/test";
import { login, loginAsAdmin } from "../helpers/auth";

async function setupStudy(page: Page, viewer = "native") {
  await loginAsAdmin(page);
  const nonce = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const created = await page.request.post("/api/admin/studies", {
    data: { name: `Release ${nonce}` },
  });
  expect(created.status()).toBe(201);
  const study = await created.json();
  const settings = await page.request.put(`/api/admin/studies/${study.id}/settings`, {
    data: { dataset_name: "demo_dataset", session_instruction: "", default_image_viewer: viewer },
  });
  expect(settings.ok()).toBeTruthy();
  const dataset = await page.request.get("/api/admin/datasets/demo_dataset/images?per_page=2");
  const images = (await dataset.json()).items;
  const added = await page.request.post(`/api/admin/studies/${study.id}/dataset/add-bulk`, {
    data: { images },
  });
  expect(added.ok()).toBeTruthy();
  const users = [];
  for (const index of [1, 2]) {
    const email = `release-${nonce}-${index}@example.com`;
    const createdUser = await page.request.post("/api/admin/users", {
      data: { email, first_name: "Release", last_name: `Reader ${index}`,
        institution: "Test Center", role: "participant", password: "release-password",
        study_ids: [study.id] },
    });
    expect(createdUser.status()).toBe(201);
    users.push(await createdUser.json());
  }
  expect((await page.request.post(`/api/admin/studies/${study.id}/activate`)).ok()).toBeTruthy();
  await page.request.post("/api/auth/logout");
  await login(page, users[0].email, "release-password");
  return { study, users };
}

async function openStudy(page: Page, studyId: number) {
  await page.goto(`/studies/${studyId}/evaluate`);
  await expect(page.getByText("Nuclear detail & cytology")).toBeVisible();
}

test("native viewer renders after delayed image data, navigation, and resize", async ({ page }) => {
  const { study } = await setupStudy(page);
  await page.route(`**/api/studies/${study.id}/image/*`, async route => {
    await new Promise(resolve => setTimeout(resolve, 300));
    await route.continue();
  });
  await openStudy(page, study.id);
  const first = page.getByRole("img", { name: "Image 1", exact: true });
  await expect(first).toBeVisible();
  await expect.poll(() => first.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
  await page.locator('[data-image-position="2"]').click();
  const second = page.getByRole("img", { name: "Image 2", exact: true });
  await expect(second).toBeVisible();
  await page.setViewportSize({ width: 1100, height: 800 });
  await expect(second).toBeVisible();
  await expect(page.getByRole("button", { name: "Fit", exact: true })).toBeVisible();
  await page.reload();
  await expect(second).toBeVisible();
});

test("failed autosaves survive reload and recover without losing the answer", async ({ page }) => {
  const { study, users } = await setupStudy(page);
  await openStudy(page, study.id);
  await page.route("**/api/ratings/*/response", route => route.fulfill({
    status: 503, contentType: "application/json", body: JSON.stringify({ error: "Temporarily unavailable" }),
  }));
  await page.getByRole("button", { name: "2 consistent" }).first().click();
  const key = `spare.pendingRatingSaves.${users[0].id}.${study.id}`;
  await expect.poll(() => page.evaluate(key => localStorage.getItem(key), key)).not.toBeNull();
  page.on("dialog", dialog => dialog.accept());
  await page.unroute("**/api/ratings/*/response");
  await page.reload();
  await expect(page.getByRole("button", { name: "2 consistent" }).first()).toHaveClass(/bg-primary/);
  await expect.poll(async () => {
    const response = await page.request.get(`/api/studies/${study.id}/image/1`);
    return (await response.json()).rating.responses.F1;
  }).toBe(2);
  await expect.poll(() => page.evaluate(key => localStorage.getItem(key), key)).toBeNull();
});

for (const newerQueue of ["legacy", "current", "legacy-only"] as const) {
  test(`SPaRE restores pending ratings with the newest edit in the ${newerQueue} queue`, async ({ page }) => {
    const { study, users } = await setupStudy(page);
    const response = await page.request.get(`/api/studies/${study.id}/image/1`);
    const { rating } = await response.json();
    const currentKey = `spare.pendingRatingSaves.${users[0].id}.${study.id}`;
    const legacyKey = `syneval.pendingRatingSaves.${users[0].id}.${study.id}`;
    const otherUserKey = `syneval.pendingRatingSaves.${users[1].id}.${study.id}`;
    await page.evaluate(({ ratingId, currentKey, legacyKey, otherUserKey, newerQueue }) => {
      const entry = { key: `response:${ratingId}:F1`, kind: "response", ratingId,
        position: 1, questionId: "F1", version: 1, updatedAt: Date.now(), value: 2 };
      const older = { ...entry, version: 9, updatedAt: entry.updatedAt - 1000, value: 1 };
      const otherQuestion = { ...entry, key: `response:${ratingId}:F2`, questionId: "F2", value: 1 };
      localStorage.setItem(legacyKey, JSON.stringify([newerQueue !== "current" ? entry : older, otherQuestion]));
      if (newerQueue !== "legacy-only") {
        localStorage.setItem(currentKey, JSON.stringify([newerQueue === "current" ? entry : older]));
      }
      localStorage.setItem(otherUserKey, "[]");
      localStorage.removeItem("spare-theme");
      localStorage.setItem("syneval-theme", "dark");
    }, { ratingId: rating.id, currentKey, legacyKey, otherUserKey, newerQueue });
    await openStudy(page, study.id);
    await expect(page).toHaveTitle("SPaRE");
    await expect(page.locator("html")).toHaveClass(/dark/);
    await expect.poll(async () => {
      const response = await page.request.get(`/api/studies/${study.id}/image/1`);
      return (await response.json()).rating.responses;
    }).toMatchObject({ F1: 2, F2: 1 });
    await expect.poll(() => page.evaluate(key => localStorage.getItem(key), currentKey)).toBeNull();
    expect(await page.evaluate(key => localStorage.getItem(key), legacyKey)).toBeNull();
    expect(await page.evaluate(key => localStorage.getItem(key), otherUserKey)).toBe("[]");
    expect(await page.evaluate(() => localStorage.getItem("spare-theme"))).toBe("dark");
    expect(await page.evaluate(() => localStorage.getItem("syneval-theme"))).toBeNull();
  });
}

test("a second participant cannot inherit another participant's pending answers", async ({ page }) => {
  const { study, users } = await setupStudy(page);
  await openStudy(page, study.id);
  await page.route("**/api/ratings/*/response", route => route.fulfill({
    status: 503, contentType: "application/json", body: JSON.stringify({ error: "Temporarily unavailable" }),
  }));
  await page.getByRole("button", { name: "2 consistent" }).first().click();
  const firstKey = `spare.pendingRatingSaves.${users[0].id}.${study.id}`;
  await expect.poll(() => page.evaluate(key => localStorage.getItem(key), firstKey)).not.toBeNull();
  page.on("dialog", dialog => dialog.accept());
  await page.request.post("/api/auth/logout");
  await page.goto("/login");
  await page.unroute("**/api/ratings/*/response");
  await login(page, users[1].email, "release-password");
  await openStudy(page, study.id);
  await expect(page.getByRole("button", { name: "2 consistent" }).first()).not.toHaveClass(/bg-primary/);
  await page.getByRole("button", { name: "1 borderline" }).first().click();
  await expect.poll(async () => {
    const response = await page.request.get(`/api/studies/${study.id}/image/1`);
    const rating = (await response.json()).rating;
    return rating.responses.F1;
  }).toBe(1);
  expect(await page.evaluate(key => localStorage.getItem(key), firstKey)).not.toBeNull();
});

test("XOpat displays tiles and forwards evaluation keyboard shortcuts", async ({ page }) => {
  test.setTimeout(60_000);
  const { study } = await setupStudy(page, "xopat");
  const tile = page.waitForResponse(response => response.url().includes("_files/") && response.status() === 200);
  await openStudy(page, study.id);
  await tile;
  const viewer = page.frameLocator('iframe[title^="XOpat viewer"]');
  await expect(viewer.locator("canvas").first()).toBeVisible();
  await viewer.locator(".openseadragon-canvas").first().click();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator('iframe[title="XOpat viewer for image 2"]')).toBeVisible();
});

test("participant rating controls remain usable on a narrow screen", async ({ page }) => {
  const { study } = await setupStudy(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await openStudy(page, study.id);
  const score = page.getByRole("button", { name: "2 consistent" }).first();
  await score.click();
  await expect(score).toHaveClass(/bg-primary/);
  await expect.poll(async () => {
    const response = await page.request.get(`/api/studies/${study.id}/image/1`);
    return (await response.json()).rating.responses.F1;
  }).toBe(2);
});
