# Phase 3: reliable live demo and Decision X-Ray

**Status:** planned, not implemented. **Prerequisite:** merged Phase 1–2 foundation.
**Outcome:** repair the inherited gate and evidence gaps, verify the live model, and make the full decision understandable in the browser.

Read AGENTS.md, README.md, this plan, PROGRESS.md, and docs/MODEL_INTEGRATION.md. Track inherited findings in [PR #5 carryover](pr-5-carryover.md). Phase 1–2 merge status does not mean its outstanding acceptance criteria passed.

Use one focused implementation PR per numbered milestone. Complete the milestone's rejection and success tests before moving on. No real deletion, arbitrary shell execution, external imports or additional council roles.

## 3.1 Fresh-state execution and path validation

Carryover: C01, C17.

- Add an uncached execution-time snapshot of fixture bytes, metadata and authoritative policy.
- Bind approval to policy content as well as version, exact scope, manifest digests and recovery configuration.
- Reject changes after evaluation/approval, even when policy version is unchanged and the cache has not been cleared.
- Independently measure source hashes after simulation; do not copy the before map into both result fields.
- Reject symlink components before resolution, then verify resolved containment.
- Preserve atomic updates, approval expiration, duplicate-execution behavior and rollback.

**Acceptance**
- [ ] Disposable-fixture tests change bytes, scope, ownership/legal hold and policy after approval without clearing caches; execution returns 409 and no synthetic state changes.
- [ ] Missing/rejected/expired approval and incorrect hashes remain rejected.
- [ ] Concurrent execute calls produce one execution; transaction failure leaves no partial state.
- [ ] Symlink, absolute-path and traversal tests reject invalid input on supported platforms.
- [ ] Normal approve → simulate → rollback succeeds and independently measured source hashes match.

## 3.2 Complete council inputs and conservative reconciliation

Carryover: C02–C05, C12.

- Give Red-team the actual candidates, inventory, policy and source context.
- Give Privacy the relevant source facts and Red-team structured output.
- Give Arbiter the prior reviews, candidate decisions and counterfactual summary. Prior model output remains untrusted evidence.
- Validate nested candidate/file/evidence/finding references and assessment coverage, including Arbiter selections.
- Define a typed reconciliation result: deterministic prohibitions remain enforced; unresolved credible facts/safeguards add clarification or review. Unsupported accusations are not established policy facts.
- Required probe failures produce an incomplete result without an executable action hash. Enforce this in approval and execution, not only the UI.
- Define explicit skipped-probe handling for unsupported/non-seeded tasks. Do not treat skipped coverage as success.
- Preserve null selection; do not substitute the first candidate. Attribute risk to a named candidate, distinguishing the Planner preference from final selection.

**Acceptance**
- [ ] Tests capture complete role inputs.
- [ ] Unknown nested references, missing required coverage and invalid selections fail explicitly after bounded correction.
- [ ] A clarification request cannot silently become an approvable archive.
- [ ] A model cannot relax a deterministic block.
- [ ] Failed or skipped required probes cannot approve/execute through raw API calls.
- [ ] Null selections and differing preferred/final candidates produce honest decisions and score labels.
- [ ] Complete, valid evidence still permits the bounded synthetic flow.

## 3.3 Persist reproducible evidence and enforce live capacity

Carryover: C06–C08.

- Persist sanitized complete structured outputs and per-attempt metadata: model, prompt/schema versions and hashes, times, duration, tokens where available, finish reason and failure category.
- Store exact baseline/variant inputs and full content digests including policy, inventory and untrusted context. Preserve failed-check details and coverage.
- Never persist keys, authorization headers, private reasoning or raw sensitive provider errors.
- Reserve request budget before every HTTP attempt, including transport/schema/reference retries. Keep the combined maximum at two attempts per logical call.
- Persist daily usage across restart. Count actual attempts, not generate() calls.
- Atomically admit at most one active plus two queued runs initially. Bound the queue and use a safe event-loop handoff from HTTP handlers.
- Keep the whole-run deadline, explicit interrupted-run failure, context/response limits and single-backend-instance scope.

**Acceptance**
- [ ] A database round-trip reconstructs all four base passes and five probe calls, including retries/failures.
- [ ] Changing input content with the same context IDs changes the digest.
- [ ] Budget exhaustion prevents the next HTTP attempt; restart retains daily accounting.
- [ ] Concurrent admissions cannot exceed capacity; full capacity returns a documented retryable error.
- [ ] Cancellation/deadline/restart failures yield no executable result.
- [ ] Failed/refused/truncated output cannot become an accepted partial recommendation.

## 3.4 Browser recovery and inspectable reports

Carryover: C09–C12, C18.

- Add stable run URLs; load stored progress and resume polling on refresh.
- Show retryable polling errors and bounded reconnect behavior; cancel outstanding requests on navigation.
- Render reviewer concerns, disagreements, scenario hypotheses, prerequisites and source references before approval.
- Show raw proposal versus enforced result, named-candidate risk, mode and completed/failed/skipped coverage.
- Improve mobile layout, keyboard navigation, focus and accessible status messages.
- Make dependency installation/platform support explicit: platform-aware uvloop requirement, portable Playwright server startup and consistent supported Node version.
- Add a trace diagram only if its nodes link to real stored events/evidence.

**Acceptance**
- [ ] Refresh during a delayed fake live run resumes viewing the same run.
- [ ] One transient GET failure recovers without an indefinite frozen polling screen.
- [ ] An operator can inspect all concerns and scenario hypotheses before approving.
- [ ] Desktop/mobile and keyboard flows work; session expiry is visible and enforced.
- [ ] Fresh-clone commands and browser tests work on declared supported platforms.

## 3.5 Real model verification and demo handoff

Carryover: C19. Prerequisites: 3.1–3.4, server-side credentials, and an explicitly bounded inference budget.

- Verify an exact NVIDIA model available in the account and the currently supported response format/parameters.
- Run two consecutive small Planner smoke tests with local schema and semantic validation.
- Run two complete seeded live evaluations with four base passes and all five probes; record actual model/configuration, attempts, failures, duration and usage.
- Inspect source trust labels, file IDs and observable attack behavior. Do not manufacture an attack failure.
- Where the verified gate permits, demonstrate authenticated approval → simulation → independent source verification → rollback.
- Record an actual walkthrough and update README, MODEL_INTEGRATION and PROGRESS with observed evidence.

**Acceptance**
- [ ] Both smoke tests and complete runs have sanitized retained evidence.
- [ ] Real deletion remains non-executable regardless of model output.
- [ ] Missing credits/access or provider incompatibility remain explicit blockers, not mock substitutes.
- [ ] Demo and documentation accurately distinguish implemented, test-verified, live-model-verified and simulated.
- [ ] Original Phase 2 live exit requirements are rechecked and their remaining gaps listed.

## Phase exit and next step

All milestones above pass their checks. Run full backend tests and frontend typecheck/lint/build/browser checks, recording real results. Public exposure also requires Phase 5 security controls; a local live demonstration is not deployment readiness.

Next: [Phase 4](04-phase-4-evaluation-evidence.md). Start implementation with 3.1.
