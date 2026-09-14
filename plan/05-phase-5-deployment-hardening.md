# Phase 5: hardened, verified deployment

**Status:** planned. **Prerequisite:** Phase 3 correctness/live gates; Phase 4 evidence before reliability claims.
**Outcome:** a controlled public synthetic demonstration with verified access, cost, storage and recovery controls.

Carryover: C07–C08 and C13–C16, C18–C19. Security/dependency preparation may start during Phase 3, but public exposure is gated on this plan.

## 5.1 Dependency and production configuration baseline

Review current dependency advisories against the actual deployment platform and enabled features. Upgrade affected packages to supported patched versions with a reviewed migration and lockfile; do not force dependency updates blindly. Pin supported runtimes consistently.

Validate required production settings at startup. Reject missing/unsafe operator authentication and session-signing configuration in production while keeping an explicit local-demo mode. Bound request bodies, contexts and responses.

**Acceptance**
- [ ] Dependency audit findings are remediated or explicitly assessed with supporting evidence; no unresolved applicable critical/high finding is silently accepted.
- [ ] Typecheck/lint/build/backend/browser checks pass after migration.
- [ ] Missing production credentials fail startup or protected access closed.
- [ ] Secrets stay server-side and out of logs/reports/client bundles.

## 5.2 Authentication and abuse controls

Rate-limit login and public evaluation creation, with testable reset/expiry and retryable responses. Use a separate high-entropy session-signing secret with rotation and expiration handling. Apply durable raw-attempt limits from Phase 3 and bound persisted mock runs/storage.

Keep the scope explicitly single-operator unless multiple operators are required. Before multi-user access, add authenticated IDs, per-run authorization/ownership and attributable approval/execution records. Do not use a shared credential as evidence of individual identity.

**Acceptance**
- [ ] Anonymous protected calls, incorrect/expired sessions and cross-origin attempts fail.
- [ ] Authorized success paths still work.
- [ ] Login/evaluation quotas reject abuse and recover after the allowed interval.
- [ ] Restart does not reset daily model limits.
- [ ] If multi-user: another operator cannot read/approve/execute unauthorized runs; attribution survives report export.
- [ ] Public reports contain only approved synthetic evidence and have a defined retention policy.

## 5.3 Deploy one persistent backend instance

Use the existing frontend/backend separation and one Python instance with persistent SQLite storage initially. Select hosting based on verified support for long-lived worker execution and persistent disk. Confirm TLS, origin configuration, secret injection, readiness and stored-report behavior.

Use sanitized operational logs and metrics for queue depth, errors, request attempts, latency and storage. Do not include provider credentials or raw sensitive payloads.

**Acceptance**
- [ ] Record real frontend/backend URLs and deployment revision.
- [ ] Public route auth and exact approve → simulate → rollback flow are verified.
- [ ] Restart marks interrupted work failed and preserves completed reports and usage caps.
- [ ] Capacity and timeout behavior matches the documented contract.
- [ ] Readiness failures do not silently serve an unsafe partial system.

## 5.4 Recovery and release handoff

Define retention cleanup for synthetic reports, database backups, restore verification, secret rotation, incident handling and deployment rollback. Exercise these on a non-production copy before relying on them.

**Acceptance**
- [ ] Restore a backup and verify report/approval/execution consistency.
- [ ] Demonstrate deployment rollback and record limitations.
- [ ] No cleanup removes active runs or required audit evidence unexpectedly.
- [ ] Walkthrough uses the actual deployed application and labels simulation/live/mock correctly.
- [ ] PROGRESS records URLs, commands, outcomes and unverified limitations.

## Phase exit

Public deployment is independently reached and tested with access, spending/storage limits and recovery evidence. A local build or historic green CI is insufficient.

Next: [Phase 6](06-phase-6-optional-integrations.md), only if a concrete need exists.

