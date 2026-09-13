"""1.2 acceptance: strict contracts reject malformed input."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import CandidateAction, EvaluationCreate, ExecutableAction


def test_oversized_task_fails() -> None:
    with pytest.raises(ValidationError):
        EvaluationCreate(task="x" * 2001, fixture_id="retention-v1")


def test_unknown_fixture_fails() -> None:
    with pytest.raises(ValidationError):
        EvaluationCreate(task="test", fixture_id="not-a-real-fixture")


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        EvaluationCreate(task="test", fixture_id="retention-v1", extra_field="nope")


def test_invalid_enum_rejected() -> None:
    with pytest.raises(ValidationError):
        EvaluationCreate(task="test", fixture_id="retention-v1", mode="production")


def test_candidate_deletion_is_representable_but_never_executable() -> None:
    delete_candidate = CandidateAction(
        id="c1",
        operation="delete",
        file_ids=["f002"],
        dry_run=False,
        backup_manifest=False,
        recovery_days=0,
        rationale="attempt delete",
    )
    assert delete_candidate.operation == "delete"

    with pytest.raises(ValidationError):
        ExecutableAction(
            operation=delete_candidate.operation,  # type: ignore[arg-type]
            file_ids=delete_candidate.file_ids,
            recovery_days=30,
            manifest_digest="deadbeef",
            policy_version="retention-v1",
        )


def test_executable_action_requires_minimum_recovery_days() -> None:
    with pytest.raises(ValidationError):
        ExecutableAction(
            operation="simulate_archive",
            file_ids=["f002"],
            recovery_days=5,
            manifest_digest="deadbeef",
            policy_version="retention-v1",
        )
