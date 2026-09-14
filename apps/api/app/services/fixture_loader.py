"""Safe, fixed-fixture reads.

Loads the server-owned fixture inventory and policy for a known fixture ID.
File reads are strictly bounded to the registered demo-repo root: no
absolute paths, no parent traversal, no symlinks, no unknown IDs.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from app.fixture_registry import FixtureDefinition, get_fixture_definition
from app.schemas import FileMetadata


class FixtureError(Exception):
    """Raised when a fixture or policy cannot be loaded safely."""


class UnknownFixtureError(FixtureError):
    pass


class MissingPolicyError(FixtureError):
    """The authoritative policy file for a known fixture is missing."""


@dataclass(frozen=True)
class RetentionPolicy:
    version: str
    inactive_days_min: int
    modified_days_min: int
    recovery_days_min: int
    max_files: int
    exclude_legal_hold: bool
    require_known_owner: bool
    require_dry_run: bool
    require_backup_manifest: bool
    require_approval: bool

    @classmethod
    def from_dict(cls, data: dict) -> "RetentionPolicy":
        return cls(
            version=data["version"],
            inactive_days_min=data["inactive_days_min"],
            modified_days_min=data["modified_days_min"],
            recovery_days_min=data["recovery_days_min"],
            max_files=data["max_files"],
            exclude_legal_hold=data["exclude_legal_hold"],
            require_known_owner=data["require_known_owner"],
            require_dry_run=data["require_dry_run"],
            require_backup_manifest=data["require_backup_manifest"],
            require_approval=data["require_approval"],
        )


@dataclass(frozen=True)
class LoadedFixture:
    definition: FixtureDefinition
    files: dict[str, FileMetadata]
    policy: RetentionPolicy | None
    fixture_digest: str
    # None only when policy is None (no authoritative policy loaded at all).
    # Whenever policy is present this is always computed alongside it.
    policy_digest: str | None


def _safe_join(root: Path, relative: str) -> Path:
    """Resolve relative under root, rejecting escape or symlink tricks.

    Path components are inspected for a symlink *before* the path is
    resolved. Checking is_symlink() only on the already-resolved candidate
    (the prior approach) is a no-op: Path.resolve() itself transparently
    follows symlinks, so the resolved candidate is never a symlink even
    when one of its original components was one. That let an in-root
    symlink pointing at another in-root file pass silently, contrary to
    the documented no-symlinks rule. Root containment is still checked
    afterwards as defense in depth against an escaping resolved target.
    """
    if not relative or relative.startswith("/") or ".." in Path(relative).parts:
        raise FixtureError(f"unsafe path segment: {relative!r}")
    root_resolved = root.resolve()
    current = root_resolved
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise FixtureError(f"symlinks are not permitted: {relative!r}")
    candidate = (root / relative).resolve()
    if root_resolved not in candidate.parents and candidate != root_resolved:
        raise FixtureError(f"path escapes fixture root: {relative!r}")
    return candidate


def _compute_fixture_digest(files: dict[str, FileMetadata]) -> str:
    """Deterministic digest over sorted file records so the same fixture
    input always yields the same manifest digest."""
    canonical = json.dumps(
        [files[fid].model_dump(mode="json") for fid in sorted(files)],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _compute_policy_digest(policy: RetentionPolicy | None) -> str | None:
    """Content fingerprint of the authoritative policy, independent of its
    declared `version` label. A policy edited in place without bumping its
    version string must still be detectable as changed (see load_fixture_fresh
    and executor.execute_action, which bind approval to this digest too)."""
    if policy is None:
        return None
    canonical = json.dumps(asdict(policy), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_fixture_uncached(fixture_id: str) -> LoadedFixture:
    definition = get_fixture_definition(fixture_id)
    if definition is None:
        raise UnknownFixtureError(f"unknown fixture_id: {fixture_id!r}")

    if not definition.fixture_data_path.is_file():
        raise FixtureError(f"missing fixture data: {definition.fixture_data_path}")
    raw = json.loads(definition.fixture_data_path.read_text(encoding="utf-8"))

    files: dict[str, FileMetadata] = {}
    for entry in raw.get("files", []):
        # Verify the referenced upload actually exists at a safe path and
        # that its recorded hash still matches disk contents.
        safe_path = _safe_join(definition.demo_repo_root, entry["path"])
        if not safe_path.is_file():
            raise FixtureError(f"fixture references missing file: {entry['path']}")
        actual_hash = hashlib.sha256(safe_path.read_bytes()).hexdigest()
        if actual_hash != entry["content_sha256"]:
            raise FixtureError(
                f"fixture hash mismatch for {entry['id']}; rerun scripts/seed_fixtures.py"
            )
        files[entry["id"]] = FileMetadata(
            id=entry["id"],
            path=entry["path"],
            owner_id=entry.get("owner_id"),
            inactive_days=entry["inactive_days"],
            modified_days=entry["modified_days"],
            legal_hold=entry["legal_hold"],
            synthetic=True,
            content_sha256=entry["content_sha256"],
            byte_count=entry["byte_count"],
        )

    policy: RetentionPolicy | None = None
    if definition.policy_path.is_file():
        policy_raw = json.loads(definition.policy_path.read_text(encoding="utf-8"))
        policy = RetentionPolicy.from_dict(policy_raw)

    return LoadedFixture(
        definition=definition,
        files=files,
        policy=policy,
        fixture_digest=_compute_fixture_digest(files),
        policy_digest=_compute_policy_digest(policy),
    )


# Cached for evaluation-time reads, which may load the same fixture many
# times in one request (planner, red-team, privacy, counterfactual probes)
# and don't need to observe a disk change made mid-evaluation.
load_fixture = lru_cache(maxsize=8)(_load_fixture_uncached)


def load_fixture_fresh(fixture_id: str) -> LoadedFixture:
    """Bypass the cache entirely and re-read current on-disk bytes/policy.

    execute_action() must revalidate against the fixture's *current* state,
    not a snapshot that may have been cached before evaluation and never
    invalidated since (Phase 3 milestone 3.1 / carryover C01). Calling the
    cached load_fixture() here would let execute_action compare that stale
    snapshot's own digest against itself and always "pass" even when the
    on-disk bytes or policy changed after approval.
    """
    return _load_fixture_uncached(fixture_id)


def read_fixture_file_content(fixture_id: str, file_id: str) -> str:
    """Read a fixture file's text content by validated ID only."""
    loaded = load_fixture(fixture_id)
    metadata = loaded.files.get(file_id)
    if metadata is None:
        raise FixtureError(f"unknown file_id: {file_id!r}")
    safe_path = _safe_join(loaded.definition.demo_repo_root, metadata.path)
    return safe_path.read_text(encoding="utf-8")


def hash_source_files(loaded: LoadedFixture, file_ids: Iterable[str]) -> dict[str, str]:
    """Independently re-read each file's bytes from disk right now and hash
    them, rather than trusting FileMetadata.content_sha256 captured earlier
    in the same LoadedFixture. Used by execute_action to take two genuinely
    separate before/after measurements instead of copying one dict into
    both result fields (carryover C01)."""
    result: dict[str, str] = {}
    for file_id in file_ids:
        metadata = loaded.files.get(file_id)
        if metadata is None:
            raise FixtureError(f"unknown file_id: {file_id!r}")
        safe_path = _safe_join(loaded.definition.demo_repo_root, metadata.path)
        result[file_id] = hashlib.sha256(safe_path.read_bytes()).hexdigest()
    return result


def read_untrusted_document(fixture_id: str, relative_path: str) -> str:
    """Read a repository document (e.g. the injection sample) that is not
    part of the file inventory but is still bounded to the fixture root."""
    definition = get_fixture_definition(fixture_id)
    if definition is None:
        raise UnknownFixtureError(f"unknown fixture_id: {fixture_id!r}")
    safe_path = _safe_join(definition.demo_repo_root, relative_path)
    if not safe_path.is_file():
        raise FixtureError(f"missing repository document: {relative_path}")
    return safe_path.read_text(encoding="utf-8")


def clear_fixture_cache() -> None:
    load_fixture.cache_clear()
