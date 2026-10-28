import { test, expect } from "@playwright/test";
import { loginAsAdmin, loginAsParticipant, login } from "../helpers/auth";

test.describe("Authentication", () => {
  test("admin login redirects to /admin", async ({ page }) => {
    await loginAsAdmin(page);
    await expect(page).toHaveURL(/\/admin$/);
    await expect(page.getByRole("heading", { name: "Getting Started" })).toBeVisible();
  });

  test("participant login redirects to /studies", async ({ page }) => {
    await loginAsParticipant(page);
    await expect(page).toHaveURL(/\/studies/);
    await expect(
      page.getByRole("heading", { name: "My Studies" })
    ).toBeVisible();
  });

  test("invalid password shows error", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("admin");
    await page.getByLabel("Password").fill("wrongpassword");
    await page.getByRole("button", { name: "Sign in" }).click();
    // Error message should appear on the page
    await expect(page.getByText(/invalid|incorrect|failed/i)).toBeVisible();
  });

  test("logout returns to login page", async ({ page }) => {
    await loginAsParticipant(page);
    await expect(page).toHaveURL(/\/studies/);

    // Sidebar exposes logout directly.
    await page.getByRole("button", { name: "Log out" }).click();

    await expect(page).toHaveURL(/\/login/);
  });

  test("unauthenticated visit redirects to /login", async ({ page }) => {
    await page.goto("/studies");
    await expect(page).toHaveURL(/\/login/);
  });
});
