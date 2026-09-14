# Phase 4: repeatable evaluation evidence

**Status:** planned. **Prerequisite:** Phase 3's validated evidence pipeline and live verification.
**Outcome:** a reproducible, bounded evaluation suite with honest measurements.

Carryover: C02, C05–C08 and C12 remain regression requirements; this phase does not defer their Phase 3 fixes. Read [the carryover ledger](pr-5-carryover.md).

## 4.1 Version a synthetic dataset

Create reviewed cases for clean requests, paraphrases, added read-only constraints, missing facts, unknown owners, legal holds, scope expansion and varied repository injections. Label expected deterministic outcomes separately from acceptable advisory model behavior. Keep authoritative policy and untrusted content separate.

Define development and frozen holdout sets before tuning prompts. Record case IDs, dataset version, exact content hashes, expected prerequisites and rationale for ambiguous cases.

**Acceptance**
- [ ] Every case is synthetic and has provenance, expected policy behavior and reviewed labels.
- [ ] Meaning-preserving perturbations change one factor; legitimate constraint changes are separately classified.
- [ ] Holdout cases are not used for prompt tuning.
- [ ] No dataset text is executed or granted authority.

## 4.2 Build an offline and opt-in live harness

Replay saved structured outputs through validation and policy without paid calls. Add an explicit live command with configured case selection, attempt/token limits and an estimated maximum call count before starting.

Store exact prompts, schemas, policy/model configuration, input/output digests, attempts, coverage and failures through Phase 3's evidence pipeline. Compare model-only proposals and gated outcomes on identical inputs.

**Acceptance**
- [ ] Offline runs reproduce saved policy outcomes.
- [ ] Live attempts respect durable limits including retries.
- [ ] Provider or validation failures remain failures, never successful defenses.
- [ ] Null selections and incomplete evidence remain distinguishable.
- [ ] Artifacts can be reconstructed after process restart.

## 4.3 Report separate metrics

Report raw attack following, gate enforcement, false blocks, clarification, invalid output, successful completion, coverage, latency and usage separately. Include numerator/denominator and exact dataset/model/configuration with every score. Show per-case diffs for regressions.

Do not infer general model security from this domain. Do not call the risk rubric a calibrated probability. Report uncertainty where sample sizes support it; otherwise state the sample limitation plainly.

**Acceptance**
- [ ] Failed/skipped cases cannot improve stability or resistance metrics.
- [ ] Legitimate read-only behavior is not labeled instability.
- [ ] Model behavior and deterministic enforcement have separate columns.
- [ ] Each displayed metric traces to stored cases and call evidence.

## 4.4 Establish regression gates

Review initial results before selecting thresholds. Use deterministic invariant tests and offline replay in ordinary CI. Keep paid inference a manual or explicitly budgeted job, separate from routine tests. Require a reviewed baseline update when model/prompt/schema/policy versions change.

**Acceptance**
- [ ] A clean checkout reproduces the offline report.
- [ ] Deliberately unsafe fake outputs trigger the expected failures.
- [ ] CI detects known gate/coverage/reference regressions.
- [ ] Thresholds, limitations and baseline-change policy are documented.

## Phase exit

Publish a versioned evaluation report and reproducible commands with actual results, failures and limitations. Preserve Phase 3 gates. Next: [Phase 5](05-phase-5-deployment-hardening.md).
