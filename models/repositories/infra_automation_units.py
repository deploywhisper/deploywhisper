"""Flush-only immutable inventory rows within the caller's authority transaction."""

from __future__ import annotations
from sqlalchemy import select, func, inspect
from infra_automation.lifecycle import LifecycleError
from models.tables import InfraAutomationUnitRevision, InfraAutomationRunUnits


def revision(session, revision_id):
    return session.get(InfraAutomationUnitRevision, revision_id)


def latest(session, inventory_id):
    return session.scalar(
        select(InfraAutomationUnitRevision)
        .where(InfraAutomationUnitRevision.inventory_id == inventory_id)
        .order_by(InfraAutomationUnitRevision.revision_number.desc())
        .limit(1)
    )


def revisions(session, project_id, workspace_id=None):
    query = select(InfraAutomationUnitRevision).where(
        InfraAutomationUnitRevision.project_id == project_id
    )
    if workspace_id is not None:
        query = query.where(InfraAutomationUnitRevision.workspace_id == workspace_id)
    rows = list(
        session.scalars(
            query.order_by(
                InfraAutomationUnitRevision.revision_number.desc(),
                InfraAutomationUnitRevision.inventory_id,
            ).limit(801)
        )
    )
    if len(rows) > 800:
        raise LifecycleError(503)
    return rows


def revision_history(session, inventory_id, project_id, workspace_id):
    rows = list(
        session.scalars(
            select(InfraAutomationUnitRevision)
            .where(
                InfraAutomationUnitRevision.inventory_id == inventory_id,
                InfraAutomationUnitRevision.project_id == project_id,
                InfraAutomationUnitRevision.workspace_id == workspace_id,
            )
            .order_by(InfraAutomationUnitRevision.revision_number.desc())
            .limit(33)
        )
    )
    if len(rows) > 32:
        raise LifecycleError(503)
    return rows


def run_units(session, run_id):
    return session.get(InfraAutomationRunUnits, run_id)


def add(session, row):
    session.add(row)
    session.flush()
    return row


def retained_bytes(session, project_id=None):
    """Bound payload plus reserved immutable row bookkeeping for logical quotas."""
    if not inspect(session.connection()).has_table("infra_automation_unit_revisions"):
        return 0
    query = select(func.sum(func.length(InfraAutomationUnitRevision.plan_bytes) + 1024))
    if project_id is not None:
        query = query.where(InfraAutomationUnitRevision.project_id == project_id)
    return session.scalar(query) or 0
