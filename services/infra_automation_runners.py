"""Scoped one-use runner enrollment and live credential lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from typing import Annotated, Literal

from pydantic import Field, SecretStr, StrictStr
from sqlalchemy import select
from infra_automation.contracts import ClosedModel
from infra_automation.lifecycle import CursorEnvelope, LifecycleError, Positive, Reason
from infra_automation.workflow_schema import Digest, Identifier
from infra_automation.runner.protocol import Enrollment, RunnerCredential
from models.repositories import infra_automation_runners as repo
from models.repositories import infra_automation_workflows as audit
from models.repositories import project_memberships
from models.tables import (
    IdentityAccount,
    InfraAutomationRunner,
    InfraAutomationRunnerEnrollment,
    InfraAutomationRunnerTask,
    InfraAutomationAttempt,
)
from services.content_security import redact_text
from services import project_service as authorization
from services import infra_automation_support as support


_INERT_VERIFIER = "!disabled-runner-audit"


class EnrollmentRequest(ClosedModel):
    project_id: Positive
    workspace_id: Positive
    tags: Annotated[list[Identifier], Field(max_length=16)]
    tool: Identifier
    profile_digest: Digest
    runner_version: Identifier
    reason: Reason


class EnrollmentIssued(ClosedModel):
    enrollment: Enrollment
    token: SecretStr


class CredentialIssued(ClosedModel):
    runner_id: Identifier
    token: SecretStr
    expires_at: StrictStr
    generation: Positive
    audience: Literal["runner-task-v1"] = "runner-task-v1"


def _now(value=None):
    value = datetime.now(timezone.utc) if value is None else value
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise LifecycleError(422)
    return value.astimezone(timezone.utc)


def _utc(value):
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def _time(value):
    return _utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash(token, prefix):
    if (
        type(token) is not str
        or not token.startswith(prefix)
        or len(token) != len(prefix) + 64
    ):
        raise LifecycleError(401)
    try:
        bytes.fromhex(token[len(prefix) :])
    except ValueError:
        raise LifecycleError(401) from None
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _screen(value):
    if (
        type(value) is not str
        or not 1 <= len(value) <= 256
        or redact_text(value, sensitive_values=("enroll-v1-", "runner-v1-")) != value
    ):
        raise LifecycleError(422)
    return support.screened_label(value)


def _human(session, project_id, workspace_id, *, mutation=True):
    grant = support.scope(
        session,
        project_id,
        workspace_id,
        "automation.admin" if mutation else "automation.read",
        mutation=mutation,
    )
    if (
        grant.principal.principal_type != "human"
        or grant.principal.credential_audience != "human"
        or (not mutation and grant.role not in {"admin", "maintainer"})
        or (mutation and not grant.principal.production_eligible)
    ):
        raise authorization.TrustedAuthorizationError()
    return grant


def _live(session, row, now):
    authorization._require_operation(session)
    policy, settings = support.policy_state(session, row.project_id)
    account = session.get(
        IdentityAccount, row.issuer_principal_id, populate_existing=True
    )
    member = project_memberships.get_membership(
        session, principal_id=row.issuer_principal_id, project_id=row.project_id
    )
    if (
        policy is None
        or not settings.enabled
        or account is None
        or member is None
        or not account.enabled
        or account.principal_type != "human"
        or not member.enabled
        or member.role != "admin"
        or member.workspace_id not in (None, row.workspace_id)
        or account.authentication_version != row.issuer_authentication_version
        or member.authorization_version != row.issuer_membership_version
        or policy.authorization_epoch != row.authorization_epoch
        or policy.restore_epoch != row.restore_epoch
        or now < _utc(row.last_observed_at)
    ):
        raise LifecycleError(403)
    return settings


def _view(row):
    return {
        "id": row.id,
        "project_id": row.project_id,
        "workspace_id": row.workspace_id,
        "tags": json.loads(row.tags_json),
        "tool": row.tool,
        "profile_digest": row.profile_digest,
        "runner_version": row.runner_version,
        "protocol_version": row.protocol_version,
        "generation": row.generation,
        "status": row.status,
        "last_seen_at": _time(row.last_seen_at) if row.last_seen_at else None,
        "credential_expires_at": _time(row.credential_expires_at)
        if row.credential_expires_at
        else None,
        "isolation_qualified": False,
    }


def _digest(row):
    return support.digest(support.canonical(_view(row)))


def _audit(session, row, event, reason, before=None, *, grant=None, now=None):
    audit.append_audit(
        session,
        project_id=row.project_id,
        workspace_id=row.workspace_id,
        actor_principal_id=grant.principal.principal_id if grant else row.id,
        actor_type="human" if grant else "runner",
        actor_role=grant.role if grant else "runner",
        event_type=event,
        target_id=row.id,
        reason=reason,
        before_digest=before,
        after_digest=_digest(row),
        now=now,
    )


def _envelope(row, enrollment):
    return Enrollment(
        audience="runner-enrollment-v1",
        enrollment_id=enrollment.id,
        runner_id=row.id,
        project_id=str(row.project_id),
        workspace_id=str(row.workspace_id),
        expires_at=_time(enrollment.expires_at),
        one_use=True,
    )


def create_enrollment(request: EnrollmentRequest, *, now=None):
    request = support.revalidate(request, EnrollmentRequest)
    with authorization.authorized_session() as session:
        timestamp = _now(now)
        grant = _human(session, request.project_id, request.workspace_id)
        _screen(request.reason)
        for value in (*request.tags, request.tool, request.runner_version):
            _screen(value)
        policy, settings = support.policy_state(session, request.project_id)
        if policy is None or not settings.enabled:
            raise LifecycleError(403)
        if repo.live_count(session, request.project_id, timestamp) >= 100:
            raise LifecycleError(429)
        runner_id = "runner-" + secrets.token_hex(24)
        row = InfraAutomationRunner(
            id=runner_id,
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            tags_json=json.dumps(sorted(set(request.tags))),
            tool=request.tool,
            profile_digest=request.profile_digest,
            runner_version=request.runner_version,
            protocol_version=1,
            generation=1,
            status="pending",
            created_at=timestamp,
            last_observed_at=timestamp,
            issuer_principal_id=grant.principal.principal_id,
            issuer_authentication_version=grant.principal.authentication_version,
            issuer_membership_version=grant.authorization_version,
            authorization_epoch=policy.authorization_epoch,
            restore_epoch=policy.restore_epoch,
        )
        session.add(row)
        # Disabled machine audit identity cannot authenticate or gain membership.
        session.add(
            IdentityAccount(
                id=runner_id,
                username=runner_id + " ",
                principal_type="runner",
                password_verifier=_INERT_VERIFIER,
                enabled=False,
                is_admin=False,
                authentication_version=1,
                created_at=timestamp,
            )
        )
        session.flush()
        token = "enroll-v1-" + secrets.token_hex(32)
        enrollment = InfraAutomationRunnerEnrollment(
            id=secrets.token_hex(24),
            runner_id=row.id,
            token_hash=_hash(token, "enroll-v1-"),
            created_at=timestamp,
            expires_at=(
                timestamp + timedelta(seconds=min(300, settings.credential_ttl_seconds))
            ).replace(microsecond=0),
        )
        session.add(enrollment)
        _audit(
            session,
            row,
            "runner.enrollment_created",
            request.reason,
            grant=grant,
            now=timestamp,
        )
        return EnrollmentIssued(
            enrollment=_envelope(row, enrollment), token=SecretStr(token)
        )


def _issue(row, settings, timestamp):
    token = "runner-v1-" + secrets.token_hex(32)
    row.credential_hash = _hash(token, "runner-v1-")
    row.credential_expires_at = (
        timestamp + timedelta(seconds=settings.credential_ttl_seconds)
    ).replace(microsecond=0)
    row.status = "active"
    row.last_observed_at = timestamp
    return CredentialIssued(
        runner_id=row.id,
        token=SecretStr(token),
        expires_at=_time(row.credential_expires_at),
        generation=row.generation,
    )


def redeem(
    enrollment_id,
    token,
    *,
    enrollment=None,
    protocol_version=1,
    capabilities=("screened-collection-v1",),
    now=None,
):
    supplied = _hash(token, "enroll-v1-")
    if (
        type(protocol_version) is not int
        or protocol_version != 1
        or tuple(capabilities) != ("screened-collection-v1",)
    ):
        raise LifecycleError(422)
    with authorization.authorized_session() as session:
        timestamp = _now(now)
        item = repo.get_enrollment(session, enrollment_id)
        if (
            item is None
            or not hmac.compare_digest(item.token_hash, supplied)
            or item.consumed_at is not None
            or not _utc(item.created_at)
            <= timestamp
            < _utc(item.expires_at).replace(microsecond=0)
        ):
            raise LifecycleError(401)
        row = repo.get_runner(session, item.runner_id)
        if row is None or row.status != "pending":
            raise LifecycleError(403)
        if enrollment is not None and support.revalidate(
            enrollment, Enrollment
        ) != _envelope(row, item):
            raise LifecycleError(403)
        settings = _live(session, row, timestamp)
        before = _digest(row)
        item.consumed_at = timestamp
        issued = _issue(row, settings, timestamp)
        row.last_seen_at = timestamp
        _audit(
            session,
            row,
            "runner.enrollment_redeemed",
            "One-use runner enrollment redeemed.",
            before,
            now=timestamp,
        )
        return issued


def authenticate(session, credential: RunnerCredential, *, now=None):
    timestamp = _now(now)
    authorization._require_operation(session)
    if type(credential) is not RunnerCredential:
        raise LifecycleError(401)
    supplied = _hash(credential.token, "runner-v1-")
    row = repo.get_runner(session, credential.runner_id)
    if (
        row is None
        or row.status != "active"
        or row.credential_hash is None
        or not hmac.compare_digest(row.credential_hash, supplied)
        or row.credential_expires_at is None
        or not _utc(row.created_at)
        <= timestamp
        < _utc(row.credential_expires_at).replace(microsecond=0)
    ):
        raise LifecycleError(401)
    _live(session, row, timestamp)
    row.last_seen_at = timestamp
    row.last_observed_at = timestamp
    return row


def rotate(runner_id, *, reason, now=None):
    with authorization.authorized_session() as session:
        timestamp = _now(now)
        row = repo.get_runner(session, runner_id)
        if row is None:
            raise authorization.TrustedAuthorizationError()
        grant = _human(session, row.project_id, row.workspace_id)
        _screen(reason)
        settings = _live(session, row, timestamp)
        if row.status != "active":
            raise LifecycleError(409)
        if repo.live_count(session, row.project_id, timestamp, excluding=row.id) >= 100:
            raise LifecycleError(429)
        before = _digest(row)
        row.generation += 1
        issued = _issue(row, settings, timestamp)
        _audit(
            session,
            row,
            "runner.credential_rotated",
            reason,
            before,
            grant=grant,
            now=timestamp,
        )
        return issued


def revoke(runner_id, *, reason, now=None):
    with authorization.authorized_session() as session:
        timestamp = _now(now)
        row = repo.get_runner(session, runner_id)
        if row is None:
            raise authorization.TrustedAuthorizationError()
        grant = _human(session, row.project_id, row.workspace_id)
        _screen(reason)
        if timestamp < _utc(row.last_observed_at):
            raise LifecycleError(409)
        before = _digest(row)
        if row.status != "revoked":
            row.generation += 1
            row.status = "revoked"
            row.credential_hash = None
            row.last_observed_at = timestamp
            _audit(
                session,
                row,
                "runner.revoked",
                reason,
                before,
                grant=grant,
                now=timestamp,
            )
        return _view(row)


class RunnerTaskHealth(ClosedModel):
    run_id: Identifier
    step_id: Identifier
    attempt_id: Identifier


class RunnerHealth(ClosedModel):
    id: Identifier
    project_id: Positive
    workspace_id: Positive
    tags: Annotated[list[Identifier], Field(max_length=16)]
    tool: Identifier
    profile_digest: Digest
    runner_version: Identifier
    protocol_version: Literal[1]
    generation: Positive
    status: Literal["pending", "active", "revoked"]
    last_seen_at: StrictStr | None
    credential_expires_at: StrictStr | None
    isolation_qualified: Literal[False]
    current_task: RunnerTaskHealth | None


class RunnerHealthPage(ClosedModel):
    items: Annotated[list[RunnerHealth], Field(max_length=100)]
    cursor: CursorEnvelope


def health(project_id, workspace_id, *, limit=25, cursor=None):
    from services.infra_automation_service import _binding, _page

    with authorization.authorized_session() as session:
        grant = _human(session, project_id, workspace_id, mutation=False)

        def render(item):
            row = item.runner
            view = _view(row)
            active = session.scalar(
                select(InfraAutomationAttempt)
                .join(
                    InfraAutomationRunnerTask,
                    InfraAutomationRunnerTask.attempt_id == InfraAutomationAttempt.id,
                )
                .where(
                    InfraAutomationRunnerTask.runner_id == row.id,
                    InfraAutomationAttempt.project_id == project_id,
                    InfraAutomationAttempt.workspace_id == workspace_id,
                    InfraAutomationAttempt.state.in_(("claimed", "running")),
                )
                .order_by(
                    InfraAutomationAttempt.created_at.desc(),
                    InfraAutomationAttempt.id.desc(),
                )
                .limit(1)
            )
            view["current_task"] = (
                {
                    "run_id": active.run_id,
                    "step_id": active.step_id,
                    "attempt_id": active.id,
                }
                if active
                else None
            )
            return RunnerHealth.model_validate(view).model_dump(mode="json")

        page = _page(
            binding=_binding(grant, workspace_id=workspace_id, family="runner-health"),
            limit=limit,
            cursor=cursor,
            maximum=repo.max_sequence(session, project_id, workspace_id),
            fetch=lambda **kw: repo.list_runners(
                session, project_id, workspace_id, **kw
            ),
            render=render,
        )
        return RunnerHealthPage.model_validate(page).model_dump(mode="json")


def validate_runner(session, row, *, now=None):
    """Deny-only live registry check; never supplies bearer or task authority."""
    timestamp = _now(now)
    if (
        row.status != "active"
        or row.credential_hash is None
        or row.credential_expires_at is None
        or not _utc(row.created_at)
        <= timestamp
        < _utc(row.credential_expires_at).replace(microsecond=0)
    ):
        raise LifecycleError(401)
    _live(session, row, timestamp)
    return row
