"""Council orchestration: Planner -> deterministic candidate checks ->
Red-team -> Privacy -> counterfactual Planner probes -> Arbiter -> final
deterministic reconciliation (plan/02-phase-2-live-council.md 2.4).

This module never rewrites or weakens app.services.policy_engine /
decision_service — it only supplies them with model-proposed candidates
instead of scripted ones. The final decision is always computed by
decision_service.select_final_decision from real policy findings, never
by trusting any provider's own suggested_outcome.
"""
from __future__ import annotations

import datetime as dt
from typing import Awaitable, Callable

from app.council.contracts import ArbiterOutput, PlannerOutput, PrivacyOutput, RedTeamOutput
from app.council.context import build_system_prompt
from app.counterfactuals.runner import run_all_variants
from app.counterfactuals.scoring import (
    VariantResult,
    combine_risk_ratings,
    compute_injection_susceptibility,
    compute_risk_ratings,
    compute_stability,
    compute_transparent_risk_score,
)
from app.counterfactuals.variants import STABILITY_VARIANT_IDS
from app.providers.base import ModelOutputError, Provider
from app.schemas import EvaluationReport, EventRecord, Plan, Review
from app.services import decision_service
from app.services.context_builder import build_context_items, build_files_payload, build_policy_payload
from app.services.fixture_loader import load_fixture
from app.services.mock_provider import SEEDED_TASK
from app.services.policy_engine import evaluate_context

PROMPT_VERSION = "v1"


class CouncilRunFailed(Exception):
    """Raised when a required council pass cannot produce a validated
    output after retries. No partial recommendation is ever treated as
    safe when this is raised — the caller must mark the run failed."""

    def __init__(self, stage: str, category: str, message: str) -> None:
        self.stage = stage
        self.category = category
        super().__init__(f"{stage}: {category}: {message}")


def _event(sequence: int, stage: str, status: str, message: str) -> EventRecord:
    return EventRecord(sequence=sequence, stage=stage, status=status, message=message, created_at=dt.datetime.now(dt.timezone.utc))


def _validate_known_file_ids(candidates, known_ids: set[str], stage: str) -> None:
    unknown = sorted({fid for c in candidates for fid in c.file_ids if fid not in known_ids})
    if unknown:
        raise CouncilRunFailed(stage, "invalid_reference", f"unknown file ids: {unknown}")


async def run_council_evaluation(
    run_id: str,
    task: str,
    fixture_id: str,
    provider: Provider,
    *,
    include_counterfactuals: bool = True,
    on_stage: Callable[[str, str, str], Awaitable[None]] | None = None,
) -> EvaluationReport:
    """on_stage, when given, is awaited after every event below is recorded
    locally — the live-run worker uses it to persist progress incrementally
    so GET can show partial results while this coroutine is still running
    (plan 2.6). The returned report is always self-contained regardless."""
    events: list[EventRecord] = []

    async def record(stage: str, status: str, message: str) -> None:
        events.append(_event(len(events), stage, status, message))
        if on_stage is not None:
            await on_stage(stage, status, message)

    await record("created", "ok", "Run created.")
    await record("evaluating", "ok", "Loading fixture and policy.")

    loaded = load_fixture(fixture_id)
    if loaded.policy is None:
        return decision_service.missing_policy_report(run_id, "live", task, fixture_id, events)

    # The main run's context is clean (no injection doc): with the 9-call
    # budget (4 base passes + 5 counterfactual probes, plan 2.4/2.5), this
    # Planner call also serves as the counterfactual baseline, and the
    # single injection sample lives only in its own dedicated probe below.
    context = build_context_items(loaded, include_injection_doc=False)
    files_payload = build_files_payload(loaded)
    policy_payload = build_policy_payload(loaded)
    known_ids = set(loaded.files.keys())

    # --- Planner ---------------------------------------------------------
    try:
        planner_result = await provider.generate(
            role="planner",
            system_prompt=build_system_prompt("planner"),
            input_payload={
                "task": task,
                "files": files_payload,
                "policy": policy_payload,
                "context": [c.model_dump(mode="json") for c in context],
            },
            output_model=PlannerOutput,
            prompt_version=PROMPT_VERSION,
        )
    except ModelOutputError as exc:
        raise CouncilRunFailed("planner", exc.category, str(exc)) from exc
    planner_output = planner_result.output
    if planner_output is None:
        raise CouncilRunFailed("planner", "empty_output", "provider returned no planner output")
    _validate_known_file_ids(planner_output.candidates, known_ids, "planner")
    await record("planner", "ok", f"Planner proposed {len(planner_output.candidates)} candidate(s).")

    # --- Deterministic candidate checks (never weakened by any pass) -----
    context_findings = evaluate_context(context)
    decisions = decision_service.evaluate_candidates(planner_output.candidates, files=loaded.files, policy=loaded.policy)
    if context_findings:
        decisions = [d.model_copy(update={"findings": [*context_findings, *d.findings]}) for d in decisions]
    candidate_decisions_payload = {
        d.candidate_id: {"outcome": d.outcome, "findings": [f.model_dump(mode="json") for f in d.findings]}
        for d in decisions
    }
    await record("decision_ready", "ok", "Deterministic policy checks complete.")

    # --- Red-team ----------------------------------------------------------
    try:
        red_team_result = await provider.generate(
            role="red_team",
            system_prompt=build_system_prompt("red_team"),
            input_payload={
                "task": task,
                "candidate_decisions": candidate_decisions_payload,
                "context": [c.model_dump(mode="json") for c in context],
            },
            output_model=RedTeamOutput,
            prompt_version=PROMPT_VERSION,
        )
    except ModelOutputError as exc:
        raise CouncilRunFailed("red_team", exc.category, str(exc)) from exc
    red_team_output = red_team_result.output
    if red_team_output is None:
        raise CouncilRunFailed("red_team", "empty_output", "provider returned no red_team output")
    _assert_assessments_known(red_team_output.assessments, set(candidate_decisions_payload), "red_team")
    await record("red_team", "ok", "Red-team review complete.")

    # --- Privacy -----------------------------------------------------------
    try:
        privacy_result = await provider.generate(
            role="privacy",
            system_prompt=build_system_prompt("privacy"),
            input_payload={
                "task": task,
                "candidate_decisions": candidate_decisions_payload,
                "planner_candidates": [c.model_dump(mode="json") for c in planner_output.candidates],
                "preferred_candidate_id": planner_output.preferred_candidate_id,
                "policy": policy_payload,
            },
            output_model=PrivacyOutput,
            prompt_version=PROMPT_VERSION,
        )
    except ModelOutputError as exc:
        raise CouncilRunFailed("privacy", exc.category, str(exc)) from exc
    privacy_output = privacy_result.output
    if privacy_output is None:
        raise CouncilRunFailed("privacy", "empty_output", "provider returned no privacy output")
    _assert_assessments_known(privacy_output.assessments, set(candidate_decisions_payload), "privacy")
    await record("privacy", "ok", "Privacy review complete.")

    # --- Counterfactual probes (Planner reused; five sequential calls) -----
    counterfactual_summary: dict | None = None
    # The five variants are fixed perturbations of the one seeded retention
    # scenario (plan/README.md: one synthetic use case only); running them
    # against a differently-worded live task would compare unrelated
    # scenarios, so they only run when the live task matches exactly.
    if include_counterfactuals and task == SEEDED_TASK:
        variant_results = await run_all_variants(loaded, provider, build_system_prompt("planner"))
        baseline = _synthesize_baseline_result(task, planner_output, decisions)
        stability = compute_stability(variant_results, baseline, STABILITY_VARIANT_IDS)
        injection = compute_injection_susceptibility(variant_results["injection"], baseline)
        counterfactual_summary = {
            "stability": stability,
            "injection_susceptibility": injection,
            "variants": {
                vid: {
                    "changed_dimension": r.changed_dimension,
                    "status": r.status,
                    "proposed_operation": r.proposed_operation,
                    "proposed_file_ids": r.proposed_file_ids,
                    "model_suggested_outcome": r.model_suggested_outcome,
                    "effective_outcome": r.effective_outcome,
                    "error_category": r.error_category,
                }
                for vid, r in variant_results.items()
            },
        }
        await record("counterfactuals", "ok", "Five controlled perturbations complete.")

    # --- Arbiter -------------------------------------------------------------
    allowed_ids = [d.candidate_id for d in decisions if d.outcome != "blocked"]
    try:
        arbiter_result = await provider.generate(
            role="arbiter",
            system_prompt=build_system_prompt("arbiter"),
            input_payload={
                "candidate_decisions": candidate_decisions_payload,
                "allowed_candidate_ids": allowed_ids,
                "preferred_candidate_id": planner_output.preferred_candidate_id,
                "unanswered_questions": planner_output.unanswered_questions,
            },
            output_model=ArbiterOutput,
            prompt_version=PROMPT_VERSION,
        )
    except ModelOutputError as exc:
        raise CouncilRunFailed("arbiter", exc.category, str(exc)) from exc
    arbiter_output = arbiter_result.output
    if arbiter_output is None:
        raise CouncilRunFailed("arbiter", "empty_output", "provider returned no arbiter output")
    await record("arbiter", "ok", "Arbiter synthesis complete.")

    # --- Final deterministic reconciliation ---------------------------------
    # The arbiter's selection/outcome is evidence only. If it disagrees with
    # (or tries to override) a deterministic block, that disagreement is
    # preserved in the stored Review below, but it never changes what
    # actually gets selected or executed.
    final_decision = decision_service.select_final_decision(
        run_id=run_id, candidates=planner_output.candidates, decisions=decisions, loaded=loaded
    )
    status = decision_service.outcome_to_status(final_decision.outcome)
    await record(status, "ok", f"Final decision: {final_decision.outcome}.")

    plan = Plan(
        id=f"plan-{run_id}",
        assumptions=planner_output.assumptions,
        unanswered_questions=planner_output.unanswered_questions,
        candidates=planner_output.candidates,
        preferred_candidate_id=planner_output.preferred_candidate_id,
    )

    reviews = [
        Review(
            role="planner",
            summary=planner_output.task_summary,
            concerns=planner_output.unanswered_questions,
            suggested_outcome=planner_output.suggested_outcome,
            evidence_ids=[],
        ),
        Review(
            role="red_team",
            summary=red_team_output.summary,
            concerns=[c.explanation for a in red_team_output.assessments for c in a.concerns][:20],
            suggested_outcome=_pick_assessment_outcome(red_team_output.assessments, planner_output.preferred_candidate_id),
            evidence_ids=red_team_output.injection_evidence_ids,
        ),
        Review(
            role="privacy",
            summary=privacy_output.summary,
            concerns=[c.explanation for a in privacy_output.assessments for c in a.concerns][:20],
            suggested_outcome=_pick_assessment_outcome(privacy_output.assessments, planner_output.preferred_candidate_id),
            evidence_ids=[],
        ),
        Review(
            role="arbiter",
            summary=arbiter_output.summary,
            concerns=[*arbiter_output.required_facts, *arbiter_output.required_safeguards][:20],
            suggested_outcome=arbiter_output.suggested_outcome,
            evidence_ids=arbiter_output.evidence_ids,
        ),
    ]

    # Never display a risk score computed only from what a model reported —
    # a manipulated or simply mistaken reviewer could self-report an
    # artificially low rating. The rule-derived rating is a floor: for each
    # dimension, use whichever of the deterministic and model-reported
    # value is higher (more conservative), never the model's value alone.
    preferred_id = planner_output.preferred_candidate_id or planner_output.candidates[0].id
    preferred_candidate = next(c for c in planner_output.candidates if c.id == preferred_id)
    preferred_decision = next((d for d in decisions if d.candidate_id == preferred_id), None)
    deterministic_ratings = compute_risk_ratings(
        preferred_candidate, preferred_decision.findings if preferred_decision else [], loaded.policy
    )
    combined_ratings = combine_risk_ratings(deterministic_ratings, privacy_output.risk_ratings)
    risk_score = compute_transparent_risk_score(combined_ratings)
    extensions = {
        "risk_ratings": [r.model_dump(mode="json") for r in combined_ratings],
        "deterministic_risk_ratings": [r.model_dump(mode="json") for r in deterministic_ratings],
        "model_risk_ratings": [r.model_dump(mode="json") for r in privacy_output.risk_ratings],
        "transparent_risk_score": risk_score,
        "arbiter_raw_selection": arbiter_output.model_dump(mode="json"),
        "counterfactual_summary": counterfactual_summary,
    }

    return EvaluationReport(
        run_id=run_id,
        mode="live",
        status=status,
        task=task,
        fixture_id=fixture_id,
        context=context,
        plan=plan,
        reviews=reviews,
        scenarios=planner_output.scenarios,
        candidate_decisions=decisions,
        final_decision=final_decision,
        events=events,
        extensions=extensions,
    )


def _assert_assessments_known(assessments, known_ids: set[str], stage: str) -> None:
    unknown = sorted({a.candidate_id for a in assessments if a.candidate_id not in known_ids})
    if unknown:
        raise CouncilRunFailed(stage, "invalid_reference", f"assessment references unknown candidate ids: {unknown}")


def _pick_assessment_outcome(assessments, preferred_candidate_id: str | None):
    if preferred_candidate_id:
        match = next((a for a in assessments if a.candidate_id == preferred_candidate_id), None)
        if match:
            return match.suggested_outcome
    return assessments[0].suggested_outcome if assessments else "clarification_required"


def _synthesize_baseline_result(task: str, planner_output: PlannerOutput, decisions) -> VariantResult:
    """The main run's own (clean, injection-free) Planner call doubles as
    the counterfactual baseline — this keeps the whole council + probe
    suite inside the plan's nine-logical-call budget instead of spending a
    tenth call re-deriving what the main run already computed."""
    preferred_id = planner_output.preferred_candidate_id or planner_output.candidates[0].id
    preferred = next(c for c in planner_output.candidates if c.id == preferred_id)
    decision = next((d for d in decisions if d.candidate_id == preferred_id), None)
    return VariantResult(
        id="baseline",
        task=task,
        changed_dimension="none (clean baseline)",
        input_digest="",
        context_ids=[],
        proposed_operation=preferred.operation,
        proposed_file_ids=sorted(preferred.file_ids),
        preferred_candidate_id=preferred_id,
        model_suggested_outcome=planner_output.suggested_outcome,
        effective_outcome=decision.outcome if decision else None,
        checks_failed=decision.prerequisites_missing if decision else [],
        status="completed",
    )
