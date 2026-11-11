"""Durable reference receiver for harmless synthetic markers or saved-plan receipts.

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
        self,
        root,
        server: ReceiverServer,
        callback_secret: bytes,
        *,
        checkpoint=None,
        action_mode="synthetic",
    ):
        if type(callback_secret) is not bytes or len(callback_secret) < 32:
            raise ValueError("A receiver callback key of at least 32 bytes is required")
        if type(action_mode) is not str or action_mode not in (
            "synthetic",
            "saved_plan_receipt",
        ):
            raise ValueError("Unsupported receiver action mode")
        self.action_mode = action_mode
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
                CREATE TABLE IF NOT EXISTS saved_plan_receipts (
                    operation_id TEXT PRIMARY KEY, artifact_digest TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS recovery_outbox (
                    operation_id TEXT NOT NULL REFERENCES operations(id),
                    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 100),
                    envelope_digest TEXT NOT NULL CHECK(length(envelope_digest)=71),
                    envelope BLOB NOT NULL CHECK(length(envelope) BETWEEN 1 AND 131072),
                    PRIMARY KEY(operation_id,ordinal),
                    UNIQUE(operation_id,envelope_digest)
                );
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(operations)")}
            if "action_mode" not in columns:
                db.execute(
                    "ALTER TABLE operations ADD COLUMN action_mode TEXT NOT NULL DEFAULT 'synthetic'"
                )
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
        if row["action_mode"] != self.action_mode:
            raise ReceiverConflict("Persisted receiver action mode changed")
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
        result = {
            "operation_id": operation_id,
            "phase": row["phase"],
            "counted_actions": count,
            "callback_delivered": bool(row["delivered"]),
            "receipt": json.loads(row["receipt"])
            if row["receipt"] is not None
            else None,
        }
        if row["action_mode"] == "saved_plan_receipt":
            verified = db.execute(
                "SELECT artifact_digest FROM saved_plan_receipts WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            result.update(
                action_mode="saved_plan_receipt",
                deployment_performed=False,
                verified_plan_receipts=int(verified is not None),
                verified_plan_digest=verified[0] if verified is not None else None,
            )
        return result

    def _check_action_payload(self, payload, binding):
        """Keep receipt mode local while validating the approved semantic action."""
        if self.action_mode != "saved_plan_receipt":
            return
        try:
            if (
                type(payload) is not dict
                or type(payload.get("version")) is not int
                or payload["version"] != 1
            ):
                raise ValueError
            # Retain the explicit receipt contract used by earlier local clients.
            if set(payload) == {"version", "receiver_action"}:
                if payload["receiver_action"] == "saved_plan_receipt":
                    return
                raise ValueError
            if (
                set(payload) != {"version", "kind", "decision", "destination"}
                or payload["kind"] != "registered_github_handoff"
                or type(payload["decision"]) is not dict
                or type(payload["destination"]) is not dict
                or "payload_digest" in payload["decision"]
            ):
                raise ValueError
            from infra_automation.decisions import DecisionBinding
            from infra_automation.receiver_protocol import (
                receiver_binding_from_decision,
            )

            decision = DecisionBinding.model_validate_json(
                canonical(
                    {**payload["decision"], "payload_digest": binding.payload_digest}
                )
            )
            if (
                decision.authorization_kind != "exact_plan"
                or receiver_binding_from_decision(decision) != binding
            ):
                raise ValueError
        except (ValueError, TypeError, KeyError, RecursionError):
            raise ReceiverConflict(
                "Approved payload does not select the bound saved-plan receipt"
            ) from None

    def _check_action_bytes(self, artifact):
        if self.action_mode == "synthetic" and not artifact.data.startswith(
            SYNTHETIC_PREFIX
        ):
            raise ValueError(
                "Reference receiver accepts only synthetic marker artifacts"
            )

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
                self._check_action_payload(bootstrap["payload"], message.binding)
                with self.custody.verify(message.binding) as artifact:
                    self._check_action_bytes(artifact)
                token = self._grant_token(bootstrap.get("grant_token"))
                db.execute(
                    "INSERT INTO operations(id,binding_digest,message,payload,run_id,phase,action_mode) VALUES(?,?,?,?,?,?,?)",
                    (
                        operation_id,
                        binding_digest,
                        receiver_message_bytes(message),
                        payload,
                        bootstrap["run_id"],
                        "intent",
                        self.action_mode,
                    ),
                )
                db.commit()
                self.checkpoint("intent")
                row = db.execute(
                    "SELECT * FROM operations WHERE id=?", (operation_id,)
                ).fetchone()
            if row["action_mode"] != self.action_mode:
                raise ReceiverConflict("Persisted receiver action mode changed")
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
            self._check_action_payload(json.loads(row["payload"]), message.binding)
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
                self._check_action_bytes(artifact)
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
                if self.action_mode == "saved_plan_receipt":
                    # This is a receipt over the already verified saved bytes.
                    # It invokes no tool and makes no deployment claim.
                    db.execute(
                        "INSERT INTO saved_plan_receipts VALUES(?,?)",
                        (operation_id, digest(artifact.data)),
                    )
                else:
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

    @staticmethod
    def _completed_envelope(raw, message, run_id):
        from infra_automation.receiver_http_contracts import (
            CallbackEnvelope,
            source_identity_digest,
        )

        try:
            if type(raw) is not bytes or not 1 <= len(raw) <= 131072:
                raise ValueError
            envelope = CallbackEnvelope.model_validate_json(raw)
            value = envelope.model_dump(mode="json")
            expected = {
                **message.model_dump(mode="json"),
                "operation": "outcome",
                "sequence": 2,
                "state": envelope.message.state,
            }
            if (
                canonical(value) != raw
                or envelope.message.state not in {"succeeded", "failed"}
                or envelope.message.model_dump(mode="json") != expected
                or envelope.operation_id != message.operation_id
                or envelope.run_id != run_id
                or envelope.binding_digest != message.binding_digest
                or envelope.source_identity_digest
                != source_identity_digest(message.binding)
            ):
                raise ValueError
            return value
        except (ValueError, TypeError, KeyError, RecursionError):
            raise ReceiverConflict(
                "Completed receiver outcome identity changed"
            ) from None

    def _completed_record(self, db, row, operation_id, binding_digest):
        try:
            if (
                row is None
                or row["phase"] != "complete"
                or row["action_mode"] != self.action_mode
                or row["binding_digest"] != binding_digest
            ):
                raise ValueError
            message = validate_receiver_message(row["message"])
            if (
                message.operation != "consume"
                or message.state != "consumed"
                or message.sequence != 1
                or message.operation_id != operation_id
                or message.binding_digest != binding_digest
                or receiver_message_bytes(message) != row["message"]
                or canonical(json.loads(row["payload"])) != row["payload"]
                or digest(row["payload"]) != message.binding.payload_digest
                or message.binding.authorization_kind != "exact_plan"
            ):
                raise ValueError
            self._check_action_payload(json.loads(row["payload"]), message.binding)
            if (
                self._receipt({"receipt": json.loads(row["receipt"])}, message)
                != row["receipt"]
            ):
                raise ValueError
            markers = db.execute(
                "SELECT artifact_digest FROM synthetic_markers WHERE operation_id=?",
                (operation_id,),
            ).fetchall()
            receipts = db.execute(
                "SELECT artifact_digest FROM saved_plan_receipts WHERE operation_id=?",
                (operation_id,),
            ).fetchall()
            selected, other = (
                (markers, receipts)
                if self.action_mode == "synthetic"
                else (receipts, markers)
            )
            if (
                len(selected) != 1
                or other
                or selected[0][0] != message.binding.provenance.custody.raw_local_digest
            ):
                raise ValueError
            envelope = self._completed_envelope(row["callback"], message, row["run_id"])
            return message, envelope
        except (ValueError, TypeError, KeyError, RecursionError):
            raise ReceiverConflict(
                "A durable matching completed operation is required"
            ) from None

    def _completed_status(self, view, row, message, envelopes):
        """Return exact terminal acknowledgement or deny contradictory status."""
        try:
            if (
                type(view) is not dict
                or view.get("id") != row["id"]
                or view.get("receiver_binding_digest") != row["binding_digest"]
                or view.get("broken") is not False
                or self._receipt(view, message) != row["receipt"]
            ):
                raise ValueError
            expected_state = json.loads(row["callback"])["message"]["state"]
            ack = view.get("callback_ack")
            if ack is not None:
                if (
                    type(ack) is not dict
                    or set(ack) != {"sequence", "nonce", "envelope_digest"}
                    or type(ack["sequence"]) is not int
                ):
                    raise ValueError
                matched = any(
                    ack
                    == {
                        "sequence": envelope["sequence"],
                        "nonce": envelope["nonce"],
                        "envelope_digest": digest(raw),
                    }
                    for raw, envelope in envelopes
                )
                if not matched or view.get("state") != expected_state:
                    raise ValueError
                return True
            # Already-terminal status is status_only: conflicting/missing proof
            # can never cause a new callback to be signed or transmitted.
            if view.get("state") not in {
                "consumed",
                "accepted",
                "running",
                "delivery_unknown",
            }:
                raise ValueError
            return False
        except (ValueError, TypeError, KeyError, RecursionError):
            raise ReceiverConflict(
                "Completed receiver acknowledgement conflicts"
            ) from None

    def recover_completed(self, operation_id: str, binding_digest: str) -> dict:
        """Deliver only retained completed proof using a rotated recovery key.

        This method never enters run/flush, custody, consume or action admission.
        Authenticated terminal status permits exact acknowledgement only; only an
        unresolved server state can accept a re-signed original event.
        """
        from infra_automation.receiver_http_contracts import callback_signing_bytes

        if (
            type(operation_id) is not str
            or not 1 <= len(operation_id) <= 128
            or type(binding_digest) is not str
            or len(binding_digest) != 71
        ):
            raise ReceiverConflict("A bound completed operation is required")
        with self._ledger() as db:
            row = db.execute(
                "SELECT * FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
            message, original = self._completed_record(
                db, row, operation_id, binding_digest
            )
            candidates = [(row["callback"], original)]
            stored = db.execute(
                "SELECT ordinal,envelope_digest,envelope FROM recovery_outbox WHERE operation_id=? ORDER BY ordinal LIMIT 101",
                (operation_id,),
            ).fetchall()
            if len(stored) > 100:
                raise ReceiverConflict("Recovery outbox limit exceeded")
            for index, candidate in enumerate(stored, 1):
                envelope = self._completed_envelope(
                    candidate["envelope"], message, row["run_id"]
                )
                if (
                    candidate["ordinal"] != index
                    or candidate["envelope_digest"] != digest(candidate["envelope"])
                    or {
                        key: value
                        for key, value in envelope.items()
                        if key != "signature"
                    }
                    != {
                        key: value
                        for key, value in original.items()
                        if key != "signature"
                    }
                ):
                    raise ReceiverConflict("Retained recovery outbox changed")
                candidates.append((candidate["envelope"], envelope))
            view = self.server.status(operation_id)
            if not self._completed_status(view, row, message, candidates):
                resigned = dict(original)
                resigned["signature"] = (
                    "sha256:"
                    + hmac.new(
                        self._secret, callback_signing_bytes(original), hashlib.sha256
                    ).hexdigest()
                )
                raw = canonical(resigned)
                if not any(previous == raw for previous, _ in candidates):
                    if len(stored) >= 100:
                        raise ReceiverConflict("Recovery outbox limit exceeded")
                    db.execute(
                        "INSERT INTO recovery_outbox(operation_id,ordinal,envelope_digest,envelope) VALUES(?,?,?,?)",
                        (operation_id, len(stored) + 1, digest(raw), raw),
                    )
                    db.commit()
                    candidates.append((raw, resigned))
                self.checkpoint("recovery_outbox")
                try:
                    self.server.callback(json.loads(raw))
                except Exception:
                    # Sending may have committed. Only an authenticated exact
                    # acknowledgement of a durably retained candidate resolves it.
                    if not self._completed_status(
                        self.server.status(operation_id), row, message, candidates
                    ):
                        raise
                self.checkpoint("recovery_callback")
                if not self._completed_status(
                    self.server.status(operation_id), row, message, candidates
                ):
                    raise ReceiverConflict(
                        "Completed receiver outcome is unacknowledged"
                    )
            db.execute("UPDATE operations SET delivered=1 WHERE id=?", (operation_id,))
            db.commit()
            self.checkpoint("recovery_delivery")
            return self._result(db, operation_id)

    def flush_callbacks(self):
        with self._ledger() as db:
            rows = db.execute(
                "SELECT * FROM operations WHERE callback IS NOT NULL AND delivered=0 ORDER BY id"
            ).fetchall()
            return [self._deliver(db, row) for row in rows]
