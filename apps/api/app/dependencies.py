"""FastAPI dependencies."""
from __future__ import annotations

import hmac
from collections.abc import Generator

from fastapi import Header, Request
from sqlalchemy.orm import Session

from app.errors import AppError

OPERATOR_CREDENTIAL_HEADER = "X-Operator-Credential"


def get_session(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.session_factory
    session: Session = session_factory()
    try:
        yield session
    finally:
        session.close()


def check_operator_credential(request: Request, provided: str | None) -> None:
    """Gate a mutation route with OPERATOR_CREDENTIAL, when the operator has
    set one. Unset (the local/demo default) leaves the route open — this
    matches the plan's synthetic-mock-stays-public stance while giving a
    real deployment a way to actually protect approval/execution/rollback
    and live-run creation, none of which had any auth before this."""
    settings = request.app.state.settings
    expected = settings.operator_credential
    if not expected:
        return
    if not provided or not hmac.compare_digest(provided, expected):
        raise AppError(
            f"missing or invalid {OPERATOR_CREDENTIAL_HEADER} header",
            code="operator_credential_required",
            status_code=401,
        )


def require_operator_credential(
    request: Request, x_operator_credential: str | None = Header(default=None, alias=OPERATOR_CREDENTIAL_HEADER)
) -> None:
    """FastAPI dependency form of check_operator_credential, for routes that
    should always be gated regardless of request body content."""
    check_operator_credential(request, x_operator_credential)
