import { expect, test, type Page } from "@playwright/test";

// Must match TEST_OPERATOR_CREDENTIAL in ../../playwright.config.ts, which
// configures this same value on both the FastAPI and Next.js processes for
// the whole suite.
const TEST_OPERATOR_CREDENTIAL = "e2e-test-operator-credential";

async function signInAsOperator(page: Page): Promise<void> {
  await page.getByPlaceholder("Operator credential").fill(TEST_OPERATOR_CREDENTIAL);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Operator session active.")).toBeVisible();
}

// Full seeded flow: evaluate -> approve -> simulate -> roll back. No
// external model call happens anywhere in this path (mode=mock), so
// nothing here depends on network access beyond the local API server.
//
// This whole suite runs with OPERATOR_CREDENTIAL configured on both the
// backend and the Next.js server (see playwright.config.ts). Signing in
// through the actual operator-auth UI here — not just via a bare API call
// — is what proves the whole chain works end to end: the login form sets
// an HttpOnly session cookie, and the same-origin proxy route
// (app/api/v1/evaluations/[[...path]]/route.ts) checks that cookie before
// it will attach the operator credential and forward a protected request.
// The browser itself never sees the credential after the initial submit.
test("seeded evaluate -> approve -> execute -> rollback (with OPERATOR_CREDENTIAL configured)", async ({ page }) => {
  await page.goto("/");
  await signInAsOperator(page);

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
// than a silent fallback to mock output. Starting a live run is itself a
// protected operator action, so this also needs to sign in first.
test("live council errors clearly when NEBIUS_API_KEY is not configured", async ({ page }) => {
  await page.goto("/");
  await signInAsOperator(page);
  await page.getByRole("button", { name: "Run live council (Nemotron)" }).click();
  await expect(page.getByText(/live mode is not configured/i)).toBeVisible({ timeout: 15_000 });
});

test("protected actions are locked in the UI before operator sign-in", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/requires an operator sign-in/i)).toBeVisible();
  const liveButton = page.getByRole("button", { name: "Run live council (Nemotron)" });
  await expect(liveButton).toBeDisabled();

  // Mock evaluation stays public even though live/approve/execute/rollback
  // are locked — only the operator-gated actions are affected.
  await page.getByRole("button", { name: "Run evaluation" }).click();
  await expect(page.getByText("Status: awaiting_approval")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Approve simulation" })).toBeDisabled();
});
