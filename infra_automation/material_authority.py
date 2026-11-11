"""Owner-local monotonic metadata ledger for co-located material authority.

The ledger contains only nonsecret identities and generations. Raw custody bytes
and filesystem paths never enter this document or the application material port.
"""

from __future__ import annotations

import json
import fcntl
import os
from pathlib import Path
import secrets
import stat

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, StringConstraints, model_validator
from typing import Annotated, Literal

from infra_automation.contracts import ClosedModel, Digest, Identifier, SAFE_INTEGER
from infra_automation.lifecycle import Positive

MAX_LEDGER_BYTES = 1024 * 1024
Signature = Annotated[
    str,
    StringConstraints(
        strict=True, min_length=128, max_length=128, pattern=r"^[0-9a-f]{128}$"
    ),
]


class MaterialAuthorityRecord(ClosedModel):
    run_id: Identifier
    step_id: Identifier
    binding_digest: Digest
    source_digest: Digest
    custody_handle: Identifier
    raw_local_digest: Digest
    expires_at: str
    generation: Annotated[int, Field(strict=True, ge=1, le=SAFE_INTEGER)]
    state: Literal["active", "revoked"] = "active"


class MaterialAuthorityDocument(ClosedModel):
    version: Literal[1] = 1
    source_id: Identifier
    recovery_generation: Positive
    records: Annotated[tuple[MaterialAuthorityRecord, ...], Field(max_length=250)] = ()

    @model_validator(mode="after")
    def unique_records_and_generations(self):
        if len({(row.run_id, row.step_id) for row in self.records}) != len(
            self.records
        ) or len({row.generation for row in self.records}) != len(self.records):
            raise ValueError("Material records and generations must be unique")
        return self


class SignedMaterialAuthorityDocument(ClosedModel):
    version: Literal[1] = 1
    document: MaterialAuthorityDocument
    signature: Signature


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate material ledger key")
        value[key] = item
    return value


def canonical(document: MaterialAuthorityDocument) -> bytes:
    value = MaterialAuthorityDocument.model_validate(document)
    return (
        json.dumps(
            value.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode()


class MaterialAuthorityLedger:
    def __init__(self, path, *, verification_key, signing_key=None):
        self.path = Path(path).resolve()
        if not isinstance(verification_key, Ed25519PublicKey) or (
            signing_key is not None and not isinstance(signing_key, Ed25519PrivateKey)
        ):
            raise ValueError("Ed25519 material authority keys required")
        self.verification_key = verification_key
        self.signing_key = signing_key
        if signing_key is not None:
            challenge = b"deploywhisper-material-authority-key-check-v1"
            try:
                verification_key.verify(signing_key.sign(challenge), challenge)
            except InvalidSignature:
                raise ValueError("Material authority keypair mismatch") from None

    @staticmethod
    def _private_parent(path: Path):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            os.close(descriptor)
            raise ValueError("Material ledger directory must be owner-only")
        return descriptor

    def _read_file(self, parent):
        descriptor = None
        try:
            descriptor = os.open(
                self.path.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=parent,
            )
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
                or not 1 <= info.st_size <= MAX_LEDGER_BYTES
            ):
                raise ValueError("Unsafe material ledger")
            raw = os.read(descriptor, MAX_LEDGER_BYTES + 1)
            after = os.fstat(descriptor)
            named = os.stat(self.path.name, dir_fd=parent, follow_symlinks=False)
            if (
                len(raw) != info.st_size
                or (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                or (named.st_dev, named.st_ino) != (info.st_dev, info.st_ino)
            ):
                raise ValueError("Material ledger changed during read")
            envelope = SignedMaterialAuthorityDocument.model_validate_json(
                json.dumps(json.loads(raw, object_pairs_hook=_unique))
            )
            value = envelope.document
            try:
                self.verification_key.verify(
                    bytes.fromhex(envelope.signature), canonical(value)
                )
            except (InvalidSignature, ValueError):
                raise ValueError("Invalid material authority signature") from None
            return value
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def read(self, *, source_id: str, recovery_generation: int):
        parent = self._private_parent(self.path.parent)
        try:
            value = self._read_file(parent)
            if (
                value.source_id != source_id
                or value.recovery_generation != recovery_generation
            ):
                raise ValueError("Material ledger recovery domain changed")
            return value
        finally:
            os.close(parent)

    def read_any(self):
        """Read a validated prior domain for an explicit recovery rebind."""
        parent = self._private_parent(self.path.parent)
        try:
            return self._read_file(parent)
        finally:
            os.close(parent)

    def write(self, document: MaterialAuthorityDocument):
        """Atomically publish a complete operator-produced ledger snapshot."""
        if self.signing_key is None:
            raise ValueError("Material ledger writer requires the private key")
        document = MaterialAuthorityDocument.model_validate(document)
        payload = canonical(document)
        raw = (
            json.dumps(
                SignedMaterialAuthorityDocument(
                    document=document,
                    signature=self.signing_key.sign(payload).hex(),
                ).model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
        if len(raw) > MAX_LEDGER_BYTES:
            raise ValueError("Material ledger exceeds limit")
        parent = self._private_parent(self.path.parent)
        temporary = ".material-" + secrets.token_hex(16)
        descriptor = lock = None
        try:
            lock = os.open(
                ".material.lock",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent,
            )
            lock_info = os.fstat(lock)
            if (
                not stat.S_ISREG(lock_info.st_mode)
                or lock_info.st_uid != os.getuid()
                or stat.S_IMODE(lock_info.st_mode) != 0o600
                or lock_info.st_nlink != 1
            ):
                raise ValueError("Unsafe material ledger lock")
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                previous = self._read_file(parent)
            except FileNotFoundError:
                previous = None
            if previous is not None:
                if document.recovery_generation < previous.recovery_generation or (
                    document.source_id != previous.source_id
                    and document.recovery_generation <= previous.recovery_generation
                ):
                    raise ValueError("Material recovery domain rolled back")
                current = {(row.run_id, row.step_id): row for row in document.records}
                for old in previous.records:
                    new = current.get((old.run_id, old.step_id))
                    if new is None:
                        raise ValueError("Material records cannot disappear")
                    changed = old.model_dump(exclude={"generation"}) != new.model_dump(
                        exclude={"generation"}
                    )
                    if new.generation < old.generation or (
                        changed and new.generation <= old.generation
                    ):
                        raise ValueError("Material generation did not advance")
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent,
            )
            view = memoryview(raw)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("Incomplete material ledger write")
                view = view[written:]
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            os.rename(temporary, self.path.name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
            if lock is not None:
                os.close(lock)
            os.close(parent)


def _read_key(path, *, private):
    path = Path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        mode = stat.S_IMODE(info.st_mode)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or not 1 <= info.st_size <= 16 * 1024
            or (private and mode not in {0o400, 0o600})
            or (not private and mode not in {0o400, 0o444, 0o600, 0o644})
        ):
            raise ValueError("Unsafe material authority key")
        raw = os.read(descriptor, 16 * 1024 + 1)
        if len(raw) != info.st_size:
            raise ValueError("Incomplete material authority key")
    finally:
        os.close(descriptor)
    try:
        if private:
            key = serialization.load_pem_private_key(raw, password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise ValueError
            return key
        key = serialization.load_pem_public_key(raw)
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError
        return key
    except (ValueError, TypeError):
        raise ValueError("Invalid material authority key") from None


def load_private_key(path):
    return _read_key(path, private=True)


def load_public_key(path):
    return _read_key(path, private=False)
