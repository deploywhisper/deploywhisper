"""Private operator issuance and exact consumed-operation reconciliation checks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
import hashlib
import hmac
import secrets

from pydantic import SecretStr
from sqlalchemy import select, update

from infra_automation import claims, reconciliation
from infra_automation.contracts import SAFE_INTEGER
from infra_automation.lifecycle import LifecycleError, MutationRequest
from infra_automation.operator_recovery import RecoveryError
from infra_automation import operator_recovery
from infra_automation.receiver_recovery import (
    MAX_ISSUES,
    PREFIX,
    RecoveryAuthentication,
)
from infra_automation.receiver_http_contracts import (
    CallbackEnvelope,
    source_identity_digest,
)
from models.receiver_recovery import ReceiverRecoveryCredential
from models.operator_recovery import RecoveryState
from models.repositories import infra_automation_targets as registry
from models.repositories import infra_automation_runs as runs
from models.repositories import project_memberships as memberships
from models.tables import IdentityAccount, Project
from services import infra_automation_support as support
from services import project_service as authorization
from services.identity_service import IssuedCredential


def _now():
    return datetime.now(timezone.utc)


def _clock(*floors):
    value = _now()
    if type(value) is not datetime or value.tzinfo is None:
        raise LifecycleError(503)
    value = value.astimezone(timezone.utc)
    if any(value < runs.utc(floor) for floor in floors if floor is not None):
        raise LifecycleError(503)
    return value


def is_recovery(credential):
    return type(
        getattr(credential, "secret", None)
    ) is str and credential.secret.startswith(PREFIX)


def _hash(token):
    if (
        type(token) is not str
        or not token.startswith(PREFIX)
        or len(token) != len(PREFIX) + 64
    ):
        raise authorization.TrustedAuthorizationError()
    try:
        if len(bytes.fromhex(token[len(PREFIX) :])) != 32:
            raise ValueError
    except ValueError:
        raise authorization.TrustedAuthorizationError() from None
    return hashlib.sha256(
        b"deploywhisper-receiver-reconciliation-v1\0" + token.encode("ascii")
    ).hexdigest()


def _context(session, store=None):
    configured = operator_recovery.configured_store()
    if configured is None or (
        store is not None and configured.control != store.control
    ):
        raise LifecycleError(503)
    try:
        value = configured.assert_ready(effects=False, session=session)
    except (RecoveryError, OSError):
        raise LifecycleError(503) from None
    state = session.get(RecoveryState, 1, populate_existing=True)
    if state is None:
        raise LifecycleError(503)
    _clock(state.updated_at)
    return value


def _actor(session, operation):
    actor = session.get(
        IdentityAccount, operation.receiver_principal_id, populate_existing=True
    )
    if (
        actor is None
        or actor.principal_type != "service"
        or actor.is_admin
        or not actor.enabled
        or not 1 <= actor.authentication_version <= SAFE_INTEGER
    ):
        raise authorization.TrustedAuthorizationError()
    return actor


def _issuer(session, identifier, authentication_version, membership_version, operation):
    actor = session.get(IdentityAccount, identifier, populate_existing=True)
    member = memberships.get_membership(
        session, principal_id=identifier, project_id=operation.project_id
    )
    if (
        actor is None
        or actor.principal_type != "human"
        or not actor.enabled
        or not actor.is_admin
        or actor.authentication_version != authentication_version
        or member is None
        or not member.enabled
        or member.authorization_version != membership_version
        or member.workspace_id not in (None, operation.workspace_id)
        or "automation.admin"
        not in authorization.PROJECT_ROLE_CAPABILITIES.get(member.role, ())
    ):
        raise authorization.TrustedAuthorizationError()
    projects = select(Project.id)
    if authorization._profile() == "legacy-evaluation":
        projects = projects.where(
            authorization._protected_project_predicate(Project.id)
        )
    for project_id in session.scalars(projects):
        current = memberships.get_membership(
            session, principal_id=identifier, project_id=project_id
        )
        if (
            current is None
            or not current.enabled
            or current.workspace_id is not None
            or "settings.manage"
            not in authorization.PROJECT_ROLE_CAPABILITIES.get(current.role, ())
        ):
            raise authorization.TrustedAuthorizationError()
    return actor


def _eligible(session, operation, grant):
    from services.infra_automation_handoffs import _receipt
    from services import infra_automation_targets as targets

    if (
        operation.broken
        or grant.status != "consumed"
        or grant.consumed_at is None
        or _receipt(grant) is None
    ):
        raise LifecycleError(409)
    if support.digest(grant.receipt_bytes) != grant.receipt_digest:
        raise LifecycleError(503)
    capture, _ = targets.captured_target(
        session, operation.run_id, operation.step_id, live=False
    )
    lock = registry.get_lock(session, capture.lock_id)
    if (
        lock is None
        or lock.run_id != operation.run_id
        or lock.target_id != operation.target_id
        or lock.status not in {"held", "resolved"}
    ):
        raise LifecycleError(409)
    if (
        operation.state in {"consumed", "accepted", "running", "delivery_unknown"}
        and lock.status == "held"
    ):
        return "status_terminal", lock
    if operation.state not in {"succeeded", "failed"}:
        raise LifecycleError(409)
    latest = reconciliation.latest(session, operation.id, "callback")
    try:
        envelope = CallbackEnvelope.model_validate(latest)
        message = envelope.message
        if (
            envelope.operation_id != operation.id
            or envelope.run_id != operation.run_id
            or envelope.binding_digest != operation.receiver_binding_digest
            or message.operation_id != operation.id
            or message.operation != "outcome"
            or message.sequence != 2
            or message.state != operation.state
            or envelope.source_identity_digest
            != source_identity_digest(message.binding)
        ):
            raise ValueError
        from infra_automation.receiver_protocol import receiver_binding_bytes

        if receiver_binding_bytes(message.binding) != operation.receiver_binding_bytes:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise LifecycleError(409) from None
    return "status_only", lock


_BOUND_FIELDS = (
    "operation_id",
    "project_id",
    "workspace_id",
    "receiver_id",
    "receiver_principal_id",
    "installation_id",
    "generation",
    "project_restore_epoch",
    "receiver_authentication_version",
    "issuer_id",
    "issuer_authentication_version",
    "issuer_membership_version",
    "version",
    "issue_count",
    "mode",
    "token_hash",
    "binding_digest",
    "receipt_digest",
    "issued_at",
    "expires_at",
)


def _binding(value):
    fields = (
        value
        if isinstance(value, dict)
        else {name: getattr(value, name) for name in _BOUND_FIELDS}
    )
    return {
        name: runs.utc(fields[name]).isoformat()
        if isinstance(fields[name], datetime)
        else fields[name]
        for name in _BOUND_FIELDS
    }


@dataclass
class _ClockObservation:
    operation_id: str
    version: int
    credential_digest: str
    at: datetime

    def __call__(self, session):
        # Only a deny-only clock survives a rejected operation. Rotation or
        # failed first issuance cannot apply this observation to another token.
        session.execute(
            update(ReceiverRecoveryCredential)
            .where(
                ReceiverRecoveryCredential.operation_id == self.operation_id,
                ReceiverRecoveryCredential.version == self.version,
                ReceiverRecoveryCredential.credential_digest == self.credential_digest,
                ReceiverRecoveryCredential.last_observed_at < self.at,
            )
            .values(last_observed_at=self.at)
            .execution_options(synchronize_session=False)
        )


def _observe(session, sidecar, observed):
    observation = authorization.register_operation_observation(
        session,
        f"receiver-recovery-clock:{sidecar.operation_id}:{sidecar.version}",
        _ClockObservation(
            sidecar.operation_id, sidecar.version, sidecar.credential_digest, observed
        ),
    )
    if type(observation) is not _ClockObservation or observed < observation.at:
        raise LifecycleError(503)
    observation.at = observed
    observation(session)


def issue_credential(store, operation_id, reason):
    """Fresh global human/operator command; plaintext returns once to private writer."""
    from services import infra_automation_targets as targets
    from services.infra_automation_handoffs import _default_service

    operation_id = support.identifier(operation_id)
    try:
        reason = MutationRequest(reason=reason).reason
    except ValueError:
        raise LifecycleError(422) from None
    if PREFIX in reason:
        raise LifecycleError(422)
    support.screened_label(reason)
    with authorization.authorized_session() as session:
        context = _context(session, store)
        if context["phase"] != "reconciliation_required":
            raise LifecycleError(409)
        operation, grant, _, _ = _default_service._load(session, operation_id)
        human = targets._admin(
            session, operation.project_id, operation.workspace_id, mutation=True
        )
        receiver = _actor(session, operation)
        mode, lock = _eligible(session, operation, grant)
        policy, settings = support.policy_state(session, operation.project_id)
        if policy is None:
            raise LifecycleError(503)
        parent = runs.get_run(session, operation.run_id)
        previous = session.get(
            ReceiverRecoveryCredential, operation.id, populate_existing=True
        )
        observed = _clock(
            operation.last_observed_at,
            grant.consumed_at,
            lock.updated_at,
            parent.last_observed_at,
            previous.last_observed_at if previous else None,
        )
        issued_at = observed
        expires_at = (
            observed + timedelta(seconds=settings.credential_ttl_seconds)
        ).replace(microsecond=0)
        version = previous.version + 1 if previous else 1
        count = (
            previous.issue_count + 1
            if previous and previous.generation == context["generation"]
            else 1
        )
        if version > SAFE_INTEGER or count > MAX_ISSUES:
            raise LifecycleError(429)
        if previous and previous.mode == "status_only" and mode != "status_only":
            raise LifecycleError(409)
        secret = PREFIX + secrets.token_hex(32)
        values = dict(
            operation_id=operation.id,
            project_id=operation.project_id,
            workspace_id=operation.workspace_id,
            receiver_id=operation.receiver_id,
            receiver_principal_id=operation.receiver_principal_id,
            installation_id=context["installation_id"],
            generation=context["generation"],
            project_restore_epoch=policy.restore_epoch,
            receiver_authentication_version=receiver.authentication_version,
            issuer_id=human.principal.principal_id,
            issuer_authentication_version=human.principal.authentication_version,
            issuer_membership_version=human.authorization_version,
            version=version,
            issue_count=count,
            mode=mode,
            token_hash=_hash(secret),
            binding_digest=operation.receiver_binding_digest,
            receipt_digest=grant.receipt_digest,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        digest = support.digest(support.canonical(_binding(values)))
        before = previous.credential_digest if previous else None
        # Account the retained scalar row and audit (including duplicated reason)
        # conservatively on every rotation, plus bounded row/index bookkeeping.
        charge = (
            len(support.canonical(_binding(values)))
            + len(reason.encode("utf-8")) * 2
            + 2048
        )
        claims._charge(session, parent, charge, observed)
        if previous:
            changed = session.execute(
                update(ReceiverRecoveryCredential)
                .where(
                    ReceiverRecoveryCredential.operation_id == operation.id,
                    ReceiverRecoveryCredential.version == previous.version,
                )
                .values(**values, credential_digest=digest, last_observed_at=observed)
            )
            if changed.rowcount != 1:
                raise LifecycleError(409)
        else:
            session.add(
                ReceiverRecoveryCredential(
                    **values, credential_digest=digest, last_observed_at=observed
                )
            )
        session.flush()
        support.append_audit(
            session,
            human,
            workspace_id=operation.workspace_id,
            event_type="receiver_recovery_credential_issued",
            target_id=operation.id,
            reason=reason,
            before_digest=before,
            after_digest=digest,
        )
        # Re-enter verified human checks and all live credential bindings after
        # quota/audit callbacks, inside the reserved rollback-capable transaction.
        targets._admin(
            session, operation.project_id, operation.workspace_id, mutation=True
        )
        authenticate(session, operation, grant, secret, operation="status")
        return IssuedCredential(token=SecretStr(secret), expires_at=expires_at)


def authenticate(session, operation_row, grant, token, *, operation):
    """Deny-only authentication; never emits original action/consumption authority."""
    authorization._require_operation(session)
    if operation not in {"status", "terminal"}:
        raise authorization.TrustedAuthorizationError()
    supplied = _hash(token)
    sidecar = session.get(
        ReceiverRecoveryCredential, operation_row.id, populate_existing=True
    )
    if sidecar is None or not hmac.compare_digest(supplied, sidecar.token_hash):
        raise authorization.TrustedAuthorizationError()
    if (
        support.digest(support.canonical(_binding(sidecar)))
        != sidecar.credential_digest
    ):
        raise LifecycleError(503)
    context = _context(session)
    policy, _ = support.policy_state(session, operation_row.project_id)
    actor = _actor(session, operation_row)
    mode, lock = _eligible(session, operation_row, grant)
    if (
        policy is None
        or (
            sidecar.project_id,
            sidecar.workspace_id,
            sidecar.receiver_id,
            sidecar.receiver_principal_id,
            sidecar.installation_id,
            sidecar.generation,
            sidecar.project_restore_epoch,
            sidecar.receiver_authentication_version,
            sidecar.binding_digest,
            sidecar.receipt_digest,
        )
        != (
            operation_row.project_id,
            operation_row.workspace_id,
            operation_row.receiver_id,
            operation_row.receiver_principal_id,
            context["installation_id"],
            context["generation"],
            policy.restore_epoch,
            actor.authentication_version,
            operation_row.receiver_binding_digest,
            grant.receipt_digest,
        )
        or sidecar.mode not in {"status_only", "status_terminal"}
        or (sidecar.mode == "status_only" and mode != "status_only")
        or (
            operation == "terminal"
            and (sidecar.mode != "status_terminal" or mode != "status_terminal")
        )
    ):
        raise authorization.TrustedAuthorizationError()
    _issuer(
        session,
        sidecar.issuer_id,
        sidecar.issuer_authentication_version,
        sidecar.issuer_membership_version,
        operation_row,
    )
    parent = runs.get_run(session, operation_row.run_id)
    observed = _clock(
        sidecar.issued_at,
        sidecar.last_observed_at,
        operation_row.last_observed_at,
        grant.consumed_at,
        lock.updated_at,
        parent.last_observed_at,
    )
    _observe(session, sidecar, observed)
    if observed >= runs.utc(sidecar.expires_at):
        raise authorization.TrustedAuthorizationError()
    return RecoveryAuthentication(
        sidecar.operation_id,
        sidecar.version,
        sidecar.credential_digest,
        sidecar.mode,
        sidecar.issuer_id,
        sidecar.generation,
    )
