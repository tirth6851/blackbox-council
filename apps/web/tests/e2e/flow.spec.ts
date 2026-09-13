import { expect, test } from "@playwright/test";

// Full seeded flow: evaluate -> approve -> simulate -> roll back. No
// external model call happens anywhere in this path (mode=mock), so
// nothing here depends on network access beyond the local API server.
test("seeded evaluate -> approve -> execute -> rollback", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Run evaluation" }).click();

  await expect(page.getByText("Status: awaiting_approval")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Approval required").first()).toBeVisible();

  // Delete is visibly blocked; archive is the selected, approvable candidate.
  const deleteRow = page.getByRole("row", { name: /^delete/ });
  await expect(deleteRow.getByText("Blocked")).toBeVisible();

  await page.getByRole("button", { name: "Approve simulation" }).click();
  await expect(page.getByText("Status: approved")).toBeVisible();

  await page.getByRole("button", { name: "Run simulation" }).click();
  await expect(page.getByText(/Simulated archive completed/)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/Source file hashes are unchanged/)).toBeVisible();

  await page.getByRole("button", { name: "Roll back simulation" }).click();
  await expect(page.getByText(/Simulated archive was rolled back/)).toBeVisible({ timeout: 15_000 });
});
