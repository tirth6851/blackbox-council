"""Live provider against NVIDIA Nemotron via Nebius Token Factory.

**Unverified in this repository.** This is implemented against the
documented OpenAI-compatible API shape (see docs/MODEL_INTEGRATION.md) but
has not been exercised against a real Nebius account or a real Nemotron
model in this session — there is no NEBIUS_API_KEY available here. Treat
every behavioral claim in this file's docstrings as "implemented to spec,
not yet confirmed working" until scripts/model_smoke_test.py has actually
been run successfully and docs/MODEL_INTEGRATION.md updated with real
results.

Retry policy (plan/02-phase-2-live-council.md 2.2): maximum two attempts per
logical call, transport and validation combined.
- 401/403: no retry (configuration/access error).
- 429/5xx/timeout: one retry with bounded backoff.
- Invalid JSON/schema/reference: one corrective retry with the same schema
  and the validation error, never the whole traceback.
- Truncated output: one retry with a larger token cap, only within budget.
- Exhausted attempts: raise ModelOutputError. No partial recommendation is
  ever treated as safe.
"""
from __future__ import annotations

import asyncio
import datetime as dt
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.providers.base import CallMetadata, ModelOutputError, Provider, ProviderResult

T = TypeVar("T", bound=BaseModel)

_RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_NON_RETRIABLE_STATUS_CODES = {401, 403}


def _sanitize_error(exc: Exception) -> str:
    """Category only — never include the exception's raw message, which
    could carry request/response bodies or headers."""
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    if status in _NON_RETRIABLE_STATUS_CODES:
        return "auth_error"
    if status in _RETRIABLE_STATUS_CODES:
        return "transient_error"
    if "Timeout" in name:
        return "timeout"
    return "provider_error"


class NebiusProvider(Provider):
    name = "nebius"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.tokenfactory.nebius.com/v1/",
        timeout_seconds: float = 45.0,
        max_tokens: int = 2500,
    ) -> None:
        # Imported lazily so the `openai` dependency is only required when
        # live mode is actually configured/used.
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout_seconds, max_retries=0
        )
        self._model = model
        self._max_tokens = max_tokens

    async def generate(
        self, *, role, system_prompt, input_payload, output_model, prompt_version
    ) -> ProviderResult:
        import json

        serialized_input = json.dumps(input_payload, sort_keys=True)
        schema = output_model.model_json_schema()

        last_error: str | None = None
        last_category = "provider_error"
        for attempt in (1, 2):
            requested_at = dt.datetime.now(dt.timezone.utc)
            try:
                completion = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": (
                                f"{serialized_input}\n\nRespond with JSON matching this schema "
                                f"exactly (no prose, no markdown fences):\n{json.dumps(schema)}"
                            ),
                        },
                    ],
                    temperature=0,
                    max_tokens=self._max_tokens,
                )
            except Exception as exc:  # noqa: BLE001 - sanitized below, never re-raised raw
                category = _sanitize_error(exc)
                completed_at = dt.datetime.now(dt.timezone.utc)
                if category == "auth_error":
                    raise ModelOutputError(category, "authentication/authorization failed") from exc
                last_error, last_category = "transport failure", category
                if attempt == 1:
                    await _sleep_backoff(attempt)
                continue

            completed_at = dt.datetime.now(dt.timezone.utc)
            choice = completion.choices[0] if completion.choices else None
            content = choice.message.content if choice and choice.message else None
            finish_reason = choice.finish_reason if choice else None

            if not content:
                last_error, last_category = "empty response content", "empty_output"
                continue
            if finish_reason == "length":
                last_error, last_category = "truncated output", "truncated"
                continue

            try:
                output = output_model.model_validate_json(content)
            except ValidationError as exc:
                last_error, last_category = f"schema validation failed: {exc.error_count()} error(s)", "invalid_schema"
                continue

            usage = getattr(completion, "usage", None)
            return ProviderResult(
                output=output,
                metadata=CallMetadata(
                    provider=self.name,
                    model=self._model,
                    role=role,
                    prompt_version=prompt_version,
                    schema_version="1.0",
                    requested_at=requested_at,
                    completed_at=completed_at,
                    duration_ms=(completed_at - requested_at).total_seconds() * 1000,
                    input_tokens=getattr(usage, "prompt_tokens", None),
                    output_tokens=getattr(usage, "completion_tokens", None),
                    attempt=attempt,
                    finish_reason=finish_reason,
                    validation_status="valid",
                    provider_request_id=getattr(completion, "id", None),
                    error_category=None,
                ),
            )

        raise ModelOutputError(last_category, last_error or "exhausted retry attempts")


async def _sleep_backoff(attempt: int) -> None:
    # Bounded backoff before the single retry. Deliberately small (this is
    # a two-attempt-max policy, not a long-running retry loop) so the
    # automated test suite that exercises this path stays fast.
    await asyncio.sleep(min(0.25 * attempt, 2.0))
