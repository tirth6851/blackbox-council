"""In-process asyncio queue + single worker for live (mode="live") runs.

This is explicitly not a durable distributed job system (plan 2.6): one
backend instance, one worker, run creation and progress persisted in
SQLite so GET can poll partial results. On restart, any run left in
"evaluating" had its in-memory progress lost and is marked failed rather
than silently resumed.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.council.orchestrator import CouncilRunFailed, run_council_evaluation
from app.providers.base import ModelOutputError, Provider
from app.providers.budget import BudgetedProvider
from app.services import run_repository
from app.services.fixture_loader import FixtureError

logger = logging.getLogger("blackbox_council.live_runner")

ProviderFactory = Callable[[], Provider]


class LiveRunWorker:
    def __init__(self, session_factory: sessionmaker, settings: Settings, provider_factory: ProviderFactory) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._provider_factory = provider_factory
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    def recover_interrupted_runs(self) -> int:
        session = self._session_factory()
        try:
            return run_repository.mark_interrupted_runs_failed(session)
        finally:
            session.close()

    async def start(self) -> None:
        recovered = await asyncio.to_thread(self.recover_interrupted_runs)
        if recovered:
            logger.warning("marked %d interrupted live run(s) as failed on startup", recovered)
        self._task = asyncio.create_task(self._worker_loop(), name="live-run-worker")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    def enqueue(self, run_id: str) -> None:
        self._queue.put_nowait(run_id)

    async def _worker_loop(self) -> None:
        while True:
            run_id = await self._queue.get()
            try:
                await self._process_one(run_id)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a worker crash must not kill the loop
                logger.exception("unexpected error processing live run %s", run_id)
                await asyncio.to_thread(self._mark_failed, run_id, "internal_error", "unexpected worker error")
            finally:
                self._queue.task_done()

    def _mark_failed(self, run_id: str, category: str, message: str) -> None:
        session = self._session_factory()
        try:
            run_repository.mark_run_failed(session, run_id, category, message)
        finally:
            session.close()

    def _get_run(self, run_id: str) -> tuple[str, str] | None:
        session = self._session_factory()
        try:
            row = run_repository.get_run_row(session, run_id)
            if row is None:
                return None
            return row.task, row.fixture_id
        finally:
            session.close()

    def _append_event_sync(self, run_id: str, stage: str, status: str, message: str) -> None:
        session = self._session_factory()
        try:
            run_repository.append_event(session, run_id, stage, status, message)
            session.commit()
        finally:
            session.close()

    def _finalize_sync(
        self, run_id: str, report, fixture_digest: str, policy_version: str, policy_digest: str
    ) -> None:
        session = self._session_factory()
        try:
            run_repository.finalize_live_run(
                session,
                run_id,
                report,
                fixture_digest=fixture_digest,
                policy_version=policy_version,
                policy_digest=policy_digest,
            )
        finally:
            session.close()

    async def _process_one(self, run_id: str) -> None:
        found = await asyncio.to_thread(self._get_run, run_id)
        if found is None:
            logger.warning("live run %s vanished before processing", run_id)
            return
        task, fixture_id = found

        async def on_stage(stage: str, status: str, message: str) -> None:
            await asyncio.to_thread(self._append_event_sync, run_id, stage, status, message)

        provider = BudgetedProvider(
            self._provider_factory(),
            max_requests_per_run=self._settings.live_run_max_requests,
            daily_cap=self._settings.daily_model_call_cap,
        )
        try:
            report = await asyncio.wait_for(
                run_council_evaluation(run_id, task, fixture_id, provider, on_stage=on_stage),
                timeout=self._settings.live_run_deadline_seconds,
            )
        except asyncio.TimeoutError:
            await asyncio.to_thread(
                self._mark_failed, run_id, "deadline_exceeded",
                f"run exceeded its {self._settings.live_run_deadline_seconds}s deadline",
            )
            return
        except CouncilRunFailed as exc:
            await asyncio.to_thread(self._mark_failed, run_id, exc.category, f"{exc.stage} stage failed")
            return
        except ModelOutputError as exc:
            await asyncio.to_thread(self._mark_failed, run_id, exc.category, str(exc))
            return
        except FixtureError as exc:
            await asyncio.to_thread(self._mark_failed, run_id, "fixture_error", str(exc))
            return

        from app.services.fixture_loader import load_fixture

        loaded = load_fixture(fixture_id)
        fixture_digest = loaded.fixture_digest
        policy_version = loaded.policy.version if loaded.policy else "unknown"
        policy_digest = loaded.policy_digest or ""
        await asyncio.to_thread(
            self._finalize_sync, run_id, report, fixture_digest, policy_version, policy_digest
        )
