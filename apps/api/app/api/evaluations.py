"""HTTP validation/delegation only — no business logic lives in this module."""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.dependencies import get_session
from app.errors import AppError, NotFoundError
from app.schemas import ApprovalRequest, EvaluationCreate, EvaluationReport, ExecuteRequest, RollbackRequest
from app.services import run_repository
from app.services.approval_service import submit_approval
from app.services.decision_service import run_mock_evaluation
from app.services.executor import execute_action, rollback_action
from app.services.fixture_loader import FixtureError, load_fixture
from app.services.mock_provider import UnsupportedMockTaskError

router = APIRouter(prefix="/api/v1/evaluations", tags=["evaluations"])


@router.post("", status_code=201, response_model=EvaluationReport)
def create_evaluation(payload: EvaluationCreate, session: Session = Depends(get_session)) -> EvaluationReport:
    if payload.mode == "live":
        # Wired up in Phase 2 (async council orchestration); see app/api/live.py.
        raise AppError(
            "live mode is not available on this route; see /api/v1/evaluations (mode=live) after Phase 2 wiring",
            code="live_mode_unavailable",
            status_code=501,
        )

    run_id = uuid.uuid4().hex
    try:
        loaded = load_fixture(payload.fixture_id)
    except FixtureError as exc:
        raise AppError(str(exc), code="fixture_error", status_code=500) from exc

    try:
        report = run_mock_evaluation(run_id, payload.task, payload.fixture_id)
    except UnsupportedMockTaskError as exc:
        raise AppError(str(exc), code="unsupported_mock_task", status_code=422) from exc

    policy_version = loaded.policy.version if loaded.policy else "unknown"
    run_repository.create_run(
        session, report, fixture_digest=loaded.fixture_digest, policy_version=policy_version
    )
    return report


@router.get("/{run_id}", response_model=EvaluationReport)
def get_evaluation(run_id: str, session: Session = Depends(get_session)) -> EvaluationReport:
    row = run_repository.get_run_row(session, run_id)
    if row is None:
        raise NotFoundError(f"unknown run: {run_id}", code="run_not_found")
    return run_repository.load_report(session, row)


@router.get("/{run_id}/report")
def download_report(run_id: str, session: Session = Depends(get_session)) -> Response:
    row = run_repository.get_run_row(session, run_id)
    if row is None:
        raise NotFoundError(f"unknown run: {run_id}", code="run_not_found")
    report = run_repository.load_report(session, row)
    body = json.dumps(report.model_dump(mode="json"), indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="report-{run_id}.json"'},
    )


@router.post("/{run_id}/approvals", status_code=201, response_model=EvaluationReport)
def create_approval(
    run_id: str, payload: ApprovalRequest, session: Session = Depends(get_session)
) -> EvaluationReport:
    return submit_approval(session, run_id, payload.action_hash, payload.decision, payload.reason)


@router.post("/{run_id}/execute")
def execute(run_id: str, payload: ExecuteRequest, session: Session = Depends(get_session)):
    record = execute_action(session, run_id, payload.action_hash)
    return record


@router.post("/{run_id}/rollback")
def rollback(run_id: str, payload: RollbackRequest, session: Session = Depends(get_session)):
    record = rollback_action(session, run_id, payload.execution_id)
    return record
