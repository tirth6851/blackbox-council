"""Deterministic simulated manifest builders.

A "manifest" here is bounded, order-independent JSON describing which
fixture files a candidate touches. Manifests never include mutable display
text or timestamps, so the same fixture always yields the same digest.
"""
from __future__ import annotations

import hashlib
import json

from app.schemas import FileMetadata


def digest_of(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _file_hash_pairs(file_ids: list[str], files: dict[str, FileMetadata]) -> dict[str, str]:
    if len(set(file_ids)) != len(file_ids):
        raise ValueError("duplicate file_ids rejected before manifest construction")
    return {fid: files[fid].content_sha256 for fid in sorted(file_ids)}


def build_dry_run_manifest(file_ids: list[str], files: dict[str, FileMetadata]) -> dict:
    return {"kind": "dry_run", "file_hashes": _file_hash_pairs(file_ids, files)}


def build_backup_manifest(
    file_ids: list[str], files: dict[str, FileMetadata], recovery_days: int
) -> dict:
    return {
        "kind": "backup",
        "file_hashes": _file_hash_pairs(file_ids, files),
        "recovery_days": recovery_days,
    }


def build_scope_manifest(
    file_ids: list[str], files: dict[str, FileMetadata], fixture_digest: str, policy_version: str
) -> dict:
    return {
        "kind": "scope",
        "file_hashes": _file_hash_pairs(file_ids, files),
        "fixture_digest": fixture_digest,
        "policy_version": policy_version,
    }
