"""Persistence helpers over the runs/events/approvals/executions/
simulation_state tables. Short transactions; callers commit explicitly."""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from app.models.orm import ApprovalORM, EventORM, ExecutionORM, RunORM, SimulationStateORM
from app.schemas import ApprovalRecord, EvaluationReport, ExecutionRecord
from app.schemas import EventRecord as EventRecordSchema
from app.schemas import RunStatus

APPROVAL_TTL_MINUTES = 10


def create_run(session: Session, report: EvaluationReport, *, fixture_digest: str, policy_version: str) -> None:
    row = RunORM(
        id=report.run_id,
        mode=report.mode,
        status=report.status,
        version=1,
        task=report.task,
        fixture_id=report.fixture_id,
        fixture_digest=fixture_digest,
        policy_version=policy_version,
        report_json=json.dumps(report.model_dump(mode="json")),
    )
    session.add(row)
    # Flush the parent row first: plain foreign-key columns (no ORM
    # relationship() is declared between these tables) give SQLAlchemy no
    # dependency edge to order inserts by, so without this the events
    # insert can be emitted before the run insert and violate the FK.
    session.flush()
    for event in report.events:
        session.add(
            EventORM(
                run_id=report.run_id,
                sequence=event.sequence,
                stage=event.stage,
                status=event.status,
                message=event.message,
                created_at=event.created_at,
            )
        )
    session.commit()


def create_placeholder_run(session: Session, run_id: str, *, mode: str, task: str, fixture_id: str) -> None:
    """Phase 2.6: live mode returns 202 immediately. This inserts a minimal
    row with status="evaluating" that the background worker will later
    overwrite via finalize_live_run / mark_run_failed."""
    stub = EvaluationReport(
        run_id=run_id,
        mode=mode,  # type: ignore[arg-type]
        status="evaluating",
        task=task,
        fixture_id=fixture_id,
        context=[],
        plan=None,
        reviews=[],
        scenarios=[],
        candidate_decisions=[],
        final_decision=None,
        events=[],
    )
    row = RunORM(
        id=run_id,
        mode=mode,
        status="evaluating",
        version=1,
        task=task,
        fixture_id=fixture_id,
        fixture_digest="",
        policy_version="",
        report_json=json.dumps(stub.model_dump(mode="json")),
    )
    session.add(row)
    session.flush()
    append_event(session, run_id, "created", "ok", "Run created.")
    append_event(session, run_id, "evaluating", "ok", "Queued for live evaluation.")
    session.commit()


def finalize_live_run(
    session: Session, run_id: str, report: EvaluationReport, *, fixture_digest: str, policy_version: str
) -> None:
    row = get_run_row(session, run_id)
    if row is None:
        return
    row.status = report.status
    row.fixture_digest = fixture_digest
    row.policy_version = policy_version
    row.report_json = json.dumps(report.model_dump(mode="json"))
    row.version += 1
    row.updated_at = dt.datetime.now(dt.timezone.utc)
    session.commit()


def mark_run_failed(session: Session, run_id: str, category: str, message: str) -> None:
    row = get_run_row(session, run_id)
    if row is None:
        return
    row.status = "failed"
    row.version += 1
    row.updated_at = dt.datetime.now(dt.timezone.utc)
    append_event(session, run_id, "failed", "error", f"{category}: {message}")
    session.commit()


def mark_interrupted_runs_failed(session: Session) -> int:
    """Startup recovery (2.6): a run left in 'evaluating' across a process
    restart had its in-memory progress lost. Never silently resume partial
    deliberation — mark it failed and let the caller start a new run."""
    stuck = session.execute(select(RunORM).where(RunORM.status == "evaluating")).scalars().all()
    for row in stuck:
        row.status = "failed"
        row.version += 1
        append_event(session, row.id, "failed", "error", "process_interrupted: server restarted mid-evaluation.")
    if stuck:
        session.commit()
    return len(stuck)


def count_active_live_runs(session: Session) -> int:
    return session.execute(
        select(func.count()).select_from(RunORM).where(RunORM.mode == "live", RunORM.status == "evaluating")
    ).scalar_one()


def get_run_row(session: Session, run_id: str) -> RunORM | None:
    return session.get(RunORM, run_id)


def append_event(session: Session, run_id: str, stage: str, status: str, message: str) -> None:
    last = session.execute(
        select(EventORM).where(EventORM.run_id == run_id).order_by(EventORM.sequence.desc())
    ).scalars().first()
    next_sequence = (last.sequence + 1) if last else 0
    session.add(
        EventORM(run_id=run_id, sequence=next_sequence, stage=stage, status=status, message=message)
    )
    # Autoflush is off for this session factory, so without this a second
    # append_event call in the same transaction would not see the row just
    # added above and would race for the same sequence number.
    session.flush()


def set_run_status(session: Session, row: RunORM, new_status: RunStatus, *, expected_version: int) -> bool:
    """Atomic compare-and-swap. A prior SELECT-then-mutate-the-ORM-object
    approach is not actually atomic: SQLAlchemy's autoflush UPDATE filters
    only by primary key, not by the version read earlier, so a concurrent
    writer could commit in between and this would silently overwrite it.
    This instead issues one UPDATE ... WHERE id=:id AND version=:expected
    and treats rowcount==1 as the only proof of winning the race."""
    result = session.execute(
        sa_update(RunORM)
        .where(RunORM.id == row.id, RunORM.version == expected_version)
        .values(status=new_status, version=expected_version + 1, updated_at=dt.datetime.now(dt.timezone.utc))
    )
    if result.rowcount != 1:
        return False
    # Sync the passed-in ORM object from the database rather than mutating
    # its attributes by hand: refresh() clears dirty-tracking too, so a
    # later ORM autoflush can't re-issue a conflicting unconditional UPDATE
    # over whatever a concurrent transaction writes next.
    session.refresh(row)
    return True


def get_latest_approval(session: Session, run_id: str, action_hash: str) -> ApprovalORM | None:
    return session.execute(
        select(ApprovalORM)
        .where(ApprovalORM.run_id == run_id, ApprovalORM.action_hash == action_hash)
        .order_by(ApprovalORM.created_at.desc())
    ).scalars().first()


def save_approval(
    session: Session, run_id: str, action_hash: str, choice: str, reason: str
) -> ApprovalORM:
    now = dt.datetime.now(dt.timezone.utc)
    row = ApprovalORM(
        run_id=run_id,
        action_hash=action_hash,
        choice=choice,
        reason=reason,
        expires_at=now + dt.timedelta(minutes=APPROVAL_TTL_MINUTES),
        created_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def approval_to_record(row: ApprovalORM) -> ApprovalRecord:
    return ApprovalRecord(
        action_hash=row.action_hash,
        decision=row.choice,  # type: ignore[arg-type]
        reason=row.reason,
        created_at=row.created_at,
        expires_at=row.expires_at,
        consumed_at=row.consumed_at,
    )


def get_execution_by_hash(session: Session, run_id: str, action_hash: str) -> ExecutionORM | None:
    return session.execute(
        select(ExecutionORM).where(ExecutionORM.run_id == run_id, ExecutionORM.action_hash == action_hash)
    ).scalar_one_or_none()


def get_execution_by_id(session: Session, run_id: str, execution_id: str) -> ExecutionORM | None:
    return session.execute(
        select(ExecutionORM).where(ExecutionORM.run_id == run_id, ExecutionORM.id == execution_id)
    ).scalar_one_or_none()


def execution_to_record(row: ExecutionORM) -> ExecutionRecord:
    result = json.loads(row.result_json)
    return ExecutionRecord(
        id=row.id,
        run_id=row.run_id,
        action_hash=row.action_hash,
        status=row.status,  # type: ignore[arg-type]
        before_digest=result["before_digest"],
        after_digest=result["after_digest"],
        archived_file_ids=result.get("archived_file_ids", []),
        rollback_record_id=result.get("rollback_record_id"),
    )


def get_simulation_state(session: Session, run_id: str) -> SimulationStateORM | None:
    return session.get(SimulationStateORM, run_id)


def load_report(session: Session, row: RunORM) -> EvaluationReport:
    """Reconstruct the full report, overlaying live status/approval/execution
    state on top of the report captured at evaluation time."""
    data = json.loads(row.report_json)
    data["status"] = row.status
    # strict=False: the round-tripped JSON stores timestamps as ISO strings,
    # not native datetime objects, so lax coercion is required here even
    # though StrictModel enables strict validation for fresh API input.
    report = EvaluationReport.model_validate(data, strict=False)

    latest_approval = session.execute(
        select(ApprovalORM).where(ApprovalORM.run_id == row.id).order_by(ApprovalORM.created_at.desc())
    ).scalars().first()
    approval_record = approval_to_record(latest_approval) if latest_approval else None

    latest_execution = session.execute(
        select(ExecutionORM).where(ExecutionORM.run_id == row.id).order_by(ExecutionORM.created_at.desc())
    ).scalars().first()
    execution_record = execution_to_record(latest_execution) if latest_execution else None

    # Events are sourced live from the events table, not the report_json
    # snapshot, so a live-mode run's progress is visible to GET while a
    # background worker is still appending stages (plan 2.6 polling).
    event_rows = session.execute(
        select(EventORM).where(EventORM.run_id == row.id).order_by(EventORM.sequence)
    ).scalars().all()
    events = [
        EventRecordSchema(
            sequence=e.sequence, stage=e.stage, status=e.status, message=e.message, created_at=e.created_at
        )
        for e in event_rows
    ]

    return report.model_copy(update={"approval": approval_record, "execution": execution_record, "events": events})
