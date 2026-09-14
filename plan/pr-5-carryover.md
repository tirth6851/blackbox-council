# PR #5 carryover ledger

This ledger carries every comment from [review 5202586093](https://github.com/tirth6851/blackbox-council/pull/5#pullrequestreview-5202586093) into the remaining-phase plans. C01–C19 are local tracking IDs, not newly created GitHub issues.

All items are **open / not verified fixed** at plan creation. Assigning a phase does not resolve a finding. The review was performed against merged commit `03158c3`; implementation must recheck current code before making a change.

| ID | PR review comment | Primary milestone | Later regression/verification |
|---|---|---|---|
| C01 | [Fresh fixture/policy verification](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310643) | 3.1 | 5.3, 6.2 |
| C02 | [Incomplete probes must block approval](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310649) | 3.2 | 4.2–4.4, 6.2 |
| C03 | [Complete inputs to council roles](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310657) | 3.2 | 4.2, 6.2 |
| C04 | [Conservative prerequisite reconciliation](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310661) | 3.2 | 4.4, 6.2 |
| C05 | [Nested semantic reference validation](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310668) | 3.2 | 4.2–4.4, 6.2 |
| C06 | [Persist structured evidence and metadata](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310674) | 3.3 | 4.1–4.4, 6.3 |
| C07 | [Raw-attempt budgets and durable daily caps](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310678) | 3.3 | 4.2, 5.2–5.3, 6.2 |
| C08 | [Atomic admission and bounded queue](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310681) | 3.3 | 5.3, 6.2 |
| C09 | [Polling error recovery](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310687) | 3.4 | 5.3 |
| C10 | [Stable run URLs and refresh recovery](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310695) | 3.4 | 5.3 |
| C11 | [Visible reviews and scenarios](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310699) | 3.4 | 4.3 |
| C12 | [Candidate-specific risk and null selection](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310705) | 3.2, 3.4 | 4.3–4.4, 6.2 |
| C13 | [Dependency advisory remediation](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310713) | 5.1; begin before public exposure | 5.4 |
| C14 | [Login rate limits](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310725) | 5.2; before public exposure | 5.4 |
| C15 | [Separate signing secret; conditional individual identity](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310731) | 5.2 | 6.1–6.3 |
| C16 | [Production auth validation and storage limits](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310738) | 5.1–5.2 | 6.1–6.2 |
| C17 | [Pre-resolution symlink rejection](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310743) | 3.1 | 6.2 |
| C18 | [Portable setup and supported runtimes](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310749) | 3.4 | 5.1 |
| C19 | [Real live verification and accurate completion claims](https://github.com/tirth6851/blackbox-council/pull/5#discussion_r4009310758) | 3.5 | 4.2, 5.4 |

## Rules for closing carryover

- Add the fixing PR/commit and exact rejection/success test evidence beside the item.
- Distinguish implemented from test-verified, live-model-verified and deployed.
- Code-inspection concerns need a regression or demonstrated invariant; do not claim they were already reproduced.
- Keep model-cost and deployment prerequisites explicit. No keys in comments, documents or reports.
- C13–C16 are public-exposure gates even if their main home is Phase 5. Do not deploy an earlier phase publicly without them.
- C15 individual identity is required before multi-user use; the signing-secret fix is not conditional.
- Failed/skipped live verification leaves C19 open. A mock test cannot close it.

## Plan links

- [Phase 3: reliable live demo and Decision X-Ray](03-phase-3-reliable-live-demo.md)
- [Phase 4: repeatable evaluation evidence](04-phase-4-evaluation-evidence.md)
- [Phase 5: hardened, verified deployment](05-phase-5-deployment-hardening.md)
- [Phase 6: optional integrations and isolated execution](06-phase-6-optional-integrations.md)

The original Phase 1 and 2 plans remain historical requirements. Outstanding work is carried forward here without retroactively marking their checklists complete.
