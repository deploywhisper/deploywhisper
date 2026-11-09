"""Bounded exact-byte HMAC framing; authentication never parses a request body."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import re
import struct

from infra_automation.contracts import SAFE_INTEGER

DOMAIN = b"deploywhisper-signed-trigger-v1\x00"
MAX_BODY_BYTES = 131072
MAX_SKEW_SECONDS = 300
SIGNED_PATHS = frozenset(
    "/api/v1/infra-automation/triggers/" + suffix
    for suffix in ("webhook", "validate", "status", "list", "cli/run")
)
KEY_ID_HEADER = "X-DeployWhisper-Key-Id"
TIMESTAMP_HEADER = "X-DeployWhisper-Timestamp"
NONCE_HEADER = "X-DeployWhisper-Nonce"
SIGNATURE_HEADER = "X-DeployWhisper-Signature"
SIGNATURE_PREFIX = "sha256="

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_NONCE = re.compile(r"[A-Za-z0-9_-]{16,128}\Z")
_TIMESTAMP = re.compile(r"(?:0|[1-9][0-9]{0,15})\Z")
_SIGNATURE = re.compile(r"sha256=([0-9a-f]{64})\Z")


class TriggerSignatureError(ValueError):
    """Never carries request content, key bytes or caller-controlled diagnostics."""

    def __init__(self):
        super().__init__("Signed request authentication failed.")


@dataclass(frozen=True, repr=False)
class VerifiedSignature:
    """Cryptographic facts only; durable nonce and live authority checks follow."""

    key_id: str
    timestamp: int
    nonce: str
    body_digest: str
    expires_at: datetime


def signing_bytes(
    *, key_id: str, method: str, path: str, timestamp: str, nonce: str, body: bytes
) -> bytes:
    """Frame the six exact fields with unsigned four-byte big-endian lengths.

    The body field is its raw SHA-256 digest, not a parsed/canonicalized object.
    Key ID and the versioned domain prevent cross-key/protocol substitution.
    Query strings and path aliases are outside the fixed v1 signing surface.
    """
    if (
        type(key_id) is not str
        or _IDENTIFIER.fullmatch(key_id) is None
        or type(method) is not str
        or method != "POST"
        or type(path) is not str
        or path not in SIGNED_PATHS
        or type(timestamp) is not str
        or _TIMESTAMP.fullmatch(timestamp) is None
        or not 1 <= int(timestamp) <= SAFE_INTEGER
        or type(nonce) is not str
        or _NONCE.fullmatch(nonce) is None
        or type(body) is not bytes
        or len(body) > MAX_BODY_BYTES
    ):
        raise TriggerSignatureError()
    fields = (
        key_id.encode("ascii"),
        method.encode("ascii"),
        path.encode("ascii"),
        timestamp.encode("ascii"),
        nonce.encode("ascii"),
        hashlib.sha256(body).digest(),
    )
    return DOMAIN + b"".join(struct.pack(">I", len(field)) + field for field in fields)


def sign_request(
    secret: bytes,
    *,
    key_id: str,
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    body: bytes,
) -> str:
    """Sign with an exact 256-bit key supplied by protected caller custody."""
    if type(secret) is not bytes or len(secret) != 32:
        raise TriggerSignatureError()
    framed = signing_bytes(
        key_id=key_id,
        method=method,
        path=path,
        timestamp=timestamp,
        nonce=nonce,
        body=body,
    )
    return SIGNATURE_PREFIX + hmac.new(secret, framed, hashlib.sha256).hexdigest()


def verify_request(
    secret: bytes,
    *,
    signature: str,
    now: datetime,
    key_id: str,
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    body: bytes,
) -> VerifiedSignature:
    """Authenticate exact bytes within an exclusive 300-second UTC window.

    Success is not replay admission or authorization. A nonce must remain retained
    through returned expires_at; a later layer reserves it durably before parsing.
    """
    if type(secret) is not bytes or len(secret) != 32:
        raise TriggerSignatureError()
    framed = signing_bytes(
        key_id=key_id,
        method=method,
        path=path,
        timestamp=timestamp,
        nonce=nonce,
        body=body,
    )
    match = _SIGNATURE.fullmatch(signature) if type(signature) is str else None
    if match is None:
        raise TriggerSignatureError()
    expected = hmac.new(secret, framed, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, bytes.fromhex(match.group(1))):
        raise TriggerSignatureError()
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
        raise TriggerSignatureError()
    seconds = int(timestamp)
    try:
        if abs(now.timestamp() - seconds) >= MAX_SKEW_SECONDS:
            raise TriggerSignatureError()
        expires_at = datetime.fromtimestamp(seconds + MAX_SKEW_SECONDS, timezone.utc)
    except (ValueError, OverflowError, OSError):
        raise TriggerSignatureError() from None
    return VerifiedSignature(
        key_id=key_id,
        timestamp=seconds,
        nonce=nonce,
        body_digest="sha256:" + hashlib.sha256(body).hexdigest(),
        expires_at=expires_at,
    )
