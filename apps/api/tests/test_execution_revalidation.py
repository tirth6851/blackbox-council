"""Phase 3 milestone 3.1 / PR #5 carryover C01 and C17.

C01: execute_action() loaded the fixture and policy through the cached
load_fixture(), so its own "did anything change since evaluation?" checks
compared a stale snapshot against itself and always passed — even when the
on-disk fixture bytes, fixture metadata, or policy content changed after
approval and the cache was never cleared. Reproduced originally through the
API using a disposable fixture copy: evaluate -> approve -> change f002
bytes -> execute returned 200/completed. These tests exercise that exact
sequence against execute_action's fix (load_fixture_fresh, plus a policy
content digest that catches an edit that doesn't bump `version`).

C17: _safe_join rejected symlinks by calling is_symlink() only on the
already-resolved candidate path. Path.resolve() transparently follows
symlinks, so the resolved candidate is never itself a symlink even when one
of its original path components was one — the check was a no-op. These
tests exercise the fixed component-by-component check directly.
"""
from __future__ import annotations

import shutil

import pytest

from app import fixture_registry
from app.fixture_registry import FixtureDefinition
from app.services.fixture_loader import (
    FixtureError,
    _safe_join,
    clear_fixture_cache,
    hash_source_files,
    load_fixture,
    load_fixture_fresh,
)
from app.services.mock_provider import SEEDED_TASK


@pytest.fixture()
def disposable_fixture(tmp_path, monkeypatch):
    """A private on-disk copy of the retention-v1 fixture (demo-repo files,
    fixture inventory JSON, and policy JSON) that a test can freely mutate
    without touching the real repository content other tests/CI rely on.
    Mirrors how C01 was originally reproduced: a "disposable fixture copy".
    """
    original = fixture_registry.FIXTURES["retention-v1"]

    demo_repo_copy = tmp_path / "demo-repo"
    shutil.copytree(original.demo_repo_root, demo_repo_copy)
    fixture_data_copy = tmp_path / "retention-v1.json"
    shutil.copy(original.fixture_data_path, fixture_data_copy)
    policy_copy = tmp_path / "retention-v1-policy.json"
    shutil.copy(original.policy_path, policy_copy)

    patched = FixtureDefinition(
        fixture_id="retention-v1",
        demo_repo_root=demo_repo_copy,
        fixture_data_path=fixture_data_copy,
        policy_path=policy_copy,
    )
    monkeypatch.setitem(fixture_registry.FIXTURES, "retention-v1", patched)
    clear_fixture_cache()
    yield patched
    clear_fixture_cache()


def _create_and_approve(client) -> tuple[str, str]:
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
    return run_id, action_hash


def test_execute_rejects_fixture_bytes_changed_after_approval_without_clearing_cache(
    client, disposable_fixture
) -> None:
    run_id, action_hash = _create_and_approve(client)

    # Mutate the archived file's bytes directly on disk without touching the
    # fixture JSON's recorded content_sha256 and without ever clearing the
    # loader cache — the exact carryover C01 reproduction.
    target = disposable_fixture.demo_repo_root / "uploads" / "f002.txt"
    target.write_bytes(target.read_bytes() + b"tampered")

    execute = client.post(f"/api/v1/evaluations/{run_id}/execute", json={"action_hash": action_hash})
    assert execute.status_code == 409, execute.text
    assert execute.json()["error"]["code"] == "fixture_changed"

    # No synthetic state changed: the run is still "approved", not executed.
    report = client.get(f"/api/v1/evaluations/{run_id}").json()
    assert report["status"] == "approved"
    assert report["execution"] is None


def test_execute_rejects_fixture_metadata_changed_after_approval_without_clearing_cache(
    client, disposable_fixture
) -> None:
    """Ownership/legal-hold changes in the fixture inventory (not the raw
    uploaded bytes) also change the fixture digest and must be caught."""
    run_id, action_hash = _create_and_approve(client)

    import json

    data = json.loads(disposable_fixture.fixture_data_path.read_text(encoding="utf-8"))
    for entry in data["files"]:
        if entry["id"] == "f002":
            entry["legal_hold"] = True
    disposable_fixture.fixture_data_path.write_text(json.dumps(data), encoding="utf-8")

    execute = client.post(f"/api/v1/evaluations/{run_id}/execute", json={"action_hash": action_hash})
    assert execute.status_code == 409, execute.text
    assert execute.json()["error"]["code"] == "fixture_changed"

    report = client.get(f"/api/v1/evaluations/{run_id}").json()
    assert report["status"] == "approved"
    assert report["execution"] is None


def test_execute_rejects_policy_content_changed_with_version_unchanged(
    client, disposable_fixture
) -> None:
    """The core C01 gap: a policy edited in place without bumping its
    `version` string previously passed the version-only check even with a
    fresh reload. Only a content digest catches this."""
    run_id, action_hash = _create_and_approve(client)

    import json

    policy_data = json.loads(disposable_fixture.policy_path.read_text(encoding="utf-8"))
    assert policy_data["version"] == "retention-v1"
    policy_data["max_files"] = 1  # content changes, version string does not
    disposable_fixture.policy_path.write_text(json.dumps(policy_data), encoding="utf-8")

    execute = client.post(f"/api/v1/evaluations/{run_id}/execute", json={"action_hash": action_hash})
    assert execute.status_code == 409, execute.text
    assert execute.json()["error"]["code"] == "policy_changed"

    report = client.get(f"/api/v1/evaluations/{run_id}").json()
    assert report["status"] == "approved"
    assert report["execution"] is None


def test_normal_flow_still_succeeds_with_matching_independently_measured_source_hashes(
    client, disposable_fixture
) -> None:
    """Regression guard: an unmodified disposable fixture must still execute
    cleanly, and the two independently-measured source-hash readings must
    agree (nothing in this simulation touches source bytes)."""
    run_id, action_hash = _create_and_approve(client)

    execute = client.post(f"/api/v1/evaluations/{run_id}/execute", json={"action_hash": action_hash})
    assert execute.status_code == 200, execute.text
    assert execute.json()["status"] == "completed"

    loaded = load_fixture_fresh("retention-v1")
    before = hash_source_files(loaded, ["f002"])
    after = hash_source_files(loaded, ["f002"])
    assert before == after


def test_load_fixture_fresh_bypasses_the_cache(disposable_fixture) -> None:
    """Unit-level proof that load_fixture (cached) and load_fixture_fresh
    (uncached) genuinely diverge once the cache is stale."""
    cached = load_fixture("retention-v1")

    target = disposable_fixture.demo_repo_root / "uploads" / "f001.txt"
    target.write_bytes(target.read_bytes() + b"changed")
    data_path = disposable_fixture.fixture_data_path
    # Keep the fixture inventory's recorded hash correct so the fresh load
    # succeeds rather than raising a hash-mismatch FixtureError — the point
    # here is only proving the cache is bypassed, not integrity checking.
    import hashlib
    import json

    data = json.loads(data_path.read_text(encoding="utf-8"))
    for entry in data["files"]:
        if entry["id"] == "f001":
            entry["content_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
            entry["byte_count"] = len(target.read_bytes())
    data_path.write_text(json.dumps(data), encoding="utf-8")

    still_cached = load_fixture("retention-v1")
    assert still_cached.fixture_digest == cached.fixture_digest  # unchanged: still serving the stale cache

    fresh = load_fixture_fresh("retention-v1")
    assert fresh.fixture_digest != cached.fixture_digest  # the fresh read sees the real change


def test_policy_digest_changes_when_policy_content_changes_but_version_does_not(
    disposable_fixture,
) -> None:
    original = load_fixture_fresh("retention-v1")
    assert original.policy is not None
    assert original.policy_digest is not None

    import json

    policy_data = json.loads(disposable_fixture.policy_path.read_text(encoding="utf-8"))
    policy_data["max_files"] = policy_data["max_files"] + 1
    disposable_fixture.policy_path.write_text(json.dumps(policy_data), encoding="utf-8")

    changed = load_fixture_fresh("retention-v1")
    assert changed.policy is not None
    assert changed.policy.version == original.policy.version  # version untouched
    assert changed.policy_digest != original.policy_digest  # content digest still catches it


def test_safe_join_rejects_a_symlink_path_component(tmp_path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    real_file = root / "real.txt"
    real_file.write_text("content", encoding="utf-8")

    # An in-root symlink pointing at another in-root file. Root containment
    # alone would accept this (the resolved target is inside root), so only
    # the pre-resolution component check catches it.
    link = root / "link.txt"
    link.symlink_to(real_file)

    with pytest.raises(FixtureError, match="symlinks are not permitted"):
        _safe_join(root, "link.txt")

    # A non-symlinked path to the same file is unaffected.
    assert _safe_join(root, "real.txt") == real_file.resolve()


def test_safe_join_rejects_a_symlinked_directory_component(tmp_path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    real_dir = tmp_path / "outside-dir"
    real_dir.mkdir()
    (real_dir / "secret.txt").write_text("secret", encoding="utf-8")

    linked_dir = root / "uploads"
    linked_dir.symlink_to(real_dir)

    with pytest.raises(FixtureError, match="symlinks are not permitted"):
        _safe_join(root, "uploads/secret.txt")


def test_safe_join_rejects_absolute_paths(tmp_path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(FixtureError, match="unsafe path segment"):
        _safe_join(root, "/etc/passwd")


def test_safe_join_rejects_parent_traversal(tmp_path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(FixtureError, match="unsafe path segment"):
        _safe_join(root, "../outside.txt")
