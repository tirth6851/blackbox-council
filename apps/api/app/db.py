"""SQLAlchemy engine/session wiring for the SQLite-backed audit store.

One process, one backend instance. Foreign keys and a busy timeout are set
on every connection; transactions are kept short. This is an auditable
application record, not tamper-proof storage.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def _apply_sqlite_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def build_engine(database_url: str, runtime_dir: Path) -> Engine:
    if database_url.startswith("sqlite:///") and database_url != "sqlite:///:memory:":
        runtime_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)
    _apply_sqlite_pragmas(engine)
    # Import models so they register on Base.metadata before create_all.
    from app.models import orm  # noqa: F401

    Base.metadata.create_all(engine)
    return engine


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
