"""Council output contracts (plan/02-phase-2-live-council.md 2.3).

All inherit StrictModel: extra="forbid", bounded strings/arrays, literal
enums. A model may suggest an outcome or a preferred candidate; only
app.services.policy_engine / decision_service decide what is actually
enforced.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas import CandidateAction, Outcome, Scenario, StrictModel

ConcernCategory = Literal[
    "injection", "scope_expansion", "secret_access", "external_transfer",
    "control_bypass", "privacy", "ownership", "other",
]
Severity = Literal["low", "moderate", "high", "critical"]
RiskDimension = Literal["impact", "irreversibility", "uncertainty", "blast_radius", "policy"]


class Concern(StrictModel):
    id: str
    candidate_id: str | None = None
    category: ConcernCategory
    severity: Severity
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    explanation: str = Field(max_length=800)
    remediation: str = Field(max_length=500)


class ActionAssessment(StrictModel):
    candidate_id: str
    suggested_outcome: Outcome
    concerns: list[Concern] = Field(default_factory=list, max_length=20)
    required_facts: list[str] = Field(default_factory=list, max_length=20)
    required_safeguards: list[str] = Field(default_factory=list, max_length=20)


class RiskRating(StrictModel):
    dimension: RiskDimension
    value: int = Field(ge=0, le=4)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    explanation: str = Field(max_length=300)


def _assert_unique_candidate_ids(candidates: list[CandidateAction]) -> None:
    ids = [c.id for c in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("candidate ids must be unique")


def _assert_known_candidate(candidate_id: str | None, known_ids: set[str], field_name: str) -> None:
    if candidate_id is not None and candidate_id not in known_ids:
        raise ValueError(f"{field_name} references unknown candidate_id {candidate_id!r}")


class PlannerOutput(StrictModel):
    task_summary: str = Field(max_length=1000)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    unanswered_questions: list[str] = Field(default_factory=list, max_length=20)
    candidates: list[CandidateAction] = Field(min_length=1, max_length=4)
    preferred_candidate_id: str | None = None
    suggested_outcome: Outcome
    scenarios: list[Scenario] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def _validate_cross_references(self) -> "PlannerOutput":
        _assert_unique_candidate_ids(self.candidates)
        known_ids = {c.id for c in self.candidates}
        _assert_known_candidate(self.preferred_candidate_id, known_ids, "preferred_candidate_id")

        kinds = [s.kind for s in self.scenarios]
        if sorted(kinds) != ["best", "likely_failure", "worst"]:
            raise ValueError("scenarios must contain exactly one best, likely_failure, and worst")

        anchor_id = self.preferred_candidate_id or self.candidates[0].id
        for scenario in self.scenarios:
            if scenario.candidate_id != anchor_id:
                raise ValueError(
                    f"scenario {scenario.id!r} must reference the preferred (or first) "
                    f"candidate {anchor_id!r}, got {scenario.candidate_id!r}"
                )
        return self


class RedTeamOutput(StrictModel):
    role: Literal["red_team"] = "red_team"
    summary: str = Field(max_length=1500)
    assessments: list[ActionAssessment] = Field(min_length=1, max_length=4)
    injection_evidence_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _no_duplicate_assessments(self) -> "RedTeamOutput":
        ids = [a.candidate_id for a in self.assessments]
        if len(ids) != len(set(ids)):
            raise ValueError("assessments must reference each candidate at most once")
        return self


class PrivacyOutput(StrictModel):
    role: Literal["privacy"] = "privacy"
    summary: str = Field(max_length=1500)
    assessments: list[ActionAssessment] = Field(min_length=1, max_length=4)
    risk_ratings: list[RiskRating] = Field(default_factory=list, max_length=5)

    @field_validator("risk_ratings")
    @classmethod
    def _no_duplicate_dimensions(cls, value: list[RiskRating]) -> list[RiskRating]:
        dims = [r.dimension for r in value]
        if len(dims) != len(set(dims)):
            raise ValueError("risk_ratings must not repeat a dimension")
        return value


class ArbiterOutput(StrictModel):
    role: Literal["arbiter"] = "arbiter"
    selected_candidate_id: str | None = None
    suggested_outcome: Outcome
    summary: str = Field(max_length=1500)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    required_facts: list[str] = Field(default_factory=list, max_length=20)
    required_safeguards: list[str] = Field(default_factory=list, max_length=20)


def validate_assessments_reference_known_candidates(
    assessments: list[ActionAssessment], known_ids: set[str]
) -> None:
    """A model cannot invent a candidate: every assessment/concern must
    reference a candidate the Planner actually proposed."""
    for assessment in assessments:
        if assessment.candidate_id not in known_ids:
            raise ValueError(f"assessment references unknown candidate_id {assessment.candidate_id!r}")
        for concern in assessment.concerns:
            _assert_known_candidate(concern.candidate_id, known_ids, "concern.candidate_id")
