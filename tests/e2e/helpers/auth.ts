import { Page, expect } from "@playwright/test";

/**
 * Log in via the login page UI.
 */
export async function login(
  page: Page,
  email: string,
  password: string,
): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  // Wait for navigation away from /login
  await expect(page).not.toHaveURL(/\/login/);
}

/**
 * Log in as the default admin user.
 */
export async function loginAsAdmin(page: Page): Promise<void> {
  await login(page, "admin", "1a2s3d4f5g6h");
}

/**
 * Log in as the seeded test participant (sees all projects).
 */
export async function loginAsParticipant(page: Page): Promise<void> {
  await login(page, "test", "1a2s3d4f5g6h");
}
