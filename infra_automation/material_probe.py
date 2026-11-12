"""Signed live custody checks across a bounded local Unix-socket boundary."""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import stat
import struct

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import StringConstraints
from typing import Annotated, Literal

from infra_automation.contracts import ClosedModel, Digest
from infra_automation.receiver_custody import ProtectedCustody, canonical
from infra_automation.receiver_protocol import (
    ReceiverBinding,
    receiver_binding_digest,
)

MAX_MESSAGE_BYTES = 256 * 1024
Nonce = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    ),
]
Signature = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=128,
        max_length=128,
        pattern=r"^[0-9a-f]{128}$",
    ),
]


class CustodyChallenge(ClosedModel):
    version: Literal[1] = 1
    nonce: Nonce
    binding: ReceiverBinding


class CustodyResult(ClosedModel):
    version: Literal[1] = 1
    nonce: Nonce
    binding_digest: Digest
    available: Literal[True] = True


class SignedCustodyResult(ClosedModel):
    version: Literal[1] = 1
    result: CustodyResult
    signature: Signature


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate custody probe field")
        value[key] = item
    return value


def _wire(value) -> bytes:
    return canonical(value.model_dump(mode="json"))


def _send(connection, raw):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_MESSAGE_BYTES:
        raise ValueError("Invalid custody probe message")
    connection.sendall(struct.pack("!I", len(raw)) + raw)


def _receive(connection):
    header = _receive_exact(connection, 4)
    length = struct.unpack("!I", header)[0]
    if not 1 <= length <= MAX_MESSAGE_BYTES:
        raise ValueError("Invalid custody probe message size")
    return _receive_exact(connection, length)


def _receive_exact(connection, size):
    chunks = []
    remaining = size
    while remaining:
        value = connection.recv(remaining)
        if not value:
            raise ValueError("Incomplete custody probe message")
        chunks.append(value)
        remaining -= len(value)
    return b"".join(chunks)


def _socket_info(path):
    info = os.lstat(path)
    mode = stat.S_IMODE(info.st_mode)
    if (
        not stat.S_ISSOCK(info.st_mode)
        or info.st_nlink != 1
        or mode not in {0o600, 0o660}
    ):
        raise ValueError("Unsafe custody probe socket")
    return info


class UnixMaterialCustodyProbe:
    """App-side verifier: public key only, no custody path or raw material."""

    def __init__(self, socket_path, verification_key, *, timeout=2.0):
        self.socket_path = Path(socket_path)
        if not isinstance(verification_key, Ed25519PublicKey):
            raise ValueError("Ed25519 verification key required")
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 10:
            raise ValueError("Invalid custody probe timeout")
        self.verification_key = verification_key
        self.timeout = float(timeout)

    def __call__(self, record, collection, binding):
        binding = ReceiverBinding.model_validate(binding)
        custody = binding.provenance.custody
        if (
            custody is None
            or record.custody_handle != custody.handle
            or record.raw_local_digest != custody.raw_local_digest
            or collection.custody is None
            or collection.custody.handle != custody.handle
        ):
            raise ValueError("Custody identity mismatch")
        before = _socket_info(self.socket_path)
        challenge = CustodyChallenge(
            nonce=secrets.token_hex(32),
            binding=binding,
        )
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self.timeout)
            connection.connect(str(self.socket_path))
            after = _socket_info(self.socket_path)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise ValueError("Custody probe socket changed")
            _send(connection, _wire(challenge))
            raw = _receive(connection)
        envelope = SignedCustodyResult.model_validate(
            json.loads(raw, object_pairs_hook=_unique)
        )
        result = envelope.result
        if (
            result.nonce != challenge.nonce
            or result.binding_digest != receiver_binding_digest(binding)
        ):
            raise ValueError("Custody probe response mismatch")
        try:
            self.verification_key.verify(
                bytes.fromhex(envelope.signature), _wire(result)
            )
        except (InvalidSignature, ValueError):
            raise ValueError("Invalid custody probe signature") from None
        return True


class MaterialCustodyProbeServer:
    """Authority-side live descriptor verifier and signed response service."""

    def __init__(
        self, socket_path, custody_root, signing_key, *, timeout=3.0, socket_gid=None
    ):
        self.socket_path = Path(socket_path)
        self.custody = ProtectedCustody(custody_root)
        if not isinstance(signing_key, Ed25519PrivateKey):
            raise ValueError("Ed25519 signing key required")
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 10:
            raise ValueError("Invalid custody probe timeout")
        self.signing_key = signing_key
        self.timeout = float(timeout)
        if socket_gid is not None and (type(socket_gid) is not int or socket_gid < 0):
            raise ValueError("Invalid custody probe socket group")
        self.socket_gid = socket_gid
        self._listener = None
        self._identity = None

    def __enter__(self):
        parent = self.socket_path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = parent.stat()
        if info.st_uid != os.getuid():
            raise ValueError("Custody probe directory owner changed")
        if self.socket_gid is None:
            if stat.S_IMODE(info.st_mode) != 0o700:
                raise ValueError("Custody probe directory must be owner-only")
        else:
            os.chown(parent, -1, self.socket_gid)
            os.chmod(parent, 0o710)
            info = parent.stat()
            if info.st_gid != self.socket_gid or stat.S_IMODE(info.st_mode) != 0o710:
                raise ValueError("Custody probe directory group access unavailable")
        try:
            os.lstat(self.socket_path)
        except FileNotFoundError:
            pass
        else:
            raise ValueError("Custody probe socket already exists")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self.socket_path))
        if self.socket_gid is None:
            os.chmod(self.socket_path, 0o600)
        else:
            os.chown(self.socket_path, -1, self.socket_gid)
            os.chmod(self.socket_path, 0o660)
        listener.listen(8)
        listener.settimeout(self.timeout)
        self._listener = listener
        self._identity = _socket_info(self.socket_path)
        return self

    def serve_once(self):
        if self._listener is None:
            raise ValueError("Custody probe server is not started")
        connection, _ = self._listener.accept()
        with connection:
            connection.settimeout(self.timeout)
            try:
                challenge = CustodyChallenge.model_validate(
                    json.loads(_receive(connection), object_pairs_hook=_unique)
                )
                with self.custody.verify(challenge.binding):
                    result = CustodyResult(
                        nonce=challenge.nonce,
                        binding_digest=receiver_binding_digest(challenge.binding),
                    )
                envelope = SignedCustodyResult(
                    result=result,
                    signature=self.signing_key.sign(_wire(result)).hex(),
                )
                _send(connection, _wire(envelope))
                return True
            except Exception:
                # No exception text or custody fact is exposed to the caller.
                return False

    def __exit__(self, *_):
        if self._listener is not None:
            self._listener.close()
            self._listener = None
        try:
            current = _socket_info(self.socket_path)
            if self._identity is not None and (
                current.st_dev,
                current.st_ino,
            ) == (self._identity.st_dev, self._identity.st_ino):
                os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
        self._identity = None
