"""Provider interface shared by MockProvider and NebiusProvider.

Mode selection happens on the server; nothing here can call executor
functions, and no provider output is ever trusted as pre-authorized —
app.services.policy_engine and decision_service always have the final say.
"""
from __future__ import annotations

import abc
import datetime as dt
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

ValidationStatus = str  # "valid" | "invalid_schema" | "invalid_reference" | "empty" | "error"


@dataclass(frozen=True)
class CallMetadata:
    provider: str
    model: str
    role: str
    prompt_version: str
    schema_version: str
    requested_at: dt.datetime
    completed_at: dt.datetime
    duration_ms: float
    input_tokens: int | None
    output_tokens: int | None
    attempt: int
    finish_reason: str | None
    validation_status: ValidationStatus
    provider_request_id: str | None
    # Sanitized category only (e.g. "timeout", "auth_error"). Never an API
    # key, authorization header, or raw traceback.
    error_category: str | None


@dataclass(frozen=True)
class ProviderResult(Generic[T]):
    output: T | None
    metadata: CallMetadata


class ModelOutputError(Exception):
    """Raised once retry attempts are exhausted for a logical call. No
    partial recommendation is ever treated as safe when this is raised."""

    def __init__(self, category: str, message: str) -> None:
        self.category = category
        super().__init__(message)


class Provider(abc.ABC):
    name: str

    @abc.abstractmethod
    async def generate(
        self,
        *,
        role: str,
        system_prompt: str,
        input_payload: dict,
        output_model: type[T],
        prompt_version: str,
    ) -> ProviderResult[T]:
        """Run one logical evaluation pass and return a validated output
        plus call metadata. Implementations own their own retry policy but
        must report attempts truthfully in metadata.attempt."""
        raise NotImplementedError
