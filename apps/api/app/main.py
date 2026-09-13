"""FastAPI application factory.

create_app(settings=None) so tests can inject an isolated in-memory or
temp-file database instead of the real runtime path. No database creation
happens at module import time.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.db import build_engine, build_session_factory
from app.errors import AppError


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(title="BlackBox Council")
    app.state.settings = settings

    engine = build_engine(settings.resolved_database_url(), settings.runtime_dir)
    app.state.engine = engine
    app.state.session_factory = build_session_factory(engine)

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
