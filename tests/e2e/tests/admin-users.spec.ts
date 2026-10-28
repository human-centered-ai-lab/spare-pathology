import { test, expect } from "@playwright/test";
import { loginAsAdmin } from "../helpers/auth";

test.describe("Admin Users", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto("/admin/users");
    await expect(page).toHaveURL(/\/admin\/users/);
  });

  test("users list shows seeded users", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Users" })).toBeVisible();
    // Should see admin user row in the table
    await expect(page.getByRole("cell", { name: "Admin User" })).toBeVisible();
    // Seeded test user row
    await expect(
      page.getByRole("row").filter({ hasText: "Test User" })
    ).toBeVisible();
  });

  test("create new participant user", async ({ page }) => {
    await page.getByRole("link", { name: "Add User" }).click();
    await expect(page).toHaveURL(/\/admin\/users\/create/);
    await expect(
      page.getByRole("heading", { name: "Create User" })
    ).toBeVisible();

    // Fill in the form
    await page.getByLabel("First Name").fill("E2E");
    await page.getByLabel("Last Name").fill("Tester");
    await page.getByLabel("Institution").fill("Test University");
    await page.getByLabel("Email").fill("e2e-tester@example.com");
    await page.getByLabel("Password").fill("testpass123");

    await page.getByRole("button", { name: "Create User" }).click();

    // Should redirect back to users list
    await expect(page).toHaveURL(/\/admin\/users$/);
    // New user should appear in the table
    await expect(page.getByRole("cell", { name: "E2E Tester" })).toBeVisible();
  });

  test("edit user name", async ({ page }) => {
    // Click the row for a seeded participant (Amara Okafor).
    const row = page.getByRole("row").filter({ hasText: "Amara" });
    await row.click();

    await expect(page).toHaveURL(/\/admin\/users\/\d+\/edit/);
    await expect(
      page.getByRole("heading", { name: "Edit User" })
    ).toBeVisible();

    // Change first name
    const firstNameInput = page.getByLabel("First Name");
    await firstNameInput.clear();
    await firstNameInput.fill("Amara-Edited");

    await page.getByRole("button", { name: "Save Changes" }).click();

    // Should redirect back to users list with updated name
    await expect(page).toHaveURL(/\/admin\/users$/);
    await expect(
      page.getByRole("cell", { name: /Amara-Edited/ })
    ).toBeVisible();
  });

  test("update user password from edit form", async ({ page }) => {
    const row = page.getByRole("row").filter({ hasText: "Carlos" });
    await row.click();
    await expect(page).toHaveURL(/\/admin\/users\/\d+\/edit/);

    await page.getByLabel(/Password/).fill("newpass456");
    await page.getByRole("button", { name: "Save Changes" }).click();
    await expect(page).toHaveURL(/\/admin\/users$/);
  });

  test("delete user", async ({ page }) => {
    // First create a disposable user
    await page.getByRole("link", { name: "Add User" }).click();
    await page.getByLabel("First Name").fill("Disposable");
    await page.getByLabel("Last Name").fill("User");
    await page.getByLabel("Institution").fill("Test");
    await page.getByLabel("Email").fill("disposable@example.com");
    await page.getByLabel("Password").fill("testpass123");
    await page.getByRole("button", { name: "Create User" }).click();
    await expect(page).toHaveURL(/\/admin\/users$/);
    await expect(
      page.getByRole("cell", { name: "Disposable User" })
    ).toBeVisible();

    // Now delete
    const row = page.getByRole("row").filter({ hasText: "Disposable" });
    await row.locator("button").first().click();

    // Confirm deletion in the alert dialog
    await expect(
      page.getByRole("heading", { name: "Delete User" })
    ).toBeVisible();
    await page.getByRole("alertdialog").getByRole("button", { name: "Delete" }).click();

    // User should be gone from table
    await expect(
      page.getByRole("cell", { name: "Disposable User" })
    ).not.toBeVisible();
  });
});
