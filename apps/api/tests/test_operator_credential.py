"""Review finding: approval/execute/rollback (and live evaluation
creation) had no authentication at all — anyone who obtained a run_id and
action_hash could approve/execute/roll back a run. When OPERATOR_CREDENTIAL
is configured, these routes must require it; when it is unset (the local
demo default), they stay open, matching plan/README.md's "synthetic mock
demonstration stays public" stance."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.fixture_loader import clear_fixture_cache
from app.services.mock_provider import SEEDED_TASK

CREDENTIAL_HEADER = "X-Operator-Credential"


def setup_function() -> None:
    clear_fixture_cache()


def _create_run(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/evaluations", json={"task": SEEDED_TASK, "fixture_id": "retention-v1", "mode": "mock"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_mutation_routes_stay_open_when_no_credential_is_configured(tmp_path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")  # operator_credential unset
    app = create_app(settings)
    client = TestClient(app)

    body = _create_run(client)
    run_id, action_hash = body["run_id"], body["final_decision"]["action_hash"]

    approve = client.post(
        f"/api/v1/evaluations/{run_id}/approvals",
        json={"action_hash": action_hash, "decision": "approve", "reason": ""},
    )
    assert approve.status_code == 201


def test_approval_requires_credential_when_configured(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}", operator_credential="s3cret"
    )
    app = create_app(settings)
    client = TestClient(app)

    body = _create_run(client)
    run_id, action_hash = body["run_id"], body["final_decision"]["action_hash"]

    no_header = client.post(
        f"/api/v1/evaluations/{run_id}/approvals",
        json={"action_hash": action_hash, "decision": "approve", "reason": ""},
    )
    assert no_header.status_code == 401
    assert no_header.json()["error"]["code"] == "operator_credential_required"

    wrong_header = client.post(
        f"/api/v1/evaluations/{run_id}/approvals",
        json={"action_hash": action_hash, "decision": "approve", "reason": ""},
        headers={CREDENTIAL_HEADER: "wrong"},
    )
    assert wrong_header.status_code == 401

    correct_header = client.post(
        f"/api/v1/evaluations/{run_id}/approvals",
        json={"action_hash": action_hash, "decision": "approve", "reason": ""},
        headers={CREDENTIAL_HEADER: "s3cret"},
    )
    assert correct_header.status_code == 201


def test_execute_and_rollback_require_credential_when_configured(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}", operator_credential="s3cret"
    )
    app = create_app(settings)
    client = TestClient(app)
    headers = {CREDENTIAL_HEADER: "s3cret"}

    body = _create_run(client)
    run_id, action_hash = body["run_id"], body["final_decision"]["action_hash"]
    client.post(
        f"/api/v1/evaluations/{run_id}/approvals",
        json={"action_hash": action_hash, "decision": "approve", "reason": ""},
        headers=headers,
    )

    no_header = client.post(f"/api/v1/evaluations/{run_id}/execute", json={"action_hash": action_hash})
    assert no_header.status_code == 401

    execute = client.post(
        f"/api/v1/evaluations/{run_id}/execute", json={"action_hash": action_hash}, headers=headers
    )
    assert execute.status_code == 200
    execution_id = execute.json()["id"]

    no_header_rollback = client.post(
        f"/api/v1/evaluations/{run_id}/rollback", json={"execution_id": execution_id}
    )
    assert no_header_rollback.status_code == 401

    rollback = client.post(
        f"/api/v1/evaluations/{run_id}/rollback", json={"execution_id": execution_id}, headers=headers
    )
    assert rollback.status_code == 200


def test_live_evaluation_creation_requires_credential_when_configured(tmp_path) -> None:
    from app.providers.mock import MockProvider

    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}", operator_credential="s3cret"
    )
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.live_provider_factory = lambda: MockProvider()
        app.state.live_mode_configured = lambda: True

        no_header = client.post(
            "/api/v1/evaluations", json={"task": SEEDED_TASK, "fixture_id": "retention-v1", "mode": "live"}
        )
        assert no_header.status_code == 401
        assert no_header.json()["error"]["code"] == "operator_credential_required"

        with_header = client.post(
            "/api/v1/evaluations",
            json={"task": SEEDED_TASK, "fixture_id": "retention-v1", "mode": "live"},
            headers={CREDENTIAL_HEADER: "s3cret"},
        )
        assert with_header.status_code == 202


def test_mock_evaluation_creation_stays_public_even_when_credential_is_configured(tmp_path) -> None:
    """The plan is explicit that the synthetic mock demo stays public; only
    mutation and live-model routes get gated."""
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}", operator_credential="s3cret"
    )
    app = create_app(settings)
    client = TestClient(app)

    response = client.post(
        "/api/v1/evaluations", json={"task": SEEDED_TASK, "fixture_id": "retention-v1", "mode": "mock"}
    )
    assert response.status_code == 201
