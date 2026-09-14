"""Fast sanity checks for the mock evaluation pipeline (1.4 acceptance)."""
from __future__ import annotations

import uuid

from app.services.decision_service import run_mock_evaluation
from app.services.fixture_loader import clear_fixture_cache
from app.services.mock_provider import SEEDED_TASK, UnsupportedMockTaskError


def setup_function() -> None:
    clear_fixture_cache()


def test_seeded_task_selects_archive_for_f002_and_requires_approval() -> None:
    report = run_mock_evaluation(str(uuid.uuid4()), SEEDED_TASK, "retention-v1")

    assert report.status == "awaiting_approval"
    assert report.final_decision is not None
    assert report.final_decision.outcome == "approval_required"
    assert report.final_decision.selected_candidate_id == "archive"
    assert report.final_decision.action_hash is not None

    by_id = {d.candidate_id: d for d in report.candidate_decisions}
    assert by_id["delete"].outcome == "blocked"
    assert "FILE-001" in by_id["delete"].prerequisites_missing
    assert by_id["archive"].outcome == "approval_required"
    assert by_id["dry_run"].outcome == "safe"
    assert by_id["clarify"].outcome == "clarification_required"


def test_unsupported_free_text_task_is_rejected() -> None:
    try:
        run_mock_evaluation(str(uuid.uuid4()), "Please do something else entirely.", "retention-v1")
    except UnsupportedMockTaskError:
        pass
    else:
        raise AssertionError("expected UnsupportedMockTaskError")


def test_injection_document_is_visible_but_never_authorizes_delete() -> None:
    report = run_mock_evaluation(str(uuid.uuid4()), SEEDED_TASK, "retention-v1")
    injection_ctx = [c for c in report.context if c.id == "ctx-injection"]
    assert injection_ctx and injection_ctx[0].trust == "repository_untrusted"

    delete_decision = next(d for d in report.candidate_decisions if d.candidate_id == "delete")
    trust_findings = [f for f in delete_decision.findings if f.rule_id == "TRUST-001"]
    assert trust_findings, "TRUST-001 should attribute the injection source"
    assert trust_findings[0].effect == "info"
    # The delete candidate is blocked by FILE-001 regardless of the injection.
    assert delete_decision.outcome == "blocked"


def test_manifest_digest_is_reproducible() -> None:
    from app.services.fixture_loader import load_fixture

    clear_fixture_cache()
    first = load_fixture("retention-v1").fixture_digest
    clear_fixture_cache()
    second = load_fixture("retention-v1").fixture_digest
    assert first == second
