"""Request-budget enforcement wrapper (plan 2.6): a live run gets at most
LIVE_RUN_MAX_REQUESTS logical calls, and the whole server gets at most
DAILY_MODEL_CALL_CAP logical calls per UTC day.

Caveat, stated plainly: this counts logical provider.generate() calls, not
raw HTTP attempts (a provider's internal retry is one logical call even if
it makes two HTTP requests), and the daily counter is in-memory only — it
resets on process restart rather than persisting across it. That is a
known simplification, not a claim of a production rate limiter.
"""
from __future__ import annotations

import datetime as dt
import threading

from app.providers.base import ModelOutputError, Provider, ProviderResult


class _DailyCallCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day: dt.date | None = None
        self._count = 0

    def increment_and_check(self, cap: int) -> bool:
        """Returns True if the call is allowed (and counts it)."""
        today = dt.datetime.now(dt.timezone.utc).date()
        with self._lock:
            if self._day != today:
                self._day, self._count = today, 0
            if self._count >= cap:
                return False
            self._count += 1
            return True


_DAILY_COUNTER = _DailyCallCounter()


class BudgetExceededError(ModelOutputError):
    def __init__(self, message: str) -> None:
        super().__init__("budget_exceeded", message)


class BudgetedProvider(Provider):
    """Wraps another provider, enforcing a per-run call cap and the shared
    daily cap before delegating."""

    name = "budgeted"

    def __init__(self, delegate: Provider, *, max_requests_per_run: int, daily_cap: int) -> None:
        self._delegate = delegate
        self._max_requests_per_run = max_requests_per_run
        self._daily_cap = daily_cap
        self.calls_made = 0
        self.name = delegate.name

    async def generate(self, *, role, system_prompt, input_payload, output_model, prompt_version) -> ProviderResult:
        if self.calls_made >= self._max_requests_per_run:
            raise BudgetExceededError(
                f"run exceeded its budget of {self._max_requests_per_run} model calls"
            )
        if not _DAILY_COUNTER.increment_and_check(self._daily_cap):
            raise BudgetExceededError(f"daily model call cap of {self._daily_cap} reached")
        self.calls_made += 1
        return await self._delegate.generate(
            role=role,
            system_prompt=system_prompt,
            input_payload=input_payload,
            output_model=output_model,
            prompt_version=prompt_version,
        )
