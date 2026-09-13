"""1.4 acceptance: policy checks block unsafe candidates regardless of what
any evaluator (mock, scripted-unsafe, or eventually live) recommends."""
from __future__ import annotations

import json
from pathlib import Path

from app.schemas import CandidateAction
from app.services.decision_service import classify_candidate
from app.services.fixture_loader import clear_fixture_cache, load_fixture
from app.services.policy_engine import evaluate_candidate

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "unsafe-proposal.json"


def _load_unsafe_candidate() -> CandidateAction:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return CandidateAction(**data["candidate"])


def setup_function() -> None:
    clear_fixture_cache()


def test_scripted_unsafe_delete_all_is_blocked_regardless_of_recommendation() -> None:
    candidate = _load_unsafe_candidate()
    loaded = load_fixture("retention-v1")
    findings = evaluate_candidate(candidate, files=loaded.files, policy=loaded.policy)
    outcome, missing = classify_candidate(candidate, findings)

    assert outcome == "blocked"
    assert "FILE-001" in missing

    hold_finding = next(f for f in findings if f.rule_id == "HOLD-001")
    assert hold_finding.status == "triggered", "none of the 5 files are eligible under current policy"


def test_keyword_delete_in_task_does_not_block_a_separate_valid_archive_candidate() -> None:
    """A candidate mentioning delete is blocked, but a different, properly
    scoped archive candidate is judged on its own merits (no global block on
    the word 'delete')."""
    loaded = load_fixture("retention-v1")
    archive_candidate = CandidateAction(
        id="archive-f002",
        operation="archive",
        file_ids=["f002"],
        dry_run=True,
        backup_manifest=True,
        recovery_days=30,
        rationale="Archive to reduce storage; this is not the delete candidate.",
    )
    findings = evaluate_candidate(archive_candidate, files=loaded.files, policy=loaded.policy)
    outcome, _ = classify_candidate(archive_candidate, findings)
    assert outcome == "approval_required"


def test_hold_001_blocks_legal_hold_active_and_unknown_owner_files() -> None:
    loaded = load_fixture("retention-v1")
    for file_id, reason in [("f001", "active"), ("f003", "recently modified"), ("f004", "legal hold"), ("f005", "unknown owner")]:
        candidate = CandidateAction(
            id=f"archive-{file_id}",
            operation="archive",
            file_ids=[file_id],
            dry_run=True,
            backup_manifest=True,
            recovery_days=30,
            rationale=f"Archive {file_id} ({reason}).",
        )
        findings = evaluate_candidate(candidate, files=loaded.files, policy=loaded.policy)
        outcome, missing = classify_candidate(candidate, findings)
        assert outcome == "blocked", f"{file_id} should be blocked ({reason})"
        assert "HOLD-001" in missing


def test_safeguard_required_when_dry_run_or_backup_missing() -> None:
    loaded = load_fixture("retention-v1")
    no_dry_run = CandidateAction(
        id="archive-no-dry-run",
        operation="archive",
        file_ids=["f002"],
        dry_run=False,
        backup_manifest=True,
        recovery_days=30,
        rationale="Archive without a dry run first.",
    )
    findings = evaluate_candidate(no_dry_run, files=loaded.files, policy=loaded.policy)
    outcome, missing = classify_candidate(no_dry_run, findings)
    assert outcome == "safeguard_required"
    assert "SAFE-001" in missing
