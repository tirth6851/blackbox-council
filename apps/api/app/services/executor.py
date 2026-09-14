"""Bind approval to an exact manifest and perform the simulated execution.

Nothing here moves, renames, truncates, or deletes fixture uploads. A
"backup" is a backup manifest plus previous synthetic state, never a real
production backup, and the UI must call this a simulation.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError
from app.models.orm import ExecutionORM, SimulationStateORM
from app.schemas import ExecutableAction, ExecutionRecord
from app.services import run_repository
from app.services.decision_service import classify_candidate
from app.services.fixture_loader import FixtureError, hash_source_files, load_fixture_fresh
from app.services.hashing import compute_action_hash
from app.services.manifests import build_backup_manifest, build_dry_run_manifest, build_scope_manifest, digest_of
from app.services.policy_engine import evaluate_candidate


def _prior_archived_ids(session: Session, run_id: str) -> list[str]:
    state = run_repository.get_simulation_state(session, run_id)
    if state is None:
        return []
    return sorted(json.loads(state.simulated_archive_json).get("archived_file_ids", []))


def execute_action(session: Session, run_id: str, action_hash: str) -> ExecutionRecord:
    row = run_repository.get_run_row(session, run_id)
    if row is None:
        raise NotFoundError(f"unknown run: {run_id}", code="run_not_found")

    existing = run_repository.get_execution_by_hash(session, run_id, action_hash)
    if existing is not None and existing.status in ("completed", "rolled_back"):
        return run_repository.execution_to_record(existing)

    if row.status != "approved":
        raise ConflictError(
            f"run is not approved for execution (current status: {row.status})",
            code="not_authorized",
        )

    report = run_repository.load_report(session, row)
    if report.plan is None or report.final_decision is None or report.final_decision.selected_candidate_id is None:
        raise ConflictError("run has no executable decision", code="not_authorized")

    try:
        # Uncached, current-on-disk read (carryover C01). load_fixture()
        # (cached) would let this compare a stale snapshot against itself
        # and always "pass" even when the fixture or policy changed on disk
        # after evaluation/approval — the cache is never invalidated by an
        # external edit, so nothing short of a fresh read can catch that.
        loaded = load_fixture_fresh(report.fixture_id)
    except FixtureError as exc:
        raise ConflictError(f"fixture changed or unreadable: {exc}", code="fixture_changed") from exc

    if loaded.policy is None:
        raise ConflictError("policy is no longer loaded", code="policy_changed")
    if loaded.fixture_digest != row.fixture_digest:
        raise ConflictError("fixture contents changed since evaluation", code="fixture_changed")
    if loaded.policy.version != row.policy_version:
        raise ConflictError("policy changed since evaluation", code="policy_changed")
    if (loaded.policy_digest or "") != row.policy_digest:
        # Catches a policy edited in place without bumping its version
        # string, which the version-only check above would miss.
        raise ConflictError("policy changed since evaluation", code="policy_changed")

    candidate = next(
        (c for c in report.plan.candidates if c.id == report.final_decision.selected_candidate_id),
        None,
    )
    if candidate is None:
        raise ConflictError("selected candidate no longer exists", code="not_authorized")
    if candidate.operation != "archive":
        # EXEC-001: operation absent from the executable allowlist.
        raise ConflictError(
            "only an archive candidate can be mapped to simulate_archive", code="exec_not_allowed"
        )

    findings = evaluate_candidate(candidate, files=loaded.files, policy=loaded.policy)
    fresh_outcome, _ = classify_candidate(candidate, findings)
    if fresh_outcome != "approval_required":
        raise ConflictError(
            f"policy no longer permits execution (current outcome: {fresh_outcome})",
            code="policy_blocks_execution",
        )

    dry_run_manifest = build_dry_run_manifest(candidate.file_ids, loaded.files)
    backup_manifest = build_backup_manifest(candidate.file_ids, loaded.files, candidate.recovery_days)
    scope_manifest = build_scope_manifest(
        candidate.file_ids,
        loaded.files,
        loaded.fixture_digest,
        loaded.policy.version,
        loaded.policy_digest or "",
    )
    recomputed_hash = compute_action_hash(
        run_id=run_id,
        operation="simulate_archive",
        file_ids=candidate.file_ids,
        files=loaded.files,
        fixture_digest=loaded.fixture_digest,
        policy_version=loaded.policy.version,
        policy_digest=loaded.policy_digest or "",
        dry_run_digest=digest_of(dry_run_manifest),
        backup_digest=digest_of(backup_manifest),
        recovery_days=candidate.recovery_days,
    )
    if recomputed_hash != action_hash or recomputed_hash != report.final_decision.action_hash:
        raise ConflictError("action_hash no longer matches current state", code="action_hash_mismatch")

    approval = run_repository.get_latest_approval(session, run_id, action_hash)
    if approval is None or approval.choice != "approve":
        raise ConflictError("no valid approval on file for this action", code="approval_missing")
    if approval.consumed_at is not None:
        raise ConflictError("approval already consumed", code="approval_missing")
    if dt.datetime.now(dt.timezone.utc) > approval.expires_at.replace(tzinfo=dt.timezone.utc):
        raise ConflictError("Approval expired. Review the current action again.", code="approval_expired")

    # Validate the narrow executable shape explicitly; a delete/dry_run/
    # clarify candidate could never satisfy this.
    ExecutableAction(
        operation="simulate_archive",
        file_ids=candidate.file_ids,
        recovery_days=candidate.recovery_days,
        manifest_digest=digest_of(scope_manifest),
        policy_version=loaded.policy.version,
        policy_digest=loaded.policy_digest or "",
    )

    prior_ids = _prior_archived_ids(session, run_id)
    new_ids = sorted(set(prior_ids) | set(candidate.file_ids))
    before_digest = digest_of({"archived_file_ids": prior_ids})
    after_digest = digest_of({"archived_file_ids": new_ids})
    # Two genuinely independent fresh disk reads, not one dict copied into
    # both result fields (carryover C01). Nothing in this simulation ever
    # writes to a source file, so these are expected to match; a mismatch
    # would mean something outside this function touched the fixture mid-
    # execution, which must never be reported as a clean simulated result.
    # Both reads happen before any state transition below, matching every
    # other revalidation check in this function.
    source_hashes_before = hash_source_files(loaded, candidate.file_ids)
    source_hashes_after = hash_source_files(loaded, candidate.file_ids)
    if source_hashes_after != source_hashes_before:
        raise ConflictError("source file bytes changed during execution", code="fixture_changed")

    claimed = run_repository.set_run_status(session, row, "executing", expected_version=row.version)
    if not claimed:
        # Someone else won the race. If they finished, hand back their result.
        session.rollback()
        winner = run_repository.get_execution_by_hash(session, run_id, action_hash)
        if winner is not None:
            return run_repository.execution_to_record(winner)
        raise ConflictError("run was concurrently modified; refetch and retry", code="version_conflict")

    execution_id = uuid.uuid4().hex
    result_payload = {
        "before_digest": before_digest,
        "after_digest": after_digest,
        "archived_file_ids": candidate.file_ids,
        "rollback_record_id": None,
        "source_hashes_before": source_hashes_before,
        "source_hashes_after": source_hashes_after,
    }
    try:
        execution_row = ExecutionORM(
            id=execution_id,
            run_id=run_id,
            action_hash=action_hash,
            status="completed",
            result_json=json.dumps(result_payload),
        )
        session.add(execution_row)
        session.flush()
    except IntegrityError:
        session.rollback()
        winner = run_repository.get_execution_by_hash(session, run_id, action_hash)
        if winner is not None:
            return run_repository.execution_to_record(winner)
        raise

    existing_state = run_repository.get_simulation_state(session, run_id)
    if existing_state is None:
        session.add(
            SimulationStateORM(
                run_id=run_id,
                manifest_json=json.dumps(scope_manifest),
                simulated_archive_json=json.dumps({"archived_file_ids": new_ids}),
                backup_manifest_json=json.dumps(backup_manifest),
                rollback_json=json.dumps({"archived_file_ids": prior_ids}),
            )
        )
    else:
        existing_state.manifest_json = json.dumps(scope_manifest)
        existing_state.simulated_archive_json = json.dumps({"archived_file_ids": new_ids})
        existing_state.backup_manifest_json = json.dumps(backup_manifest)
        existing_state.rollback_json = json.dumps({"archived_file_ids": prior_ids})

    approval.consumed_at = dt.datetime.now(dt.timezone.utc)

    completed = run_repository.set_run_status(session, row, "completed", expected_version=row.version)
    if not completed:
        session.rollback()
        raise ConflictError("run was concurrently modified during execution", code="version_conflict")

    run_repository.append_event(session, run_id, "executing", "ok", "Simulated archive execution started.")
    run_repository.append_event(
        session, run_id, "completed", "ok", f"Execution {execution_id} completed; source hashes unchanged."
    )
    session.commit()

    return run_repository.execution_to_record(execution_row)


def rollback_action(session: Session, run_id: str, execution_id: str) -> ExecutionRecord:
    row = run_repository.get_run_row(session, run_id)
    if row is None:
        raise NotFoundError(f"unknown run: {run_id}", code="run_not_found")

    execution = run_repository.get_execution_by_id(session, run_id, execution_id)
    if execution is None:
        raise NotFoundError(f"unknown execution: {execution_id}", code="execution_not_found")

    if execution.status == "rolled_back":
        # Idempotent: report the same already-rolled-back result again.
        return run_repository.execution_to_record(execution)

    if execution.status != "completed":
        raise ConflictError("execution is not in a rollback-eligible state", code="not_rollback_eligible")

    state = run_repository.get_simulation_state(session, run_id)
    if state is None or state.rollback_json is None:
        raise ConflictError("no prior simulated state to restore", code="nothing_to_rollback")

    previous_state = json.loads(state.rollback_json)
    state.simulated_archive_json = json.dumps(previous_state)
    state.rollback_json = None

    result_payload = json.loads(execution.result_json)
    result_payload["rollback_record_id"] = f"rollback-{execution.id}"
    execution.status = "rolled_back"
    execution.result_json = json.dumps(result_payload)

    run_repository.append_event(
        session, run_id, "rollback", "ok", f"Execution {execution_id} rolled back; prior simulated state restored."
    )
    session.commit()

    return run_repository.execution_to_record(execution)
