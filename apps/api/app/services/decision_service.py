"""Selection and effective-outcome logic.

Combines deterministic policy findings for each candidate into a per-candidate
decision, then selects the single most useful permitted candidate for the
run's final decision. A model (mock or live) may suggest an outcome; only
this module and policy_engine determine the enforced outcome.
"""
from __future__ import annotations

import datetime as dt

from app.schemas import (
    CandidateAction,
    CandidateDecision,
    ContextItem,
    EventRecord,
    EvaluationReport,
    FinalDecision,
    Outcome,
    Plan,
    Review,
    RunStatus,
    Scenario,
)
from app.services import mock_provider
from app.services.fixture_loader import LoadedFixture, RetentionPolicy, load_fixture
from app.services.hashing import compute_action_hash
from app.services.manifests import build_backup_manifest, build_dry_run_manifest, digest_of
from app.services.policy_engine import evaluate_candidate, evaluate_context, evaluate_missing_policy

# Higher priority (lower number) wins when multiple non-blocked candidates
# are available. Blocked candidates are never selected but stay visible.
_SELECTION_PRIORITY: dict[Outcome, int] = {
    "approval_required": 0,
    "safeguard_required": 1,
    "safe": 2,
    "clarification_required": 3,
}

_OUTCOME_TO_STATUS: dict[Outcome, RunStatus] = {
    "safe": "completed",
    "safeguard_required": "needs_safeguards",
    "clarification_required": "needs_clarification",
    "approval_required": "awaiting_approval",
    "blocked": "blocked",
}


def outcome_to_status(outcome: Outcome) -> RunStatus:
    return _OUTCOME_TO_STATUS[outcome]


def classify_candidate(candidate: CandidateAction, findings: list) -> tuple[Outcome, list[str]]:
    blocking = [f for f in findings if f.effect == "block" and f.status == "triggered"]
    if blocking:
        return "blocked", [f.rule_id for f in blocking]

    if candidate.operation == "clarify":
        return "clarification_required", ["unresolved question: see plan.unanswered_questions"]

    clarifying = [f for f in findings if f.effect == "clarify" and f.status == "triggered"]
    if clarifying:
        return "clarification_required", [f.rule_id for f in clarifying]

    safeguards_missing = [f for f in findings if f.effect == "safeguard" and f.status == "triggered"]
    if safeguards_missing:
        return "safeguard_required", [f.rule_id for f in safeguards_missing]

    if candidate.operation == "archive":
        return "approval_required", ["approval"]

    return "safe", []


def evaluate_candidates(
    candidates: list[CandidateAction],
    *,
    files: dict,
    policy: RetentionPolicy,
) -> list[CandidateDecision]:
    decisions: list[CandidateDecision] = []
    for candidate in candidates:
        findings = evaluate_candidate(candidate, files=files, policy=policy)
        outcome, prerequisites_missing = classify_candidate(candidate, findings)
        decisions.append(
            CandidateDecision(
                candidate_id=candidate.id,
                outcome=outcome,
                findings=findings,
                prerequisites_missing=prerequisites_missing,
            )
        )
    return decisions


def select_final_decision(
    *,
    run_id: str,
    candidates: list[CandidateAction],
    decisions: list[CandidateDecision],
    loaded: LoadedFixture,
) -> FinalDecision:
    eligible = [d for d in decisions if d.outcome in _SELECTION_PRIORITY]
    if not eligible:
        return FinalDecision(
            outcome="blocked",
            selected_candidate_id=None,
            summary="Every candidate was blocked by policy. No action is available.",
            safeguards=[],
            action_hash=None,
        )

    chosen = sorted(eligible, key=lambda d: _SELECTION_PRIORITY[d.outcome])[0]
    candidate = next(c for c in candidates if c.id == chosen.candidate_id)

    safeguards: list[str] = []
    action_hash: str | None = None
    if candidate.operation == "archive":
        safeguards = ["dry_run", "backup_manifest", f"{candidate.recovery_days}_day_recovery"]
        if chosen.outcome == "approval_required":
            dry_run_manifest = build_dry_run_manifest(candidate.file_ids, loaded.files)
            backup_manifest = build_backup_manifest(
                candidate.file_ids, loaded.files, candidate.recovery_days
            )
            action_hash = compute_action_hash(
                run_id=run_id,
                operation="simulate_archive",
                file_ids=candidate.file_ids,
                files=loaded.files,
                fixture_digest=loaded.fixture_digest,
                policy_version=loaded.policy.version,
                dry_run_digest=digest_of(dry_run_manifest),
                backup_digest=digest_of(backup_manifest),
                recovery_days=candidate.recovery_days,
            )

    summary_by_outcome = {
        "approval_required": (
            f"Archive simulation is available for candidate '{candidate.id}'. "
            "Human approval is required before any simulated mutation."
        ),
        "safeguard_required": f"Candidate '{candidate.id}' is missing required safeguards.",
        "safe": f"Candidate '{candidate.id}' is a read-only action and needs no further approval.",
        "clarification_required": f"Candidate '{candidate.id}' needs clarification before it can proceed.",
    }

    return FinalDecision(
        outcome=chosen.outcome,
        selected_candidate_id=candidate.id,
        summary=summary_by_outcome[chosen.outcome],
        safeguards=safeguards,
        action_hash=action_hash,
    )


def _event(sequence: int, stage: str, status: str, message: str) -> EventRecord:
    return EventRecord(
        sequence=sequence,
        stage=stage,
        status=status,
        message=message,
        created_at=dt.datetime.now(dt.timezone.utc),
    )


def run_mock_evaluation(run_id: str, task: str, fixture_id: str) -> EvaluationReport:
    """Full mock orchestration: validate, load fixture/policy, produce
    scripted alternatives, run real policy checks, and select a decision."""
    events = [_event(0, "created", "ok", "Run created."), _event(1, "evaluating", "ok", "Loading fixture and policy.")]

    loaded = load_fixture(fixture_id)

    if loaded.policy is None:
        events.append(
            _event(2, "decision_ready", "needs_clarification", "No authoritative policy is loaded.")
        )
        return EvaluationReport(
            run_id=run_id,
            mode="mock",
            status="needs_clarification",
            task=task,
            fixture_id=fixture_id,
            context=[],
            plan=None,
            reviews=[],
            scenarios=[],
            candidate_decisions=[],
            final_decision=FinalDecision(
                outcome="clarification_required",
                selected_candidate_id=None,
                summary="No authoritative retention policy is loaded for this fixture.",
                safeguards=[],
                action_hash=None,
            ),
            events=events,
        )

    context, plan, reviews, scenarios = mock_provider.generate_mock_evaluation(task, loaded)

    context_findings = evaluate_context(context)
    decisions = evaluate_candidates(plan.candidates, files=loaded.files, policy=loaded.policy)
    # Attach context-level findings (e.g. TRUST-001) to every candidate's
    # visible findings list so injection evidence is never hidden.
    if context_findings:
        decisions = [
            d.model_copy(update={"findings": [*context_findings, *d.findings]}) for d in decisions
        ]

    final_decision = select_final_decision(
        run_id=run_id, candidates=plan.candidates, decisions=decisions, loaded=loaded
    )
    status = outcome_to_status(final_decision.outcome)

    events.append(_event(2, "decision_ready", "ok", "Policy checks complete."))
    events.append(_event(3, status, "ok", f"Final decision: {final_decision.outcome}."))

    return EvaluationReport(
        run_id=run_id,
        mode="mock",
        status=status,
        task=task,
        fixture_id=fixture_id,
        context=context,
        plan=plan,
        reviews=reviews,
        scenarios=scenarios,
        candidate_decisions=decisions,
        final_decision=final_decision,
        events=events,
    )
