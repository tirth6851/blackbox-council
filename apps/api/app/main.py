"""FastAPI application factory.

create_app(settings=None) so tests can inject an isolated in-memory or
temp-file database instead of the real runtime path. No database creation
happens at module import time.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.db import build_engine, build_session_factory
from app.errors import AppError
from app.providers.base import Provider
from app.services.live_runner import LiveRunWorker


def _default_live_provider_factory(settings: Settings):
    def factory() -> Provider:
        if not settings.nebius_api_key or not settings.nebius_model:
            raise RuntimeError(
                "live mode is not configured: set NEBIUS_API_KEY and NEBIUS_MODEL"
            )
        from app.providers.nebius import NebiusProvider

        return NebiusProvider(
            api_key=settings.nebius_api_key,
            model=settings.nebius_model,
            base_url=settings.nebius_base_url,
            timeout_seconds=settings.model_timeout_seconds,
        )

    return factory


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    engine = build_engine(settings.resolved_database_url(), settings.runtime_dir)
    session_factory = build_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        worker = LiveRunWorker(session_factory, settings, lambda: app.state.live_provider_factory())
        app.state.live_worker = worker
        await worker.start()
        try:
            yield
        finally:
            await worker.stop()

    app = FastAPI(title="BlackBox Council", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    # Tests may override this with a fake/mock provider factory to exercise
    # the live-mode path without a real Nebius account.
    app.state.live_provider_factory = _default_live_provider_factory(settings)
    app.state.live_mode_configured = lambda: bool(settings.nebius_api_key and settings.nebius_model)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    def _handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "mode": settings.model_mode}

    from app.api.evaluations import router as evaluations_router

    app.include_router(evaluations_router)

    return app


app = create_app()
