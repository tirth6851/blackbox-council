"""PR #7 review finding: Base.metadata.create_all() only creates tables
that don't exist yet -- it never alters an existing table's columns. Adding
runs.policy_digest (a non-null column) without a migration would break
every query touching an existing database with "no such column:
policy_digest" once opened with this code. Reproduced by the reviewer
against a hand-built pre-PR database; this test reproduces it with a real,
fully schema-valid run/approval (created through the actual app, then the
on-disk schema rolled back to its pre-PR shape) rather than a hand-typed
row, so nothing about the reproduction depends on guessing the exact
report JSON shape.
"""
from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.mock_provider import SEEDED_TASK


def test_upgrading_a_pre_policy_digest_database_does_not_crash_and_requires_reevaluation(
    tmp_path,
) -> None:
    db_path = tmp_path / "legacy.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}", cors_origins=["http://localhost:3000"], app_env="test"
    )

    # Step 1: create a real, fully valid run + approval with today's code
    # (fresh_database coverage doubles as the source of realistic legacy
    # data -- no need to hand-type a report_json blob that might drift from
    # the real schema).
    app = create_app(settings)
    client = TestClient(app)
    body = client.post(
        "/api/v1/evaluations",
        json={"task": SEEDED_TASK, "fixture_id": "retention-v1", "mode": "mock"},
    ).json()
    run_id = body["run_id"]
    action_hash = body["final_decision"]["action_hash"]
    approve = client.post(
        f"/api/v1/evaluations/{run_id}/approvals",
        json={"action_hash": action_hash, "decision": "approve", "reason": "ok"},
    )
    assert approve.status_code == 201, approve.text
    app.state.engine.dispose()

    # Step 2: roll the on-disk schema back to its pre-PR shape -- the exact
    # same row data, minus the column this PR added -- reproducing exactly
    # what an existing deployment's database looks like before an upgrade.
    raw = sqlite3.connect(str(db_path))
    raw.execute("ALTER TABLE runs DROP COLUMN policy_digest")
    raw.commit()
    raw.close()

    # Step 3: open it with a fresh app instance. This exercises the real
    # migration path (build_engine -> _migrate_runs_table), not a
    # hand-simulated one.
    upgraded_app = create_app(settings)
    upgraded_client = TestClient(upgraded_app)

    report = upgraded_client.get(f"/api/v1/evaluations/{run_id}")
    assert report.status_code == 200, report.text  # no "no such column" crash
    assert report.json()["status"] == "approved"
    assert report.json()["approval"]["action_hash"] == action_hash

    # A legacy run's originally-approved policy fingerprint is unknown (the
    # migration backfills policy_digest to "", deliberately not today's
    # live digest), so execution must be rejected and require reevaluation
    # rather than either crashing or silently trusting today's policy
    # content as if it were what was actually approved.
    execute = upgraded_client.post(
        f"/api/v1/evaluations/{run_id}/execute", json={"action_hash": action_hash}
    )
    assert execute.status_code == 409, execute.text
    assert execute.json()["error"]["code"] == "policy_changed"


def test_migration_is_idempotent_on_an_already_current_database(tmp_path) -> None:
    """Running the migration against a database that already has
    policy_digest (every fresh database, and one already upgraded) must be
    a no-op, not an error -- opening the same database twice in a row must
    not fail on "duplicate column name"."""
    db_path = tmp_path / "current.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}", cors_origins=["http://localhost:3000"], app_env="test"
    )

    first = create_app(settings)
    first.state.engine.dispose()

    second = create_app(settings)  # must not raise "duplicate column name: policy_digest"
    client = TestClient(second)
    response = client.get("/health")
    assert response.status_code == 200
