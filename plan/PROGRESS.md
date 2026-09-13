# Implementation progress

Current phase: 2 (code complete; live model verification still pending real credentials)
Current milestone: 2.7 exit checklist — all items done except the ones that require a real NEBIUS_API_KEY
Branch: claude/workflows-phase-1-2-3aujzd

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
62 passed in ~1.8s   (30 of these are Phase 1; see Phase 2 below for the rest)

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
62 passed   # includes test_council.py, test_counterfactuals.py,
            # test_provider_validation.py, test_live_failure_states.py

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
