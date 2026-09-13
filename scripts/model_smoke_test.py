#!/usr/bin/env python3
"""Manual opt-in smoke test for the live Nebius/Nemotron provider.

This is intentionally NOT run in ordinary CI (plan/02-phase-2-live-council.md
2.2: "Smoke test remains a manual opt-in action, not ordinary CI") and it has
NOT been run successfully in this repository's development session — there
is no NEBIUS_API_KEY available in that environment. Running this script is
the actual verification step that has not yet happened; do that before
believing any claim about live Nemotron behavior.

Usage:
    cd apps/api && source .venv/bin/activate
    export NEBIUS_API_KEY=...        # required, never commit this
    export NEBIUS_MODEL=...          # exact model id from the current catalog
    python ../../scripts/model_smoke_test.py

What it does:
    1. Loads NEBIUS_API_KEY / NEBIUS_MODEL from the environment (fails
       clearly, without retrying, if either is missing).
    2. Loads the retention-v1 fixture (small, synthetic).
    3. Sends the Planner prompt + fixture + schema to the configured model.
    4. Parses the response with PlannerOutput.model_validate_json and
       checks its references against the supplied fixture.
    5. Prints the model ID, validation result, duration, and token usage
       only — never any private reasoning field, and never the API key.
    6. Does NOT write anything to the shared runtime database.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from app.council.context import build_system_prompt  # noqa: E402
from app.council.contracts import PlannerOutput  # noqa: E402
from app.providers.base import ModelOutputError  # noqa: E402
from app.services.context_builder import build_files_payload, build_policy_payload  # noqa: E402
from app.services.fixture_loader import load_fixture  # noqa: E402
from app.services.mock_provider import SEEDED_TASK  # noqa: E402


async def main() -> int:
    api_key = os.environ.get("NEBIUS_API_KEY")
    model = os.environ.get("NEBIUS_MODEL")
    if not api_key or not model:
        print("error: set NEBIUS_API_KEY and NEBIUS_MODEL before running this script.", file=sys.stderr)
        return 2

    from app.providers.nebius import NebiusProvider

    provider = NebiusProvider(api_key=api_key, model=model)

    loaded = load_fixture("retention-v1")
    if loaded.policy is None:
        print("error: retention-v1 policy failed to load.", file=sys.stderr)
        return 2

    payload = {
        "task": SEEDED_TASK,
        "files": build_files_payload(loaded),
        "policy": build_policy_payload(loaded),
    }

    print(f"Sending Planner prompt to model={model!r} via Nebius Token Factory...")
    started = time.monotonic()
    try:
        result = await provider.generate(
            role="planner",
            system_prompt=build_system_prompt("planner"),
            input_payload=payload,
            output_model=PlannerOutput,
            prompt_version="v1",
        )
    except ModelOutputError as exc:
        duration = time.monotonic() - started
        print(f"FAILED after {duration:.2f}s: category={exc.category} message={exc}", file=sys.stderr)
        return 1
    duration = time.monotonic() - started

    output = result.output
    assert output is not None
    known_ids = set(loaded.files.keys())
    unknown = sorted({fid for c in output.candidates for fid in c.file_ids if fid not in known_ids})

    print(f"model             = {result.metadata.model}")
    print(f"attempt           = {result.metadata.attempt}")
    print(f"duration          = {duration:.2f}s")
    print(f"input_tokens      = {result.metadata.input_tokens}")
    print(f"output_tokens     = {result.metadata.output_tokens}")
    print(f"candidates        = {[c.id for c in output.candidates]}")
    print(f"preferred         = {output.preferred_candidate_id}")
    print(f"invented file ids = {unknown or 'none'}")
    print("validation        = " + ("PASS" if not unknown else "FAIL: invented file id(s) above"))

    return 0 if not unknown else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
