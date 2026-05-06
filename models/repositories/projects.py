"""Project/workspace repository helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.tables import Project, ProjectWorkspace


def create_project(
    session: Session,
    *,
    project_key: str,
    display_name: str,
    description: str | None = None,
    repository_url: str | None = None,
    default_branch: str | None = None,
    is_default: bool = False,
) -> Project:
    record = Project(
        project_key=project_key,
        display_name=display_name,
        description=description,
        repository_url=repository_url,
        default_branch=default_branch,
        is_default=is_default,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def list_projects(session: Session) -> list[Project]:
    stmt = select(Project).order_by(
        Project.is_default.desc(), Project.project_key.asc()
    )
    return list(session.execute(stmt).scalars().all())


def get_project(session: Session, project_id: int) -> Project | None:
    return session.get(Project, project_id)


def get_project_by_key(session: Session, project_key: str) -> Project | None:
    stmt = select(Project).where(Project.project_key == project_key)
    return session.execute(stmt).scalar_one_or_none()


def get_default_project(session: Session) -> Project | None:
    stmt = (
        select(Project).where(Project.is_default.is_(True)).order_by(Project.id.asc())
    )
    return session.execute(stmt).scalars().first()


def create_workspace(
    session: Session,
    *,
    project_id: int,
    workspace_key: str,
    display_name: str,
    description: str | None = None,
    environment: str | None = None,
) -> ProjectWorkspace:
    record = ProjectWorkspace(
        project_id=project_id,
        workspace_key=workspace_key,
        display_name=display_name,
        description=description,
        environment=environment,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def get_workspace(session: Session, workspace_id: int) -> ProjectWorkspace | None:
    return session.get(ProjectWorkspace, workspace_id)


def list_workspaces(
    session: Session,
    *,
    project_id: int | None = None,
) -> list[ProjectWorkspace]:
    stmt = select(ProjectWorkspace)
    if project_id is not None:
        stmt = stmt.where(ProjectWorkspace.project_id == project_id)
    stmt = stmt.order_by(
        ProjectWorkspace.project_id.asc(),
        ProjectWorkspace.workspace_key.asc(),
    )
    return list(session.execute(stmt).scalars().all())


def get_workspace_by_key(
    session: Session,
    *,
    project_id: int,
    workspace_key: str,
) -> ProjectWorkspace | None:
    stmt = select(ProjectWorkspace).where(
        ProjectWorkspace.project_id == project_id,
        ProjectWorkspace.workspace_key == workspace_key,
    )
    return session.execute(stmt).scalar_one_or_none()
