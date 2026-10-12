"""Disposable receiver and synthetic byte custody doubles, never infrastructure."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import sys


def binding():
    """All independently bound architecture 25.7 fields in harmless fixtures."""
    fields = (
        "workflow revision input source_repository source_commit project workspace "
        "environment receiver report_digest report_schema policy_version policy_digest "
        "policy_result unit_map waves sanitized_digest redaction_version raw_digest "
        "custody_handle payload_digest source_deadline evidence_deadline approval_deadline "
        "authorization_epoch restore_epoch target"
    )
    result = dict.fromkeys(fields.split(), "synthetic")
    result.update(
        major=1,
        authorization_kind="advisory_request",
        action="acknowledge",
        source_deadline=100,
        evidence_deadline=100,
        approval_deadline=100,
        authorization_epoch=1,
        restore_epoch=1,
        target="canonical-target",
    )
    return result


def authority():
    return dict(
        membership=True,
        target_enabled=True,
        feature_enabled=True,
        available=True,
        authorization_epoch=1,
        restore_epoch=1,
        now=10,
    )


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class Custody:
    """Private POSIX filesystem integrity double; no encryption or OS identity claim."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.chmod(0o700)
        self.db = sqlite3.connect(self.root / "metadata.sqlite")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS artifacts(handle PRIMARY KEY, digest, device, inode, expiry)"
        )
        self.db.commit()

    def finalize(self, data, credential, handle=None):
        if credential != "collector":
            raise ValueError("collector audience required")
        handle = handle or secrets.token_hex(16)
        if len(handle) != 32 or any(c not in "0123456789abcdef" for c in handle):
            raise ValueError("opaque handle required")
        pending = self.root / ("pending-" + secrets.token_hex(16))
        fd = os.open(
            pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            pending.chmod(0o400)
            os.link(pending, self.root / handle, follow_symlinks=False)
            info = pending.stat()
            raw_digest = hashlib.sha256(data).hexdigest()
            self.db.execute(
                "INSERT INTO artifacts VALUES(?,?,?,?,?)",
                (handle, raw_digest, info.st_dev, info.st_ino, 100),
            )
            self.db.commit()
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            return handle, raw_digest
        finally:
            pending.unlink(missing_ok=True)

    def read(self, handle, approved_digest, now, credential):
        if (
            credential != "receiver"
            or len(handle) != 32
            or any(c not in "0123456789abcdef" for c in handle)
        ):
            raise ValueError("receiver scoped opaque handle required")
        row = self.db.execute(
            "SELECT digest,device,inode,expiry FROM artifacts WHERE handle=?", (handle,)
        ).fetchone()
        if row is None or now >= row[3] or approved_digest != row[0]:
            raise ValueError("unavailable or stale custody")
        directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            try:
                fd = os.open(handle, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            except OSError as error:
                raise ValueError("custody open denied") from error
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or (info.st_dev, info.st_ino) != tuple(row[1:3])
                    or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o400
                ):
                    raise ValueError("custody descriptor identity changed")
                data = stream.read()
                if hashlib.sha256(data).hexdigest() != approved_digest:
                    raise ValueError("custody integrity changed")
                return data
        finally:
            os.close(directory)


class Receiver:
    """Single-host SQLite fault model with counted harmless local action only."""

    def __init__(self, root, custody=None, receiver_identity="synthetic"):
        self.custody = custody
        if not isinstance(receiver_identity, str) or not receiver_identity:
            raise ValueError("registered receiver identity required")
        self.receiver_identity = receiver_identity
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.chmod(0o700)
        self.db = sqlite3.connect(self.root / "receiver.sqlite", timeout=2)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS grants(token_hash PRIMARY KEY, binding, operation);
            CREATE TABLE IF NOT EXISTS operations(id PRIMARY KEY, binding, state, fence, sequence, broken DEFAULT 0);
            CREATE TABLE IF NOT EXISTS locks(target PRIMARY KEY, operation UNIQUE);
            CREATE TABLE IF NOT EXISTS audit(operation, reason);
            CREATE TABLE IF NOT EXISTS configuration(name PRIMARY KEY, value);
        """)
        self.db.execute(
            "INSERT OR IGNORE INTO configuration VALUES('receiver_identity',?)",
            (receiver_identity,),
        )
        if (
            self.db.execute(
                "SELECT value FROM configuration WHERE name='receiver_identity'"
            ).fetchone()[0]
            != receiver_identity
        ):
            self.db.rollback()
            raise ValueError("registered receiver identity changed")
        self.db.commit()
        keyfile = self.root / "receipt.key"
        try:
            fd = os.open(
                keyfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
        except FileExistsError:
            self.key = keyfile.read_bytes()
        else:
            self.key = secrets.token_bytes(32)
            with os.fdopen(fd, "wb") as stream:
                stream.write(self.key)
                stream.flush()
                os.fsync(stream.fileno())
        self.db.execute(
            "UPDATE operations SET state='delivery_unknown' WHERE state='action_started'"
        )
        self.db.commit()

    def issue(self, token, item):
        if (
            set(item) != set(binding())
            or type(item["major"]) is not int
            or item["major"] != 1
            or item["authorization_kind"] not in {"advisory_request", "exact_plan"}
        ):
            raise ValueError("unsupported binding contract")
        if item["receiver"] != self.receiver_identity:
            raise ValueError("wrong registered receiver")
        if (
            item["authorization_kind"] == "advisory_request"
            and item["action"] != "acknowledge"
        ):
            raise ValueError("advisory cannot authorize apply")
        self.db.execute(
            "INSERT INTO grants VALUES(?,?,NULL)",
            (
                hashlib.sha256(token.encode()).hexdigest(),
                json.dumps(item, sort_keys=True),
            ),
        )
        self.db.commit()

    def _live(self, item, live):
        if item["receiver"] != self.receiver_identity:
            raise ValueError("wrong registered receiver")
        if not all(
            live.get(key) is True
            for key in ("membership", "target_enabled", "feature_enabled", "available")
        ):
            raise ValueError("live authority unavailable or revoked")
        if any(
            live.get(key) != item[key]
            for key in ("authorization_epoch", "restore_epoch")
        ):
            raise ValueError("authority epoch changed")
        if live["now"] >= min(
            item[key]
            for key in ("source_deadline", "evidence_deadline", "approval_deadline")
        ):
            raise ValueError("shortest deadline expired")
        if item["authorization_kind"] == "exact_plan":
            if self.custody is None:
                raise ValueError("exact bytes unavailable")
            self.custody.read(
                item["custody_handle"], item["raw_digest"], live["now"], "receiver"
            )

    def accept(self, token, item, live, crash=None):
        if crash == "before_consume":
            os._exit(73)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT binding,operation FROM grants WHERE token_hash=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            ).fetchone()
            if row is None or digest(json.loads(row[0])) != digest(item):
                raise ValueError("grant binding mismatch")
            if item["receiver"] != self.receiver_identity:
                raise ValueError("wrong registered receiver")
            if row[1]:
                self.db.commit()
                return row[1]
            self._live(item, live)
            operation = secrets.token_hex(16)
            self.db.execute(
                "INSERT INTO operations VALUES(?,?,?,1,0,0)",
                (operation, row[0], "accepted"),
            )
            self.db.execute(
                "INSERT INTO locks VALUES(?,?)", (item["target"], operation)
            )
            self.db.execute(
                "UPDATE grants SET operation=? WHERE token_hash=? AND operation IS NULL",
                (operation, hashlib.sha256(token.encode()).hexdigest()),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        if crash == "after_consume":
            os._exit(73)
        return operation

    def start(self, operation, live, crash=None):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT binding,state,fence,broken FROM operations WHERE id=?",
                (operation,),
            ).fetchone()
            if row is None or row[1] != "accepted" or row[3]:
                raise ValueError("new action denied")
            self._live(json.loads(row[0]), live)
            self.db.execute(
                "UPDATE operations SET state='action_started' WHERE id=? AND state='accepted' AND fence=?",
                (operation, row[2]),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        if crash == "after_start":
            os._exit(73)
        with (self.root / "harmless-actions").open("ab") as stream:
            stream.write((operation + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
        if crash == "after_action":
            os._exit(73)
        self.db.execute(
            "UPDATE operations SET state='action_completed' WHERE id=? AND state='action_started'",
            (operation,),
        )
        self.db.commit()
        if crash == "after_completion":
            os._exit(73)

    def status(self, operation):
        return self.db.execute(
            "SELECT state FROM operations WHERE id=?", (operation,)
        ).fetchone()[0]

    def action_count(self):
        path = self.root / "harmless-actions"
        return len(path.read_bytes().splitlines()) if path.exists() else 0

    def locked(self):
        return bool(self.db.execute("SELECT 1 FROM locks").fetchone())

    def cancel(self, operation):
        self.db.execute(
            "INSERT INTO audit VALUES(?,?)", (operation, "cancel_requested")
        )
        self.db.commit()

    def expire_lease(self, operation):
        self.db.execute("INSERT INTO audit VALUES(?,?)", (operation, "lease_expired"))
        self.db.commit()

    def break_lock(self, operation, reason):
        if not reason:
            raise ValueError("reason required")
        with self.db:
            self.db.execute("INSERT INTO audit VALUES(?,?)", (operation, reason))
            self.db.execute("UPDATE operations SET broken=1 WHERE id=?", (operation,))
            self.db.execute("DELETE FROM locks WHERE operation=?", (operation,))

    def receipt(self, operation, state, sequence):
        row = self.db.execute(
            "SELECT binding FROM operations WHERE id=?", (operation,)
        ).fetchone()
        value = dict(
            operation=operation,
            state=state,
            sequence=sequence,
            binding_digest=digest(json.loads(row[0])),
            source_commit=json.loads(row[0])["source_commit"],
            receiver=json.loads(row[0])["receiver"],
        )
        value["signature"] = hmac.new(
            self.key, json.dumps(value, sort_keys=True).encode(), hashlib.sha256
        ).hexdigest()
        return value

    def reconcile(self, receipt):
        required = {
            "operation",
            "state",
            "sequence",
            "binding_digest",
            "source_commit",
            "receiver",
            "signature",
        }
        if (
            not isinstance(receipt, dict)
            or set(receipt) != required
            or type(receipt["sequence"]) is not int
            or receipt["sequence"] < 1
            or any(not isinstance(receipt[key], str) for key in required - {"sequence"})
            or receipt["state"] not in {"succeeded", "failed"}
        ):
            raise ValueError("unsupported receipt contract")
        value = {key: val for key, val in receipt.items() if key != "signature"}
        signature = hmac.new(
            self.key, json.dumps(value, sort_keys=True).encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, receipt.get("signature", "")):
            raise ValueError("unauthenticated receipt")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT binding,state,sequence FROM operations WHERE id=?",
                (value["operation"],),
            ).fetchone()
            if (
                row is None
                or value["receiver"] != self.receiver_identity
                or value["receiver"] != json.loads(row[0])["receiver"]
                or digest(json.loads(row[0])) != value["binding_digest"]
                or json.loads(row[0])["source_commit"] != value["source_commit"]
                or value["sequence"] <= row[2]
                or value["state"] not in {"succeeded", "failed"}
                or row[1] not in {"action_completed", "delivery_unknown"}
            ):
                raise ValueError("receipt replay or unverified terminal outcome")
            if row[1] == "delivery_unknown":
                # Only this harmless local action has independently inspectable output.
                # A signature alone does not establish the external effect occurred.
                marker = self.root / "harmless-actions"
                observed = marker.read_bytes().splitlines() if marker.exists() else []
                if (
                    value["state"] != "succeeded"
                    or observed.count(value["operation"].encode()) != 1
                ):
                    raise ValueError("unknown outcome has no observed terminal proof")
                self.db.execute(
                    "INSERT INTO audit VALUES(?,?)",
                    (value["operation"], "observed synthetic durable action marker"),
                )
            self.db.execute(
                "UPDATE operations SET state=?,sequence=? WHERE id=?",
                (value["state"], value["sequence"], value["operation"]),
            )
            self.db.execute(
                "DELETE FROM locks WHERE operation=?", (value["operation"],)
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise


if __name__ == "__main__":
    receiver = Receiver(sys.argv[1])
    point = sys.argv[2]
    op = receiver.accept("grant", binding(), authority(), point)
    receiver.start(op, authority(), point)
