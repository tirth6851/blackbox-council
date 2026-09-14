# Phase 6: optional integrations and isolated execution

**Status:** conditional planning, not an approved expansion to destructive execution.
**Prerequisite:** Phases 3–5 safety, evidence and operational gates; a concrete use case requiring an adapter.
**Outcome:** a narrowly scoped, auditable integration proven with synthetic inputs.

PR #5 carryover C01–C08, C12 and C15–C17 become non-regression requirements across every adapter. Do not weaken them to make an integration work.

## 6.1 Define the use case and threat model

Specify input sources, trust boundaries, operator/tenant authority, allowed actions, scope, resource limits, egress policy and recovery guarantees. Keep external repository ingestion read-only initially. Name what evidence an adapter must produce before an action is eligible.

**Acceptance**
- [ ] A reviewed threat model and narrow typed adapter contract exist.
- [ ] Arbitrary model-generated commands, real deletion and secret access are excluded.
- [ ] Missing authority/facts remain clarification, not implied approval.
- [ ] Additional infrastructure has a concrete requirement, not just a roadmap label.

## 6.2 Prototype an isolated adapter

Verify the selected sandbox/service's actual availability, API and isolation controls before coding against assumed interfaces. Use synthetic fixtures and constrained operations. Preserve exact action hashes, current-state verification, validated references, bounded retries, complete evidence and authenticated attribution.

**Acceptance**
- [ ] Adapter cannot execute operations outside its allowlist.
- [ ] Path escape/symlink, unauthorized network, scope expansion and stale approval attempts are rejected.
- [ ] Resource/time limits and cancellation are demonstrated.
- [ ] Original files remain unchanged in the synthetic demonstration.
- [ ] Failures produce no executable partial result and no silent mock fallback.

## 6.3 Verify recovery and audit reconstruction

Exercise interruption before/during/after a simulated action. Define idempotency and rollback behavior explicitly. Reconstruct the action and evidence from persisted records.

**Acceptance**
- [ ] Duplicate requests cannot create unintended duplicate effects.
- [ ] Recovery and rollback are demonstrated, not inferred from a backup label.
- [ ] All adapter decisions map to recorded policy, input, operator and action identity.
- [ ] Cross-tenant access is rejected if multi-user operation is introduced.

## 6.4 Decide whether to expand

Compare the prototype against the original need and maintenance/security cost. Introduce Postgres, durable workers or more complex scheduling only if measured durability/concurrency needs exceed the existing design. Any broader or destructive execution scope needs a separate design and explicit authorization.

**Exit:** a tested narrow adapter or a documented decision not to proceed. Do not claim isolation, production readiness or safe real-file execution from simulation results.

