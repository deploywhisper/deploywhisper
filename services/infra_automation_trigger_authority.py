"""Raw signed credentials, durable replay fences and live machine scope.

No human session is issued. The private proof remains request-local; every
protected operation re-resolves its operator key and database authority.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import secrets

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError

import config
from infra_automation.lifecycle import LifecycleError, MachineAuthorityStamp
from infra_automation.trigger_contracts import TriggerKeyManifest
from infra_automation.trigger_signing import verify_request
from infra_automation.runner.catalog import read_protected
from models.database import SessionLocal
from models.repositories import project_memberships
from models.tables import (
    IdentityAccount,
    InfraAutomationTriggerClock,
    InfraAutomationTriggerNonce,
)
from services.identity_service import IdentityService, IdentityError, VerifiedPrincipal
from services import project_service as auth
from services import infra_automation_support as support
from infra_automation.storage import ensure_capacity

GLOBAL_NONCES = 4096
KEY_NONCES = 1024
_CURRENT: ContextVar[TriggerAuthority | None] = ContextVar(
    "signed_trigger_authority", default=None
)


def _utc(value):
    if type(value) is not datetime or value.tzinfo is None:
        raise LifecycleError(503)
    return value.astimezone(timezone.utc)


def _instant(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Invalid manifest.")
        result[key] = value
    return result


def _integer(value):
    if len(value.lstrip("-")) > 16:
        raise ValueError("Invalid manifest.")
    result = int(value)
    if abs(result) > 2**53 - 1:
        raise ValueError("Invalid bounded JSON.")
    return result


def _invalid(value):
    raise ValueError("Invalid manifest.")


def bounded_json(raw):
    """Unique-key, integer-only bounded JSON shared by manifest and signed body."""
    if type(raw) is not bytes or not 0 < len(raw) <= 131072:
        raise ValueError("Invalid bounded JSON.")
    depth = 0
    quoted = False
    escaped = False
    for char in raw.decode("utf-8"):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 16:
                raise ValueError("Invalid bounded JSON.")
        elif char in "]}":
            depth -= 1
    value = json.loads(
        raw,
        object_pairs_hook=_unique,
        parse_int=_integer,
        parse_float=_invalid,
        parse_constant=_invalid,
    )
    if type(value) is not dict:
        raise ValueError("Invalid bounded JSON.")
    return value


def _manifest(raw):
    return TriggerKeyManifest.model_validate_json(json.dumps(bounded_json(raw)))


def protect_credentials(value, secret):
    """Screen decoded fields, including every case spelling of a hex key."""
    from infra_automation.artifact_intake import screen_decoded_credentials
    import base64

    sensitive = [
        secret.hex(),
        secret.hex().upper(),
        base64.b64encode(secret).decode(),
        base64.urlsafe_b64encode(secret).decode().rstrip("="),
    ]
    try:
        sensitive.append(secret.decode("utf-8"))
    except UnicodeError:
        pass
    screen_decoded_credentials(value, sensitive_values=tuple(sensitive))
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        if secret.hex() in encoded.casefold():
            raise ValueError
    except (ValueError, TypeError, UnicodeError):
        raise LifecycleError(422) from None


def load_key(key_id):
    """The configured file contains references and policy, never signing secrets."""
    try:
        raw = read_protected(config.settings.trigger_keys_path, 131072)
        if not hmac.compare_digest(
            support.digest(raw), config.settings.trigger_keys_sha256
        ):
            raise ValueError
        manifest = _manifest(raw)
        definition = next(
            (item for item in manifest.keys if item.key_id == key_id), None
        )
        if definition is None:
            raise LifecycleError(401)
        secret = config.trigger_secret(definition.secret_env_ref)
        try:
            protect_credentials(definition.model_dump(mode="json"), secret)
        except LifecycleError:
            raise ValueError("Unsafe signing configuration.") from None
        fingerprint = support.digest(
            support.canonical(definition.model_dump(mode="json"))
            + hmac.digest(secret, b"deploywhisper-trigger-key-binding-v1", "sha256")
        )
        return definition, secret, fingerprint
    except LifecycleError:
        raise
    except (OSError, ValueError, TypeError, UnicodeError):
        raise LifecycleError(503) from None


@dataclass
class _ClockObservation:
    at: datetime

    def __call__(self, session):
        _retain_clock(session, self.at)


def _check_clock(session, now, *, require_existing):
    clock = session.get(InfraAutomationTriggerClock, 1, populate_existing=True)
    if clock is None:
        if require_existing:
            raise LifecycleError(503)
        return
    if now < clock.last_seen_at.replace(tzinfo=timezone.utc):
        raise LifecycleError(503)
    observation = auth.register_operation_observation(
        session, "signed-trigger-clock", _ClockObservation(now)
    )
    if type(observation) is not _ClockObservation or now < observation.at:
        raise LifecycleError(503)
    observation.at = now
    _retain_clock(session, now)


def _retain_clock(session, now):
    """Advance only the checked clock; also used after business rollback."""
    try:
        session.execute(
            update(InfraAutomationTriggerClock)
            .where(
                InfraAutomationTriggerClock.id == 1,
                InfraAutomationTriggerClock.last_seen_at < now,
            )
            .values(last_seen_at=now)
            .execution_options(synchronize_session=False)
        )
    except SQLAlchemyError:
        raise LifecycleError(503) from None


def _live_key(session, definition, fingerprint, *, now):
    current, _, current_digest = load_key(definition.key_id)
    if (
        current_digest != fingerprint
        or current != definition
        or now >= _instant(current.expires_at)
    ):
        raise IdentityError()
    account = session.get(IdentityAccount, current.principal_id, populate_existing=True)
    member = project_memberships.get_membership(
        session, principal_id=current.principal_id, project_id=current.project_id
    )
    policy, _ = support.policy_state(session, current.project_id)
    if (
        account is None
        or member is None
        or policy is None
        or not account.enabled
        or account.is_admin
        or account.principal_type != current.principal_type
        or account.authentication_version != current.authentication_version
        or not member.enabled
        or member.role not in {"contributor", "read-only"}
        or member.authorization_version != current.membership_version
        or member.workspace_id != current.workspace_id
        or policy.restore_epoch != current.restore_epoch
    ):
        raise IdentityError()
    return account, member


class TriggerAuthority(IdentityService):
    """A server-created request proof usable only through this instance's token."""

    def __init__(
        self,
        *,
        key_id,
        method,
        path,
        timestamp,
        nonce,
        body,
        signature,
        session_factory=None,
        now=None,
    ):
        super().__init__(
            session_factory or SessionLocal,
            now=now,
            security_profile=config.settings.identity_profile,
            trusted_origin=config.settings.identity_origin,
        )
        self._profile()
        try:
            self.definition, self._secret, self.fingerprint = load_key(key_id)
        except LifecycleError as exc:
            if exc.status_code == 401:
                try:
                    verify_request(
                        secret=b"\0" * 32,
                        signature=signature,
                        now=_utc(self.now()),
                        key_id=key_id,
                        method=method,
                        path=path,
                        timestamp=timestamp,
                        nonce=nonce,
                        body=body,
                    )
                except ValueError:
                    pass
            raise
        self.fields = dict(
            key_id=key_id,
            method=method,
            path=path,
            timestamp=timestamp,
            nonce=nonce,
            body=body,
        )
        self.signature = signature
        self.proof = verify_request(
            secret=self._secret,
            signature=signature,
            now=_utc(self.now()),
            **self.fields,
        )
        self.token = secrets.token_urlsafe(32)
        self.reserved = False

    def resolve_session_in_transaction(self, db, token, *, csrf_token=None):
        try:
            if type(token) is not str or not hmac.compare_digest(token, self.token):
                raise IdentityError()
            now = _utc(self.now())
            verify_request(
                secret=self._secret, signature=self.signature, now=now, **self.fields
            )
            if self.reserved:
                _check_clock(db, now, require_existing=True)
            account, _ = _live_key(db, self.definition, self.fingerprint, now=now)
            return VerifiedPrincipal(
                principal_id=account.id,
                username=account.username,
                principal_type=account.principal_type,
                is_admin=False,
                enabled=True,
                authentication_version=account.authentication_version,
                credential_audience="service-request-v1",
                session_id=self.fingerprint,
                expires_at=min(
                    self.proof.expires_at, _instant(self.definition.expires_at)
                ),
                security_profile=self.security_profile,
                production_eligible=self.security_profile == "https",
            )
        except (ValueError, TypeError, LifecycleError):
            raise IdentityError() from None

    def protect(self, value):
        protect_credentials(value, self._secret)

    def decoded_body(self):
        if not self.reserved:
            raise LifecycleError(401)
        try:
            verified = verify_request(
                secret=self._secret,
                signature=self.signature,
                now=_utc(self.now()),
                **self.fields,
            )
            if verified != self.proof:
                raise ValueError
            value = bounded_json(self.fields["body"])
            self.protect(value)
            return value
        except LifecycleError:
            raise
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise LifecycleError(422) from None

    def bind_model(self, payload, model, paths):
        if self.fields["path"] not in paths:
            raise LifecycleError(403)
        try:
            parsed = model.model_validate(self.decoded_body())
            supplied = support.revalidate(payload, model)
            if support.canonical(parsed.model_dump(mode="json")) != support.canonical(
                supplied.model_dump(mode="json")
            ):
                raise LifecycleError(409)
            return parsed
        except LifecycleError:
            raise
        except (ValueError, TypeError):
            raise LifecycleError(422) from None

    @contextmanager
    def credentials(self, *, transport_check=None):
        token = _CURRENT.set(self)
        try:
            with auth.credential_context(
                self, self.token, mutation=True, transport_check=transport_check
            ):
                yield
        finally:
            _CURRENT.reset(token)

    def reserve_nonce(self):
        """Commit before parsing, so invalid bodies and later rollback consume it."""
        if auth.has_authorized_session():
            raise LifecycleError(503)
        try:
            with self.credentials(), auth.authorized_session() as db:
                auth.guard_project(
                    db,
                    self.definition.project_id,
                    self.definition.workspace_id,
                    "automation.read",
                )
                now = _utc(self.now())
                clock = db.get(InfraAutomationTriggerClock, 1)
                if clock is not None and now < clock.last_seen_at.replace(
                    tzinfo=timezone.utc
                ):
                    raise LifecycleError(503)
                db.execute(
                    delete(InfraAutomationTriggerNonce).where(
                        InfraAutomationTriggerNonce.expires_at <= now
                    )
                )
                nonce_hash = hashlib.sha256(
                    self.fields["nonce"].encode("ascii")
                ).hexdigest()
                if (
                    db.get(
                        InfraAutomationTriggerNonce,
                        (self.definition.key_id, nonce_hash),
                    )
                    is not None
                ):
                    raise LifecycleError(401)
                global_count = (
                    db.scalar(
                        select(func.count()).select_from(InfraAutomationTriggerNonce)
                    )
                    or 0
                )
                key_count = (
                    db.scalar(
                        select(func.count())
                        .select_from(InfraAutomationTriggerNonce)
                        .where(
                            InfraAutomationTriggerNonce.key_id == self.definition.key_id
                        )
                    )
                    or 0
                )
                if global_count >= GLOBAL_NONCES or key_count >= KEY_NONCES:
                    raise LifecycleError(429)
                from models.repositories.infra_automation_triggers import retained_bytes
                from models.repositories.infra_automation_units import (
                    retained_bytes as unit_bytes,
                )
                from models.tables import InfraAutomationRun

                bounds = config.engine_bounds()
                run_total = (
                    db.scalar(select(func.sum(InfraAutomationRun.retained_bytes))) or 0
                )
                project_total = (
                    db.scalar(
                        select(func.sum(InfraAutomationRun.retained_bytes)).where(
                            InfraAutomationRun.project_id == self.definition.project_id
                        )
                    )
                    or 0
                )
                delta = 512 + (1024 if clock is None else 0)
                if (
                    run_total + unit_bytes(db) + retained_bytes(db) + delta
                    > bounds.global_bytes
                    or project_total
                    + unit_bytes(db, self.definition.project_id)
                    + retained_bytes(db, self.definition.project_id)
                    + 512
                    > bounds.project_bytes
                ):
                    raise LifecycleError(429)
                ensure_capacity(db, additional_bytes=delta)
                if clock is None:
                    db.add(InfraAutomationTriggerClock(id=1, last_seen_at=now))
                else:
                    clock.last_seen_at = now
                db.add(
                    InfraAutomationTriggerNonce(
                        key_id=self.definition.key_id,
                        nonce_digest=nonce_hash,
                        project_id=self.definition.project_id,
                        expires_at=self.proof.expires_at,
                        created_at=now,
                    )
                )
                auth.guard_project(
                    db,
                    self.definition.project_id,
                    self.definition.workspace_id,
                    "automation.read",
                )
            self.reserved = True
        except SQLAlchemyError:
            raise LifecycleError(503) from None


def current():
    return _CURRENT.get()


def requester(session, grant):
    """Recheck actual credentials; a caller-built principal is never sufficient."""
    if (
        grant.principal.principal_type == "human"
        and grant.principal.credential_audience == "human"
    ):
        return
    authority = current()
    if (
        authority is None
        or not authority.reserved
        or grant.principal.credential_audience != "service-request-v1"
    ):
        raise auth.TrustedAuthorizationError()
    definition = authority.definition
    if (grant.principal.principal_id, grant.project_id, grant.workspace_id) != (
        definition.principal_id,
        definition.project_id,
        definition.workspace_id,
    ):
        raise auth.TrustedAuthorizationError()
    authority.resolve_session_in_transaction(session, authority.token)


def stamp_fields(session, grant):
    requester(session, grant)
    authority = current()
    if grant.principal.principal_type == "human":
        return {}
    return dict(
        credential_audience="service-request-v1",
        principal_type=grant.principal.principal_type,
        key_id=authority.definition.key_id,
        key_digest=authority.fingerprint,
        credential_expires_at=authority.definition.expires_at,
    )


def live_machine_stamp(session, stamp, *, now=None):
    """Deny-only effect check after the request nonce's admission window ends."""
    if type(stamp) is not MachineAuthorityStamp:
        return False
    try:
        definition, _, fingerprint = load_key(stamp.key_id)
        if (
            fingerprint != stamp.key_digest
            or definition.principal_id != stamp.principal_id
            or definition.principal_type != stamp.principal_type
            or definition.project_id != stamp.project_id
            or definition.workspace_id != stamp.workspace_id
            or definition.authentication_version != stamp.authentication_version
            or definition.membership_version != stamp.membership_version
            or definition.restore_epoch != stamp.restore_epoch
            or definition.expires_at != stamp.credential_expires_at
        ):
            return False
        timestamp = _utc(now or datetime.now(timezone.utc))
        _check_clock(session, timestamp, require_existing=True)
        _live_key(session, definition, fingerprint, now=timestamp)
        return True
    except IdentityError:
        return False
    except LifecycleError as exc:
        if exc.status_code == 401:
            return False
        raise
    except (ValueError, TypeError):
        raise LifecycleError(503) from None


def enforce_scope(principal, project_id, workspace_id):
    value = current()
    # Existing trusted-code policy doubles remain distinct from HTTP issuance.
    if value is not None and (principal.principal_id, project_id, workspace_id) != (
        value.definition.principal_id,
        value.definition.project_id,
        value.definition.workspace_id,
    ):
        raise auth.TrustedAuthorizationError()


def run_read_predicate():
    """Filter before pagination/counting; machine keys only see their own runs."""
    from sqlalchemy import and_, exists, tuple_
    from models.tables import InfraAutomationRun, InfraAutomationRunOrigin

    value = current()
    if value is None:
        return None
    key = value.definition
    return and_(
        InfraAutomationRun.project_id == key.project_id,
        InfraAutomationRun.workspace_id == key.workspace_id,
        InfraAutomationRun.requested_by == key.principal_id,
        InfraAutomationRun.revision_id.in_(key.allowed_revision_ids),
        exists(
            select(InfraAutomationRunOrigin.run_id).where(
                InfraAutomationRunOrigin.run_id == InfraAutomationRun.id,
                InfraAutomationRunOrigin.key_id == key.key_id,
                tuple_(
                    InfraAutomationRunOrigin.source_repository_id,
                    InfraAutomationRunOrigin.source_commit_sha,
                ).in_([(s.repository_id, s.commit_sha) for s in key.allowed_sources]),
            )
        ),
    )


def enforce_run_read(session, run):
    from models.tables import InfraAutomationRun

    predicate = run_read_predicate()
    if (
        predicate is not None
        and session.scalar(
            select(InfraAutomationRun.id).where(
                InfraAutomationRun.id == run.id, predicate
            )
        )
        is None
    ):
        raise auth.TrustedAuthorizationError()


def validate_machine_sources(session, grant, revision_id, sources):
    if grant.principal.credential_audience != "service-request-v1":
        return
    requester(session, grant)
    value = current()
    allowed = {
        (item.repository_id, item.commit_sha)
        for item in value.definition.allowed_sources
    }
    if (
        revision_id not in value.definition.allowed_revision_ids
        or not sources
        or any(source.kind != "collected" for source in sources)
    ):
        raise LifecycleError(422)
    pairs = {(source.repository_id, source.commit_sha) for source in sources}
    if len(pairs) != 1 or not pairs.issubset(allowed):
        raise LifecycleError(422)


def admission_workflow(session, workflow_id, workspace_id):
    """Resolve a project-wide publication through the concrete signed scope."""
    value = current()
    if value is None:
        return support.workflow(
            session, workflow_id, "automation.request", mutation=True
        )
    from models.repositories import infra_automation_workflows as workflows

    row = workflows.get_workflow(session, support.identifier(workflow_id))
    if (
        row is None
        or row.project_id != value.definition.project_id
        or workspace_id != value.definition.workspace_id
        or row.workspace_id not in {None, workspace_id}
    ):
        raise auth.TrustedAuthorizationError()
    grant = support.scope(
        session, row.project_id, workspace_id, "automation.request", mutation=True
    )
    requester(session, grant)
    return row, grant
