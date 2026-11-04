"""Runner records inside the caller's reserved authorization transaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from sqlalchemy import Integer, and_, cast, func, or_, select
from models.tables import (
    InfraAutomationAudit,
    InfraAutomationRunner,
    InfraAutomationRunnerEnrollment,
)


def get_runner(session, runner_id):
    return session.scalar(
        select(InfraAutomationRunner)
        .where(InfraAutomationRunner.id == runner_id)
        .execution_options(populate_existing=True)
    )


def get_enrollment(session, enrollment_id):
    return session.scalar(
        select(InfraAutomationRunnerEnrollment)
        .where(InfraAutomationRunnerEnrollment.id == enrollment_id)
        .execution_options(populate_existing=True)
    )


def live_count(session, project_id, now, *, excluding=None):
    """Count reserved live slots, retaining revoked/expired rows as history.

    SQLite seconds conversion enforces the exclusive whole-second wire deadline,
    including imported rows whose stored expiration has a fractional component.
    """

    def unexpired(column):
        return cast(func.strftime("%s", column), Integer) > int(now.timestamp())

    pending = (
        select(InfraAutomationRunnerEnrollment.id)
        .where(
            InfraAutomationRunnerEnrollment.runner_id == InfraAutomationRunner.id,
            InfraAutomationRunnerEnrollment.consumed_at.is_(None),
            unexpired(InfraAutomationRunnerEnrollment.expires_at),
        )
        .exists()
    )
    query = (
        select(func.count())
        .select_from(InfraAutomationRunner)
        .where(
            InfraAutomationRunner.project_id == project_id,
            or_(
                and_(
                    InfraAutomationRunner.status == "active",
                    InfraAutomationRunner.credential_hash.is_not(None),
                    unexpired(InfraAutomationRunner.credential_expires_at),
                ),
                and_(InfraAutomationRunner.status == "pending", pending),
            ),
        )
    )
    if excluding is not None:
        query = query.where(InfraAutomationRunner.id != excluding)
    return session.scalar(query) or 0


def _creation_sequence(project_id, workspace_id):
    # The append-only creation audit supplies the immutable insertion watermark;
    # timestamps are only ordering positions and cannot admit backdated inserts.
    return (
        select(
            InfraAutomationAudit.target_id.label("runner_id"),
            func.min(InfraAutomationAudit.sequence).label("sequence"),
        )
        .where(
            InfraAutomationAudit.project_id == project_id,
            InfraAutomationAudit.workspace_id == workspace_id,
            InfraAutomationAudit.event_type == "runner.enrollment_created",
        )
        .group_by(InfraAutomationAudit.target_id)
        .subquery()
    )


def max_sequence(session, project_id, workspace_id):
    creation = _creation_sequence(project_id, workspace_id)
    return session.scalar(select(func.max(creation.c.sequence))) or 0


@dataclass(frozen=True)
class RunnerPageRow:
    runner: InfraAutomationRunner
    sequence: int

    @property
    def id(self) -> str:
        return self.runner.id

    @property
    def created_at(self) -> datetime:
        return self.runner.created_at


def list_runners(
    session, project_id, workspace_id, *, snapshot_sequence, before=None, limit=25
):
    creation = _creation_sequence(project_id, workspace_id)
    query = (
        select(InfraAutomationRunner, creation.c.sequence)
        .join(creation, creation.c.runner_id == InfraAutomationRunner.id)
        .where(
            InfraAutomationRunner.project_id == project_id,
            InfraAutomationRunner.workspace_id == workspace_id,
            creation.c.sequence <= snapshot_sequence,
        )
    )
    if before is not None:
        timestamp, identifier = before
        query = query.where(
            or_(
                InfraAutomationRunner.created_at < timestamp,
                and_(
                    InfraAutomationRunner.created_at == timestamp,
                    InfraAutomationRunner.id < identifier,
                ),
            )
        )
    query = (
        query.order_by(
            InfraAutomationRunner.created_at.desc(), InfraAutomationRunner.id.desc()
        )
        .limit(limit)
        .execution_options(populate_existing=True)
    )
    return [RunnerPageRow(row, sequence) for row, sequence in session.execute(query)]
