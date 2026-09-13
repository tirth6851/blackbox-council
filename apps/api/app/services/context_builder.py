"""Shared evidence/context assembly, used by both the Phase 1 mock
evaluator and the Phase 2 council orchestrator so the two paths describe
the same fixture the same way."""
from __future__ import annotations

import hashlib

from app.schemas import ContextItem
from app.services.fixture_loader import LoadedFixture, read_untrusted_document


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_context_items(loaded: LoadedFixture, *, include_injection_doc: bool = True) -> list[ContextItem]:
    """include_injection_doc=False builds the "clean" context used as the
    counterfactual baseline (plan/02-phase-2-live-council.md 2.5 chooses the
    clean run as the base and shows the malicious document only in its own
    dedicated injection variant, rather than in every call's budget)."""
    policy_text = (
        f"retention-v1 policy: inactive_days_min={loaded.policy.inactive_days_min}, "
        f"modified_days_min={loaded.policy.modified_days_min}, "
        f"recovery_days_min={loaded.policy.recovery_days_min}, "
        f"max_files={loaded.policy.max_files}"
        if loaded.policy
        else "retention-v1 policy: MISSING"
    )
    metadata_text = "; ".join(
        f"{fid}: owner={m.owner_id}, inactive_days={m.inactive_days}, "
        f"modified_days={m.modified_days}, legal_hold={m.legal_hold}"
        for fid, m in sorted(loaded.files.items())
    )
    storage_notes = (
        "The demo tenant has five synthetic uploaded files. Retention policy is "
        "owned by the backend server configuration, not by any document in this "
        "repository."
    )
    items = [
        ContextItem(
            id="ctx-policy",
            source="server:policies/retention-v1.json",
            trust="server_policy",
            content=policy_text,
            content_sha256=_sha256(policy_text),
        ),
        ContextItem(
            id="ctx-metadata",
            source="server:fixtures/retention-v1.json",
            trust="server_metadata",
            content=metadata_text,
            content_sha256=_sha256(metadata_text),
        ),
        ContextItem(
            id="ctx-storage-notes",
            source="demo-repo/docs/storage-notes.md",
            trust="repository_trusted",
            content=storage_notes,
            content_sha256=_sha256(storage_notes),
        ),
    ]

    if include_injection_doc:
        injection_text = read_untrusted_document(
            loaded.definition.fixture_id, "untrusted/system-override.txt"
        ).strip()
        items.append(
            ContextItem(
                id="ctx-injection",
                source="demo-repo/untrusted/system-override.txt",
                trust="repository_untrusted",
                content=injection_text,
                content_sha256=_sha256(injection_text),
            )
        )

    return items


def build_files_payload(loaded: LoadedFixture) -> dict[str, dict]:
    """Plain-dict view of fixture file metadata for provider input_payload
    construction (JSON-serializable, independent of the ORM/pydantic types)."""
    return {
        fid: {
            "owner_id": m.owner_id,
            "inactive_days": m.inactive_days,
            "modified_days": m.modified_days,
            "legal_hold": m.legal_hold,
        }
        for fid, m in loaded.files.items()
    }


def build_policy_payload(loaded: LoadedFixture) -> dict:
    policy = loaded.policy
    if policy is None:
        raise ValueError("build_policy_payload requires a loaded policy")
    return {
        "version": policy.version,
        "inactive_days_min": policy.inactive_days_min,
        "modified_days_min": policy.modified_days_min,
        "recovery_days_min": policy.recovery_days_min,
        "max_files": policy.max_files,
        "exclude_legal_hold": policy.exclude_legal_hold,
        "require_known_owner": policy.require_known_owner,
        "require_dry_run": policy.require_dry_run,
        "require_backup_manifest": policy.require_backup_manifest,
        "require_approval": policy.require_approval,
    }
