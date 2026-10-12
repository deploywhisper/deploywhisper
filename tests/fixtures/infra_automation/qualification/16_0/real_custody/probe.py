"""Encrypted operator-local saved-plan custody under actual receiver UID."""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess  # nosec B404
import sys
import time
import copy

import receiver

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path("/custody")
OWNER_UID = 10002
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


def write_all(descriptor, body):
    remaining = memoryview(body)
    while remaining:
        try:
            written = os.write(descriptor, remaining)
        except InterruptedError:
            continue
        if written <= 0:
            raise OSError(errno.EIO, "incomplete custody write")
        remaining = remaining[written:]


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def finalize(checkpoint=None):
    """Publish one immutable bundle; discard abandoned staging on the next attempt.

    The trusted receiver UID exclusively owns ROOT. flock serializes cooperative
    finalizers, including recovery after process death. A completed directory
    rename is the publication boundary; errors after it never permit overwrite.
    This qualifies process restart, not host-power-loss durability.
    """
    lock = os.open(
        ROOT / ".finalize.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
    )
    pending = ROOT / ".pending"
    try:
        metadata = os.fstat(lock)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != OWNER_UID
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise ValueError("invalid custody lock ownership")
        fcntl.flock(lock, fcntl.LOCK_EX)
        if os.path.lexists(ROOT / "finalized"):
            raise FileExistsError("already finalized")
        if os.path.lexists(pending):
            # No provider can write ROOT; never follow a stale staging symlink.
            if pending.is_symlink():
                raise ValueError("invalid pending custody directory")
            shutil.rmtree(pending)
        pending.mkdir(mode=0o700)
        try:
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
                    pending / name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o400,
                )
                try:
                    write_all(descriptor, body)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                if name == "key" and checkpoint:
                    checkpoint("after_key")
            sync_directory(pending)
            if checkpoint:
                checkpoint("before_publish")
            os.rename(pending, ROOT / "finalized")
            if checkpoint:
                checkpoint("after_publish")
            sync_directory(ROOT)
            return record
        finally:
            if pending.exists():
                shutil.rmtree(pending)
    finally:
        os.close(lock)


def bundle_file(name):
    directory = os.open(
        ROOT / "finalized", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    )
    try:
        metadata = os.fstat(directory)
        if metadata.st_uid != OWNER_UID or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise ValueError("invalid custody directory ownership")
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != OWNER_UID
                or stat.S_IMODE(metadata.st_mode) != 0o400
                or metadata.st_nlink != 1
            ):
                raise ValueError("invalid custody ownership")
        except BaseException:
            os.close(descriptor)
            raise
        return descriptor
    finally:
        os.close(directory)


def load_record():
    with os.fdopen(bundle_file("record.json"), "r") as source:
        return json.load(source)


def read(record):
    handle = record["handle"]
    if not re.fullmatch("[0-9a-f]{64}", handle) or record["expiry"] <= time.time():
        raise ValueError("invalid custody handle or expired evidence")
    descriptor = bundle_file(handle)
    try:
        blob = os.read(descriptor, 2 * 1024 * 1024)
    finally:
        os.close(descriptor)
    key_descriptor = bundle_file("key")
    try:
        if os.fstat(key_descriptor).st_size != 32:
            raise ValueError("invalid key size")
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
        write_all(descriptor, raw)
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


def finalization_faults():
    """Exercise actual saved-plan bytes in private cases on the custody tmpfs.

    Short writes are injected at the syscall boundary; ENOSPC is returned by
    the kernel after filling only an owned disposable file on this bounded
    tmpfs. Crash children exit without running cleanup. Main custody is intact.
    """
    global ROOT
    if sys.platform != "linux" or os.getuid() != OWNER_UID:
        raise RuntimeError("real Linux receiver UID required")
    original_root = ROOT
    raw_digest = hashlib.sha256(Path("/staging/original.plan").read_bytes()).hexdigest()
    cases = ROOT / "finalization-checks"
    cases.mkdir(mode=0o700)
    result = {"uid": os.getuid(), "raw_digest": raw_digest, "crashes": {}}

    def verify(record):
        verified = hashlib.sha256(read(record)).hexdigest() == raw_digest
        verified = verified and bool(show(read(record)))
        try:
            finalize()
            denied = False
        except FileExistsError:
            denied = True
        return {
            "retry_verified": verified,
            "second_finalize_denied": denied,
            "original_unchanged": hashlib.sha256(read(record)).hexdigest()
            == raw_digest,
            "pending_removed": not (ROOT / ".pending").exists(),
        }

    try:
        ROOT = cases / "short-write"
        ROOT.mkdir(mode=0o700)
        original_write = os.write
        calls = 0

        def short_write(descriptor, body):
            nonlocal calls
            calls += 1
            return original_write(descriptor, body[:7])

        os.write = short_write
        try:
            record = finalize()
        finally:
            os.write = original_write
        result["short_write"] = {"write_calls": calls, **verify(record)}

        ROOT = cases / "enospc"
        ROOT.mkdir(mode=0o700)
        filler = ROOT / "owned-filler"
        key_created = False

        def fill_after_key(point):
            nonlocal key_created
            if point != "after_key":
                return
            key_created = (ROOT / ".pending" / "key").stat().st_size == 32
            descriptor = os.open(
                filler, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            try:
                while True:
                    try:
                        write_all(descriptor, bytes(4096))
                    except OSError as exc:
                        if exc.errno != errno.ENOSPC:
                            raise
                        break
            finally:
                os.close(descriptor)

        failure_errno = None
        try:
            finalize(fill_after_key)
        except OSError as exc:
            failure_errno = exc.errno
        finally:
            filler.unlink(missing_ok=True)
        unpublished = not (ROOT / "finalized").exists()
        clean_after_failure = not (ROOT / ".pending").exists()
        record = finalize()
        result["enospc"] = {
            "errno": failure_errno,
            "key_created": key_created,
            "unpublished": unpublished,
            "clean_after_failure": clean_after_failure,
            **verify(record),
        }

        for point in ("after_key", "before_publish", "after_publish"):
            ROOT = cases / point
            ROOT.mkdir(mode=0o700)
            child = os.fork()
            if child == 0:

                def crash(stage):
                    if stage == point:
                        os._exit(73)

                finalize(crash)
                os._exit(74)
            _, status = os.waitpid(child, 0)
            published = (ROOT / "finalized").exists()
            pending = (ROOT / ".pending").exists()
            retry_denied = False
            try:
                record = finalize()
            except FileExistsError:
                retry_denied = True
                record = load_record()
            result["crashes"][point] = {
                "crash_exit": os.waitstatus_to_exitcode(status),
                "published_before_retry": published,
                "pending_before_retry": pending,
                "retry_denied": retry_denied,
                **verify(record),
            }
        return result
    finally:
        ROOT = original_root
        shutil.rmtree(cases)


def main():
    mode = sys.argv[1]
    if mode == "finalization_faults":
        print(json.dumps(finalization_faults()))
        return
    if mode == "finalize":
        record = finalize()
        print(json.dumps({**record, "uid": os.getuid(), "tool": show(read(record))}))
        return
    record = load_record()
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
    path = ROOT / "finalized" / record["handle"]
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
    path.symlink_to(ROOT / "finalized" / "key")
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
    path.symlink_to(ROOT / "finalized" / "key")
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
