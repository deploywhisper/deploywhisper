"""Verified local humans, one-use recovery and deployment-bound sessions.

Only the local operator CLI may expose setup/recovery issuance. These methods
trust host access; account administration instead requires live admin sessions.
Identity does not confer project membership or automation capabilities.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
import threading
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, SecretStr
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models.database import SessionLocal
from models.repositories.identity import (
    account_by_username,
    revoke_sessions,
    transaction,
)
from models.tables import (
    AppSetting,
    IdentityAccount,
    IdentityCredential,
    IdentitySession,
)

ITERATIONS = 600_000
SETUP_SECONDS = 300
IDLE_SECONDS = 300
ABSOLUTE_SECONDS = 3600
LIMIT_KEY = "identity.login_limits.v1"
_VERIFIER = re.compile(r"pbkdf2\$600000\$[0-9a-f]{32}\$[0-9a-f]{64}")
_DUMMY_VERIFIER = "pbkdf2$600000$" + "0" * 32 + "$" + "0" * 64
_DERIVATION_SLOT = threading.BoundedSemaphore(1)


class IdentityError(Exception):
    """Safe adapter-facing error containing no account or credential values."""

    def __init__(self, status_code: int = 401, code: str = "authentication_failed"):
        self.status_code = status_code
        self.code = code
        self.message = "Authentication denied."
        super().__init__(self.message)


class AccountView(BaseModel):
    model_config = ConfigDict(frozen=True)
    principal_id: str
    username: str
    principal_type: str
    is_admin: bool
    enabled: bool
    authentication_version: int


class VerifiedPrincipal(AccountView):
    credential_audience: str
    session_id: str
    expires_at: datetime
    security_profile: str
    production_eligible: bool


class IssuedCredential(BaseModel):
    model_config = ConfigDict(frozen=True)
    token: SecretStr
    expires_at: datetime


class IssuedSession(BaseModel):
    model_config = ConfigDict(frozen=True)
    token: SecretStr
    csrf_token: SecretStr
    principal: VerifiedPrincipal


def _bytes(value: str) -> bytes:
    if not isinstance(value, str) or len(value) > 1024:
        raise IdentityError()
    try:
        result = value.encode("utf-8")
    except UnicodeEncodeError:
        raise IdentityError() from None
    if len(result) > 1024:
        raise IdentityError()
    return result


def validate_username(value: str) -> str:
    """Enforce the shared account-name contract for services and HTTP input."""
    encoded = _bytes(value)
    if (
        not 1 <= len(encoded) <= 128
        or value != value.strip()
        or any(ord(c) < 32 for c in value)
    ):
        raise IdentityError()
    return value


def _digest(token: str) -> str:
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise IdentityError()
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


@contextmanager
def _derivation():
    if not _DERIVATION_SLOT.acquire(blocking=False):
        raise IdentityError(429, "authentication_throttled")
    try:
        yield
    finally:
        _DERIVATION_SLOT.release()


def password_verifier(password: str) -> str:
    """Exact qualified verifier; creation rejects short/oversized UTF-8 input."""
    encoded = _bytes(password)
    if len(encoded) < 15:
        raise IdentityError()
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", encoded, salt, ITERATIONS, dklen=32)
    return f"pbkdf2$600000${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        encoded = _bytes(password)
    except IdentityError:
        return False
    if not isinstance(stored, str) or not _VERIFIER.fullmatch(stored):
        return False
    _, _, salt, expected = stored.split("$")
    candidate = hashlib.pbkdf2_hmac(
        "sha256", encoded, bytes.fromhex(salt), ITERATIONS, dklen=32
    )
    return hmac.compare_digest(candidate.hex(), expected)


def _account_view(account: IdentityAccount) -> AccountView:
    return AccountView(
        principal_id=account.id,
        username=account.username,
        principal_type=account.principal_type,
        is_admin=account.is_admin,
        enabled=account.enabled,
        authentication_version=account.authentication_version,
    )


class IdentityService:
    def __init__(
        self,
        session_factory: Callable[[], Session] | None = None,
        now: Callable[[], datetime] | None = None,
        *,
        security_profile: str = "disabled",
        trusted_origin: str = "",
    ) -> None:
        self.session_factory = session_factory or SessionLocal
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.security_profile = security_profile
        self.trusted_origin = trusted_origin

    @contextmanager
    def _transaction(self):
        try:
            with transaction(self.session_factory) as db:
                yield db
        except SQLAlchemyError:
            # Driver messages can contain bound credential material. Do not leak
            # or chain them into API errors/logs.
            raise IdentityError(503, "authentication_unavailable") from None

    def _profile(self):
        try:
            parsed = urlsplit(self.trusted_origin)
            valid = (
                len(self.trusted_origin) <= 512
                and parsed.hostname
                and not parsed.username
                and not parsed.password
                and not parsed.path
                and not parsed.query
                and not parsed.fragment
                and not any(c.isspace() for c in self.trusted_origin)
            )
            # Accessing port rejects malformed netloc values.
            parsed.port
            valid = valid and (
                (self.security_profile == "https" and parsed.scheme == "https")
                or (
                    self.security_profile == "local-development"
                    and parsed.scheme == "http"
                    and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                )
            )
        except ValueError:
            valid = False
        if not valid:
            raise IdentityError(403, "identity_profile_disabled")

    def _issue_credential(
        self, db, purpose: str, principal_id: str | None, now: datetime
    ) -> IssuedCredential:
        # Issuing new local evidence supersedes all unused evidence in its scope.
        for previous in db.scalars(
            select(IdentityCredential).where(
                IdentityCredential.purpose == purpose,
                IdentityCredential.principal_id == principal_id,
                IdentityCredential.consumed_at.is_(None),
            )
        ):
            previous.consumed_at = now
        token = secrets.token_urlsafe(32)
        expires = now + timedelta(seconds=SETUP_SECONDS)
        db.add(
            IdentityCredential(
                id=secrets.token_hex(16),
                token_hash=_digest(token),
                purpose=purpose,
                principal_id=principal_id,
                created_at=now,
                expires_at=expires,
            )
        )
        return IssuedCredential(token=SecretStr(token), expires_at=expires)

    def issue_setup_credential(self) -> IssuedCredential:
        with self._transaction() as db:
            if db.scalar(select(IdentityAccount.id).limit(1)):
                raise IdentityError()
            return self._issue_credential(db, "setup", None, _utc(self.now()))

    def _consume(
        self, db, token: str, purpose: str, now: datetime
    ) -> IdentityCredential:
        credential = db.scalar(
            select(IdentityCredential).where(
                IdentityCredential.token_hash == _digest(token),
                IdentityCredential.purpose == purpose,
            )
        )
        if (
            credential is None
            or credential.consumed_at is not None
            or now < _utc(credential.created_at)
            or now >= _utc(credential.expires_at)
        ):
            raise IdentityError()
        credential.consumed_at = now
        return credential

    def bootstrap(self, setup_token: str, username: str, password: str) -> AccountView:
        username = validate_username(username)
        with _derivation(), self._transaction() as db:
            now = _utc(self.now())
            if db.scalar(select(IdentityAccount.id).limit(1)):
                raise IdentityError()
            self._consume(db, setup_token, "setup", now)
            account = IdentityAccount(
                id=secrets.token_hex(16),
                username=username,
                principal_type="human",
                password_verifier=password_verifier(password),
                is_admin=True,
                enabled=True,
                authentication_version=1,
                created_at=now,
            )
            db.add(account)
            return _account_view(account)

    def _rate_limit(self, username: str, now: datetime) -> None:
        # A single bounded, nonsecret settings record survives worker/restart
        # boundaries. Unknown usernames are hashed; at most 20 slots per minute.
        throttled = False
        with self._transaction() as db:
            record = db.get(AppSetting, LIMIT_KEY)
            state = (
                json.loads(record.value)
                if record
                else {"started": now.timestamp(), "attempts": 0, "accounts": {}}
            )
            timestamp = now.timestamp()
            if timestamp >= state["started"] + 60:
                state = {"started": timestamp, "attempts": 0, "accounts": {}}
            if timestamp < state["started"] or state["attempts"] >= 20:
                throttled = True
            else:
                state["attempts"] += 1
                key = hashlib.sha256(username.encode("utf-8")).hexdigest()
                attempts = state["accounts"].get(key, 0)
                throttled = attempts >= 5
                state["accounts"][key] = min(attempts + 1, 5)
            if record is None:
                db.add(AppSetting(key=LIMIT_KEY, value=json.dumps(state)))
            else:
                record.value = json.dumps(state)
        if throttled:
            raise IdentityError(429, "authentication_throttled")

    def login(self, username: str, password: str) -> IssuedSession:
        self._profile()
        try:
            username = validate_username(username)
            _bytes(password)
        except IdentityError:
            self.record_failed_login_attempt()
            raise
        with _derivation():
            self._rate_limit(username, _utc(self.now()))
            with self._transaction() as db:
                account = account_by_username(db, username)
                valid = verify_password(
                    password, account.password_verifier if account else _DUMMY_VERIFIER
                )
                if (
                    not valid
                    or account is None
                    or not account.enabled
                    or account.principal_type != "human"
                ):
                    raise IdentityError()
                now = _utc(self.now())
                revoke_sessions(db, account.id, now)
                return self._issue_session(
                    db, account, now, now + timedelta(seconds=ABSOLUTE_SECONDS)
                )

    def record_failed_login_attempt(self) -> None:
        """Bound invalid envelopes without deriving passwords or touching sessions."""
        self._profile()
        self._rate_limit("identity:invalid-login", _utc(self.now()))

    def _principal(
        self, account: IdentityAccount, session: IdentitySession
    ) -> VerifiedPrincipal:
        return VerifiedPrincipal(
            **_account_view(account).model_dump(),
            credential_audience=session.audience,
            session_id=session.id,
            expires_at=_utc(session.expires_at),
            security_profile=session.security_profile,
            production_eligible=session.security_profile == "https",
        )

    def _issue_session(
        self,
        db,
        account: IdentityAccount,
        now: datetime,
        expires: datetime,
        *,
        authenticated_at: datetime | None = None,
    ) -> IssuedSession:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        session = IdentitySession(
            id=secrets.token_hex(16),
            principal_id=account.id,
            token_hash=_digest(token),
            csrf_hash=_digest(csrf),
            audience="human",
            security_profile=self.security_profile,
            trusted_origin=self.trusted_origin,
            authentication_version=account.authentication_version,
            created_at=authenticated_at or now,
            last_seen_at=now,
            expires_at=expires,
        )
        db.add(session)
        return IssuedSession(
            token=SecretStr(token),
            csrf_token=SecretStr(csrf),
            principal=self._principal(account, session),
        )

    def _resolve(self, db, token: str, now: datetime, csrf_token: str | None = None):
        self._profile()
        session = db.scalar(
            select(IdentitySession).where(IdentitySession.token_hash == _digest(token))
        )
        account = db.get(IdentityAccount, session.principal_id) if session else None
        if (
            session is None
            or account is None
            or not account.enabled
            or account.principal_type != "human"
            or session.audience != "human"
            or session.revoked_at is not None
            or session.authentication_version != account.authentication_version
            or session.security_profile != self.security_profile
            or session.trusted_origin != self.trusted_origin
            or now < _utc(session.created_at)
            or now < _utc(session.last_seen_at)
            or now >= _utc(session.expires_at)
            or now >= _utc(session.last_seen_at) + timedelta(seconds=IDLE_SECONDS)
        ):
            raise IdentityError()
        if csrf_token is not None:
            try:
                valid = hmac.compare_digest(_digest(csrf_token), session.csrf_hash)
            except IdentityError:
                valid = False
            if not valid:
                raise IdentityError(403, "csrf_failed")
        return account, session

    def resolve_session(
        self, token: str, *, csrf_token: str | None = None, touch: bool = True
    ) -> VerifiedPrincipal:
        with self._transaction() as db:
            now = _utc(self.now())
            account, session = self._resolve(db, token, now, csrf_token)
            if touch:
                session.last_seen_at = now
            return self._principal(account, session)

    def rotate_session(self, token: str, *, csrf_token: str) -> IssuedSession:
        with self._transaction() as db:
            now = _utc(self.now())
            account, session = self._resolve(db, token, now, csrf_token or "")
            session.revoked_at = now
            return self._issue_session(
                db,
                account,
                now,
                _utc(session.expires_at),
                authenticated_at=_utc(session.created_at),
            )

    def logout(self, token: str, *, csrf_token: str) -> None:
        with self._transaction() as db:
            now = _utc(self.now())
            _, session = self._resolve(db, token, now, csrf_token or "")
            session.revoked_at = now

    def _admin(self, db, actor_token: str, csrf_token: str, now: datetime):
        account, session = self._resolve(db, actor_token, now, csrf_token or "")
        if not account.is_admin:
            raise IdentityError(403, "administrator_required")
        return account, session

    def create_account(
        self,
        actor_token: str,
        username: str,
        password: str,
        *,
        csrf_token: str,
        is_admin: bool = False,
    ) -> AccountView:
        username = validate_username(username)
        with _derivation(), self._transaction() as db:
            now = _utc(self.now())
            _, actor_session = self._admin(db, actor_token, csrf_token, now)
            if account_by_username(db, username):
                raise IdentityError()
            account = IdentityAccount(
                id=secrets.token_hex(16),
                username=username,
                password_verifier=password_verifier(password),
                principal_type="human",
                is_admin=is_admin,
                enabled=True,
                authentication_version=1,
                created_at=now,
            )
            db.add(account)
            actor_session.last_seen_at = now
            return _account_view(account)

    def revoke_account(
        self, actor_token: str, target_principal_id: str, *, csrf_token: str
    ) -> AccountView:
        with self._transaction() as db:
            now = _utc(self.now())
            _, actor_session = self._admin(db, actor_token, csrf_token, now)
            if (
                not isinstance(target_principal_id, str)
                or len(target_principal_id) > 64
            ):
                raise IdentityError()
            account = db.get(IdentityAccount, target_principal_id)
            if account is None or account.principal_type != "human":
                raise IdentityError()
            account.enabled = False
            account.revoked_at = now
            account.authentication_version += 1
            revoke_sessions(db, account.id, now)
            actor_session.last_seen_at = now
            return _account_view(account)

    def issue_recovery_credential(self, username: str) -> IssuedCredential:
        username = validate_username(username)
        with self._transaction() as db:
            account = account_by_username(db, username)
            if account is None or account.principal_type != "human":
                raise IdentityError()
            return self._issue_credential(db, "recovery", account.id, _utc(self.now()))

    def recover(self, recovery_token: str, password: str) -> AccountView:
        with _derivation(), self._transaction() as db:
            now = _utc(self.now())
            evidence = self._consume(db, recovery_token, "recovery", now)
            account = db.get(IdentityAccount, evidence.principal_id)
            if account is None or account.principal_type != "human":
                raise IdentityError()
            account.password_verifier = password_verifier(password)
            account.authentication_version += 1
            account.enabled = True
            account.revoked_at = None
            revoke_sessions(db, account.id, now)
            return _account_view(account)
