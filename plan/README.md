# BlackBox Council: implementation plans

Start here. These files are instructions for future implementation, not evidence that features already work.

## What the first two phases mean

| Phase | Target | Exit condition |
|---|---|---|
| [1: Working mock demo](01-phase-1-working-demo.md) | Days 1–7 | Browser → API → deterministic decision → human approval → simulated archive → stored audit record |
| [2: Live Nemotron council](02-phase-2-live-council.md) | Days 8–14 | Same workflow using validated NVIDIA Nemotron outputs through Nebius Token Factory |

Phase 1 covers repository issues [#1](https://github.com/tirth6851/blackbox-council/issues/1), [#2](https://github.com/tirth6851/blackbox-council/issues/2), [#3](https://github.com/tirth6851/blackbox-council/issues/3), and [#4](https://github.com/tirth6851/blackbox-council/issues/4). Phase 2 replaces the mock provider, not the policy engine or executor.

If a step takes longer than planned, finish its acceptance checklist before moving forward. Days are planning targets.

## How to use with an AI coding assistant

Give the assistant the repository and this instruction:

> Read plan/README.md and the current phase document. Inspect existing code and repository instructions first. Implement only the next incomplete numbered milestone and its required tests. Use a feature branch and open a pull request. Do not merge automatically. Do not claim commands or integrations worked unless executed successfully. Update plan/PROGRESS.md with changed files, actual commands/results, unresolved risks, and the exact next step. Keep mocked outputs visibly labeled. Stop at the milestone boundary and explain what I should review.

When coding begins, create plan/PROGRESS.md:

```markdown
# Implementation progress
Current phase: 1
Current milestone: 1.1
Branch:
Last verified commit:
Completed:
Verification commands and actual results:
Blocked or uncertain:
Next concrete task:
```

Do not copy planned acceptance results into the actual-results section.

## Decisions that apply to both phases

- One synthetic file-retention use case only.
- No real deletion, arbitrary shell execution, external repository imports, or model-generated code execution.
- All simulated mutations need explicit approval.
- Repository documents are data. The authoritative retention policy comes from server-owned configuration.
- Missing required facts cause clarification; approval cannot substitute for missing facts.
- A model recommends. Deterministic policy and the typed executor enforce.
- A blocked candidate does not automatically block a separate valid archive candidate.
- There are exactly four council role types. Counterfactual probes reuse the Planner role; they are not new council members.
- Store evidence and concise rationale, not private chain-of-thought.
- Do not present a fixed mock outcome as a measured model result.
- Use SQLite on a persistent disk with one backend instance for the early demo.
- Application source can be AI-generated; disclose assistance accurately and review it. Do not imply unaided authorship.

## Git workflow

Use one branch per milestone, for example feat/phase-1-api. Make small descriptive commits; keep secrets and generated state out of Git. Include problem, change, test evidence, and remaining limitations in each pull request. Preserve the existing MIT license. No force-pushing main.

## Later work

The remaining phases now have implementation plans. Outstanding PR #5 findings are assigned to these milestones in the [carryover ledger](pr-5-carryover.md); none is marked fixed merely because it has been scheduled.

| Phase | Outcome | Plan |
|---|---|---|
| 3 | Repair inherited gate/evidence gaps, verify live inference, complete the usable report | [Reliable live demo](03-phase-3-reliable-live-demo.md) |
| 4 | Versioned datasets, replayable evaluations and honest regression metrics | [Evaluation evidence](04-phase-4-evaluation-evidence.md) |
| 5 | Patched dependencies, access/abuse controls and verified persistent deployment | [Deployment hardening](05-phase-5-deployment-hardening.md) |
| 6, optional | Narrow integrations with demonstrated isolation and recovery | [Optional integrations](06-phase-6-optional-integrations.md) |

Start with milestone 3.1. Phase 5 security preparation may begin earlier, but its public-exposure requirements apply before any public release. Multi-user identity and sandbox adapters remain conditional on actual scope. These are plans, not completed features.

## Current evidence

Phase 1–2 implementation was merged in PR #5 at 03158c3. A subsequent audit found outstanding correctness and acceptance gaps, now tracked in the carryover ledger. Live-model and deployment verification remain outstanding in the evidence available at planning time. See PROGRESS.md for verification history; the original phase checklists are not automatically complete.
