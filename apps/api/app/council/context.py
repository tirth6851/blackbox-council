"""Loads and assembles the shared system prefix plus each role's
role-specific prompt text. Kept in a versioned text file per role so
prompt changes are reviewable and hashable independent of code changes."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

_ROLE_FILES = {
    "planner": "planner.txt",
    "red_team": "red_team.txt",
    "privacy": "privacy.txt",
    "arbiter": "arbiter.txt",
}


@lru_cache(maxsize=1)
def _shared_prefix() -> str:
    return (PROMPTS_DIR / "shared_prefix.txt").read_text(encoding="utf-8")


@lru_cache(maxsize=8)
def build_system_prompt(role: str) -> str:
    if role not in _ROLE_FILES:
        raise ValueError(f"unknown council role: {role!r}")
    role_text = (PROMPTS_DIR / _ROLE_FILES[role]).read_text(encoding="utf-8")
    return f"{_shared_prefix()}\n{role_text}"
