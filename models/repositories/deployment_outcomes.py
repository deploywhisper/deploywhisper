"""Deployment outcome repository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from models.tables import DeploymentOutcome


def _deployment_outcome_load_options() -> list:
    return [
        selectinload(DeploymentOutcome.project),
        selectinload(DeploymentOutcome.workspace),
    ]


def create_deployment_outcome(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None = None,
    analysis_id: int,
    outcome_label: str,
    deployed_at: datetime,
    linked_incident_id: int | None = None,
    environment: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
) -> DeploymentOutcome:
    outcome = DeploymentOutcome(
        project_id=project_id,
        workspace_id=workspace_id,
        analysis_id=analysis_id,
        outcome_label=outcome_label,
        deployed_at=deployed_at,
        linked_incident_id=linked_incident_id,
        environment=environment,
        summary=summary,
        notes=notes,
    )
    session.add(outcome)
    session.commit()
    session.refresh(outcome)
    return session.execute(
        select(DeploymentOutcome)
        .options(*_deployment_outcome_load_options())
        .where(DeploymentOutcome.id == outcome.id)
    ).scalar_one()


def list_deployment_outcomes(
    session: Session,
    *,
    project_id: int | None = None,
    workspace_id: int | None = None,
    analysis_id: int | None = None,
    outcome_label: str | None = None,
    limit: int = 100,
) -> list[DeploymentOutcome]:
    stmt = (
        select(DeploymentOutcome)
        .options(*_deployment_outcome_load_options())
        .order_by(DeploymentOutcome.deployed_at.desc(), DeploymentOutcome.id.desc())
        .limit(max(1, limit))
    )
    if project_id is not None:
        stmt = stmt.where(DeploymentOutcome.project_id == project_id)
    if workspace_id is not None:
        stmt = stmt.where(DeploymentOutcome.workspace_id == workspace_id)
    if analysis_id is not None:
        stmt = stmt.where(DeploymentOutcome.analysis_id == analysis_id)
    if outcome_label:
        stmt = stmt.where(DeploymentOutcome.outcome_label == outcome_label)
    result = session.execute(stmt)
    return list(result.scalars().all())
