"""Review finding: set_run_status must be an atomic compare-and-swap, not a
SELECT-then-mutate-the-ORM-object pattern (which lets SQLAlchemy's autoflush
issue an UPDATE keyed only by primary key, ignoring the version actually
read). These tests exercise that directly at the repository layer rather
than relying on real thread/process concurrency to expose the race."""
from __future__ import annotations

import uuid

from app.services import run_repository
from app.services.decision_service import run_mock_evaluation
from app.services.fixture_loader import clear_fixture_cache, load_fixture
from app.services.mock_provider import SEEDED_TASK


def setup_function() -> None:
    clear_fixture_cache()


def _persisted_run(session) -> str:
    run_id = uuid.uuid4().hex
    report = run_mock_evaluation(run_id, SEEDED_TASK, "retention-v1")
    loaded = load_fixture("retention-v1")
    run_repository.create_run(
        session, report, fixture_digest=loaded.fixture_digest, policy_version=loaded.policy.version
    )
    return run_id


def test_set_run_status_only_the_first_writer_with_a_given_version_wins(app) -> None:
    session = app.state.session_factory()
    try:
        run_id = _persisted_run(session)
        row = run_repository.get_run_row(session, run_id)
        original_version = row.version

        # Simulate two concurrent requests that both read version=original
        # before either writes: only the first compare-and-swap may win.
        first = run_repository.set_run_status(session, row, "rejected", expected_version=original_version)
        second = run_repository.set_run_status(session, row, "approved", expected_version=original_version)

        assert first is True
        assert second is False  # the stale version must be refused, not silently overwritten

        session.commit()
        final_row = run_repository.get_run_row(session, run_id)
        assert final_row.status == "rejected"  # the second writer's change never landed
        assert final_row.version == original_version + 1  # exactly one successful transition
    finally:
        session.close()


def test_set_run_status_updates_the_passed_object_so_a_chained_call_uses_the_new_version(app) -> None:
    """executor.py chains two transitions (approved->executing->completed)
    reusing row.version between calls; the object must reflect the write it
    just made, not the version it was first loaded with."""
    session = app.state.session_factory()
    try:
        run_id = _persisted_run(session)
        row = run_repository.get_run_row(session, run_id)
        v0 = row.version

        assert run_repository.set_run_status(session, row, "rejected", expected_version=v0) is True
        assert row.version == v0 + 1
        assert row.status == "rejected"

        # Chaining off the now-current row.version must succeed.
        assert run_repository.set_run_status(session, row, "blocked", expected_version=row.version) is True
        assert row.version == v0 + 2
        assert row.status == "blocked"
    finally:
        session.close()
