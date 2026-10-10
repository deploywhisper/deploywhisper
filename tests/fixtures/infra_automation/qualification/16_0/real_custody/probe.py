"""Encrypted operator-local saved-plan custody under actual receiver UID."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess  # nosec B404
import sys
import time
import copy

import receiver

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path("/custody")
SOURCE_SHA = "cbc55062de7730dd19694c418b5f9e9ff03ee223"


def exact_binding(record, raw_digest=None):
    return {
        **receiver.binding(),
        "authorization_kind": "exact_plan",
        "source_repository": "synthetic://qualification",
        "source_commit": SOURCE_SHA,
        "source_deadline": record["expiry"],
        "evidence_deadline": record["expiry"],
        "approval_deadline": record["expiry"],
        "custody_handle": record["handle"],
        "raw_digest": raw_digest or record["raw_digest"],
        "sanitized_digest": hashlib.sha256(
            Path("/staging/screened.json").read_bytes()
        ).hexdigest(),
    }


def live_authority():
    return {**receiver.authority(), "now": int(time.time())}


def finalize():
    if (ROOT / "record.json").exists():
        raise FileExistsError("already finalized")
    raw = Path("/staging/original.plan").read_bytes()
    handle = secrets.token_hex(32)
    key = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    record = {
        "handle": handle,
        "raw_digest": hashlib.sha256(raw).hexdigest(),
        "expiry": int(time.time()) + 3600,
    }
    for name, body in (
        ("key", key),
        (handle, nonce + AESGCM(key).encrypt(nonce, raw, handle.encode())),
        ("record.json", json.dumps(record).encode()),
    ):
        descriptor = os.open(
            ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400
        )
        try:
            os.write(descriptor, body)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    directory = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return record


def read(record):
    handle = record["handle"]
    if not re.fullmatch("[0-9a-f]{64}", handle) or record["expiry"] <= time.time():
        raise ValueError("invalid custody handle or expired evidence")
    descriptor = os.open(ROOT / handle, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 10002
            or stat.S_IMODE(metadata.st_mode) != 0o400
            or metadata.st_nlink != 1
        ):
            raise ValueError("invalid custody ownership")
        blob = os.read(descriptor, 2 * 1024 * 1024)
    finally:
        os.close(descriptor)
    key_descriptor = os.open(ROOT / "key", os.O_RDONLY | os.O_NOFOLLOW)
    try:
        key_metadata = os.fstat(key_descriptor)
        if (
            key_metadata.st_uid != 10002
            or stat.S_IMODE(key_metadata.st_mode) != 0o400
            or key_metadata.st_size != 32
        ):
            raise ValueError("invalid key ownership")
        key = os.read(key_descriptor, 32)
    finally:
        os.close(key_descriptor)
    raw = AESGCM(key).decrypt(blob[:12], blob[12:], handle.encode())
    if hashlib.sha256(raw).hexdigest() != record["raw_digest"]:
        raise ValueError("changed saved plan")
    return raw


def show(raw):
    descriptor = os.memfd_create("qualified-plan", os.MFD_ALLOW_SEALING)
    try:
        os.write(descriptor, raw)
        fcntl.fcntl(
            descriptor,
            fcntl.F_ADD_SEALS,
            fcntl.F_SEAL_WRITE
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_SEAL,
        )
        result = subprocess.run(  # nosec B603
            ["/usr/local/bin/tofu", "show", "-json", f"/proc/self/fd/{descriptor}"],
            cwd="/work",
            env={"PATH": "/usr/local/bin:/usr/bin:/bin"},
            pass_fds=(descriptor,),
            capture_output=True,
            timeout=30,
            check=True,
        )
        return json.loads(result.stdout)["terraform_version"]
    finally:
        os.close(descriptor)


def main():
    mode = sys.argv[1]
    if mode == "finalize":
        record = finalize()
        print(json.dumps({**record, "uid": os.getuid(), "tool": show(read(record))}))
        return
    record = json.loads((ROOT / "record.json").read_text())
    if mode == "receiver_faults":
        print(json.dumps(receiver_faults(record)))
        return
    if mode == "replan":
        adapter = RealCustody(record)
        target = receiver.Receiver(ROOT / "receiver-mutations", custody=adapter)
        raw_digest = hashlib.sha256(
            Path("/staging/original.plan").read_bytes()
        ).hexdigest()
        item = exact_binding(record, raw_digest)
        try:
            target.accept("synthetic-grant", item, live_authority())
            denied = False
        except ValueError:
            denied = True
        print(
            json.dumps(
                {
                    "replan_requires_new_tuple": denied,
                    "actual_plan_changed": raw_digest != record["raw_digest"],
                    "action_count": target.action_count(),
                }
            )
        )
        target.db.close()
        return
    if mode == "restart":
        print(
            json.dumps(
                {
                    "restart_verified": bool(show(read(record))),
                    "raw_digest": record["raw_digest"],
                }
            )
        )
        return
    results = {}
    for label, changed in (
        ("expiry", {**record, "expiry": 0}),
        ("changed_plan", {**record, "raw_digest": "0" * 64}),
        ("path", {**record, "handle": "../key"}),
    ):
        try:
            read(changed)
            results[label] = False
        except (ValueError, OSError):
            results[label] = True
    path = ROOT / record["handle"]
    original = path.read_bytes()
    try:
        finalize()
        results["overwrite"] = False
    except FileExistsError:
        results["overwrite"] = True
    path.chmod(0o600)
    path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    path.chmod(0o400)
    try:
        read(record)
        results["tamper"] = False
    except Exception:
        results["tamper"] = True
    path.unlink()
    path.symlink_to(ROOT / "key")
    try:
        read(record)
        results["symlink"] = False
    except OSError:
        results["symlink"] = True
    path.unlink()
    path.write_bytes(original)
    path.chmod(0o400)
    # Verified descriptor bytes remain stable after replacing the pathname.
    verified = read(record)
    path.unlink()
    path.symlink_to(ROOT / "key")
    results["descriptor_toctou"] = bool(show(verified))
    print(json.dumps(results))


class RealCustody:
    def __init__(self, record):
        self.record = record

    def read(self, handle, approved_digest, now, credential):
        if (
            credential != "receiver"
            or handle != self.record["handle"]
            or approved_digest != self.record["raw_digest"]
        ):
            raise ValueError("original exact plan required")
        return read(self.record)


def receiver_faults(record):
    adapter = RealCustody(record)
    item = exact_binding(record)
    live = live_authority()
    faults = {}
    for point in (
        "before_consume",
        "after_consume",
        "after_start",
        "after_action",
        "after_completion",
    ):
        root = ROOT / ("receiver-" + point)
        original = receiver.Receiver(root, custody=adapter)
        original.issue("synthetic-grant", item)
        original.db.close()
        child = os.fork()
        if child == 0:
            target = receiver.Receiver(root, custody=adapter)
            operation = target.accept("synthetic-grant", item, live, crash=point)
            target.start(operation, live, crash=point)
            os._exit(0)
        _, status = os.waitpid(child, 0)
        reopened = receiver.Receiver(root, custody=adapter)
        operation = reopened.accept("synthetic-grant", item, live)
        if point in {"before_consume", "after_consume"}:
            reopened.start(operation, live)
        duplicate = reopened.accept("synthetic-grant", item, live)
        count = reopened.action_count()
        try:
            reopened.start(operation, live)
            repeat_denied = False
        except ValueError:
            repeat_denied = True
        faults[point] = {
            "crash_exit": os.waitstatus_to_exitcode(status),
            "action_count": count,
            "state": reopened.status(operation),
            "same_operation": duplicate == operation,
            "repeat_action_denied": repeat_denied,
            "lock_retained": reopened.locked(),
        }
        reopened.db.close()
    mutations = receiver.Receiver(ROOT / "receiver-mutations", custody=adapter)
    mutations.issue("synthetic-grant", item)
    denied = 0
    for field in item:
        changed = copy.deepcopy(item)
        changed[field] = "changed"
        try:
            mutations.accept("synthetic-grant", changed, live)
        except ValueError:
            denied += 1
    mutations.db.close()
    return {"faults": faults, "tuple_mutations_denied": denied}


if __name__ == "__main__":
    main()
