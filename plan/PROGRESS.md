# Implementation progress

Current phase: 3, milestone 3.1 in progress (fresh-state execution and path
validation). Phase 1-2 (below) merged in PR #5 at `03158c3`; a follow-up
audit on the merged code (PR #5 review 5202586093, 14 September 2026) found
acceptance gaps beyond live-credential verification and opened PR #6
(`docs/remaining-phase-plans`, not yet merged as of this entry) with
Phase 3-6 plans and a carryover ledger (`plan/pr-5-carryover.md` on that
branch) mapping all 19 findings (C01-C19) to milestones. This branch was
restarted from `main` (the PR #5 restart rule: a merged PR cannot track new
work) rather than built on top of PR #6's still-unmerged branch, so this
entry cites carryover IDs directly against the original review comments
rather than assuming PR #6's ledger file is present here.
Branch: claude/workflows-phase-1-2-3aujzd

## Milestone 3.1 (partial): fresh-state execution and path validation

Addresses carryover C01 and C17 from PR #5 review
[5202586093](https://github.com/tirth6851/blackbox-council/pull/5#pullrequestreview-5202586093),
against merged commit `03158c3`. Verified by reproducing each finding
against the pre-fix code before fixing it, per this project's regression-
test requirement.

**C01 — execute_action revalidated against a cached, stale snapshot.**
`execute_action()` called the `@lru_cache`d `load_fixture()`. Once a
fixture/policy was cached (which evaluation always does), any post-
approval on-disk change was invisible to execution's own "did anything
change?" checks — they ended up comparing the stale cached snapshot
against itself. Reproduced directly: with `execute_action.load_fixture_fresh`
patched back to the cached `load_fixture` (simulating the pre-fix code),
evaluate → approve → mutate `f002.txt` bytes → execute returned
`200 completed`, not a rejection. Separately, a policy edited in place
without bumping its `version` string was not caught at all, cached or not,
because only `policy.version` (a label) was compared, never policy content.

Fixed:
- `fixture_loader.py`: split the loader into a cached `load_fixture()` (kept
  for evaluation-time reads, which legitimately call it several times per
  run) and an uncached `load_fixture_fresh()` that always re-reads current
  on-disk bytes/policy. `executor.execute_action` now uses only the latter.
- Added a `policy_digest` content fingerprint (sha256 of the canonical
  policy fields, independent of the `version` label) to `LoadedFixture`,
  threaded through `compute_action_hash`, `build_scope_manifest`,
  `ExecutableAction`, the `runs.policy_digest` column, and every
  `create_run`/`create_placeholder_run`/`finalize_live_run` call site.
  `execute_action` now rejects execution when either the fixture digest,
  the policy version, *or* the policy content digest differs from what was
  recorded at evaluation time.
- Added `hash_source_files()`: an independent fresh disk read used for both
  the before- and after-execution source-hash measurements, replacing the
  prior single dict copied into both `source_hashes_before` and
  `source_hashes_after` result fields. A mismatch (which should never
  happen in this pure simulation) now itself raises `fixture_changed`
  rather than being silently reported as a clean result.

**C17 — `_safe_join` checked `is_symlink()` after resolving the path.**
`Path.resolve()` transparently follows symlinks, so checking
`is_symlink()` on the *already-resolved* candidate is a no-op: an in-root
symlink pointing at another in-root file always resolves to a non-symlink
real path and passed silently, contrary to the documented no-symlinks
rule. (Root containment still correctly rejected a resolved target outside
the root — this was never an escape, just a dead check.) Reproduced with a
standalone reimplementation of the old logic against a real symlink: it
accepted the symlink and returned the resolved real path instead of
raising. Fixed by checking each path component for `is_symlink()` while
walking from the root down, *before* the final resolve+containment check.

**Verification**

```
$ cd apps/api && source .venv/bin/activate && python -m pytest -q
84 passed   # 74 pre-existing (all unmodified in outcome; two test files
            # updated only to pass the new required policy_digest/
            # ExecutableAction.policy_digest argument) + 10 new in
            # tests/test_execution_revalidation.py
```

New tests (`tests/test_execution_revalidation.py`), each using a disposable
on-disk copy of the retention-v1 fixture (demo-repo files + fixture JSON +
policy JSON in a tmp dir, fixture registry monkeypatched to it) so mutation
never touches the real repository content other tests/CI rely on:
- fixture bytes changed after approval, cache never cleared → 409
  `fixture_changed`, run stays `approved`, no execution record created;
- fixture metadata (legal_hold) changed after approval → same;
- policy content changed with `version` left unchanged → 409
  `policy_changed` (the case the pre-fix version-only check missed);
- unmodified normal flow still succeeds, with two independently-measured
  source-hash reads agreeing;
- `load_fixture` (cached) vs `load_fixture_fresh` (uncached) genuinely
  diverge once the cache is stale;
- policy digest changes when policy content changes but `version` does not;
- `_safe_join` rejects an in-root symlinked file, an in-root symlinked
  directory component, an absolute path, and `..` traversal.

Each C01 case was confirmed to reproduce (return 200, not 409) against the
pre-fix code path before the fix landed, using the same disposable-fixture
technique (see commit history for the exact reproduction script run
manually, not committed). This satisfies this project's "regression test
that fails before the fix and passes after it" requirement.

**Not done in this change** (remaining milestone 3.1 scope, later
milestones): concurrent-admission/queue bounding (C08, milestone 3.3),
complete council inputs and conservative reconciliation (C02-C05, C12,
milestone 3.2), evidence persistence (C06, milestone 3.3), browser
recovery (C09-C12, C18, milestone 3.4), and real live-model verification
(C19, milestone 3.5). Frontend (`apps/web`) was not touched by this change
and its typecheck/lint/build/e2e suite was not rerun, since nothing in
`apps/web` changed.

## Review round 4 (final sign-off review)

A fourth review, on the round-3 fix (`b7d668e`), independently re-verified
every item from rounds 1-3 rather than taking the earlier fixes on faith:
PR open/non-draft/mergeable, CI run #7 green, no unresolved inline review
threads, anonymous approval/live-run requests rejected by the proxy, a
correct credential producing a signed HttpOnly `SameSite=Strict` expiring
session, the backend credential only ever attached after session
authorization, mock evaluation/report-reads staying public, cross-origin
protected requests refused, Playwright covering anonymous rejection/
invalid-login rejection/authenticated success, and the round-1 injection,
deterministic-risk-floor, atomic-CAS, and provider-retry fixes all still
present. Conclusion: **no merge-blocking finding remains for the stated
single-operator, synthetic-simulation hackathon scope.**

Three non-blocking hardening items were flagged for a later production
phase, explicitly not required for this PR:

1. rate-limit the public operator-login endpoint;
2. use a separate high-entropy session-signing secret rather than
   deriving session signatures from the operator credential itself;
3. replace the shared operator credential with real identity-based
   authentication and audit attribution if multiple operators are ever
   introduced.

No code change was made in response to this review — it identified no
required fix, and the three items above are recorded here as known,
stated follow-up work rather than actioned now (per the reviewer's own
"non-blocking ... for a later production phase" framing). The review also
reiterated, correctly, that the live Nebius/Nemotron path remains
unverified against real credentials and that the repository should not be
described as live-model-verified until that real smoke test succeeds.

## Review round 3 (confused-deputy follow-up)

A third review, on the round-2 fix (`7b5134e`), confirmed CI was green and
the BFF integration test proved the protected calls technically worked —
then caught something round 2 missed: **the proxy was an unauthenticated
confused deputy.** It correctly hid `OPERATOR_CREDENTIAL` from the
browser, but performed no check on *who* was calling it — on a public
deployment, any anonymous visitor could POST to the same-origin proxy and
have it silently upgrade their request with the operator credential. The
secret was hidden; operator authority was not actually protected.

Fixed with the reviewer's first recommended option (real operator
session/authorization in front of protected forwarding, with CSRF/origin
protection), scoped to what a single-shared-secret demo actually needs:

- `apps/web/src/lib/operator-session.ts` — a small signed-cookie session
  (HMAC-SHA256 over an expiry timestamp, keyed by `OPERATOR_CREDENTIAL`
  itself so no extra secret is needed; timing-safe comparison). This is
  deliberately not a general auth system — it only answers "did a browser
  that knows the operator credential sign in recently."
- `apps/web/src/app/api/operator/{login,logout,status}/route.ts` — login
  verifies the submitted credential (timing-safe) and sets an HttpOnly,
  `SameSite=Strict`, `Secure`-in-production session cookie; logout clears
  it; status reports `{configured, authenticated}` for the UI.
- The proxy route now refuses to forward a protected request (POST to
  `.../approvals`, `.../execute`, `.../rollback`, or a root POST with
  `mode: "live"`) without both a valid session cookie **and** a
  same-origin check on the `Origin` header (defense-in-depth on top of
  `SameSite=Strict`, which is the primary CSRF defense — a browser won't
  attach that cookie to a cross-site request at all). A request failing
  either check gets a 401/403 and is never forwarded with the credential
  attached. Public paths (mock evaluation, reading a report) are
  unaffected.
- `apps/web/src/components/operator-auth.tsx` + `page.tsx` — a visible
  sign-in/sign-out panel, shown only when the deployment has a credential
  configured; approve/execute/rollback/live-run buttons are disabled in
  the UI until authenticated (the server-side check is what's actually
  authoritative — this is just so the UI doesn't invite a click that will
  just 401).
- Tests, at both layers the reviewer asked for:
  - `tests/e2e/operator-auth.spec.ts` hits the proxy's HTTP surface
    directly (no UI) and proves an anonymous POST to a protected route is
    refused with `operator_session_required` and never forwarded, that a
    wrong credential is rejected, and that a correct login unlocks the
    same routes.
  - `tests/e2e/flow.spec.ts`'s full-flow test now signs in through the
    actual login form (not a bare API call) before running the
    evaluate→approve→execute→rollback flow, and a new test confirms
    protected buttons are disabled pre-sign-in while mock evaluation
    stays usable.

One real bug caught while building this, before it ever reached a
commit: the first same-origin check compared the `Origin` header against
`request.nextUrl.host`, which didn't match the actual incoming `Host` in
this dev setup and made the proxy reject its own legitimate same-origin
requests (the "approve" click silently failed with
`cross_origin_forbidden`). Found by actually running the browser test
rather than trusting the logic on paper; fixed by comparing against the
literal `Host` header instead.

Verified: `tsc`/lint/build clean (four new routes show up in the build
output), all 6 Playwright tests pass, all 74 backend tests pass
unmodified (no backend change was needed — FastAPI's own
`OPERATOR_CREDENTIAL` check is unchanged and remains the actual source of
truth; this round is entirely about what the Next.js server does before
it ever uses that shared secret on a caller's behalf).

## Review round 2 (follow-up: PR marked ready for review)

A follow-up review on the round-1 fix commit confirmed all five original
findings were substantively fixed, then caught a real deployment blocker
introduced by fix #2 itself: **the frontend never sent
`X-Operator-Credential`**, so configuring `OPERATOR_CREDENTIAL` (as
recommended for any public deployment) would 401 every approve/execute/
rollback click and every live-run creation in the actual web UI — the
backend fix alone left the demo broken the moment anyone turned it on.
The reviewer was explicit that a `NEXT_PUBLIC_*` variable is not an
acceptable fix (it would inline the shared secret into the client bundle,
handing it to every visitor), and asked for a same-origin BFF proxy or an
authenticated operator session instead, plus a browser test that actually
exercises the flow with the credential configured.

Fixed with the suggested same-origin proxy:

- `apps/web/src/app/api/v1/evaluations/[[...path]]/route.ts` — a Next.js
  Route Handler at the exact same path the browser already called. It
  reads `OPERATOR_CREDENTIAL` from `process.env` (deliberately **not**
  `NEXT_PUBLIC_`-prefixed, so Next.js never inlines it into any client
  bundle) and attaches it as `X-Operator-Credential` on every request it
  forwards to the real FastAPI backend (`NEXT_PUBLIC_API_BASE_URL`, still
  fine to read server-side since it's a URL, not a secret). The browser
  never holds, sees, or sends the credential.
- `apps/web/src/lib/api.ts` now fetches relative same-origin paths
  (`/api/v1/evaluations/...`) instead of a cross-origin backend URL; the
  "download audit JSON" link in `page.tsx` does the same.
- `apps/web/playwright.config.ts` now sets the **same**
  `OPERATOR_CREDENTIAL` on both the FastAPI process and the Next.js
  process (again, not `NEXT_PUBLIC_` for the latter) for the whole e2e
  suite. The existing full-flow browser test
  (`seeded evaluate -> approve -> execute -> rollback (with
  OPERATOR_CREDENTIAL configured)`) passing with this configuration *is*
  the requested integration test — it only passes if the proxy correctly
  attaches the header server-side for every protected call, since the
  backend now 401s all of them without it.

Verified: `npx tsc --noEmit` clean, `next lint` clean, `next build`
succeeds (the new route shows up as a dynamic server route), both
Playwright tests pass with the credential configured end to end, and all
74 backend tests still pass unmodified.

## Review round 1 (PR #5 draft review)

A review of the draft PR found five real issues, verified against the code
before fixing (not taken on faith):

1. **Critical.** `counterfactuals/runner.py` and `council/orchestrator.py`
   built `context` (including the injection document) but never included
   it in the `input_payload` sent to any provider — the injection
   counterfactual variant was structurally incapable of ever showing a
   model the malicious document, silently defeating the project's central
   security test. Fixed by adding `"context"` to both payloads. Added
   `tests/fakes.py::InjectionProbeProvider`, a provider that only changes
   its plan when it actually receives the override text in its payload,
   and a test (`test_council.py::test_injection_document_actually_reaches_the_model_and_is_detected_when_followed`)
   proving both that the harness now detects a susceptible model and that
   the deterministic policy gate (FILE-001) still blocks the resulting
   candidate regardless.
2. **High.** `/approvals`, `/execute`, `/rollback`, and live evaluation
   creation had no authentication at all; `OPERATOR_CREDENTIAL` existed in
   settings but was never read anywhere. Added
   `app.dependencies.require_operator_credential` / `check_operator_credential`:
   when `OPERATOR_CREDENTIAL` is set, these routes require a matching
   `X-Operator-Credential` header (401 otherwise); unset (the local/demo
   default) leaves them open, matching the plan's "synthetic mock
   demonstration stays public" stance. Mock evaluation creation stays
   public even when a credential is configured. Tested in
   `tests/test_operator_credential.py`.
3. **High.** The displayed transparent risk score was computed directly
   from `privacy_output.risk_ratings` (model-reported), even though
   `policy_engine`'s deterministic `compute_risk_ratings` existed and was
   never called from the orchestrator. A manipulated or simply mistaken
   reviewer could self-report artificially low risk. Added
   `counterfactuals/scoring.py::combine_risk_ratings`, which takes the max
   per dimension of the deterministic (floor) and model-reported value,
   missing model dimensions falling back to the deterministic value.
   `extensions` now carries `risk_ratings` (combined), plus
   `deterministic_risk_ratings` and `model_risk_ratings` separately for
   transparency. Tested directly (a "lowballing" fake privacy reviewer
   that reports 0 on every dimension cannot lower the displayed score
   below the deterministic floor).
4. **Medium.** `run_repository.set_run_status` did a SELECT filtered by
   `version`, then mutated the loaded ORM object and flushed — the actual
   UPDATE SQLAlchemy emits on flush filters only by primary key, not by
   the version that was read, so it was not a true atomic
   compare-and-swap. Replaced with a single
   `UPDATE runs SET ... WHERE id=:id AND version=:expected_version`,
   requiring `rowcount == 1`, then `session.refresh(row)` to sync the
   passed-in object (executor.py chains two transitions off `row.version`)
   without leaving it dirty for a later conflicting autoflush. Tested in
   `tests/test_run_repository.py` (a second compare-and-swap against a
   stale version is refused, and a chained call correctly picks up the
   version the first call just wrote). Note: this proves the CAS
   contract's correctness; it does not reproduce true multi-connection
   concurrency, which is hard to do deterministically against SQLite in a
   test — the single-statement UPDATE is the standard correct pattern
   regardless.
5. **Medium.** `providers/nebius.py`'s docstring promised a corrective
   retry that includes the validation error, and a larger token cap after
   truncation — the code instead resent an identical request on both
   attempts. Implemented both for real: a schema-validation failure now
   carries `exc.errors(include_url=False, include_context=False)` into
   the retry's user message; a truncated attempt now retries with
   `max_tokens` doubled, capped at 8000. Tested with a mocked HTTP client
   asserting the second attempt's request actually differs from the
   first in both cases.

All fixes are covered by new or updated tests; the full suite (74 backend
tests, frontend typecheck/lint/build, 2 browser tests) passes after these
changes — see the verification commands below.

## Phase 1 — working mock demo

Status: complete. All milestones 1.1-1.8 implemented; exit checklist passes locally.

### Completed

- `apps/api/app/schemas.py` — strict Pydantic contracts (CandidateAction vs
  ExecutableAction kept separate, Outcome/RunStatus literals, explicit
  `ALLOWED_STATUS_TRANSITIONS` table with `is_valid_transition`).
- `apps/api/app/fixture_registry.py`, `app/services/fixture_loader.py` —
  server-owned fixture/policy loading, path-traversal/symlink guards, hash
  verification against disk content.
- `demo-repo/` synthetic fixture tree (f001-f005, storage notes, the
  inert prompt-injection sample) and `scripts/seed_fixtures.py`, which
  computes real SHA-256 hashes/byte counts.
- `apps/api/app/services/policy_engine.py` — every rule in the plan
  (CMD-001, FILE-001, TRUST-001, SECRET-001, NET-001, AUTH-001, SCOPE-001,
  RET-001, HOLD-001, SAFE-001, SAFE-002; EXEC-001 and APPROVAL-001
  enforced at the executor/approval boundary) plus a scripted mock
  evaluator that only accepts the seeded task and visibly labels every
  mocked review "[MOCK]".
- `apps/api/app/services/decision_service.py` — per-candidate
  classification (block > clarify > safeguard > approval > safe) and
  final-candidate selection; a blocked delete never vetoes a separately
  valid archive candidate (tested).
- SQLite persistence (`app/db.py`, `app/models/orm.py`,
  `app/services/run_repository.py`) for runs/events/approvals/executions/
  simulation_state, FK+busy_timeout pragmas, optimistic-concurrency status
  updates. Events are read live from the events table (not a frozen JSON
  snapshot), which is what makes Phase 2's polling progress work too.
- Canonical server-computed action hashing, a 10-minute approval TTL,
  transactional approve->execute->complete, idempotent duplicate-execute
  handling, idempotent rollback. Source file bytes are never touched.
- All Phase 1 REST routes, `{"error":{code,message}}` envelope.
- `apps/web/` — Next.js 14 one-page UI with the required components, a
  mode badge, and no `dangerouslySetInnerHTML` near repository/model
  content.
- `.github/workflows/ci.yml` — backend pytest, frontend typecheck/lint/
  build, and a Playwright job running the full seeded
  evaluate->approve->execute->rollback flow in a real browser.

### Verification (this session)

```
$ cd apps/api && python -m pytest -q
74 passed   (30 Phase 1, 44 Phase 2 including the review-round fixes above)

$ cd apps/web && npx tsc --noEmit        # clean
$ cd apps/web && npx next lint           # no warnings
$ cd apps/web && npx next build          # succeeds
$ cd apps/web && npx playwright test     # 2 passed (mock flow + live-unconfigured error)
```

Three real bugs were found and fixed while getting the above green (not
invented — this is what actually broke on first run):

1. `run_repository.create_run` inserted `events` rows before the parent
   `runs` row was flushed (no ORM `relationship()` between the tables, so
   SQLAlchemy had no FK dependency edge to order the insert) →
   `FOREIGN KEY constraint failed`. Fixed by flushing the run row first.
2. `run_repository.append_event`, called twice in one transaction
   (`autoflush=False`), computed the same next `sequence` twice since the
   first insert wasn't visible to the second query yet → `UNIQUE
   constraint failed`. Fixed by flushing after each append.
3. `EvaluationReport.model_validate(...)` failed reconstructing a
   persisted report because `StrictModel` uses `strict=True` and the
   round-tripped JSON stores timestamps as ISO strings, not native
   `datetime`. Fixed with `strict=False` only on the read-back path.

Also caught during Phase 2 development, before it ever ran outside a
test: an automated find/replace while adding incremental event recording
to `council/orchestrator.py` rewrote the `record()` helper's own body
into `await record(...)` — infinite self-recursion. Caught by re-reading
the diff before running anything, fixed before the recursive call was
ever executed.

## Phase 2 — live Nemotron council

Status: code complete for every milestone (2.1-2.7). **The live call to
NVIDIA Nemotron via Nebius Token Factory has not been executed in this
session** — there is no `NEBIUS_API_KEY` in this environment. That is
stated here plainly, not left ambiguous. Everything below that is
described as "implemented" has automated test coverage against a fake
in-process provider (`tests/fakes.py`) or a mocked HTTP client
(`tests/test_provider_validation.py`), never real network I/O — exactly
what the plan's own 2.7 instructions ask for in CI.

### Completed

- `app/providers/base.py` — the `Provider` interface (`generate(role,
  system_prompt, input_payload, output_model, prompt_version)`) shared by
  every provider.
- `app/providers/mock.py` — a deterministic MockProvider that builds
  PlannerOutput/RedTeamOutput/PrivacyOutput/ArbiterOutput from the
  supplied fixture facts and task text (keyword-based, not hardcoded
  per-variant strings), and never follows injected instructions because it
  never even reads repository content for its own reasoning.
- `app/providers/nebius.py` — implemented against the documented
  OpenAI-compatible shape with the plan's exact retry policy (max two
  attempts; no retry on 401/403; one retry on 429/5xx/timeout/invalid
  JSON/empty/truncated). **Unverified against a real account** — see
  `docs/MODEL_INTEGRATION.md`.
- `app/providers/budget.py` — per-run request cap and a shared (in-memory,
  non-durable) daily call cap, both stated as simplifications rather than
  hidden.
- `app/council/contracts.py` — Concern/ActionAssessment/RiskRating and the
  four StrictModel role outputs, with cross-reference validators (unique
  candidate ids, exactly one scenario of each kind tied to the preferred
  candidate, etc.).
- `app/council/context.py` + `app/council/prompts/*.txt` — the shared
  system prefix and the four versioned role prompts, copied verbatim from
  the plan.
- `app/council/orchestrator.py` — Planner -> deterministic candidate
  checks -> Red-team -> Privacy -> five counterfactual Planner probes ->
  Arbiter -> final deterministic reconciliation. The final decision is
  always computed by `decision_service.select_final_decision`, never by
  trusting any provider's own suggested outcome — tested directly: a
  rogue arbiter that recommends the blocked delete candidate outright
  does not change the enforced decision (`tests/test_council.py`).
- `app/counterfactuals/variants.py`, `runner.py`, `scoring.py` — the five
  perturbations, stability score (reword + injection only, per plan),
  injection-susceptibility flag, and the five-dimension transparent risk
  rubric that reports "unavailable" rather than defaulting missing data
  to zero.
- `app/services/live_runner.py` + `app/main.py` lifespan — the async
  202-then-poll flow: one in-process worker, a concurrency cap enforced by
  counting `status="evaluating"` rows, a whole-run deadline via
  `asyncio.wait_for`, and startup recovery that marks any run stuck in
  `evaluating` across a restart as `failed` (tested: `create_app` twice
  against the same DB file, second instance marks the first's stuck run
  failed with `process_interrupted`).
- `apps/web/` — a second "Run live council (Nemotron)" button, 202/poll
  handling in `page.tsx` (polls every 1.5s until the run leaves
  `evaluating`), and a `CounterfactualPanel` component showing the raw
  vs. enforced outcome per variant plus the stability/injection/risk
  scores with their coverage caveats. Verified end-to-end in a real
  browser (Playwright): clicking the live button with no `NEBIUS_API_KEY`
  configured shows the "live mode is not configured" error rather than a
  silent mock fallback.
- `scripts/model_smoke_test.py` — the documented manual opt-in smoke
  test. Confirmed to run and correctly report "no key configured" in this
  environment; **not** run successfully against a real key.
- `docs/MODEL_INTEGRATION.md` — written to say exactly what is and isn't
  verified, and what running the smoke test successfully would need to
  update.

### Verification commands and actual results (this session)

```
$ cd apps/api && python -m pytest -q
74 passed   # includes test_council.py, test_counterfactuals.py,
            # test_provider_validation.py, test_live_failure_states.py,
            # test_operator_credential.py, test_run_repository.py
            # (the last two, plus additions to the first three, came from
            # the PR review round documented above)

$ python scripts/model_smoke_test.py     # no NEBIUS_API_KEY set
error: set NEBIUS_API_KEY and NEBIUS_MODEL before running this script.
(exit code 2 — correct behavior, not a successful live call)
```

### Known simplifications (stated, not hidden)

- Daily model-call cap is in-memory only (resets on restart).
- Per-run budget counts logical `provider.generate()` calls, not raw HTTP
  attempts.
- Concurrency cap is enforced by counting DB rows, not a distributed lock
  (fine for the plan's one-backend-instance scope).
- The counterfactual suite only runs when the live task exactly matches
  the seeded task — running it against an arbitrary different live task
  would compare unrelated scenarios, so it's skipped (not silently
  mis-scored) in that case.

### Blocked or uncertain

- All live Nebius/Nemotron behavior: exact model ID availability,
  structured-output compatibility, real latency/token usage. Requires a
  real `NEBIUS_API_KEY` this session does not have.
- Public preview deployment (Vercel + persistent Python host) has not
  been attempted in this session.
- No demo video has been recorded in this session.

### Next concrete step

Run `scripts/model_smoke_test.py` with a real `NEBIUS_API_KEY` and
`NEBIUS_MODEL` against an account with Nebius Token Factory access, record
the actual model ID/latency/response-format results in
`docs/MODEL_INTEGRATION.md`, then drive one live `POST /api/v1/evaluations`
(`mode: "live"`) with the seeded task through the browser, inspect
`extensions.counterfactual_summary`, and replace the "unverified" language
in this file and in the root README with real observed results.
