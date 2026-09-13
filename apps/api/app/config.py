"""Environment-backed application settings.

Loaded explicitly from apps/api/.env relative to this file, never from the
process working directory, so behavior does not change with the caller's
current directory.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
API_ROOT = APP_DIR.parent
ENV_FILE = API_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    model_mode: str = Field(default="mock", alias="MODEL_MODE")
    database_url: str = Field(
        default="sqlite:///./runtime/blackbox.db", alias="DATABASE_URL"
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"], alias="CORS_ORIGINS"
    )

    # Phase 2 / live provider configuration. All optional so Phase 1 mock
    # mode never requires them.
    nebius_api_key: str | None = Field(default=None, alias="NEBIUS_API_KEY")
    nebius_model: str | None = Field(default=None, alias="NEBIUS_MODEL")
    nebius_base_url: str = Field(
        default="https://api.tokenfactory.nebius.com/v1/", alias="NEBIUS_BASE_URL"
    )
    model_timeout_seconds: float = Field(default=45.0, alias="MODEL_TIMEOUT_SECONDS")
    live_run_max_requests: int = Field(default=18, alias="LIVE_RUN_MAX_REQUESTS")
    live_run_concurrency: int = Field(default=1, alias="LIVE_RUN_CONCURRENCY")
    live_run_deadline_seconds: int = Field(default=600, alias="LIVE_RUN_DEADLINE_SECONDS")
    daily_model_call_cap: int = Field(default=200, alias="DAILY_MODEL_CALL_CAP")
    operator_credential: str | None = Field(default=None, alias="OPERATOR_CREDENTIAL")

    @property
    def runtime_dir(self) -> Path:
        """Server-owned absolute path for runtime/database state."""
        raw = self.database_url
        if raw.startswith("sqlite:///"):
            db_path = raw.removeprefix("sqlite:///")
            if db_path == ":memory:":
                return API_ROOT / "runtime"
            path = Path(db_path)
            if not path.is_absolute():
                path = API_ROOT / path
            return path.parent
        return API_ROOT / "runtime"

    def resolved_database_url(self) -> str:
        """Return a sqlite URL pointing at an absolute, server-owned path."""
        if self.database_url.startswith("sqlite:///") and self.database_url != "sqlite:///:memory:":
            db_path = self.database_url.removeprefix("sqlite:///")
            if db_path == ":memory:":
                return self.database_url
            path = Path(db_path)
            if not path.is_absolute():
                path = API_ROOT / path
            return f"sqlite:///{path}"
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
