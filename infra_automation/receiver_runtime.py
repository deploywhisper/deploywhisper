"""Durable reference receiver for a harmless, counted synthetic action only.

The server port is authenticated by its implementation. A durable action fence
precedes the effect; a crash after that fence is reconciliation-only.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import hmac
import json
import os
import re
from pathlib import Path
import secrets
import sqlite3
from typing import Protocol

from infra_automation.receiver_custody import (
    ProtectedCustody,
    canonical,
    check_file,
    digest,
    private_directory,
)
from infra_automation.receiver_protocol import (
    ReceiverMessage,
    receiver_message_bytes,
    validate_receiver_message,
)

SYNTHETIC_PREFIX = b"deploywhisper-synthetic-v1\n"


class ReceiverServer(Protocol):
    """All returned data comes from an authenticated server connection."""

    def bootstrap(self, operation_id: str, binding_digest: str) -> dict: ...
    def consume(self, message: ReceiverMessage, grant_token: str) -> dict: ...
    def status(self, operation_id: str) -> dict: ...
    def authorize_action(self, operation_id: str) -> dict: ...
    def callback(self, envelope: dict) -> dict: ...


class ReceiverConflict(ValueError):
    pass


class ReferenceReceiver:
    def __init__(
        self, root, server: ReceiverServer, callback_secret: bytes, *, checkpoint=None
    ):
        if type(callback_secret) is not bytes or len(callback_secret) < 32:
            raise ValueError("A receiver callback key of at least 32 bytes is required")
        self.root = Path(root)
        directory = private_directory(self.root)
        os.close(directory)
        self.server = server
        self._secret = callback_secret
        self.checkpoint = checkpoint or (lambda name: None)
        self.custody = ProtectedCustody(self.root / "custody")

    @contextmanager
    def _ledger(self):
        root = private_directory(self.root)
        lock = os.open(
            "receiver.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=root
        )
        fd = None
        db = None
        try:
            check_file(lock, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            fd = os.open(
                "receiver.sqlite3",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                0o600,
                dir_fd=root,
            )
            original = check_file(fd, 0o600)
            # The owner-only directory and cross-process flock serialize SQLite
            # and its sidecars. Reject pre-existing unsafe SQLite sidecars too.
            for name in (
                "receiver.sqlite3-journal",
                "receiver.sqlite3-wal",
                "receiver.sqlite3-shm",
            ):
                try:
                    side = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root)
                except FileNotFoundError:
                    continue
                try:
                    check_file(side, 0o600)
                finally:
                    os.close(side)
            db = sqlite3.connect(self.root / "receiver.sqlite3")
            current = os.stat("receiver.sqlite3", dir_fd=root, follow_symlinks=False)
            if (original.st_dev, original.st_ino) != (current.st_dev, current.st_ino):
                raise ValueError("Receiver ledger replaced")
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY, binding_digest TEXT NOT NULL,
                    message BLOB NOT NULL, payload BLOB NOT NULL, run_id TEXT NOT NULL,
                    receipt BLOB, phase TEXT NOT NULL, callback BLOB, delivered INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS synthetic_markers (
                    operation_id TEXT PRIMARY KEY, artifact_digest TEXT NOT NULL
                );
            """)
            db.commit()
            os.fsync(root)
            yield db
        finally:
            if db is not None:
                db.close()
            if fd is not None:
                os.close(fd)
            os.close(lock)
            os.close(root)

    @staticmethod
    def _grant_token(value: object) -> str:
        if (
            not isinstance(value, str)
            or type(value) is not str
            or re.fullmatch(r"[!-~]{1,256}", value) is None
        ):
            raise ReceiverConflict("A bounded printable receiver grant is required")
        return value

    @staticmethod
    def _receipt(view, message):
        receipt = validate_receiver_message(view["receipt"])
        if (
            receipt.operation,
            receipt.state,
            receipt.sequence,
            receipt.operation_id,
            receipt.binding_digest,
        ) != (
            "receipt",
            "consumed",
            1,
            message.operation_id,
            message.binding_digest,
        ) or receipt.binding != message.binding:
            raise ReceiverConflict("Original consumed receipt identity mismatch")
        return receiver_message_bytes(receipt)

    @staticmethod
    def _authorize(view, message, receipt):
        if (
            view.get("id") != message.operation_id
            or ReferenceReceiver._receipt(view, message) != receipt
            or view.get("state") not in ("consumed", "accepted", "running")
            or view.get("broken")
        ):
            raise ValueError("Current server authorization denied")
        if view.get("receiver_binding_digest") != message.binding_digest:
            raise ReceiverConflict("Current server identity mismatch")

    @staticmethod
    def _current_deadline(message):
        if message.binding.deadline().replace(tzinfo=timezone.utc) <= datetime.now(
            timezone.utc
        ):
            raise ValueError("Receiver evidence expired before synthetic effect")

    def _envelope(self, message, run_id, state):
        from infra_automation.receiver_http_contracts import (
            callback_signing_bytes,
            source_identity_digest,
        )

        outcome = ReceiverMessage.model_validate(
            {
                **message.model_dump(mode="json"),
                "operation": "outcome",
                "sequence": 2,
                "state": state,
            }
        )
        envelope = {
            "version": 1,
            "operation_id": message.operation_id,
            "run_id": run_id,
            "binding_digest": message.binding_digest,
            "source_identity_digest": source_identity_digest(message.binding),
            "nonce": secrets.token_hex(32),
            "sequence": 1,
            "message": outcome.model_dump(mode="json"),
            "signature": "sha256:" + "0" * 64,
        }
        envelope["signature"] = (
            "sha256:"
            + hmac.new(
                self._secret, callback_signing_bytes(envelope), hashlib.sha256
            ).hexdigest()
        )
        return canonical(envelope)

    def _deliver(self, db, row):
        if row["callback"] is not None and not row["delivered"]:
            envelope = json.loads(row["callback"])
            try:
                self.server.callback(envelope)
            except Exception:
                # The server deliberately denies nonce/sequence replay. A lost
                # response can be recovered only from the retained exact fact.
                view = self.server.status(row["id"])
                message = validate_receiver_message(row["message"])
                expected_ack = {
                    "sequence": envelope["sequence"],
                    "nonce": envelope["nonce"],
                    "envelope_digest": digest(row["callback"]),
                }
                if (
                    view.get("id") != row["id"]
                    or view.get("receiver_binding_digest") != row["binding_digest"]
                    or view.get("callback_ack") != expected_ack
                    or self._receipt(view, message) != row["receipt"]
                ):
                    raise
            db.execute("UPDATE operations SET delivered=1 WHERE id=?", (row["id"],))
            db.commit()
        return self._result(db, row["id"])

    @staticmethod
    def _result(db, operation_id):
        row = db.execute(
            "SELECT * FROM operations WHERE id=?", (operation_id,)
        ).fetchone()
        count = db.execute(
            "SELECT count(*) FROM synthetic_markers WHERE operation_id=?",
            (operation_id,),
        ).fetchone()[0]
        return {
            "operation_id": operation_id,
            "phase": row["phase"],
            "counted_actions": count,
            "callback_delivered": bool(row["delivered"]),
            "receipt": json.loads(row["receipt"])
            if row["receipt"] is not None
            else None,
        }

    def run(self, operation_id: str, binding_digest: str) -> dict:
        """Resume by identity; consume ambiguity never causes consume to be retried."""
        with self._ledger() as db:
            row = db.execute(
                "SELECT * FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
            fresh = row is None
            token = None
            if fresh:
                bootstrap = self.server.bootstrap(operation_id, binding_digest)
                message = validate_receiver_message(bootstrap["message"])
                if type(bootstrap["payload"]) is not dict:
                    raise ReceiverConflict("A semantic payload object is required")
                payload = canonical(bootstrap["payload"])
                if len(payload) > 128 * 1024:
                    raise ReceiverConflict("Semantic payload exceeds its bound")
                if (
                    message.operation,
                    message.operation_id,
                    message.binding_digest,
                ) != ("consume", operation_id, binding_digest) or digest(
                    payload
                ) != message.binding.payload_digest:
                    raise ReceiverConflict("Bootstrap identity or payload changed")
                if message.binding.authorization_kind != "exact_plan":
                    raise ValueError("Advisory evidence cannot authorize exact action")
                with self.custody.verify(message.binding) as artifact:
                    if not artifact.data.startswith(SYNTHETIC_PREFIX):
                        raise ValueError(
                            "Reference receiver accepts only synthetic marker artifacts"
                        )
                token = self._grant_token(bootstrap.get("grant_token"))
                db.execute(
                    "INSERT INTO operations(id,binding_digest,message,payload,run_id,phase) VALUES(?,?,?,?,?,?)",
                    (
                        operation_id,
                        binding_digest,
                        receiver_message_bytes(message),
                        payload,
                        bootstrap["run_id"],
                        "intent",
                    ),
                )
                db.commit()
                self.checkpoint("intent")
                row = db.execute(
                    "SELECT * FROM operations WHERE id=?", (operation_id,)
                ).fetchone()
            if row["binding_digest"] != binding_digest:
                raise ReceiverConflict("Operation already bound to different bytes")
            message = validate_receiver_message(row["message"])
            if (
                message.operation != "consume"
                or message.operation_id != operation_id
                or message.binding_digest != binding_digest
                or receiver_message_bytes(message) != row["message"]
                or canonical(json.loads(row["payload"])) != row["payload"]
                or digest(row["payload"]) != message.binding.payload_digest
            ):
                raise ReceiverConflict("Persisted operation identity changed")
            if row["phase"] == "complete":
                return self._deliver(db, row)
            if row["phase"] == "action_started":
                # Even an effect that did not happen cannot safely be repeated.
                self.server.status(operation_id)
                envelope = self._envelope(message, row["run_id"], "delivery_unknown")
                db.execute(
                    "UPDATE operations SET phase='reconcile', callback=? WHERE id=?",
                    (envelope, operation_id),
                )
                db.commit()
                row = db.execute(
                    "SELECT * FROM operations WHERE id=?", (operation_id,)
                ).fetchone()
                return self._deliver(db, row)
            if row["phase"] == "reconcile":
                return self._deliver(db, row)
            if row["receipt"] is None:
                if fresh:
                    view = self.server.consume(message, self._grant_token(token))
                    token = None
                    self.checkpoint("server_consume")
                else:
                    view = self.server.status(operation_id)
                if view.get("receipt") is None:
                    # Intent may have died before consume. No replacement grant
                    # or retry: the operation requires operator reconciliation.
                    return self._result(db, operation_id)
                receipt = self._receipt(view, message)
                db.execute(
                    "UPDATE operations SET receipt=?,phase='received' WHERE id=?",
                    (receipt, operation_id),
                )
                db.commit()
                self.checkpoint("local_receipt")
                row = db.execute(
                    "SELECT * FROM operations WHERE id=?", (operation_id,)
                ).fetchone()
            with self.custody.verify(message.binding) as artifact:
                if not artifact.data.startswith(SYNTHETIC_PREFIX):
                    raise ValueError("Synthetic action bytes required")
                self._authorize(
                    self.server.authorize_action(operation_id), message, row["receipt"]
                )
                self._current_deadline(message)
                db.execute(
                    "UPDATE operations SET phase='action_started' WHERE id=?",
                    (operation_id,),
                )
                db.commit()
                self.checkpoint("action_fence")
                self._current_deadline(message)
                # Consume the already verified immutable byte snapshot, never a
                # reopened filename, generated plan, shell, or provider command.
                db.execute(
                    "INSERT INTO synthetic_markers VALUES(?,?)",
                    (operation_id, digest(artifact.data)),
                )
                db.commit()
                self.checkpoint("effect")
                envelope = self._envelope(message, row["run_id"], "succeeded")
                db.execute(
                    "UPDATE operations SET phase='complete',callback=? WHERE id=?",
                    (envelope, operation_id),
                )
                db.commit()
                self.checkpoint("completion")
            row = db.execute(
                "SELECT * FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
            return self._deliver(db, row)

    def flush_callbacks(self):
        with self._ledger() as db:
            rows = db.execute(
                "SELECT * FROM operations WHERE callback IS NOT NULL AND delivered=0 ORDER BY id"
            ).fetchall()
            return [self._deliver(db, row) for row in rows]
