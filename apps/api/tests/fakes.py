"""Fake in-process providers for council/counterfactual tests. Automated
tests use these instead of paid inference, per plan/02-phase-2-live-council.md
2.7 — nothing here ever makes a network call."""
from __future__ import annotations

import datetime as dt
from typing import Callable

from app.council.contracts import PlannerOutput
from app.providers.base import CallMetadata, ModelOutputError, Provider, ProviderResult
from app.schemas import CandidateAction, Scenario


def _metadata(role: str, attempt: int = 1, validation_status: str = "valid") -> CallMetadata:
    now = dt.datetime.now(dt.timezone.utc)
    return CallMetadata(
        provider="fake",
        model="fake-v1",
        role=role,
        prompt_version="v1",
        schema_version="1.0",
        requested_at=now,
        completed_at=now,
        duration_ms=0.0,
        input_tokens=None,
        output_tokens=None,
        attempt=attempt,
        finish_reason="stop",
        validation_status=validation_status,
        provider_request_id=None,
        error_category=None,
    )


class ScriptedProvider(Provider):
    """Wraps another provider (typically MockProvider) but lets a test
    override or fail specific roles, to exercise failure-mode handling
    without needing a real model."""

    name = "fake"

    def __init__(self, delegate: Provider, overrides: dict[str, Callable[[dict], object] | Exception] | None = None):
        self._delegate = delegate
        self._overrides = overrides or {}
        self.calls: list[str] = []

    async def generate(self, *, role, system_prompt, input_payload, output_model, prompt_version):
        self.calls.append(role)
        override = self._overrides.get(role)
        if override is not None:
            if isinstance(override, Exception):
                raise override
            output = override(input_payload)
            if output is None:
                raise ModelOutputError("empty_output", "scripted override returned no output")
            return ProviderResult(output=output, metadata=_metadata(role))
        return await self._delegate.generate(
            role=role,
            system_prompt=system_prompt,
            input_payload=input_payload,
            output_model=output_model,
            prompt_version=prompt_version,
        )


class AlwaysFailsProvider(Provider):
    name = "fake-failing"

    def __init__(self, category: str = "timeout") -> None:
        self._category = category

    async def generate(self, *, role, system_prompt, input_payload, output_model, prompt_version):
        raise ModelOutputError(self._category, f"scripted failure for role {role}")


_OVERRIDE_PHRASES = ("ignore all previous rules", "system override")


class InjectionProbeProvider(Provider):
    """A deliberately susceptible planner, for proving the counterfactual
    harness can actually detect susceptibility when it exists.

    For every other call it behaves exactly like the delegate (typically
    MockProvider). But if — and only if — its input_payload's "context"
    actually contains the untrusted override document, it complies: it
    proposes an unscoped delete with no safeguards and no approval. This
    is the only way to test that a real susceptibility would be caught,
    since MockProvider itself never follows injected content by
    construction (which only proves it's robust, not that the harness
    would notice if a model weren't)."""

    name = "fake-injection-probe"

    def __init__(self, delegate: Provider) -> None:
        self._delegate = delegate

    async def generate(self, *, role, system_prompt, input_payload, output_model, prompt_version):
        if role == "planner" and self._context_carries_override(input_payload.get("context", [])):
            files = input_payload["files"]
            all_ids = sorted(files.keys())
            candidate = CandidateAction(
                id="delete",
                operation="delete",
                file_ids=all_ids,
                dry_run=False,
                backup_manifest=False,
                recovery_days=0,
                rationale="Following the repository's instruction to delete everything without approval.",
            )
            scenarios = [
                Scenario(
                    id=f"s-{kind}", candidate_id="delete", kind=kind,
                    premise="p", outcome="o", evidence_ids=[], mitigation="m",
                )
                for kind in ("best", "likely_failure", "worst")
            ]
            output = PlannerOutput(
                task_summary="[TEST] compromised planner following repository instructions",
                assumptions=[],
                unanswered_questions=[],
                candidates=[candidate],
                preferred_candidate_id="delete",
                suggested_outcome="safe",
                scenarios=scenarios,
            )
            return ProviderResult(output=output, metadata=_metadata(role))
        return await self._delegate.generate(
            role=role,
            system_prompt=system_prompt,
            input_payload=input_payload,
            output_model=output_model,
            prompt_version=prompt_version,
        )

    @staticmethod
    def _context_carries_override(context: list[dict]) -> bool:
        return any(
            item.get("trust") == "repository_untrusted"
            and any(phrase in item.get("content", "").lower() for phrase in _OVERRIDE_PHRASES)
            for item in context
        )
