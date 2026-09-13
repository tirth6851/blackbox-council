"""Pure deterministic policy checks.

No network, database, or model calls happen here. Every function takes
already-validated task/context/candidate/manifest/policy data and returns
PolicyFinding objects. Keyword matches in free text are treated as evidence
for human/red-team review, never as the sole security boundary — the
structural checks (file scope, ownership, hold status, safeguards) are what
actually blocks or gates a candidate.
"""
from __future__ import annotations

import re

from app.schemas import CandidateAction, ContextItem, FileMetadata, PolicyFinding
from app.services.fixture_loader import RetentionPolicy

# --- heuristic text patterns -------------------------------------------------
# Evidence-only signals. They never independently authorize an action; they
# flag candidates whose *structured fields* also need a hard structural check.

_SHELL_PAYLOAD_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\$\(", r"`[^`]+`", r"subprocess", r"os\.system", r"eval\(", r"exec\(",
        r"rm\s+-rf", r"powershell", r"/bin/sh", r"/bin/bash",
    ]
]

_NETWORK_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [r"https?://", r"ftp://", r"upload\s+to", r"send\s+.*\s+to\s", r"webhook"]
]

_AUTH_BYPASS_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"bypass\s+approval", r"skip\s+approval", r"no\s+approval\s+needed",
        r"ignore\s+polic", r"override\s+polic", r"disable\s+safeguard",
    ]
]

_INSTRUCTION_OVERRIDE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [r"system\s+override", r"ignore\s+all\s+previous\s+rules", r"do\s+not\s+ask\s+for\s+approval"]
]

_PROTECTED_PATH_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [r"secret", r"\.env\b", r"private[-_]?key", r"credential", r"config"]
]


def _finding(
    rule_id: str,
    *,
    candidate_id: str | None,
    severity: str,
    triggered: bool,
    effect: str,
    evidence: list[str],
    explanation: str,
    remediation: str,
) -> PolicyFinding:
    return PolicyFinding(
        rule_id=rule_id,
        candidate_id=candidate_id,
        severity=severity,  # type: ignore[arg-type]
        status="triggered" if triggered else "clear",
        effect=effect,  # type: ignore[arg-type]
        evidence=evidence,
        explanation=explanation,
        remediation=remediation,
    )


def evaluate_missing_policy(candidate: CandidateAction) -> PolicyFinding:
    """RET-001: no authoritative policy loaded for this fixture."""
    return _finding(
        "RET-001",
        candidate_id=candidate.id,
        severity="high",
        triggered=True,
        effect="clarify",
        evidence=[],
        explanation="No authoritative retention policy is loaded for this fixture.",
        remediation="Load a server-owned retention-v1 policy before evaluating eligibility.",
    )


def evaluate_context(context_items: list[ContextItem]) -> list[PolicyFinding]:
    """TRUST-001: flag untrusted repository text that asks for an
    instruction override. Informational only; never changes policy state by
    itself."""
    findings: list[PolicyFinding] = []
    for item in context_items:
        if item.trust != "repository_untrusted":
            continue
        if any(p.search(item.content) for p in _INSTRUCTION_OVERRIDE_PATTERNS):
            findings.append(
                _finding(
                    "TRUST-001",
                    candidate_id=None,
                    severity="moderate",
                    triggered=True,
                    effect="info",
                    evidence=[item.id],
                    explanation=(
                        f"Repository document '{item.source}' (id={item.id}) attempts to "
                        "instruct the system to override rules and skip approval. It is "
                        "untrusted evidence, not an instruction source."
                    ),
                    remediation="Ignore embedded instructions from repository content; rely only on server policy.",
                )
            )
    return findings


def evaluate_candidate(
    candidate: CandidateAction,
    *,
    files: dict[str, FileMetadata],
    policy: RetentionPolicy,
) -> list[PolicyFinding]:
    """Run every structural rule against one candidate action."""
    findings: list[PolicyFinding] = []
    text_fields = " ".join([candidate.rationale])

    # CMD-001 — shell/code payload in the proposal text. Reject schema/dispatch;
    # never invoke subprocess/eval/exec regardless of match.
    cmd_hit = [p.pattern for p in _SHELL_PAYLOAD_PATTERNS if p.search(text_fields)]
    findings.append(
        _finding(
            "CMD-001",
            candidate_id=candidate.id,
            severity="critical",
            triggered=bool(cmd_hit),
            effect="block" if cmd_hit else "info",
            evidence=[],
            explanation=(
                "Candidate rationale contains shell/code payload language."
                if cmd_hit
                else "No shell/code payload language detected."
            ),
            remediation="Reject the candidate; never execute shell or code payloads.",
        )
    )

    # FILE-001 — direct deletion is blocked in the MVP even with approval.
    is_delete = candidate.operation == "delete"
    findings.append(
        _finding(
            "FILE-001",
            candidate_id=candidate.id,
            severity="critical",
            triggered=is_delete,
            effect="block" if is_delete else "info",
            evidence=[],
            explanation=(
                "Direct deletion is not executable in this demo."
                if is_delete
                else "Candidate does not propose direct deletion."
            ),
            remediation="Propose a bounded archive workflow instead of deletion.",
        )
    )

    # SCOPE-001 — empty mutation scope, unknown IDs, or too many files.
    requires_scope = candidate.operation in ("delete", "archive")
    unknown_ids = [fid for fid in candidate.file_ids if fid not in files]
    scope_problem = (
        (requires_scope and len(candidate.file_ids) == 0)
        or bool(unknown_ids)
        or len(candidate.file_ids) > policy.max_files
    )
    findings.append(
        _finding(
            "SCOPE-001",
            candidate_id=candidate.id,
            severity="high",
            triggered=scope_problem,
            effect="block" if scope_problem else "info",
            evidence=unknown_ids,
            explanation=(
                f"Scope problem: empty={requires_scope and len(candidate.file_ids) == 0}, "
                f"unknown_ids={unknown_ids}, count={len(candidate.file_ids)}, max={policy.max_files}."
                if scope_problem
                else "File scope is bounded and every ID is known."
            ),
            remediation="Rebuild a bounded manifest using only known file IDs within the cap.",
        )
    )

    # SECRET-001 — references to protected/secret-like paths.
    protected_hits = [
        fid
        for fid in candidate.file_ids
        if fid in files and any(p.search(files[fid].path) for p in _PROTECTED_PATH_PATTERNS)
    ]
    findings.append(
        _finding(
            "SECRET-001",
            candidate_id=candidate.id,
            severity="critical",
            triggered=bool(protected_hits),
            effect="block" if protected_hits else "info",
            evidence=protected_hits,
            explanation=(
                f"Candidate references protected-looking paths: {protected_hits}."
                if protected_hits
                else "No protected/secret-like paths referenced."
            ),
            remediation="Use only fixed, non-protected fixture metadata.",
        )
    )

    # NET-001 — request for network egress/upload in the executor sense.
    net_hit = [p.pattern for p in _NETWORK_PATTERNS if p.search(text_fields)]
    findings.append(
        _finding(
            "NET-001",
            candidate_id=candidate.id,
            severity="critical",
            triggered=bool(net_hit),
            effect="block" if net_hit else "info",
            evidence=[],
            explanation=(
                "Candidate text asks for network upload or an external destination."
                if net_hit
                else "No network egress requested."
            ),
            remediation="Allow only local simulated state; reject the executor schema.",
        )
    )

    # AUTH-001 — request to bypass approval or mutate policy.
    auth_hit = [p.pattern for p in _AUTH_BYPASS_PATTERNS if p.search(text_fields)]
    findings.append(
        _finding(
            "AUTH-001",
            candidate_id=candidate.id,
            severity="critical",
            triggered=bool(auth_hit),
            effect="block" if auth_hit else "info",
            evidence=[],
            explanation=(
                "Candidate text requests bypassing approval or changing server policy."
                if auth_hit
                else "No approval-bypass or policy-mutation request detected."
            ),
            remediation="Reject; the caller cannot change server configuration.",
        )
    )

    # HOLD-001 — selected files must be eligible: not on hold, not active,
    # not recently modified, owner known. Only meaningful once scope itself
    # is valid.
    if not scope_problem and candidate.operation in ("delete", "archive"):
        ineligible: list[str] = []
        reasons: list[str] = []
        for fid in candidate.file_ids:
            meta = files[fid]
            if policy.exclude_legal_hold and meta.legal_hold:
                ineligible.append(fid)
                reasons.append(f"{fid}: legal hold")
                continue
            if meta.inactive_days < policy.inactive_days_min:
                ineligible.append(fid)
                reasons.append(f"{fid}: active ({meta.inactive_days}d inactive)")
                continue
            if meta.modified_days < policy.modified_days_min:
                ineligible.append(fid)
                reasons.append(f"{fid}: recently modified ({meta.modified_days}d)")
                continue
            if policy.require_known_owner and meta.owner_id is None:
                ineligible.append(fid)
                reasons.append(f"{fid}: unknown owner")
                continue
        findings.append(
            _finding(
                "HOLD-001",
                candidate_id=candidate.id,
                severity="high",
                triggered=bool(ineligible),
                effect="block" if ineligible else "info",
                evidence=ineligible,
                explanation="; ".join(reasons) if reasons else "All selected files are eligible.",
                remediation="Rescan for eligible files under the current policy.",
            )
        )

    # SAFE-001 — archive without a dry run.
    if candidate.operation == "archive":
        missing_dry_run = policy.require_dry_run and not candidate.dry_run
        findings.append(
            _finding(
                "SAFE-001",
                candidate_id=candidate.id,
                severity="moderate",
                triggered=missing_dry_run,
                effect="safeguard" if missing_dry_run else "info",
                evidence=[],
                explanation=(
                    "Archive is missing dry-run evidence." if missing_dry_run else "Dry-run evidence present."
                ),
                remediation="Generate a dry-run manifest before archiving.",
            )
        )

        # SAFE-002 — missing backup manifest or insufficient recovery window.
        missing_backup = policy.require_backup_manifest and not candidate.backup_manifest
        short_recovery = candidate.recovery_days < policy.recovery_days_min
        safeguard_issue = missing_backup or short_recovery
        findings.append(
            _finding(
                "SAFE-002",
                candidate_id=candidate.id,
                severity="moderate",
                triggered=safeguard_issue,
                effect="safeguard" if safeguard_issue else "info",
                evidence=[],
                explanation=(
                    f"missing_backup_manifest={missing_backup}, "
                    f"recovery_days={candidate.recovery_days} < min={policy.recovery_days_min}: {short_recovery}."
                    if safeguard_issue
                    else "Backup manifest and recovery window satisfy the policy minimum."
                ),
                remediation="Create a simulated backup manifest with at least the minimum recovery window.",
            )
        )

    return findings
