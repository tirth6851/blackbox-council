"""Strict API and domain contracts for BlackBox Council.

All models forbid unknown fields and validate strictly. CandidateAction is an
advisory proposal that may describe a forbidden operation (e.g. delete) so
the policy report can visibly block it. ExecutableAction is the narrow,
separately-validated shape the executor actually accepts; the two are never
merged into one permissive schema.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Outcome = Literal[
    "safe",
    "safeguard_required",
    "clarification_required",
    "approval_required",
    "blocked",
]

RunStatus = Literal[
    "created",
    "evaluating",
    "decision_ready",
    "awaiting_approval",
    "approved",
    "executing",
    "completed",
    "rejected",
    "needs_clarification",
    "needs_safeguards",
    "blocked",
    "failed",
]

# Explicit state-transition table. Any pair not listed here is rejected.
# Encoded as code (not prose) per plan/01-phase-1-working-demo.md 1.2.
ALLOWED_STATUS_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    "created": frozenset({"evaluating", "failed"}),
    "evaluating": frozenset(
        {
            "decision_ready",
            "needs_clarification",
            "needs_safeguards",
            "blocked",
            "rejected",
            "failed",
        }
    ),
    "decision_ready": frozenset(
        {"awaiting_approval", "needs_clarification", "needs_safeguards", "blocked", "completed"}
    ),
    "awaiting_approval": frozenset({"approved", "rejected", "awaiting_approval"}),
    "approved": frozenset({"executing"}),
    "executing": frozenset({"completed", "failed"}),
    "completed": frozenset(),
    "rejected": frozenset(),
    "needs_clarification": frozenset(),
    "needs_safeguards": frozenset(),
    "blocked": frozenset(),
    "failed": frozenset(),
}

TERMINAL_STATUSES: frozenset[RunStatus] = frozenset(
    {"completed", "rejected", "needs_clarification", "needs_safeguards", "blocked", "failed"}
)


def is_valid_transition(current: RunStatus, target: RunStatus) -> bool:
    """Explicit refusal of transitions from a terminal failure-like state
    directly into executing (or any other state not enumerated above)."""
    return target in ALLOWED_STATUS_TRANSITIONS.get(current, frozenset())


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class EvaluationCreate(StrictModel):
    task: str = Field(min_length=1, max_length=2000)
    fixture_id: Literal["retention-v1"]
    mode: Literal["mock", "live"] = "mock"


class ApprovalRequest(StrictModel):
    action_hash: str = Field(min_length=8, max_length=128)
    decision: Literal["approve", "reject"]
    reason: str = Field(default="", max_length=500)


class ExecuteRequest(StrictModel):
    action_hash: str = Field(min_length=8, max_length=128)


class RollbackRequest(StrictModel):
    execution_id: str = Field(min_length=1, max_length=64)


# ---------------------------------------------------------------------------
# Domain / evidence models
# ---------------------------------------------------------------------------

TrustLevel = Literal[
    "server_policy",
    "server_metadata",
    "repository_trusted",
    "repository_untrusted",
    "model_output",
]


class ContextItem(StrictModel):
    id: str
    source: str
    trust: TrustLevel
    content: str = Field(max_length=4000)
    content_sha256: str = Field(min_length=64, max_length=64)


class FileMetadata(StrictModel):
    id: str
    path: str
    owner_id: str | None = None
    inactive_days: int = Field(ge=0)
    modified_days: int = Field(ge=0)
    legal_hold: bool
    synthetic: Literal[True] = True
    content_sha256: str = Field(min_length=64, max_length=64)
    byte_count: int = Field(ge=0)


class CandidateAction(StrictModel):
    """Advisory proposal. May describe an operation the executor forbids."""

    id: str
    operation: Literal["delete", "archive", "dry_run", "clarify"]
    file_ids: list[str] = Field(default_factory=list, max_length=10)
    dry_run: bool
    backup_manifest: bool
    recovery_days: int = Field(ge=0, le=365)
    rationale: str = Field(max_length=1000)

    @field_validator("file_ids")
    @classmethod
    def _no_duplicate_file_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("file_ids must not contain duplicates")
        return value


class ExecutableAction(StrictModel):
    """Narrow, separately-validated action the executor is allowed to run.

    Only simulate_archive is representable here. A CandidateAction describing
    delete can never validate as an ExecutableAction.
    """

    operation: Literal["simulate_archive"]
    file_ids: list[str] = Field(min_length=1, max_length=10)
    recovery_days: int = Field(ge=30, le=365)
    manifest_digest: str
    policy_version: str

    @field_validator("file_ids")
    @classmethod
    def _no_duplicate_file_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("file_ids must not contain duplicates")
        return value


class Scenario(StrictModel):
    id: str
    candidate_id: str
    kind: Literal["best", "likely_failure", "worst"]
    premise: str = Field(max_length=500)
    outcome: str = Field(max_length=800)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    mitigation: str = Field(max_length=500)


class Plan(StrictModel):
    id: str
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    unanswered_questions: list[str] = Field(default_factory=list, max_length=20)
    candidates: list[CandidateAction] = Field(min_length=1, max_length=4)
    preferred_candidate_id: str | None = None

    @field_validator("preferred_candidate_id")
    @classmethod
    def _preferred_must_exist(cls, value: str | None, info) -> str | None:
        if value is None:
            return value
        candidates = info.data.get("candidates") or []
        ids = {c.id for c in candidates}
        if value not in ids:
            raise ValueError("preferred_candidate_id must reference a supplied candidate")
        return value


ReviewRole = Literal["planner", "red_team", "privacy", "arbiter", "mock"]


class Review(StrictModel):
    role: ReviewRole
    summary: str = Field(max_length=1500)
    concerns: list[str] = Field(default_factory=list, max_length=20)
    suggested_outcome: Outcome
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)


PolicySeverity = Literal["info", "low", "moderate", "high", "critical"]
PolicyEffect = Literal["block", "clarify", "safeguard", "info"]


class PolicyFinding(StrictModel):
    rule_id: str
    candidate_id: str | None = None
    severity: PolicySeverity
    status: Literal["triggered", "clear"]
    effect: PolicyEffect
    evidence: list[str] = Field(default_factory=list, max_length=20)
    explanation: str = Field(max_length=1000)
    remediation: str = Field(max_length=500)


class CandidateDecision(StrictModel):
    candidate_id: str
    outcome: Outcome
    findings: list[PolicyFinding] = Field(default_factory=list)
    prerequisites_missing: list[str] = Field(default_factory=list, max_length=20)


class FinalDecision(StrictModel):
    outcome: Outcome
    selected_candidate_id: str | None = None
    summary: str = Field(max_length=1500)
    safeguards: list[str] = Field(default_factory=list, max_length=20)
    action_hash: str | None = None


class ApprovalRecord(StrictModel):
    action_hash: str
    decision: Literal["approve", "reject"]
    reason: str = Field(default="", max_length=500)
    created_at: dt.datetime
    expires_at: dt.datetime
    consumed_at: dt.datetime | None = None


class ExecutionRecord(StrictModel):
    id: str
    run_id: str
    action_hash: str
    status: Literal["completed", "failed", "rolled_back"]
    simulated: Literal[True] = True
    before_digest: str
    after_digest: str
    archived_file_ids: list[str] = Field(default_factory=list, max_length=10)
    rollback_record_id: str | None = None


class EventRecord(StrictModel):
    sequence: int = Field(ge=0)
    stage: str
    status: str
    message: str = Field(max_length=1000)
    created_at: dt.datetime


class EvaluationReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    mode: Literal["mock", "live"]
    status: RunStatus
    task: str
    fixture_id: str
    context: list[ContextItem] = Field(default_factory=list)
    plan: Plan | None = None
    reviews: list[Review] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)
    candidate_decisions: list[CandidateDecision] = Field(default_factory=list)
    final_decision: FinalDecision | None = None
    events: list[EventRecord] = Field(default_factory=list)
    approval: ApprovalRecord | None = None
    execution: ExecutionRecord | None = None
    # Forward-compatible bag for Phase 2 data (risk ratings, counterfactual
    # summary, per-call metadata) that doesn't need its own strict contract
    # yet. Never used to smuggle anything past policy_engine/decision_service
    # — final_decision above is always the enforced outcome.
    extensions: dict[str, object] | None = None


class ErrorBody(StrictModel):
    code: str
    message: str


class ErrorEnvelope(StrictModel):
    error: ErrorBody
