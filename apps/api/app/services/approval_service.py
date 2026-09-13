"""Approval submission. The client only ever echoes a hash the server
already computed; the server independently verifies it before recording an
approval or rejection. Approval never overrides a block or a missing
prerequisite — it can only be recorded against a run already awaiting one."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError
from app.schemas import EvaluationReport
from app.services import run_repository


def submit_approval(
    session: Session, run_id: str, action_hash: str, decision: str, reason: str
) -> EvaluationReport:
    row = run_repository.get_run_row(session, run_id)
    if row is None:
        raise NotFoundError(f"unknown run: {run_id}", code="run_not_found")

    report = run_repository.load_report(session, row)

    if row.status != "awaiting_approval":
        raise ConflictError(
            f"run is not awaiting approval (current status: {row.status})",
            code="invalid_state",
        )

    if report.final_decision is None or report.final_decision.action_hash != action_hash:
        raise ConflictError(
            "action_hash does not match the current decision; refetch the report",
            code="action_hash_mismatch",
        )

    run_repository.save_approval(session, run_id, action_hash, decision, reason)

    target_status = "approved" if decision == "approve" else "rejected"
    ok = run_repository.set_run_status(session, row, target_status, expected_version=row.version)
    if not ok:
        raise ConflictError("run was concurrently modified; refetch and retry", code="version_conflict")

    run_repository.append_event(
        session, run_id, target_status, "ok", f"Approval decision recorded: {decision}."
    )
    session.commit()

    row = run_repository.get_run_row(session, run_id)
    assert row is not None
    return run_repository.load_report(session, row)
