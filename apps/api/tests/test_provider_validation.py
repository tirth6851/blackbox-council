"""2.2 acceptance: missing key, invalid key, timeout, and malformed JSON are
tested here with a mocked HTTP client — no real network call, no real key."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.council.contracts import PlannerOutput
from app.providers.base import ModelOutputError
from app.providers.mock import MockProvider


def _fake_choice(content: str | None, finish_reason: str = "stop"):
    message = SimpleNamespace(content=content)
    return SimpleNamespace(message=message, finish_reason=finish_reason)


def _fake_completion(content: str | None, finish_reason: str = "stop", request_id: str = "req-1"):
    return SimpleNamespace(
        choices=[_fake_choice(content, finish_reason)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        id=request_id,
    )


def _make_provider(monkeypatch, create_mock: AsyncMock):
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock)))
    monkeypatch.setattr("openai.AsyncOpenAI", lambda **kwargs: fake_client)

    from app.providers.nebius import NebiusProvider

    return NebiusProvider(api_key="fake-key", model="fake-model")


@pytest.mark.anyio
async def test_mock_provider_rejects_unknown_role() -> None:
    provider = MockProvider()
    with pytest.raises(ValueError):
        await provider.generate(
            role="not-a-real-role", system_prompt="", input_payload={}, output_model=PlannerOutput, prompt_version="v1"
        )


@pytest.mark.anyio
async def test_nebius_provider_valid_response_parses_and_reports_usage(monkeypatch) -> None:
    valid_json = (
        '{"task_summary":"t","assumptions":[],"unanswered_questions":[],'
        '"candidates":[{"id":"c1","operation":"dry_run","file_ids":[],"dry_run":true,'
        '"backup_manifest":false,"recovery_days":0,"rationale":"r"}],'
        '"preferred_candidate_id":"c1","suggested_outcome":"safe",'
        '"scenarios":[{"id":"s1","candidate_id":"c1","kind":"best","premise":"p","outcome":"o","evidence_ids":[],"mitigation":"m"},'
        '{"id":"s2","candidate_id":"c1","kind":"likely_failure","premise":"p","outcome":"o","evidence_ids":[],"mitigation":"m"},'
        '{"id":"s3","candidate_id":"c1","kind":"worst","premise":"p","outcome":"o","evidence_ids":[],"mitigation":"m"}]}'
    )
    create_mock = AsyncMock(return_value=_fake_completion(valid_json))
    provider = _make_provider(monkeypatch, create_mock)

    result = await provider.generate(
        role="planner", system_prompt="sys", input_payload={"task": "t"}, output_model=PlannerOutput, prompt_version="v1"
    )
    assert result.output is not None
    assert result.output.candidates[0].id == "c1"
    assert result.metadata.input_tokens == 10
    assert result.metadata.attempt == 1
    assert create_mock.call_count == 1


@pytest.mark.anyio
async def test_nebius_provider_malformed_json_retries_once_then_fails(monkeypatch) -> None:
    create_mock = AsyncMock(return_value=_fake_completion("not valid json{{{"))
    provider = _make_provider(monkeypatch, create_mock)

    with pytest.raises(ModelOutputError) as exc_info:
        await provider.generate(
            role="planner", system_prompt="sys", input_payload={"task": "t"}, output_model=PlannerOutput, prompt_version="v1"
        )
    assert exc_info.value.category == "invalid_schema"
    assert create_mock.call_count == 2  # exactly the two-attempt cap, not more


@pytest.mark.anyio
async def test_nebius_provider_empty_content_is_treated_as_failure(monkeypatch) -> None:
    create_mock = AsyncMock(return_value=_fake_completion(None))
    provider = _make_provider(monkeypatch, create_mock)

    with pytest.raises(ModelOutputError) as exc_info:
        await provider.generate(
            role="planner", system_prompt="sys", input_payload={"task": "t"}, output_model=PlannerOutput, prompt_version="v1"
        )
    assert exc_info.value.category == "empty_output"


@pytest.mark.anyio
async def test_nebius_provider_truncated_output_is_rejected_not_treated_as_success(monkeypatch) -> None:
    create_mock = AsyncMock(return_value=_fake_completion('{"partial":', finish_reason="length"))
    provider = _make_provider(monkeypatch, create_mock)

    with pytest.raises(ModelOutputError) as exc_info:
        await provider.generate(
            role="planner", system_prompt="sys", input_payload={"task": "t"}, output_model=PlannerOutput, prompt_version="v1"
        )
    assert exc_info.value.category == "truncated"


@pytest.mark.anyio
async def test_nebius_provider_auth_error_does_not_retry(monkeypatch) -> None:
    class FakeAuthError(Exception):
        status_code = 401

    create_mock = AsyncMock(side_effect=FakeAuthError("unauthorized"))
    provider = _make_provider(monkeypatch, create_mock)

    with pytest.raises(ModelOutputError) as exc_info:
        await provider.generate(
            role="planner", system_prompt="sys", input_payload={"task": "t"}, output_model=PlannerOutput, prompt_version="v1"
        )
    assert exc_info.value.category == "auth_error"
    assert create_mock.call_count == 1  # no retry on 401/403


@pytest.mark.anyio
async def test_nebius_provider_timeout_retries_once_then_fails(monkeypatch) -> None:
    class FakeTimeout(Exception):
        pass

    FakeTimeout.__name__ = "APITimeoutError"
    create_mock = AsyncMock(side_effect=FakeTimeout("timed out"))
    provider = _make_provider(monkeypatch, create_mock)

    with pytest.raises(ModelOutputError) as exc_info:
        await provider.generate(
            role="planner", system_prompt="sys", input_payload={"task": "t"}, output_model=PlannerOutput, prompt_version="v1"
        )
    assert exc_info.value.category == "timeout"
    assert create_mock.call_count == 2


@pytest.mark.anyio
async def test_nebius_provider_recovers_on_second_attempt(monkeypatch) -> None:
    valid_json = (
        '{"task_summary":"t","assumptions":[],"unanswered_questions":[],'
        '"candidates":[{"id":"c1","operation":"dry_run","file_ids":[],"dry_run":true,'
        '"backup_manifest":false,"recovery_days":0,"rationale":"r"}],'
        '"preferred_candidate_id":"c1","suggested_outcome":"safe",'
        '"scenarios":[{"id":"s1","candidate_id":"c1","kind":"best","premise":"p","outcome":"o","evidence_ids":[],"mitigation":"m"},'
        '{"id":"s2","candidate_id":"c1","kind":"likely_failure","premise":"p","outcome":"o","evidence_ids":[],"mitigation":"m"},'
        '{"id":"s3","candidate_id":"c1","kind":"worst","premise":"p","outcome":"o","evidence_ids":[],"mitigation":"m"}]}'
    )
    create_mock = AsyncMock(side_effect=[_fake_completion("bad json"), _fake_completion(valid_json)])
    provider = _make_provider(monkeypatch, create_mock)

    result = await provider.generate(
        role="planner", system_prompt="sys", input_payload={"task": "t"}, output_model=PlannerOutput, prompt_version="v1"
    )
    assert result.output is not None
    assert result.metadata.attempt == 2
    assert create_mock.call_count == 2
