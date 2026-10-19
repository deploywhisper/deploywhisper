"""Internal audit identity for durable work; never a credential issuer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from infra_automation.lifecycle import LifecycleError
from models.tables import IdentityAccount
from services import infra_automation_support as support
from services import project_service as authorization

if TYPE_CHECKING:
    from infra_automation.state import AuditActor

ENGINE_ACTOR_ID = "infra-engine-coordinator"
# A trailing space is outside the existing human username contract. Reserving an
# already-invalid name avoids locking out a previously legitimate human name.
ENGINE_ACTOR_USERNAME = "infra-engine-coordinator "
_INERT_VERIFIER = "!disabled-local-engine-audit"


def _valid_actor(row: IdentityAccount | None) -> bool:
    return row is not None and (
        row.id == ENGINE_ACTOR_ID
        and row.username == ENGINE_ACTOR_USERNAME
        and row.principal_type == "service"
        and not row.enabled
        and not row.is_admin
        and row.password_verifier == _INERT_VERIFIER
        and row.authentication_version == 1
    )


def engine_actor(session: Session) -> AuditActor:
    """Resolve audit attribution only; callers still authenticate each operation."""
    from infra_automation.state import AuditActor

    authorization._require_operation(session)
    row = session.get(IdentityAccount, ENGINE_ACTOR_ID, populate_existing=True)
    if not _valid_actor(row):
        raise LifecycleError(503)
    return AuditActor(ENGINE_ACTOR_ID, "service", "coordinator")


def ensure_engine_actor(
    session: Session, grant: authorization.TrustedProjectScope | None
) -> AuditActor:
    """Create only inside an independently verified human admission transaction.

    Never run this during empty application startup/migration: any account would
    prevent the one-time first-human bootstrap. No session or membership is issued.
    """
    authorization._require_operation(session)
    if not isinstance(grant, authorization.TrustedProjectScope):
        raise authorization.TrustedAuthorizationError()
    # Recheck credentials rather than trusting a caller-constructed scope object.
    verified = support.scope(
        session,
        grant.project_id,
        grant.workspace_id,
        "automation.request",
        mutation=True,
    )
    if verified.principal.principal_type != "human":
        raise authorization.TrustedAuthorizationError()
    row = session.get(IdentityAccount, ENGINE_ACTOR_ID, populate_existing=True)
    if row is None:
        if session.scalar(
            select(IdentityAccount.id).where(
                IdentityAccount.username == ENGINE_ACTOR_USERNAME
            )
        ):
            raise LifecycleError(503)
        row = IdentityAccount(
            id=ENGINE_ACTOR_ID,
            username=ENGINE_ACTOR_USERNAME,
            principal_type="service",
            password_verifier=_INERT_VERIFIER,
            enabled=False,
            is_admin=False,
            authentication_version=1,
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.flush()
    return engine_actor(session)
