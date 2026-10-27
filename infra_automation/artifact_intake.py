"""Bounded local screening before automation artifacts or metadata are retained."""

from __future__ import annotations

from collections.abc import Iterable
import json
from typing import cast

from infra_automation.lifecycle import LifecycleError
from parsers.registry import detect_tool_type
from services.content_security import (
    BLOCKED_CONTENT,
    REDACTED,
    redact_text,
    redact_value,
    sensitive_submission_values,
)
from services.intake_service import (
    is_sensitive_file,
    total_upload_bytes,
    trusted_relative_artifact_path,
)

MAX_ARTIFACT_BYTES = 8388608
MAX_ARTIFACTS = 32


def _byte_bound(max_bytes: int) -> int:
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_ARTIFACT_BYTES:
        raise LifecycleError(422)
    return max_bytes


def _has_nontext(value: str) -> bool:
    return any(
        ord(char) < 32 and char not in "\t\r\n" or ord(char) == 127 for char in value
    )


def screen_metadata(value, *, max_bytes: int = 16384):
    """Reject known sensitive metadata atomically, without reflecting its contents.

    This is pattern screening of a bounded JSON value, not universal detection.
    Errors and streamed diagnostics must be assembled within their byte limit
    before this function is called; individual chunks are never safe to retain.
    """
    if type(max_bytes) is not int or not 1 <= max_bytes <= 16384:
        raise LifecycleError(422)
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(encoded) > max_bytes:
            raise LifecycleError(429)
        wrapped = {"metadata": value}
        if redact_value(wrapped) != wrapped or any(
            marker.encode() in encoded for marker in (REDACTED, BLOCKED_CONTENT)
        ):
            raise LifecycleError(422)
        return value
    except LifecycleError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise LifecycleError(422) from None


def screen_artifacts(
    files: list[tuple[str, bytes | None]], *, max_bytes: int = MAX_ARTIFACT_BYTES
) -> tuple[tuple[str, bytes], ...]:
    """Accept exact supported UTF-8 inputs only after whole-submission screening.

    Uploaded source establishes neither repository identity nor plan custody.
    No rejected filename, content, parser error, or credential is reflected.
    """
    maximum = _byte_bound(max_bytes)
    if type(files) is not list or not 1 <= len(files) <= MAX_ARTIFACTS:
        raise LifecycleError(422)
    for item in files:
        if (
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not bytes
        ):
            raise LifecycleError(422)
    if total_upload_bytes(files) > maximum:
        raise LifecycleError(429)
    names: set[str] = set()
    texts = []
    for name, raw in files:
        if not 1 <= len(name) <= 256:
            raise LifecycleError(422)
        try:
            name.encode("utf-8", errors="strict")
        except UnicodeError:
            raise LifecycleError(422) from None
        if (
            any(ord(char) < 32 or ord(char) == 127 for char in name)
            or "\\" in name
            or trusted_relative_artifact_path(name) != name
            or name in names
            or is_sensitive_file(name)
            or name.lower().endswith((".tfplan", ".plan", ".zip"))
            or not raw
            or raw.startswith(b"PK")
        ):
            raise LifecycleError(422)
        names.add(name)
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeError:
            raise LifecycleError(422) from None
        if not text.strip() or _has_nontext(text) or text.lstrip().startswith("\ufeff"):
            raise LifecycleError(422)
        # A Terraform state file remains forbidden when disguised as source or
        # plan JSON. Content identity takes precedence over its filename.
        if text.lstrip().startswith("{"):
            try:
                document = json.loads(text)
            except (ValueError, RecursionError):
                document = None
            if isinstance(document, dict) and (
                {"serial", "lineage"} <= document.keys()
                or {"terraform_version", "resources", "version"} <= document.keys()
                or {"version", "modules"} <= document.keys()
            ):
                raise LifecycleError(422)
        texts.append(text)
    try:
        sensitive = sensitive_submission_values(files)
        if sensitive:
            raise LifecycleError(422)
        for (name, raw), text in zip(files, texts, strict=True):
            if (
                redact_text(name, sensitive_values=sensitive) != name
                or redact_text(text, sensitive_values=sensitive) != text
                or any(marker in text for marker in (REDACTED, BLOCKED_CONTENT))
                or detect_tool_type(name, raw) == "unsupported"
            ):
                raise LifecycleError(422)
    except (ValueError, TypeError, RecursionError):
        raise LifecycleError(422) from None
    return cast(tuple[tuple[str, bytes], ...], tuple(files))


def collect_screened_artifact(
    name: str, chunks: Iterable[bytes], *, max_bytes: int = MAX_ARTIFACT_BYTES
) -> tuple[str, bytes]:
    """Buffer within a hard ceiling, then screen across every chunk boundary.

    Nothing is yielded or stored while the stream is incomplete. HTTP adapters
    must additionally apply the aggregate ceiling across the whole submission.
    """
    maximum = _byte_bound(max_bytes)
    content = bytearray()
    for chunk in chunks:
        if type(chunk) is not bytes:
            raise LifecycleError(422)
        if len(content) + len(chunk) > maximum:
            raise LifecycleError(429)
        content.extend(chunk)
    return screen_artifacts([(name, bytes(content))], max_bytes=maximum)[0]
