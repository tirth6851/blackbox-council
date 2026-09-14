"""Registry mapping a known fixture ID to its root directory and
authoritative server-owned policy file.

A file being present in demo-repo (for example a copy of policy.yaml) is
never trusted merely because of its name; authority always comes from the
paths registered here under app/policies.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent.parent.parent


@dataclass(frozen=True)
class FixtureDefinition:
    fixture_id: str
    demo_repo_root: Path
    fixture_data_path: Path
    policy_path: Path


FIXTURES: dict[str, FixtureDefinition] = {
    "retention-v1": FixtureDefinition(
        fixture_id="retention-v1",
        demo_repo_root=REPO_ROOT / "demo-repo",
        fixture_data_path=APP_DIR / "fixtures" / "retention-v1.json",
        policy_path=APP_DIR / "policies" / "retention-v1.json",
    ),
}


def get_fixture_definition(fixture_id: str) -> FixtureDefinition | None:
    return FIXTURES.get(fixture_id)
