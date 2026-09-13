import { expect, test } from "@playwright/test";

// Full seeded flow: evaluate -> approve -> simulate -> roll back. No
// external model call happens anywhere in this path (mode=mock), so
// nothing here depends on network access beyond the local API server.
//
// This whole suite runs with OPERATOR_CREDENTIAL configured on both the
// backend and the Next.js server (see playwright.config.ts), so this test
// passing is also the proof that approval/execute/rollback still work
// end to end through the browser once a real deployment protects those
// routes — the browser itself never sees the credential; the same-origin
// proxy route (app/api/v1/evaluations/[[...path]]/route.ts) attaches it
// server-side on every forwarded request.
test("seeded evaluate -> approve -> execute -> rollback (with OPERATOR_CREDENTIAL configured)", async ({ page }) => {
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

// This CI environment has no NEBIUS_API_KEY configured, so this asserts the
// honest, expected behavior here: a clear "not configured" error rather
// than a silent fallback to mock output.
test("live council errors clearly when NEBIUS_API_KEY is not configured", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Run live council (Nemotron)" }).click();
  await expect(page.getByText(/live mode is not configured/i)).toBeVisible({ timeout: 15_000 });
});
