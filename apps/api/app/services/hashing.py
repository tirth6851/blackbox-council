"""Server-side approval-action hashing.

The client only ever echoes back a hash the server already computed and
displayed; the server independently recomputes it from canonical state
before honoring an approval. Mutable display text is never part of the
hashed payload.
"""
from __future__ import annotations

import hashlib
import json

from app.schemas import FileMetadata


def compute_action_hash(
    *,
    run_id: str,
    operation: str,
    file_ids: list[str],
    files: dict[str, FileMetadata],
    fixture_digest: str,
    policy_version: str,
    dry_run_digest: str,
    backup_digest: str,
    recovery_days: int,
) -> str:
    if len(set(file_ids)) != len(file_ids):
        raise ValueError("duplicate file_ids rejected before hashing")
    payload = {
        "run_id": run_id,
        "operation": operation,
        "file_ids": [[fid, files[fid].content_sha256] for fid in sorted(file_ids)],
        "fixture_digest": fixture_digest,
        "policy_version": policy_version,
        "dry_run_digest": dry_run_digest,
        "backup_digest": backup_digest,
        "recovery_days": recovery_days,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
