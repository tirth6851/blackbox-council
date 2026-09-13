from __future__ import annotations

from app.services.mock_provider import SEEDED_TASK


def _create_run(client):
    response = client.post(
        "/api/v1/evaluations",
        json={"task": SEEDED_TASK, "fixture_id": "retention-v1", "mode": "mock"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_evaluation_returns_awaiting_approval(client) -> None:
    body = _create_run(client)
    assert body["mode"] == "mock"
    assert body["status"] == "awaiting_approval"
    assert body["final_decision"]["outcome"] == "approval_required"
    assert body["final_decision"]["selected_candidate_id"] == "archive"
    assert body["final_decision"]["action_hash"]


def test_get_unknown_run_returns_404(client) -> None:
    response = client.get("/api/v1/evaluations/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "run_not_found"


def test_oversized_task_returns_422(client) -> None:
    response = client.post(
        "/api/v1/evaluations", json={"task": "x" * 2001, "fixture_id": "retention-v1"}
    )
    assert response.status_code == 422


def test_unsupported_free_text_task_returns_422_with_labeled_error(client) -> None:
    response = client.post(
        "/api/v1/evaluations",
        json={"task": "Something not seeded.", "fixture_id": "retention-v1"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_mock_task"


def test_run_persists_and_survives_a_fresh_app_instance(app, settings, client) -> None:
    from app.main import create_app

    body = _create_run(client)
    run_id = body["run_id"]

    # Simulate a process restart: build a brand-new app/session factory
    # against the same on-disk database file.
    from fastapi.testclient import TestClient

    fresh_app = create_app(settings)
    fresh_client = TestClient(fresh_app)
    response = fresh_client.get(f"/api/v1/evaluations/{run_id}")
    assert response.status_code == 200
    assert response.json()["final_decision"]["outcome"] == "approval_required"


def test_approve_then_execute_then_rollback_flow(client) -> None:
    body = _create_run(client)
    run_id = body["run_id"]
    action_hash = body["final_decision"]["action_hash"]

    approve = client.post(
        f"/api/v1/evaluations/{run_id}/approvals",
        json={"action_hash": action_hash, "decision": "approve", "reason": "looks good"},
    )
    assert approve.status_code == 201, approve.text
    assert approve.json()["status"] == "approved"

    execute = client.post(f"/api/v1/evaluations/{run_id}/execute", json={"action_hash": action_hash})
    assert execute.status_code == 200, execute.text
    execution = execute.json()
    assert execution["status"] == "completed"
    assert execution["before_digest"] != execution["after_digest"]
    assert execution["archived_file_ids"] == ["f002"]

    report = client.get(f"/api/v1/evaluations/{run_id}").json()
    assert report["status"] == "completed"

    rollback = client.post(
        f"/api/v1/evaluations/{run_id}/rollback", json={"execution_id": execution["id"]}
    )
    assert rollback.status_code == 200, rollback.text
    assert rollback.json()["status"] == "rolled_back"

    # Idempotent: rolling back again returns the same result, not an error.
    rollback_again = client.post(
        f"/api/v1/evaluations/{run_id}/rollback", json={"execution_id": execution["id"]}
    )
    assert rollback_again.status_code == 200
    assert rollback_again.json()["status"] == "rolled_back"


def test_execute_without_approval_is_rejected(client) -> None:
    body = _create_run(client)
    run_id = body["run_id"]
    action_hash = body["final_decision"]["action_hash"]

    execute = client.post(f"/api/v1/evaluations/{run_id}/execute", json={"action_hash": action_hash})
    assert execute.status_code == 409
    assert execute.json()["error"]["code"] == "not_authorized"


def test_reject_then_execute_is_refused(client) -> None:
    body = _create_run(client)
    run_id = body["run_id"]
    action_hash = body["final_decision"]["action_hash"]

    reject = client.post(
        f"/api/v1/evaluations/{run_id}/approvals",
        json={"action_hash": action_hash, "decision": "reject", "reason": "not now"},
    )
    assert reject.status_code == 201
    assert reject.json()["status"] == "rejected"

    execute = client.post(f"/api/v1/evaluations/{run_id}/execute", json={"action_hash": action_hash})
    assert execute.status_code == 409


def test_stale_action_hash_is_rejected_on_approval(client) -> None:
    body = _create_run(client)
    run_id = body["run_id"]

    approve = client.post(
        f"/api/v1/evaluations/{run_id}/approvals",
        json={"action_hash": "0" * 64, "decision": "approve", "reason": "wrong hash"},
    )
    assert approve.status_code == 409
    assert approve.json()["error"]["code"] == "action_hash_mismatch"


def test_double_submit_execute_creates_one_execution(client) -> None:
    body = _create_run(client)
    run_id = body["run_id"]
    action_hash = body["final_decision"]["action_hash"]
    client.post(
        f"/api/v1/evaluations/{run_id}/approvals",
        json={"action_hash": action_hash, "decision": "approve", "reason": "ok"},
    )

    first = client.post(f"/api/v1/evaluations/{run_id}/execute", json={"action_hash": action_hash})
    second = client.post(f"/api/v1/evaluations/{run_id}/execute", json={"action_hash": action_hash})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_blocked_delete_candidate_can_never_be_approved(client) -> None:
    body = _create_run(client)
    run_id = body["run_id"]
    decisions = {d["candidate_id"]: d for d in body["candidate_decisions"]}
    assert decisions["delete"]["outcome"] == "blocked"

    # The only action_hash the server ever produced is for the archive
    # candidate; the delete candidate has no path to approval at all.
    approve_delete = client.post(
        f"/api/v1/evaluations/{run_id}/approvals",
        json={"action_hash": "1" * 64, "decision": "approve", "reason": "please delete"},
    )
    assert approve_delete.status_code == 409
