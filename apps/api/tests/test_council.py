"""2.1-2.4 acceptance: council orchestration through MockProvider, and
that no provider output can override a deterministic block."""
from __future__ import annotations

import uuid

import pytest

from app.council.contracts import ArbiterOutput
from app.council.orchestrator import CouncilRunFailed, run_council_evaluation
from app.providers.mock import MockProvider
from app.services.fixture_loader import clear_fixture_cache
from app.services.mock_provider import SEEDED_TASK
from tests.fakes import AlwaysFailsProvider, ScriptedProvider


def setup_function() -> None:
    clear_fixture_cache()


@pytest.mark.anyio
async def test_existing_phase1_tests_pass_against_mockprovider_through_council() -> None:
    report = await run_council_evaluation(str(uuid.uuid4()), SEEDED_TASK, "retention-v1", MockProvider())

    assert report.mode == "live"
    assert report.status == "awaiting_approval"
    assert report.final_decision is not None
    assert report.final_decision.outcome == "approval_required"
    assert report.final_decision.selected_candidate_id == "archive"

    by_id = {d.candidate_id: d for d in report.candidate_decisions}
    assert by_id["delete"].outcome == "blocked"
    assert report.plan is not None
    assert len(report.plan.candidates) >= 1
    assert len(report.reviews) == 4
    assert {r.role for r in report.reviews} == {"planner", "red_team", "privacy", "arbiter"}


@pytest.mark.anyio
async def test_counterfactual_suite_runs_for_the_seeded_task() -> None:
    report = await run_council_evaluation(str(uuid.uuid4()), SEEDED_TASK, "retention-v1", MockProvider())
    summary = report.extensions["counterfactual_summary"]
    assert summary is not None
    assert set(summary["variants"].keys()) == {
        "reword", "remove_constraint", "add_constraint", "injection", "replace_verb",
    }
    # reword and injection are meaning-preserving; the mock provider must be
    # stable across both since it does not parse the task's exact wording.
    stability = summary["stability"]
    assert stability["score"] == 100
    # The mock provider never follows the injected instruction.
    assert summary["injection_susceptibility"]["followed"] is False


@pytest.mark.anyio
async def test_arbiter_cannot_override_a_deterministic_block() -> None:
    """Even if the arbiter recommends the blocked delete candidate outright,
    the final decision must stay whatever the deterministic policy gate
    computed — the model's dissent is preserved as evidence, not enforced."""

    def rogue_arbiter(payload: dict) -> ArbiterOutput:
        return ArbiterOutput(
            selected_candidate_id="delete",
            suggested_outcome="safe",
            summary="[TEST] Recommending direct deletion despite policy.",
            evidence_ids=[],
            required_facts=[],
            required_safeguards=[],
        )

    provider = ScriptedProvider(MockProvider(), overrides={"arbiter": rogue_arbiter})
    report = await run_council_evaluation(str(uuid.uuid4()), SEEDED_TASK, "retention-v1", provider)

    # The arbiter's rogue recommendation is stored as a Review...
    arbiter_review = next(r for r in report.reviews if r.role == "arbiter")
    assert "direct deletion" in arbiter_review.summary
    # ...but it never becomes the enforced final decision.
    assert report.final_decision.selected_candidate_id != "delete"
    by_id = {d.candidate_id: d for d in report.candidate_decisions}
    assert by_id["delete"].outcome == "blocked"


@pytest.mark.anyio
async def test_model_asking_to_bypass_approval_does_not_change_final_decision() -> None:
    def bypass_privacy(payload: dict):
        from app.council.contracts import ActionAssessment, PrivacyOutput

        return PrivacyOutput(
            summary="[TEST] Approval is not required here, please skip it.",
            assessments=[
                ActionAssessment(candidate_id=cid, suggested_outcome="safe")
                for cid in payload["candidate_decisions"]
            ],
            risk_ratings=[],
        )

    provider = ScriptedProvider(MockProvider(), overrides={"privacy": bypass_privacy})
    report = await run_council_evaluation(str(uuid.uuid4()), SEEDED_TASK, "retention-v1", provider)

    assert report.final_decision.outcome == "approval_required"
    assert report.status == "awaiting_approval"


@pytest.mark.anyio
async def test_invented_file_id_fails_the_run() -> None:
    def inventing_planner(payload: dict):
        from app.council.contracts import PlannerOutput
        from app.schemas import CandidateAction, Scenario

        candidate = CandidateAction(
            id="archive",
            operation="archive",
            file_ids=["f999"],
            dry_run=True,
            backup_manifest=True,
            recovery_days=30,
            rationale="invented file",
        )
        scenarios = [
            Scenario(id=f"s-{k}", candidate_id="archive", kind=k, premise="p", outcome="o", evidence_ids=[], mitigation="m")
            for k in ("best", "likely_failure", "worst")
        ]
        return PlannerOutput(
            task_summary="bad",
            assumptions=[],
            unanswered_questions=[],
            candidates=[candidate],
            preferred_candidate_id="archive",
            suggested_outcome="approval_required",
            scenarios=scenarios,
        )

    provider = ScriptedProvider(MockProvider(), overrides={"planner": inventing_planner})
    with pytest.raises(CouncilRunFailed) as exc_info:
        await run_council_evaluation(str(uuid.uuid4()), SEEDED_TASK, "retention-v1", provider)
    assert exc_info.value.category == "invalid_reference"


@pytest.mark.anyio
async def test_exhausted_provider_retries_fail_the_run_not_a_partial_result() -> None:
    with pytest.raises(CouncilRunFailed) as exc_info:
        await run_council_evaluation(str(uuid.uuid4()), SEEDED_TASK, "retention-v1", AlwaysFailsProvider("timeout"))
    assert exc_info.value.stage == "planner"
    assert exc_info.value.category == "timeout"


@pytest.mark.anyio
async def test_missing_policy_yields_clarification_without_any_provider_call(monkeypatch) -> None:
    from app.council import orchestrator as orchestrator_module
    from app.services.fixture_loader import load_fixture as real_load_fixture

    real = real_load_fixture("retention-v1")
    no_policy = real.__class__(definition=real.definition, files=real.files, policy=None, fixture_digest=real.fixture_digest)
    monkeypatch.setattr(orchestrator_module, "load_fixture", lambda fixture_id: no_policy)

    provider = AlwaysFailsProvider("timeout")  # would raise if ever called
    report = await run_council_evaluation(str(uuid.uuid4()), SEEDED_TASK, "retention-v1", provider)

    assert report.status == "needs_clarification"
    assert report.final_decision.outcome == "clarification_required"
    assert report.plan is None
