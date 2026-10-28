"""Project policy mutations and transaction-local deny checks for future consumers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from infra_automation.contracts import SAFE_INTEGER
from infra_automation.lifecycle import (
    AdvanceEpochRequest,
    AuthorityStamp,
    LifecycleError,
    UpdateSettingsRequest,
)
from models.repositories import infra_automation_workflows as repository
from models.repositories import project_memberships
from models.tables import (
    IdentityAccount,
    InfraAutomationRun,
    InfraWorkflowRevision,
    Project,
    ProjectWorkspace,
)
from services import infra_automation_support as support
from services import project_service as authorization


def get_capabilities(project_id: int, workspace_id: int | None = None) -> dict:
    """Project editor permissions and feature state from one live read operation.

    Permissions remain descriptive: every mutation still checks its own current
    credentials, resource, scope and policy. Execution disable does not remove
    authoring permissions or authorized historical reads.
    """
    with authorization.authorized_session() as session:
        grant = support.scope(
            session, project_id, workspace_id, "automation.read", mutation=False
        )
        if (
            grant.principal.principal_type != "human"
            or grant.principal.credential_audience != "human"
        ):
            raise authorization.TrustedAuthorizationError()
        row, settings = support.policy_state(session, project_id)
        return support.bounded_payload(
            {
                "version": 1,
                "project_id": project_id,
                "workspace_id": workspace_id,
                "membership_version": grant.authorization_version,
                "policy_version": row.version if row else 0,
                "execution_enabled": settings.enabled,
                "capabilities": [
                    capability
                    for capability in (
                        "automation.read",
                        "automation.draft",
                        "automation.publish",
                        "automation.request",
                    )
                    if authorization.trusted_capability_allowed(
                        grant.principal, grant.role, capability
                    )
                ],
            }
        )


def get_settings(project_id: int) -> dict:
    with authorization.authorized_session() as session:
        support.scope(session, project_id, None, "automation.draft", mutation=False)
        return support.bounded_payload(support.policy_view(session, project_id))


def _counters(row) -> None:
    if any(
        type(value) is not int or not 1 <= value < SAFE_INTEGER
        for value in (row.version, row.authorization_epoch, row.restore_epoch)
    ):
        raise LifecycleError(503)


def _write(session, grant, settings, expected_version, reason, *, event, restore=False):
    before = support.policy_view(session, grant.project_id)
    changed = repository.save_policy(
        session,
        project_id=grant.project_id,
        expected_version=expected_version,
        settings_json=support.canonical(settings.model_dump(mode="json")).decode(),
        restore=restore,
    )
    if changed is None:
        raise LifecycleError(409)
    after = support.policy_view(session, grant.project_id)
    support.append_audit(
        session,
        grant,
        workspace_id=None,
        event_type=event,
        target_id=str(grant.project_id),
        reason=reason,
        before_digest=support.digest(support.canonical(before)),
        after_digest=support.digest(support.canonical(after)),
    )
    return after


def update_settings(request: UpdateSettingsRequest) -> dict:
    request = support.revalidate(request, UpdateSettingsRequest)
    with authorization.authorized_session() as session:
        grant = support.scope(
            session, request.project_id, None, "automation.admin", mutation=True
        )
        support.screened_label(request.reason)
        row, current = support.policy_state(session, request.project_id)
        if request.expected_version != (row.version if row else 0):
            raise LifecycleError(409)
        if row:
            _counters(row)
            if current == request.settings:
                return support.bounded_payload(
                    support.policy_view(session, request.project_id)
                )
        from infra_automation.state import ACTIVE_STATES

        active_runs = (
            session.scalar(
                select(func.count())
                .select_from(InfraAutomationRun)
                .where(
                    InfraAutomationRun.project_id == request.project_id,
                    InfraAutomationRun.state.in_(ACTIVE_STATES),
                )
            )
            or 0
        )
        queued_runs = (
            session.scalar(
                select(func.count())
                .select_from(InfraAutomationRun)
                .where(
                    InfraAutomationRun.project_id == request.project_id,
                    InfraAutomationRun.state == "queued",
                )
            )
            or 0
        )
        if (
            request.settings.max_active_runs < active_runs
            or request.settings.max_queued_runs < queued_runs
        ):
            raise LifecycleError(409)
        maximum = (
            session.scalar(
                select(func.count(InfraWorkflowRevision.sequence))
                .where(InfraWorkflowRevision.project_id == request.project_id)
                .group_by(InfraWorkflowRevision.workflow_id)
                .order_by(func.count(InfraWorkflowRevision.sequence).desc())
                .limit(1)
            )
            or 0
        )
        if (
            repository.count_workflows(session, project_id=request.project_id)
            > request.settings.max_workflows
            or maximum > request.settings.max_revisions_per_workflow
        ):
            raise LifecycleError(409)
        return support.bounded_payload(
            _write(
                session,
                grant,
                request.settings,
                request.expected_version,
                request.reason,
                event="automation_settings_changed",
            )
        )


def advance_epoch(request: AdvanceEpochRequest, *, restore: bool = False) -> dict:
    request = support.revalidate(request, AdvanceEpochRequest)
    if type(restore) is not bool:
        raise LifecycleError(422)
    with authorization.authorized_session() as session:
        grant = support.scope(
            session, request.project_id, None, "automation.admin", mutation=True
        )
        support.screened_label(request.reason)
        row, settings = support.policy_state(session, request.project_id)
        if row is None or row.version != request.expected_version:
            raise LifecycleError(409)
        _counters(row)
        return support.bounded_payload(
            _write(
                session,
                grant,
                settings,
                request.expected_version,
                request.reason,
                event="automation_restore_invalidated"
                if restore
                else "automation_revoked",
                restore=restore,
            )
        )


def advisory_policy_changed(session: Session, project_key: str) -> None:
    """Called only on a stored advisory-policy change inside its write transaction."""
    authorization._require_operation(session)
    project = session.scalar(select(Project).where(Project.project_key == project_key))
    if project is None:
        return
    row = repository.get_policy(session, project_id=project.id)
    if row is None:
        return
    grant = support.scope(session, project.id, None, "automation.admin", mutation=True)
    _, settings = support.policy_state(session, project.id)
    _counters(row)
    _write(
        session,
        grant,
        settings,
        row.version,
        "Advisory policy changed; prior automation authority invalidated.",
        event="automation_advisory_policy_changed",
    )


def _scoped_rows(session: Session, stamp: AuthorityStamp):
    authorization._require_operation(session)
    workflow = repository.get_workflow(session, stamp.workflow_id)
    revision = repository.get_revision(session, stamp.revision_id)
    workspace = session.scalar(
        select(ProjectWorkspace)
        .where(
            ProjectWorkspace.id == stamp.workspace_id,
            ProjectWorkspace.project_id == stamp.project_id,
        )
        .execution_options(populate_existing=True)
    )
    if (
        workflow is None
        or revision is None
        or workspace is None
        or workflow.project_id != stamp.project_id
        or revision.project_id != stamp.project_id
        or revision.workflow_id != workflow.id
        or revision.workspace_id != workflow.workspace_id
        or (
            workflow.workspace_id is not None
            and workflow.workspace_id != stamp.workspace_id
        )
    ):
        raise authorization.TrustedAuthorizationError()
    return workflow


def _current_authority(session: Session, stamp: AuthorityStamp):
    """Return known-valid/invalid authority; unavailable/corrupt state raises."""
    row, settings = support.policy_state(session, stamp.project_id)
    account = session.scalar(
        select(IdentityAccount)
        .where(IdentityAccount.id == stamp.principal_id)
        .execution_options(populate_existing=True)
    )
    member = project_memberships.get_membership(
        session, principal_id=stamp.principal_id, project_id=stamp.project_id
    )
    if row is None or account is None or member is None:
        raise LifecycleError(503)
    _counters(row)
    for current, captured in (
        (account.authentication_version, stamp.authentication_version),
        (member.authorization_version, stamp.membership_version),
        (row.authorization_epoch, stamp.authorization_epoch),
        (row.restore_epoch, stamp.restore_epoch),
    ):
        if (
            type(current) is not int
            or not 1 <= current <= SAFE_INTEGER
            or current < captured
        ):
            raise LifecycleError(503)
    if (
        account.principal_type not in {"human", "service", "agent"}
        or member.role not in authorization.PROJECT_ROLE_CAPABILITIES
    ):
        raise LifecycleError(503)
    advisory = support.advisory_policy(session, stamp.project_id)
    policy_matches = stamp.policy_digest == support.digest(
        support.canonical(settings.model_dump(mode="json"))
    )
    advisory_matches = stamp.advisory_policy_digest == support.digest(
        support.canonical(advisory.model_dump(mode="json"))
    )
    epochs_match = (
        row.authorization_epoch == stamp.authorization_epoch
        and row.restore_epoch == stamp.restore_epoch
    )
    if epochs_match and (not policy_matches or not advisory_matches):
        # A digest-only change without the atomic epoch hook is not a proven
        # invalidation event and cannot justify deleting evidence.
        raise LifecycleError(503)
    current = (
        settings.enabled
        and account.enabled
        and member.enabled
        and account.principal_type == "human"
        and account.authentication_version == stamp.authentication_version
        and member.authorization_version == stamp.membership_version
        and (member.workspace_id is None or member.workspace_id == stamp.workspace_id)
        and "automation.request" in authorization.PROJECT_ROLE_CAPABILITIES[member.role]
        and epochs_match
        and policy_matches
        and advisory_matches
    )
    return bool(current), settings


def check_live_policy(session: Session, stamp: AuthorityStamp, operation: str) -> None:
    """Additional deny-only check; a stamp is public data, never a credential.

    Consumers must authenticate their own audience and operation first, then hold
    the same authorization.authorized_session through this check AND their local mutation.
    Machine audience/attempt authentication belongs to each future machine owner.
    Read/reconcile instead check the current reader, not the historic requester.
    """
    stamp = support.revalidate(stamp, AuthorityStamp)
    if type(operation) is not str or operation not in {
        "start",
        "claim",
        "dispatch",
        "consume",
        "read",
        "reconcile",
    }:
        raise LifecycleError(422)
    workflow = _scoped_rows(session, stamp)
    if operation in {"read", "reconcile"}:
        support.scope(
            session,
            stamp.project_id,
            stamp.workspace_id,
            "automation.read",
            mutation=False,
        )
        return
    current, _ = _current_authority(session, stamp)
    if not current or (operation == "start" and workflow.archived):
        raise authorization.TrustedAuthorizationError()


def retention_allows_delete(
    session: Session,
    stamp: AuthorityStamp,
    state: str,
    evidence_created_at: datetime,
    now: datetime,
) -> bool:
    """Deny deletion absent current admin and positive, bounded retention proof.

    Accepted/unknown work always retains evidence. Pending work additionally needs
    expired evidence and a known authority invalidation; age alone is insufficient.
    This predicate neither deletes data nor issues authority.
    """
    stamp = support.revalidate(stamp, AuthorityStamp)
    _scoped_rows(session, stamp)
    support.scope(
        session, stamp.project_id, stamp.workspace_id, "automation.admin", mutation=True
    )
    if type(state) is not str or state not in {
        "pending",
        "accepted",
        "unknown",
        "terminal",
    }:
        raise LifecycleError(422)
    if state in {"accepted", "unknown"}:
        return False
    if any(
        type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None
        for value in (evidence_created_at, now)
    ):
        raise LifecycleError(422)
    elapsed = (
        now.astimezone(timezone.utc) - evidence_created_at.astimezone(timezone.utc)
    ).total_seconds()
    try:
        current, settings = _current_authority(session, stamp)
    except LifecycleError:
        return False
    if elapsed < settings.retention_seconds:
        return False
    if state == "terminal":
        return True
    return elapsed >= settings.evidence_ttl_seconds and not current
