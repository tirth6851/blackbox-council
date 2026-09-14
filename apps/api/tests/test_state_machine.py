from app.schemas import is_valid_transition


def test_allowed_forward_transitions() -> None:
    assert is_valid_transition("created", "evaluating")
    assert is_valid_transition("evaluating", "decision_ready")
    assert is_valid_transition("decision_ready", "awaiting_approval")
    assert is_valid_transition("awaiting_approval", "approved")
    assert is_valid_transition("approved", "executing")
    assert is_valid_transition("executing", "completed")


def test_terminal_states_reject_all_transitions() -> None:
    for terminal in ("completed", "rejected", "needs_clarification", "needs_safeguards", "blocked", "failed"):
        assert not is_valid_transition(terminal, "executing")
        assert not is_valid_transition(terminal, "completed")


def test_blocked_or_failed_or_rejected_cannot_jump_to_executing() -> None:
    assert not is_valid_transition("blocked", "executing")
    assert not is_valid_transition("failed", "executing")
    assert not is_valid_transition("rejected", "executing")


def test_created_cannot_skip_straight_to_executing() -> None:
    assert not is_valid_transition("created", "executing")
