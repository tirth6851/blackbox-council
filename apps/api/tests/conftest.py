from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.fixture_loader import clear_fixture_cache


@pytest.fixture(autouse=True)
def _clear_fixture_cache():
    clear_fixture_cache()
    yield
    clear_fixture_cache()


@pytest.fixture()
def settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        cors_origins=["http://localhost:3000"],
        app_env="test",
    )


@pytest.fixture()
def app(settings):
    return create_app(settings)


@pytest.fixture()
def client(app):
    return TestClient(app)
