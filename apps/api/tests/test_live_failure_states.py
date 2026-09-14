"""2.6 acceptance: async live-run handling, concurrency limits, restart
recovery, and budget exhaustion — all against MockProvider so no real
network call happens."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers.mock import MockProvider
from app.services import run_repository
from app.services.fixture_loader import clear_fixture_cache
from app.services.mock_provider import SEEDED_TASK


def setup_function() -> None:
    clear_fixture_cache()


def _configure_for_mock_live(app) -> None:
    """Point the live path at MockProvider so tests never need a real key."""
    app.state.live_provider_factory = lambda: MockProvider()
    app.state.live_mode_configured = lambda: True


def _poll_until_terminal(client: TestClient, run_id: str, timeout_s: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout_s
    terminal = {
        "completed", "rejected", "needs_clarification", "needs_safeguards", "blocked", "failed",
        "awaiting_approval",
    }
    while time.monotonic() < deadline:
        body = client.get(f"/api/v1/evaluations/{run_id}").json()
        if body["status"] in terminal:
            return body
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not reach a terminal status within {timeout_s}s")


def test_live_mode_returns_503_when_not_configured(tmp_path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/evaluations", json={"task": SEEDED_TASK, "fixture_id": "retention-v1", "mode": "live"}
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "live_mode_unconfigured"


def test_live_mode_returns_202_and_reaches_awaiting_approval(tmp_path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")
    app = create_app(settings)
    with TestClient(app) as client:
        _configure_for_mock_live(app)
        response = client.post(
            "/api/v1/evaluations", json={"task": SEEDED_TASK, "fixture_id": "retention-v1", "mode": "live"}
        )
        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "evaluating"
        assert body["mode"] == "live"

        final = _poll_until_terminal(client, body["run_id"])
        assert final["status"] == "awaiting_approval"
        assert final["final_decision"]["outcome"] == "approval_required"
        assert final["final_decision"]["selected_candidate_id"] == "archive"
        assert len(final["reviews"]) == 4
        stage_names = {e["stage"] for e in final["events"]}
        assert {"planner", "red_team", "privacy", "arbiter"}.issubset(stage_names)


def test_concurrency_limit_returns_409_when_a_live_run_is_already_evaluating(tmp_path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", live_run_concurrency=1)
    app = create_app(settings)
    with TestClient(app) as client:
        _configure_for_mock_live(app)
        session = app.state.session_factory()
        try:
            run_repository.create_placeholder_run(
                session, "already-running", mode="live", task=SEEDED_TASK, fixture_id="retention-v1"
            )
        finally:
            session.close()

        response = client.post(
            "/api/v1/evaluations", json={"task": SEEDED_TASK, "fixture_id": "retention-v1", "mode": "live"}
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "live_run_busy"


def test_interrupted_run_is_marked_failed_on_restart(tmp_path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")

    # First "process": create a run and leave it stuck in evaluating, as if
    # the server crashed mid-evaluation.
    app1 = create_app(settings)
    session = app1.state.session_factory()
    try:
        run_repository.create_placeholder_run(
            session, "stuck-run", mode="live", task=SEEDED_TASK, fixture_id="retention-v1"
        )
    finally:
        session.close()

    # Second "process" against the same database: startup recovery must
    # mark it failed, never silently resume it.
    app2 = create_app(settings)
    with TestClient(app2) as client:
        body = client.get("/api/v1/evaluations/stuck-run").json()
        assert body["status"] == "failed"
        assert any("process_interrupted" in e["message"] for e in body["events"])


def test_budget_exhaustion_fails_the_run_cleanly(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        live_run_max_requests=1,  # only the Planner call is allowed
    )
    app = create_app(settings)
    with TestClient(app) as client:
        _configure_for_mock_live(app)
        response = client.post(
            "/api/v1/evaluations", json={"task": SEEDED_TASK, "fixture_id": "retention-v1", "mode": "live"}
        )
        run_id = response.json()["run_id"]

        final = _poll_until_terminal(client, run_id)
        assert final["status"] == "failed"
        assert any("budget_exceeded" in e["message"] for e in final["events"])
