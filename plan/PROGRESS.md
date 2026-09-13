# Implementation progress

Current phase: 2
Current milestone: 2.7 (see below — live model verification is explicitly unverified)
Branch: claude/workflows-phase-1-2-3aujzd

## Phase 1 — working mock demo

Status: complete, all milestones 1.1–1.8 implemented and passing locally.

### Completed

- `apps/api/app/schemas.py` — strict Pydantic contracts (CandidateAction vs
  ExecutableAction kept separate, Outcome/RunStatus literals, explicit
  `ALLOWED_STATUS_TRANSITIONS` table with `is_valid_transition`).
- `apps/api/app/fixture_registry.py`, `app/services/fixture_loader.py` —
  server-owned fixture/policy loading, path-traversal/symlink guards, hash
  verification against disk content.
- `demo-repo/` synthetic fixture tree (f001–f005, storage notes, the
  inert prompt-injection sample) and `scripts/seed_fixtures.py`, which
  computes real SHA-256 hashes/byte counts — nothing is hardcoded.
- `apps/api/app/services/policy_engine.py` — all thirteen rules from the
  plan (EXEC-001 enforced at the executor boundary; the other twelve as
  PolicyFinding-producing checks): CMD-001, FILE-001, TRUST-001,
  SECRET-001, NET-001, AUTH-001, SCOPE-001, RET-001, HOLD-001, SAFE-001,
  SAFE-002, plus APPROVAL-001 enforced via the approval/execute flow.
- `apps/api/app/services/mock_provider.py` — four labeled `[MOCK]` reviews,
  three scenario hypotheses, four scripted candidates (delete/dry_run/
  archive/clarify); rejects any task other than the seeded one with
  `unsupported_mock_task`.
- `apps/api/app/services/decision_service.py` — per-candidate
  classification (block > clarify > safeguard > approval > safe) and
  final-candidate selection; a blocked delete never vetoes the separately
  valid archive candidate (tested).
- `apps/api/app/db.py`, `app/models/orm.py`,
  `app/services/run_repository.py` — SQLite persistence for
  runs/events/approvals/executions/simulation_state, FK+busy_timeout
  pragmas, optimistic-concurrency status transitions.
- `apps/api/app/services/hashing.py`, `services/manifests.py`,
  `services/executor.py` — canonical server-computed action hash, 10-minute
  approval TTL, transactional approve→execute→complete, idempotent
  duplicate-execute handling, idempotent rollback restoring prior
  simulated state. Source file bytes are never touched; only a SQLite
  "simulated archive index" changes.
- `apps/api/app/api/evaluations.py`, `app/main.py` — all Phase 1 routes,
  `{"error":{"code","message"}}` envelope, CORS from settings.
- `apps/web/` — Next.js 14 (App Router, TypeScript, Tailwind), one page
  with the required components (task-form, timeline, action-comparison,
  evidence-panel, approval-panel, execution-result), typed `lib/api.ts`.
  Mode badge always shows "Mock"; repository/model text is rendered as
  plain escaped text, never `dangerouslySetInnerHTML`.
- `.github/workflows/ci.yml` — backend pytest, frontend typecheck/lint/
  build, and a Playwright browser job running the full seeded
  evaluate→approve→execute→rollback flow against the real mock API.

### Verification commands and actual results (this session)

```
$ cd apps/api && python -m pytest -q
30 passed, 1 warning in 0.52s

$ cd apps/web && npx tsc --noEmit
(no output — clean)

$ cd apps/web && npx next lint
✔ No ESLint warnings or errors

$ cd apps/web && npx next build
✓ Compiled successfully / ✓ Generating static pages (5/5)

$ cd apps/web && npx playwright test   # against /opt/pw-browsers/chromium
1 passed (8.9s)
```

Two real bugs were found and fixed during this session while making the
above pass (not invented — this is what actually broke on first run):

1. `run_repository.create_run` inserted `events` rows before the parent
   `runs` row was flushed (no ORM `relationship()` was declared between
   the tables, so SQLAlchemy had no FK dependency edge to order the
   insert) → `FOREIGN KEY constraint failed`. Fixed by flushing the run
   row before adding its events.
2. `run_repository.append_event`, called twice within one transaction
   (session factory has `autoflush=False`), computed the same next
   `sequence` twice because the first insert wasn't visible to the
   second's query yet → `UNIQUE constraint failed: events.run_id,
   events.sequence`. Fixed by flushing after each append.
3. `EvaluationReport.model_validate(...)` failed reconstructing a
   persisted report because `StrictModel` uses `strict=True` and the
   round-tripped JSON stores timestamps as ISO strings, not native
   `datetime` objects. Fixed by validating with `strict=False` only on
   the read-back path (fresh API input still validates strictly).

### Known limitations at end of Phase 1

- Persistence is one SQLite file, one process — matches the plan's scope,
  not a claim of durability beyond that.
- The frontend has not been run against a deployed (Vercel + hosted API)
  environment in this session — only local dev/build and the Playwright
  job against locally-started servers. Preview deployment is not done.
- No demo video has been recorded in this session.

## Phase 2 — live Nemotron council

Status: all code paths implemented (provider abstraction, council
contracts/orchestrator, counterfactual runner, async live-run queue).
**Live verification against the real Nebius Token Factory endpoint was
NOT performed in this session** — there is no `NEBIUS_API_KEY` available
in this environment. This is stated plainly rather than left ambiguous:
nothing here should be read as "tested against NVIDIA Nemotron."　What
*was* verified:

- All Phase 1 tests still pass with `MockProvider` wired through the new
  `providers/base.py` interface.
- `NebiusProvider` is implemented against the documented OpenAI-compatible
  API shape (see `docs/MODEL_INTEGRATION.md`) but its actual request/response
  behavior against a live model is unverified.
- Every council/counterfactual/orchestrator test uses a fake in-process
  provider (`tests/fakes.py`), never network I/O, per the plan's own
  instruction that automated tests use fake provider responses, not paid
  inference.
- `scripts/model_smoke_test.py` exists as the documented manual opt-in
  smoke test but has not been run against a real key in this session.

See `docs/MODEL_INTEGRATION.md` for the exact compatibility caveats and
what remains to be verified with real credentials.

### Next concrete step

Run `scripts/model_smoke_test.py` with a real `NEBIUS_API_KEY` and
`NEBIUS_MODEL` against an account that has Nebius Token Factory access,
record the actual model ID/latency/response-format results in
`docs/MODEL_INTEGRATION.md`, then re-run the five counterfactual
perturbations live and record real (not fake-provider) results before
claiming Phase 2's live-model exit criteria are met.

### Blocked or uncertain

- Live Nebius/Nemotron behavior, exact model ID availability, structured
  output compatibility, and live latency/token usage are all unverified
  pending real credentials.
- Public preview deployment (Vercel + persistent Python host) has not
  been attempted in this session.
