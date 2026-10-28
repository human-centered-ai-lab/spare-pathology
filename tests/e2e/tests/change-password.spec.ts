import { test, expect } from "@playwright/test";
import { login, loginAsParticipant } from "../helpers/auth";

test.describe("Change Password", () => {
  test("change password and login with new password", async ({ page }) => {
    // Login as test participant
    await loginAsParticipant(page);
    await expect(page).toHaveURL(/\/studies/);

    // Navigate to profile via sidebar footer link.
    await page.getByRole("link", { name: "Profile" }).click();
    await expect(page).toHaveURL(/\/profile/);

    // Fill change password form
    await page.getByLabel("Current Password").fill("1a2s3d4f5g6h");
    await page.getByLabel("New Password", { exact: true }).fill("newpass999");
    await page.getByLabel("Confirm New Password").fill("newpass999");

    // Submit
    await page.getByRole("button", { name: "Change Password" }).click();

    // Verify success toast ("Password changed successfully")
    await expect(
      page.getByText("Password changed successfully")
    ).toBeVisible({ timeout: 5_000 });

    // Logout
    await page.getByRole("button", { name: "Log out" }).click();
    await expect(page).toHaveURL(/\/login/);

    // Login with new password
    await login(page, "test", "newpass999");
    await expect(page).toHaveURL(/\/studies/);

    // Change password back to original for cleanup
    await page.getByRole("link", { name: "Profile" }).click();
    await expect(page).toHaveURL(/\/profile/);

    await page.getByLabel("Current Password").fill("newpass999");
    await page.getByLabel("New Password", { exact: true }).fill("1a2s3d4f5g6h");
    await page.getByLabel("Confirm New Password").fill("1a2s3d4f5g6h");
    await page.getByRole("button", { name: "Change Password" }).click();
    await expect(
      page.getByText("Password changed successfully")
    ).toBeVisible({ timeout: 5_000 });
  });
});
