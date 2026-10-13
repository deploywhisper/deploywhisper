"""Project membership queries and append-only audit in caller-owned transactions."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import secrets

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from models.tables import ProjectAuthorizationAudit, ProjectMembership

ROLES = frozenset({"admin", "maintainer", "reviewer", "contributor", "read-only"})


def get_membership(
    session: Session, *, principal_id: str, project_id: int
) -> ProjectMembership | None:
    """Refresh live state instead of trusting a session identity-map grant."""
    return session.scalar(
        select(ProjectMembership)
        .where(
            ProjectMembership.principal_id == principal_id,
            ProjectMembership.project_id == project_id,
        )
        .execution_options(populate_existing=True)
    )


def list_memberships(session: Session, *, project_id: int) -> list[ProjectMembership]:
    return list(
        session.scalars(
            select(ProjectMembership)
            .where(ProjectMembership.project_id == project_id)
            .order_by(ProjectMembership.created_at, ProjectMembership.id)
            .execution_options(populate_existing=True)
        )
    )


def upsert_membership(
    session: Session,
    *,
    principal_id: str,
    project_id: int,
    role: str,
    workspace_id: int | None = None,
    now: datetime | None = None,
) -> ProjectMembership:
    """Assign an existing principal/scope; caller authenticates and audits atomically.

    Membership writers and protected operations must use the identity transaction's
    SQLite writer reservation, which serializes live checks with changes.
    """
    if role not in ROLES:
        raise ValueError("Unknown project membership role")
    now = now or datetime.now(UTC)
    member = get_membership(session, principal_id=principal_id, project_id=project_id)
    if member is None:
        member = ProjectMembership(
            id=secrets.token_hex(24),
            principal_id=principal_id,
            project_id=project_id,
            workspace_id=workspace_id,
            role=role,
            enabled=True,
            authorization_version=1,
            created_at=now,
            updated_at=now,
        )
        session.add(member)
        session.flush()
    else:
        session.execute(
            update(ProjectMembership)
            .where(ProjectMembership.id == member.id)
            .values(
                role=role,
                workspace_id=workspace_id,
                enabled=True,
                authorization_version=ProjectMembership.authorization_version + 1,
                updated_at=now,
            )
        )
        session.refresh(member)
    return member


def revoke_membership(
    session: Session, *, principal_id: str, project_id: int, now: datetime | None = None
) -> ProjectMembership | None:
    """Retain the membership tombstone so reassignment cannot reset its version."""
    member = get_membership(session, principal_id=principal_id, project_id=project_id)
    if member is not None:
        session.execute(
            update(ProjectMembership)
            .where(ProjectMembership.id == member.id)
            .values(
                enabled=False,
                authorization_version=ProjectMembership.authorization_version + 1,
                updated_at=now or datetime.now(UTC),
            )
        )
        session.refresh(member)
    return member


def append_audit(
    session: Session,
    *,
    actor_principal_id: str,
    project_id: int,
    action: str,
    target_principal_id: str | None = None,
    workspace_id: int | None = None,
    object_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    now: datetime | None = None,
) -> ProjectAuthorizationAudit:
    """Append nonsecret metadata selected by the trusted service; never update/delete."""
    audit = ProjectAuthorizationAudit(
        id=secrets.token_hex(24),
        actor_principal_id=actor_principal_id,
        target_principal_id=target_principal_id,
        project_id=project_id,
        workspace_id=workspace_id,
        action=action,
        object_id=object_id,
        before_json=json.dumps(before or {}, sort_keys=True, separators=(",", ":")),
        after_json=json.dumps(after or {}, sort_keys=True, separators=(",", ":")),
        created_at=now or datetime.now(UTC),
    )
    session.add(audit)
    session.flush()
    return audit
