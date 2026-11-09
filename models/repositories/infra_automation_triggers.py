"""Logical replay-storage accounting within caller-owned transactions."""

from __future__ import annotations
from sqlalchemy import func, inspect, select
from models.tables import InfraAutomationTriggerClock, InfraAutomationTriggerNonce


def retained_bytes(session, project_id=None):
    inspector = inspect(session.connection())
    if not inspector.has_table("infra_automation_trigger_nonces"):
        return 0
    query = select(func.count()).select_from(InfraAutomationTriggerNonce)
    if project_id is not None:
        query = query.where(InfraAutomationTriggerNonce.project_id == project_id)
    total = (session.scalar(query) or 0) * 512
    if project_id is None and inspector.has_table("infra_automation_trigger_clock"):
        total += (
            session.scalar(
                select(func.count()).select_from(InfraAutomationTriggerClock)
            )
            or 0
        ) * 1024
    return total
