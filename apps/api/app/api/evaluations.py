"""HTTP validation/delegation only — no business logic lives in this module."""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.dependencies import check_operator_credential, get_session, require_operator_credential
from app.errors import AppError, ConflictError, NotFoundError
from app.schemas import ApprovalRequest, EvaluationCreate, EvaluationReport, ExecuteRequest, RollbackRequest
from app.services import run_repository
from app.services.approval_service import submit_approval
from app.services.decision_service import run_mock_evaluation
from app.services.executor import execute_action, rollback_action
from app.services.fixture_loader import FixtureError, load_fixture
from app.services.mock_provider import UnsupportedMockTaskError

router = APIRouter(prefix="/api/v1/evaluations", tags=["evaluations"])


@router.post("", status_code=201, response_model=EvaluationReport)
def create_evaluation(
    payload: EvaluationCreate, request: Request, response: Response, session: Session = Depends(get_session)
) -> EvaluationReport:
    if payload.mode == "live":
        return _create_live_evaluation(payload, request, response, session)

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


def _create_live_evaluation(
    payload: EvaluationCreate, request: Request, response: Response, session: Session
) -> EvaluationReport:
    """202 Accepted: live evaluation runs in the background. Poll GET
    /evaluations/{run_id} for progress and the final decision (plan 2.6)."""
    settings = request.app.state.settings
    check_operator_credential(request, request.headers.get("X-Operator-Credential"))
    if not request.app.state.live_mode_configured():
        # Fails fast with a clear "not configured" error rather than
        # silently substituting mock output into a live run.
        raise AppError(
            "live mode is not configured: set NEBIUS_API_KEY and NEBIUS_MODEL",
            code="live_mode_unconfigured",
            status_code=503,
        )

    active = run_repository.count_active_live_runs(session)
    if active >= settings.live_run_concurrency:
        raise ConflictError(
            "a live evaluation is already running; try again shortly", code="live_run_busy"
        )

    run_id = uuid.uuid4().hex
    run_repository.create_placeholder_run(session, run_id, mode="live", task=payload.task, fixture_id=payload.fixture_id)
    request.app.state.live_worker.enqueue(run_id)

    response.status_code = 202
    row = run_repository.get_run_row(session, run_id)
    return run_repository.load_report(session, row)


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


@router.post(
    "/{run_id}/approvals",
    status_code=201,
    response_model=EvaluationReport,
    dependencies=[Depends(require_operator_credential)],
)
def create_approval(
    run_id: str, payload: ApprovalRequest, session: Session = Depends(get_session)
) -> EvaluationReport:
    return submit_approval(session, run_id, payload.action_hash, payload.decision, payload.reason)


@router.post("/{run_id}/execute", dependencies=[Depends(require_operator_credential)])
def execute(run_id: str, payload: ExecuteRequest, session: Session = Depends(get_session)):
    record = execute_action(session, run_id, payload.action_hash)
    return record


@router.post("/{run_id}/rollback", dependencies=[Depends(require_operator_credential)])
def rollback(run_id: str, payload: RollbackRequest, session: Session = Depends(get_session)):
    record = rollback_action(session, run_id, payload.execution_id)
    return record
