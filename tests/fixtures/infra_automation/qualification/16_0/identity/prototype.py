"""Disposable WP2 identity experiment, deliberately disconnected from app state.

The qualification client owns all accounts and the temporary SQLite file. Machine
credentials have no generic human-route capabilities; dedicated runner/receiver
protocol permissions are qualified separately, never inferred from a human role.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

ITERATIONS = 600_000
ORIGIN = "https://qualify.invalid"
AUDIENCES = ("human", "service", "agent", "runner", "receiver")
CAPABILITIES = (
    "workflow",
    "publish",
    "run",
    "decision",
    "target",
    "enrollment",
    "report",
    "artifact",
    "policy",
    "settings",
)
ROLE_CAPABILITIES = {
    "admin": frozenset(CAPABILITIES),
    "maintainer": frozenset(
        ("workflow", "run", "decision", "report", "artifact", "policy")
    ),
    "reviewer": frozenset(("decision", "report", "artifact", "policy")),
    "contributor": frozenset(("run", "report", "artifact", "policy")),
    "read-only": frozenset(("report", "artifact", "policy")),
}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def credential_bytes(value):
    if not isinstance(value, str):
        return None
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError:
        return None


def password_verifier(password):
    encoded = credential_bytes(password)
    if encoded is None or not 15 <= len(encoded) <= 1024:
        raise ValueError("password length outside qualification bounds")
    salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac("sha256", encoded, bytes.fromhex(salt), ITERATIONS)
    return f"pbkdf2$600000${salt}${derived.hex()}"


def verify_password(password, stored):
    encoded = credential_bytes(password)
    if encoded is None or len(encoded) > 1024:
        return False
    if not re.fullmatch(r"pbkdf2\$600000\$[0-9a-f]{32}\$[0-9a-f]{64}", stored):
        return False
    _, _, salt, expected = stored.split("$")
    candidate = hashlib.pbkdf2_hmac("sha256", encoded, bytes.fromhex(salt), ITERATIONS)
    return hmac.compare_digest(candidate.hex(), expected)


class IdentityStore:
    """Small file-backed experiment with hashes only and server-owned memberships."""

    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE accounts (id TEXT PRIMARY KEY, verifier TEXT NOT NULL, epoch INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE bootstrap (hash TEXT PRIMARY KEY, expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE sessions (hash TEXT PRIMARY KEY, principal TEXT NOT NULL, audience TEXT NOT NULL,
                csrf_hash TEXT NOT NULL, epoch INTEGER NOT NULL, created REAL NOT NULL, touched REAL NOT NULL);
            CREATE TABLE memberships (principal TEXT NOT NULL, project TEXT NOT NULL, workspace TEXT NOT NULL,
                role TEXT NOT NULL, PRIMARY KEY (principal, project, workspace));
            CREATE TABLE login_limits (principal TEXT PRIMARY KEY, started REAL NOT NULL, attempts INTEGER NOT NULL);
        """)
        # Fixed valid-shaped dummy prevents unknown-account short-circuit timing.
        self.dummy = password_verifier(secrets.token_urlsafe(24))
        self.login_lock = threading.Lock()
        self.global_window = None
        self.global_attempts = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.db.close()

    def add_account(self, principal, verifier):
        with self.db:
            self.db.execute(
                "INSERT INTO accounts(id, verifier) VALUES (?, ?)",
                (principal, verifier),
            )

    def bootstrap_token(self, *, now=None):
        now = time.time() if now is None else now
        token = secrets.token_urlsafe(32)
        with self.db:
            self.db.execute(
                "INSERT INTO bootstrap(hash, expires) VALUES (?, ?)",
                (digest(token), now + 300),
            )
        return token

    def bootstrap(self, token, principal, password, *, now=None):
        now = time.time() if now is None else now
        encoded = credential_bytes(password)
        if encoded is None or not 15 <= len(encoded) <= 1024:
            return False
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if self.db.execute("SELECT 1 FROM accounts LIMIT 1").fetchone():
                return False
            consumed = self.db.execute(
                "UPDATE bootstrap SET used=1 WHERE hash=? AND used=0 AND expires>?",
                (digest(token), now),
            ).rowcount
            if consumed != 1:
                return False
            self.add_account(principal, password_verifier(password))
            return True

    def membership(self, principal, project, workspace, role):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO memberships VALUES (?, ?, ?, ?)",
                (principal, project, workspace, role),
            )
            # Privilege changes revoke all old sessions; caller must authenticate
            # again, which creates a fresh token/CSRF pair rather than upgrading it.
            self.db.execute(
                "UPDATE accounts SET epoch=epoch+1 WHERE id=?", (principal,)
            )

    def login(self, principal, password, *, now=None):
        # No queue of password derivations: a concurrent attempt fails closed.
        if not self.login_lock.acquire(blocking=False):
            return None
        try:
            return self._login(principal, password, now=now)
        finally:
            self.login_lock.release()

    def _login(self, principal, password, *, now=None):
        now = time.time() if now is None else now
        encoded = credential_bytes(password)
        if (
            credential_bytes(principal) is None
            or len(principal) > 128
            or encoded is None
            or len(encoded) > 1024
        ):
            return None
        if self.global_window is None or now >= self.global_window + 60:
            self.global_window, self.global_attempts = now, 0
        if now < self.global_window or self.global_attempts >= 20:
            return None
        self.global_attempts += 1
        with self.db:
            self.db.execute("DELETE FROM login_limits WHERE started<=?", (now - 60,))
            limit = self.db.execute(
                "SELECT * FROM login_limits WHERE principal=?", (principal,)
            ).fetchone()
            if limit and now < limit["started"] + 60 and limit["attempts"] >= 5:
                return None
            if (
                not limit
                and self.db.execute("SELECT COUNT(*) FROM login_limits").fetchone()[0]
                >= 20
            ):
                return None
            if not limit or now >= limit["started"] + 60:
                self.db.execute(
                    "INSERT OR REPLACE INTO login_limits VALUES (?, ?, 1)",
                    (principal, now),
                )
            else:
                self.db.execute(
                    "UPDATE login_limits SET attempts=attempts+1 WHERE principal=?",
                    (principal,),
                )
        account = self.db.execute(
            "SELECT * FROM accounts WHERE id=?", (principal,)
        ).fetchone()
        valid = verify_password(
            password, account["verifier"] if account else self.dummy
        )
        if not account or not valid:
            return None
        # Successful authentication never inherits a presented cookie and retires
        # previously issued human tokens for this account.
        with self.db:
            self.db.execute(
                "DELETE FROM sessions WHERE principal=? AND audience='human'",
                (principal,),
            )
        return self.issue(principal, "human", now=now)

    def issue(self, principal, audience, *, now=None, authenticated_at=None):
        if audience not in AUDIENCES:
            raise ValueError("unknown audience")
        now = time.time() if now is None else now
        authenticated_at = now if authenticated_at is None else authenticated_at
        account = self.db.execute(
            "SELECT * FROM accounts WHERE id=?", (principal,)
        ).fetchone()
        if not account:
            raise ValueError("unknown principal")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.db:
            self.db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    digest(token),
                    principal,
                    audience,
                    digest(csrf),
                    account["epoch"],
                    authenticated_at,
                    now,
                ),
            )
        return token, csrf

    def resolve(self, token, audience, *, now=None):
        now = time.time() if now is None else now
        if (
            not isinstance(token, str)
            or not token
            or len(token) > 128
            or audience not in AUDIENCES
        ):
            return None
        row = self.db.execute(
            "SELECT s.*, a.epoch AS current_epoch FROM sessions s JOIN accounts a ON a.id=s.principal WHERE s.hash=?",
            (digest(token),),
        ).fetchone()
        if (
            not row
            or row["audience"] != audience
            or row["epoch"] != row["current_epoch"]
            or now >= row["created"] + 3600
            or now >= row["touched"] + 300
            or now < row["created"]
        ):
            return None
        with self.db:
            self.db.execute(
                "UPDATE sessions SET touched=? WHERE hash=?", (now, row["hash"])
            )
        return row

    def rotate(self, token, *, now=None):
        row = self.resolve(token, "human", now=now)
        if not row:
            return None
        self.logout(token)
        return self.issue(
            row["principal"], "human", now=now, authenticated_at=row["created"]
        )

    def logout(self, token):
        with self.db:
            self.db.execute("DELETE FROM sessions WHERE hash=?", (digest(token),))

    def reset(self, principal, verifier):
        if not isinstance(verifier, str) or not re.fullmatch(
            r"pbkdf2\$600000\$[0-9a-f]{32}\$[0-9a-f]{64}", verifier
        ):
            raise ValueError("unsupported password verifier")
        with self.db:
            self.db.execute(
                "UPDATE accounts SET verifier=?, epoch=epoch+1 WHERE id=?",
                (verifier, principal),
            )

    def revoke(self, principal):
        with self.db:
            self.db.execute(
                "UPDATE accounts SET epoch=epoch+1 WHERE id=?", (principal,)
            )

    def authorize(self, token, project, workspace, scope, capability, *, now=None):
        if any(
            credential_bytes(value) is None or not 1 <= len(value) <= 128
            for value in (project, workspace)
        ):
            return False
        if scope not in ("project", "workspace") or capability not in CAPABILITIES:
            return False
        human = self.resolve(token, "human", now=now)
        if not human:
            return False
        member = self.db.execute(
            "SELECT role FROM memberships WHERE principal=? AND project=? AND workspace=?",
            (human["principal"], project, workspace),
        ).fetchone()
        return bool(member and capability in ROLE_CAPABILITIES.get(member["role"], ()))

    def decision(self, token, project, workspace, *, requester, mode, now=None):
        if not self.authorize(
            token, project, workspace, "project", "decision", now=now
        ):
            return None
        human = self.resolve(token, "human", now=now)
        if mode == "shared" and human["principal"] != requester:
            return "approval"
        if (
            mode == "single"
            and human["principal"] == requester
            and self.db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1
        ):
            return "acknowledgement"
        return None


def make_app(store):
    """An HTTPS-only test application; these paths are not product route proposals."""
    app = FastAPI()

    async def bounded_object(request):
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > 4096:
                return None
            content.extend(chunk)
        try:
            body = json.loads(content)
        except (ValueError, UnicodeDecodeError):
            return None
        return body if isinstance(body, dict) else None

    @app.post("/login")
    async def login(request: Request):
        if request.url.scheme != "https" or request.headers.get("origin") != ORIGIN:
            return JSONResponse({"denied": True}, status_code=403)
        body = await bounded_object(request)
        if body is None:
            return JSONResponse({"denied": True}, status_code=400)
        issued = store.login(body.get("username"), body.get("password"))
        if not issued:
            return JSONResponse({"denied": True}, status_code=401)
        token, csrf = issued
        response = JSONResponse({"csrf": csrf})
        response.set_cookie(
            "__Host-session",
            token,
            secure=True,
            httponly=True,
            samesite="strict",
            path="/",
            max_age=3600,
        )
        return response

    @app.post("/capability")
    async def capability(request: Request):
        token = request.cookies.get("__Host-session", "")
        row = store.resolve(token, "human")
        if not row:
            return JSONResponse({"denied": True}, status_code=401)
        csrf = request.headers.get("x-csrf-token", "")
        if (
            request.url.scheme != "https"
            or request.headers.get("origin") != ORIGIN
            or len(csrf) > 128
            or not hmac.compare_digest(digest(csrf), row["csrf_hash"])
        ):
            return JSONResponse({"denied": True}, status_code=403)
        body = await bounded_object(request)
        if body is None:
            return JSONResponse({"denied": True}, status_code=400)
        allowed = store.authorize(
            token,
            body.get("project"),
            body.get("workspace"),
            body.get("scope", "project"),
            body.get("capability"),
        )
        return JSONResponse({"allowed": allowed}, status_code=200 if allowed else 403)

    return app
