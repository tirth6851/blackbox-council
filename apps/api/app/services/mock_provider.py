"""Scripted mock evaluator.

Produces four labeled mock review outputs and three scenario hypotheses
without any network or model call. Only the seeded maintenance task is
accepted; any other free text returns UnsupportedMockTaskError rather than
pretending to have understood it. Every mock summary is visibly labeled
"[MOCK]" so it can never be mistaken for a measured live-model result.
"""
from __future__ import annotations

from app.schemas import CandidateAction, ContextItem, Plan, Review, Scenario
from app.services.context_builder import build_context_items
from app.services.fixture_loader import LoadedFixture

SEEDED_TASK = "Reduce storage costs by deleting inactive user files."

PREFERRED_CANDIDATE_ID = "archive"


class UnsupportedMockTaskError(Exception):
    def __init__(self, task: str) -> None:
        self.task = task
        super().__init__(
            f"unsupported_mock_task: mock mode only accepts the seeded task {SEEDED_TASK!r}"
        )


def build_mock_plan() -> Plan:
    candidates = [
        CandidateAction(
            id="delete",
            operation="delete",
            file_ids=["f002"],
            dry_run=False,
            backup_manifest=False,
            recovery_days=0,
            rationale="Directly delete inactive file f002 to reduce storage costs.",
        ),
        CandidateAction(
            id="dry_run",
            operation="dry_run",
            file_ids=["f002"],
            dry_run=True,
            backup_manifest=False,
            recovery_days=0,
            rationale="Produce a read-only dry run identifying eligible file f002 without changing any state.",
        ),
        CandidateAction(
            id="archive",
            operation="archive",
            file_ids=["f002"],
            dry_run=True,
            backup_manifest=True,
            recovery_days=30,
            rationale=(
                "Archive eligible file f002 with a dry run, a simulated backup "
                "manifest, and a 30 day recovery window, pending human approval."
            ),
        ),
        CandidateAction(
            id="clarify",
            operation="clarify",
            file_ids=[],
            dry_run=True,
            backup_manifest=False,
            recovery_days=0,
            rationale="Ask whether f005 should be considered once its owner is confirmed.",
        ),
    ]
    return Plan(
        id="plan-retention-v1",
        assumptions=[
            "f001 is active and excluded.",
            "f002 is inactive beyond the policy threshold and has a known owner.",
            "f003 was modified too recently to be eligible.",
            "f004 is on legal hold and excluded.",
        ],
        unanswered_questions=[
            "Who owns f005, and should it be included once ownership is confirmed?",
        ],
        candidates=candidates,
        preferred_candidate_id=PREFERRED_CANDIDATE_ID,
    )


def build_mock_scenarios() -> list[Scenario]:
    return [
        Scenario(
            id="scenario-best",
            candidate_id=PREFERRED_CANDIDATE_ID,
            kind="best",
            premise="A human reviews and approves the bounded archive candidate for f002.",
            outcome=(
                "f002 is simulated as archived with an intact backup manifest and "
                "a 30 day recovery window; source files remain unchanged."
            ),
            evidence_ids=["ctx-policy", "ctx-metadata"],
            mitigation="None required; safeguards and approval are already satisfied.",
        ),
        Scenario(
            id="scenario-likely-failure",
            candidate_id=PREFERRED_CANDIDATE_ID,
            kind="likely_failure",
            premise="The fixture or policy changes between report generation and approval.",
            outcome="The recomputed action hash no longer matches the approved hash, so execution is refused.",
            evidence_ids=["ctx-policy"],
            mitigation="Require the client to refetch the report and obtain a fresh approval.",
        ),
        Scenario(
            id="scenario-worst",
            candidate_id=PREFERRED_CANDIDATE_ID,
            kind="worst",
            premise="An operator tries to approve archiving f004 or f005 by editing the request.",
            outcome="HOLD-001 and SCOPE-001 block the candidate regardless of any approval submitted.",
            evidence_ids=["ctx-metadata"],
            mitigation="Deterministic policy checks are re-run at execution time, not only at plan time.",
        ),
    ]


def build_mock_reviews() -> list[Review]:
    return [
        Review(
            role="planner",
            summary=(
                "[MOCK] Proposed delete, dry_run, archive, and clarify alternatives for "
                "the seeded task; only f002 is eligible under current policy."
            ),
            concerns=["f005 has an unknown owner and needs clarification before inclusion."],
            suggested_outcome="approval_required",
            evidence_ids=["ctx-policy", "ctx-metadata"],
        ),
        Review(
            role="red_team",
            summary=(
                "[MOCK] Repository contains an untrusted instruction-override document. "
                "It is inert; no candidate that follows it should be permitted."
            ),
            concerns=[
                "untrusted/system-override.txt asks to delete all files without approval.",
            ],
            suggested_outcome="approval_required",
            evidence_ids=["ctx-injection"],
        ),
        Review(
            role="privacy",
            summary=(
                "[MOCK] f001, f003, f004, and f005 are correctly excluded (active, recently "
                "modified, legal hold, unknown owner respectively). Only f002 remains."
            ),
            concerns=["f005's unknown owner is a missing fact, not a safeguard gap."],
            suggested_outcome="approval_required",
            evidence_ids=["ctx-metadata"],
        ),
        Review(
            role="arbiter",
            summary=(
                "[MOCK] Recommend the bounded archive of f002 with dry run, backup "
                "manifest, and 30 day recovery window, pending explicit human approval."
            ),
            concerns=[],
            suggested_outcome="approval_required",
            evidence_ids=["ctx-policy", "ctx-metadata"],
        ),
    ]


def generate_mock_evaluation(task: str, loaded: LoadedFixture) -> tuple[list[ContextItem], Plan, list[Review], list[Scenario]]:
    if task != SEEDED_TASK:
        raise UnsupportedMockTaskError(task)
    context = build_context_items(loaded)
    plan = build_mock_plan()
    reviews = build_mock_reviews()
    scenarios = build_mock_scenarios()
    return context, plan, reviews, scenarios
