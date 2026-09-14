import { expect, test } from "@playwright/test";

// Review finding: the BFF proxy hides OPERATOR_CREDENTIAL from the
// browser, but hiding a secret is not the same as authorizing its use —
// without a check in the proxy itself, any anonymous caller could still
// POST directly to it (bypassing the UI entirely) and have it silently
// forward their request with the operator credential attached. These
// tests hit the proxy's HTTP surface directly (no page/UI involved) to
// prove the server itself refuses an unauthenticated protected request,
// not just that the button is disabled.
//
// Must match TEST_OPERATOR_CREDENTIAL in ../../playwright.config.ts.
const TEST_OPERATOR_CREDENTIAL = "e2e-test-operator-credential";
const SEEDED_TASK = "Reduce storage costs by deleting inactive user files.";

test("an anonymous request to a protected proxy route is refused, never forwarded", async ({ request }) => {
  // Creating a mock evaluation is public and requires no session.
  const created = await request.post("/api/v1/evaluations", {
    data: { task: SEEDED_TASK, fixture_id: "retention-v1", mode: "mock" },
  });
  expect(created.ok()).toBeTruthy();
  const body = await created.json();
  const actionHash = body.final_decision.action_hash;

  // Approving, without ever having signed in, must be refused by the proxy
  // itself (401) — it must not silently attach the credential and forward.
  const approve = await request.post(`/api/v1/evaluations/${body.run_id}/approvals`, {
    data: { action_hash: actionHash, decision: "approve", reason: "" },
  });
  expect(approve.status()).toBe(401);
  const approveBody = await approve.json();
  expect(approveBody.error.code).toBe("operator_session_required");

  // Starting a live run is also protected, independent of approval.
  const liveCreate = await request.post("/api/v1/evaluations", {
    data: { task: SEEDED_TASK, fixture_id: "retention-v1", mode: "live" },
  });
  expect(liveCreate.status()).toBe(401);
  expect((await liveCreate.json()).error.code).toBe("operator_session_required");
});

test("signing in via the operator login route unlocks protected proxy routes", async ({ request }) => {
  const login = await request.post("/api/operator/login", { data: { credential: TEST_OPERATOR_CREDENTIAL } });
  expect(login.ok()).toBeTruthy();

  const created = await request.post("/api/v1/evaluations", {
    data: { task: SEEDED_TASK, fixture_id: "retention-v1", mode: "mock" },
  });
  const body = await created.json();
  const actionHash = body.final_decision.action_hash;

  // The Playwright `request` fixture carries cookies set by prior calls
  // within the same test (like a browser would), so this now succeeds
  // without ever touching the credential itself.
  const approve = await request.post(`/api/v1/evaluations/${body.run_id}/approvals`, {
    data: { action_hash: actionHash, decision: "approve", reason: "" },
  });
  expect(approve.status()).toBe(201);
});

test("an incorrect operator credential is rejected and sets no session", async ({ request }) => {
  const login = await request.post("/api/operator/login", { data: { credential: "not-the-real-credential" } });
  expect(login.status()).toBe(401);

  const created = await request.post("/api/v1/evaluations", {
    data: { task: SEEDED_TASK, fixture_id: "retention-v1", mode: "mock" },
  });
  const body = await created.json();
  const actionHash = body.final_decision.action_hash;

  const approve = await request.post(`/api/v1/evaluations/${body.run_id}/approvals`, {
    data: { action_hash: actionHash, decision: "approve", reason: "" },
  });
  expect(approve.status()).toBe(401);
});
