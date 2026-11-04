"""Owner-local custody of bounded original bytes; no provider execution support."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys

from infra_automation.receiver_protocol import Collected, Custody, ReceiverBinding

MAX_ARTIFACT_BYTES = 8 * 1024 * 1024


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def check_file(fd, mode=0o400):
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != mode
        or info.st_nlink != 1
    ):
        raise ValueError("Unsafe receiver file")
    return info


def private_directory(path):
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(fd)
        raise ValueError("Receiver directory must be owner-only")
    return fd


def write_all(fd, raw):
    remaining = memoryview(raw)
    while remaining:
        count = os.write(fd, remaining)
        if count <= 0:
            raise OSError("Incomplete receiver write")
        remaining = remaining[count:]
    os.fsync(fd)


def _publish_directory(root_fd, pending, handle):
    """Use the kernel's exclusive rename; no check-then-replace fallback."""
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        name, flags = "renameatx_np", 0x00000004  # RENAME_EXCL
    elif sys.platform.startswith("linux"):
        name, flags = "renameat2", 1  # RENAME_NOREPLACE
    else:
        raise OSError(errno.ENOTSUP, "Exclusive custody rename unavailable")
    rename = getattr(library, name, None)
    if rename is None:
        raise OSError(errno.ENOTSUP, "Exclusive custody rename unavailable")
    rename.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    rename.restype = ctypes.c_int
    if rename(root_fd, os.fsencode(pending), root_fd, os.fsencode(handle), flags) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


@dataclass(frozen=True)
class VerifiedArtifact:
    fd: int
    data: bytes
    metadata: dict


class ProtectedCustody:
    def __init__(self, root):
        self.root = Path(root)
        fd = private_directory(root)
        os.close(fd)

    @staticmethod
    def _handle(handle):
        if (
            type(handle) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", handle) is None
        ):
            raise ValueError("Invalid custody handle")
        return handle

    def publish(
        self, handle: str, raw: bytes, source: dict, expires_at: str
    ) -> Custody:
        handle = self._handle(handle)
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_ARTIFACT_BYTES:
            raise ValueError("Bounded original bytes required")
        source = Collected.model_validate(source).model_dump(mode="json")
        record = Custody(
            handle=handle, raw_local_digest=digest(raw), expires_at=expires_at
        )
        expiry = datetime.strptime(expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        collected = datetime.strptime(
            source["collected_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        source_deadline = datetime.strptime(
            source["source_deadline"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        if not collected <= datetime.now(timezone.utc) < expiry <= source_deadline:
            raise ValueError("Expired or inconsistent custody evidence")
        root = private_directory(self.root)
        lock = bundle = None
        published = complete = False
        pending_identity = None
        pending = ".pending-" + secrets.token_hex(16)
        try:
            lock = os.open(
                ".publish.lock",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
                dir_fd=root,
            )
            check_file(lock, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                os.stat(handle, dir_fd=root, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise FileExistsError("Custody handle is immutable")
            os.mkdir(pending, 0o700, dir_fd=root)
            pending_identity = os.stat(pending, dir_fd=root, follow_symlinks=False)
            bundle = os.open(
                pending, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root
            )
            fd = os.open(
                "artifact",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o400,
                dir_fd=bundle,
            )
            try:
                write_all(fd, raw)
                info = check_file(fd)
            finally:
                os.close(fd)
            metadata = {
                **record.model_dump(mode="json"),
                "source": source,
                "device": info.st_dev,
                "inode": info.st_ino,
                "size": info.st_size,
            }
            fd = os.open(
                "metadata.json",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o400,
                dir_fd=bundle,
            )
            try:
                write_all(fd, canonical(metadata))
            finally:
                os.close(fd)
            os.fsync(bundle)
            # Kernel-exclusive publication never replaces an existing handle.
            if not collected <= datetime.now(timezone.utc) < expiry:
                raise ValueError("Expired custody")
            _publish_directory(root, pending, handle)
            published = True
            os.fsync(root)
            complete = True
            return record
        finally:
            try:
                if pending_identity is not None and not complete:
                    # Only remove this invocation's held bundle, never a substituted
                    # path or another immutable handle after an exclusive-rename failure.
                    name = handle if published else pending
                    held = os.fstat(bundle) if bundle is not None else pending_identity
                    named = os.stat(name, dir_fd=root, follow_symlinks=False)
                    if (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino):
                        raise ValueError("Custody cleanup identity changed")
                    if bundle is not None:
                        for child in ("artifact", "metadata.json"):
                            try:
                                os.unlink(child, dir_fd=bundle)
                            except FileNotFoundError:
                                pass
                    os.rmdir(name, dir_fd=root)
                    os.fsync(root)
            finally:
                for descriptor in (bundle, lock, root):
                    if descriptor is not None:
                        os.close(descriptor)

    @contextmanager
    def verify(self, binding: ReceiverBinding):
        binding = ReceiverBinding.model_validate_json(binding.model_dump_json())
        custody = binding.provenance.custody
        if binding.authorization_kind != "exact_plan" or custody is None:
            raise ValueError("Exact action requires local collected custody")
        if binding.deadline().replace(tzinfo=timezone.utc) <= datetime.now(
            timezone.utc
        ):
            raise ValueError("Expired receiver evidence")
        root = private_directory(self.root)
        bundle = fd = metadata_fd = None
        try:
            bundle = os.open(
                self._handle(custody.handle),
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=root,
            )
            directory = os.fstat(bundle)
            if (
                directory.st_uid != os.getuid()
                or stat.S_IMODE(directory.st_mode) != 0o700
            ):
                raise ValueError("Unsafe custody bundle")
            metadata_fd = os.open(
                "metadata.json",
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=bundle,
            )
            metadata_info = check_file(metadata_fd)
            if not 0 < metadata_info.st_size <= 128 * 1024:
                raise ValueError("Invalid custody metadata size")
            metadata_raw = os.read(metadata_fd, 128 * 1024 + 1)
            if len(metadata_raw) != metadata_info.st_size:
                raise ValueError("Incomplete custody metadata")
            metadata = json.loads(metadata_raw)
            expected = custody.model_dump(mode="json")
            if any(
                metadata.get(key) != value for key, value in expected.items()
            ) or metadata.get("source") != binding.provenance.source.model_dump(
                mode="json"
            ):
                raise ValueError("Custody source identity changed")
            fd = os.open(
                "artifact", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=bundle
            )
            info = check_file(fd)
            if (info.st_dev, info.st_ino, info.st_size) != (
                metadata.get("device"),
                metadata.get("inode"),
                metadata.get("size"),
            ) or not 0 < info.st_size <= MAX_ARTIFACT_BYTES:
                raise ValueError("Custody artifact replaced")
            chunks = []
            remaining = MAX_ARTIFACT_BYTES + 1
            while remaining:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = check_file(fd)
            path_info = os.stat("artifact", dir_fd=bundle, follow_symlinks=False)
            if (
                (
                    info.st_dev,
                    info.st_ino,
                    info.st_size,
                    info.st_mtime_ns,
                    info.st_ctime_ns,
                )
                != (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ctime_ns,
                )
                or (path_info.st_dev, path_info.st_ino) != (info.st_dev, info.st_ino)
                or digest(raw) != custody.raw_local_digest
            ):
                raise ValueError("Custody bytes changed")
            metadata_after = check_file(metadata_fd)
            if any(
                getattr(metadata_info, key) != getattr(metadata_after, key)
                for key in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            ):
                raise ValueError("Custody metadata changed")
            if binding.deadline().replace(tzinfo=timezone.utc) <= datetime.now(
                timezone.utc
            ):
                raise ValueError("Expired receiver evidence")
            os.lseek(fd, 0, os.SEEK_SET)
            yield VerifiedArtifact(fd, raw, metadata)
        finally:
            for descriptor in (fd, metadata_fd, bundle, root):
                if descriptor is not None:
                    os.close(descriptor)
