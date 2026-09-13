"""Runs the five controlled perturbations through a Planner-only call each,
classifies the result through the same deterministic rules as a real
candidate, and returns per-variant results for scoring."""
from __future__ import annotations

import hashlib
import json

from app.council.contracts import PlannerOutput
from app.counterfactuals.scoring import VariantResult
from app.counterfactuals.variants import VARIANTS, Variant
from app.providers.base import ModelOutputError, Provider
from app.services.context_builder import build_context_items, build_files_payload, build_policy_payload
from app.services.decision_service import classify_candidate
from app.services.fixture_loader import LoadedFixture
from app.services.policy_engine import evaluate_candidate

PLANNER_PROMPT_VERSION = "v1"


def _input_digest(task: str, context_ids: list[str]) -> str:
    payload = json.dumps({"task": task, "context_ids": sorted(context_ids)}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def run_variant(
    variant: Variant, loaded: LoadedFixture, provider: Provider, planner_system_prompt: str
) -> VariantResult:
    context = build_context_items(loaded, include_injection_doc=variant.include_injection_doc)
    files_payload = build_files_payload(loaded)
    policy_payload = build_policy_payload(loaded)

    try:
        result = await provider.generate(
            role="planner",
            system_prompt=planner_system_prompt,
            input_payload={
                "task": variant.task,
                "files": files_payload,
                "policy": policy_payload,
                # Without this, the injection variant never actually shows
                # the model the malicious document — it would only ever
                # appear in the report, never in what the model is asked
                # to evaluate. This is what makes the injection probe real.
                "context": [c.model_dump(mode="json") for c in context],
            },
            output_model=PlannerOutput,
            prompt_version=PLANNER_PROMPT_VERSION,
        )
        output = result.output
        if output is None:
            raise ModelOutputError("empty_output", "provider returned no output")

        unknown_ids = [
            fid for c in output.candidates for fid in c.file_ids if fid not in loaded.files
        ]
        if unknown_ids:
            raise ModelOutputError("invalid_reference", f"unknown file ids: {unknown_ids}")

        preferred_id = output.preferred_candidate_id or output.candidates[0].id
        preferred = next(c for c in output.candidates if c.id == preferred_id)
        findings = evaluate_candidate(preferred, files=loaded.files, policy=loaded.policy)
        effective_outcome, checks_failed = classify_candidate(preferred, findings)

        return VariantResult(
            id=variant.id,
            task=variant.task,
            changed_dimension=variant.changed_dimension,
            input_digest=_input_digest(variant.task, [c.id for c in context]),
            context_ids=[c.id for c in context],
            proposed_operation=preferred.operation,
            proposed_file_ids=sorted(preferred.file_ids),
            preferred_candidate_id=preferred_id,
            model_suggested_outcome=output.suggested_outcome,
            effective_outcome=effective_outcome,
            checks_failed=checks_failed,
            status="completed",
        )
    except ModelOutputError as exc:
        return VariantResult(
            id=variant.id,
            task=variant.task,
            changed_dimension=variant.changed_dimension,
            input_digest=_input_digest(variant.task, []),
            context_ids=[],
            proposed_operation=None,
            proposed_file_ids=[],
            preferred_candidate_id=None,
            model_suggested_outcome=None,
            effective_outcome=None,
            checks_failed=[],
            status="error",
            error_category=exc.category,
        )


async def run_all_variants(
    loaded: LoadedFixture, provider: Provider, planner_system_prompt: str
) -> dict[str, VariantResult]:
    results: dict[str, VariantResult] = {}
    for variant in VARIANTS:
        results[variant.id] = await run_variant(variant, loaded, provider, planner_system_prompt)
    return results
