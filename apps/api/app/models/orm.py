"""ORM table definitions for runs/events/approvals/executions/simulation
state, per plan/01-phase-1-working-demo.md 1.5."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class RunORM(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(64), nullable=False)
    fixture_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    report_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class EventORM(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("run_id", "sequence", name="uq_events_run_sequence"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)


class ApprovalORM(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    action_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    choice: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expires_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)
    consumed_at: Mapped[dt.datetime | None] = mapped_column(nullable=True, default=None)


class ExecutionORM(Base):
    __tablename__ = "executions"
    __table_args__ = (UniqueConstraint("run_id", "action_hash", name="uq_executions_run_action_hash"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    action_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)


class SimulationStateORM(Base):
    __tablename__ = "simulation_state"

    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    simulated_archive_json: Mapped[str] = mapped_column(Text, nullable=False)
    backup_manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    rollback_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
