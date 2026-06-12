"""Intake workflow orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from api.schemas import IntakeItem, PendingAnalysis
from parsers.registry import detect_tool_type, parse_uploaded_files

SENSITIVE_FILE_MARKERS = {
    ".env",
    ".pem",
    ".key",
    ".tfstate",
    "id_rsa",
    "kubeconfig",
    "credentials",
}
MAX_TOTAL_UPLOAD_BYTES = 50_000_000
UNSAFE_ARTIFACT_PREFIX = "__unsafe_path__"
EXTERNAL_ARTIFACT_PREFIX = "__external_path__"


def artifact_name_has_traversal(original_name: str) -> bool:
    """Return whether the submitted name contains parent traversal segments."""
    return any(
        part.strip() == ".."
        for part in str(original_name or "").replace("\\", "/").split("/")
    )


def artifact_name_is_traversal_normalized(name: str) -> bool:
    normalized = str(name or "").replace("\\", "/").strip().lstrip("/")
    normalized_lower = normalized.lower()
    unsafe_prefix = UNSAFE_ARTIFACT_PREFIX.lower()
    return normalized_lower == unsafe_prefix or normalized_lower.startswith(
        f"{unsafe_prefix}/"
    )


def artifact_name_is_ownership_untrusted(name: str) -> bool:
    normalized = str(name or "").replace("\\", "/").strip().lstrip("/")
    normalized_lower = normalized.lower()
    for prefix in (UNSAFE_ARTIFACT_PREFIX, EXTERNAL_ARTIFACT_PREFIX):
        prefix_lower = prefix.lower()
        if normalized_lower == prefix_lower or normalized_lower.startswith(
            f"{prefix_lower}/"
        ):
            return True
    return False


def _is_drive_relative_segment(value: str) -> bool:
    return len(value) >= 2 and value[0].isalpha() and value[1] == ":"


def trusted_relative_artifact_path(value: object) -> str | None:
    """Return normalized trusted browser/API relative path metadata, if valid."""
    if not isinstance(value, str):
        return None
    normalized = value.replace("\\", "/").strip()
    if not normalized or normalized.startswith("/"):
        return None
    reserved_prefixes = {
        UNSAFE_ARTIFACT_PREFIX.lower(),
        EXTERNAL_ARTIFACT_PREFIX.lower(),
    }
    parts: list[str] = []
    for raw_part in normalized.split("/"):
        part = raw_part.strip()
        if not part or part == ".":
            continue
        if (
            part == ".."
            or part.endswith(":")
            or _is_drive_relative_segment(part)
            or part.lower() in reserved_prefixes
        ):
            return None
        parts.append(part)
    if not parts:
        return None
    return "/".join(parts)


def trusted_artifact_path_matches_filename(
    artifact_path: str,
    filename: object,
) -> bool:
    """Return whether trusted path metadata can be bound to this upload filename."""
    trusted_path = trusted_relative_artifact_path(artifact_path)
    if trusted_path is None:
        return False
    filename_text = str(filename or "").replace("\\", "/").strip()
    if not filename_text:
        return False
    trusted_filename = trusted_relative_artifact_path(filename_text)
    if trusted_filename is not None and "/" in trusted_filename:
        return trusted_filename == trusted_path
    if trusted_filename is None and "/" in filename_text:
        return False
    filename_leaf = filename_text.rsplit("/", maxsplit=1)[-1]
    return trusted_path.rsplit("/", maxsplit=1)[-1] == filename_leaf


def _filename_leaf(filename: object) -> str | None:
    filename_text = str(filename or "").replace("\\", "/").strip()
    if not filename_text:
        return None
    filename_leaf = filename_text.rsplit("/", maxsplit=1)[-1].strip()
    return filename_leaf or None


def trusted_artifact_path_binding_is_ambiguous(
    artifact_paths: Iterable[str],
    filenames: Iterable[object],
) -> bool:
    """Return whether path metadata cannot be unambiguously paired to uploads."""
    trusted_paths: list[str] = []
    for artifact_path in artifact_paths:
        trusted_path = trusted_relative_artifact_path(artifact_path)
        if trusted_path is None:
            return False
        trusted_paths.append(trusted_path)

    filename_paths: list[str | None] = []
    filename_leaves: list[str] = []
    for filename in filenames:
        filename_leaf = _filename_leaf(filename)
        if filename_leaf is None:
            return False
        filename_leaves.append(filename_leaf)
        filename_text = str(filename or "").replace("\\", "/").strip()
        trusted_filename = trusted_relative_artifact_path(filename_text)
        filename_paths.append(
            trusted_filename
            if trusted_filename is not None and "/" in trusted_filename
            else None
        )

    if len(set(trusted_paths)) != len(trusted_paths):
        return True

    path_leaves = [path.rsplit("/", maxsplit=1)[-1] for path in trusted_paths]
    duplicate_path_leaves = {
        leaf for leaf in path_leaves if path_leaves.count(leaf) > 1
    }
    duplicate_filename_leaves = {
        leaf for leaf in filename_leaves if filename_leaves.count(leaf) > 1
    }
    if not duplicate_path_leaves and not duplicate_filename_leaves:
        return False

    for trusted_path, filename_path in zip(trusted_paths, filename_paths, strict=False):
        if trusted_path.rsplit("/", maxsplit=1)[-1] in duplicate_path_leaves:
            if filename_path != trusted_path:
                return True
    return False


def normalize_artifact_name(
    original_name: str, *, allow_external_prefix: bool = False
) -> str:
    """Return a safe relative artifact name while preserving useful directories."""
    normalized = str(original_name or "").replace("\\", "/").strip()
    clean_segments = [
        part.strip() for part in normalized.split("/") if part.strip() and part != "."
    ]
    absolute_or_host_path = normalized.startswith("/") or (
        bool(clean_segments)
        and (
            clean_segments[0].endswith(":")
            or _is_drive_relative_segment(clean_segments[0])
        )
    )
    has_traversal = artifact_name_has_traversal(normalized)
    unsafe_prefixes = {UNSAFE_ARTIFACT_PREFIX.lower()}
    if not allow_external_prefix:
        unsafe_prefixes.add(EXTERNAL_ARTIFACT_PREFIX.lower())
    has_reserved_unsafe_prefix = any(
        part.strip().lower() in unsafe_prefixes for part in normalized.split("/")
    )
    parts: list[str] = []
    for part in normalized.split("/"):
        segment = part.strip()
        if not segment or segment == ".":
            continue
        if segment == "..":
            continue
        if segment.endswith(":") or _is_drive_relative_segment(segment):
            continue
        if segment.lower() in unsafe_prefixes:
            continue
        parts.append(segment)
    safe_name = "/".join(parts) or "artifact.bin"
    if absolute_or_host_path or has_traversal or has_reserved_unsafe_prefix:
        return f"{UNSAFE_ARTIFACT_PREFIX}/{safe_name}"
    return safe_name


def is_sensitive_file(name: str) -> bool:
    lower_name = name.lower()
    path = Path(lower_name)
    if path.name in SENSITIVE_FILE_MARKERS:
        return True
    if any(marker in lower_name for marker in SENSITIVE_FILE_MARKERS):
        return True
    return False


def uniquify_artifact_names(
    files: Iterable[tuple[str, bytes | None]],
    *,
    existing_names: Iterable[str] = (),
    allow_external_prefix: bool = False,
) -> list[tuple[str, bytes | None]]:
    used_names: set[str] = set(existing_names)
    duplicate_counts: dict[str, int] = {}
    normalized: list[tuple[str, bytes | None]] = []

    for original_name, raw_content in files:
        candidate = normalize_artifact_name(
            original_name,
            allow_external_prefix=allow_external_prefix,
        )
        duplicate_counts.setdefault(candidate, 0)
        unique_name = candidate
        while unique_name in used_names:
            duplicate_counts[candidate] += 1
            path = Path(candidate)
            base = path.stem or "artifact"
            suffix = path.suffix
            leaf = f"{base}#{duplicate_counts[candidate] + 1}{suffix}"
            parent = str(path.parent)
            unique_name = leaf if parent == "." else f"{parent}/{leaf}"
        used_names.add(unique_name)
        normalized.append((unique_name, raw_content))
    return normalized


def total_upload_bytes(files: Iterable[tuple[str, bytes | None]]) -> int:
    return sum(len(raw_content or b"") for _, raw_content in files)


def build_pending_analysis(
    files: Iterable[tuple[str, bytes | None]],
) -> PendingAnalysis:
    normalized_files = list(files)

    items: list[IntakeItem] = []
    for name, raw_content in normalized_files:
        if is_sensitive_file(name):
            items.append(
                IntakeItem(
                    name=name,
                    tool="unsupported",
                    status="sensitive",
                    message="Sensitive file detected and excluded from unsafe downstream handling.",
                )
            )
            continue

        tool = detect_tool_type(name, raw_content)
        if tool == "unsupported":
            items.append(
                IntakeItem(
                    name=name,
                    tool="unsupported",
                    status="unsupported",
                    message="Unsupported file type or unsupported content fingerprint.",
                )
            )
            continue

        items.append(
            IntakeItem(
                name=name,
                tool=tool,
                status="ready",
                message=f"{tool.title()} artifact accepted for pending analysis.",
            )
        )

    return PendingAnalysis(items=items)


def build_parse_batch(files: Iterable[tuple[str, bytes | None]]):
    ready_files = []
    for name, raw_content in files:
        if is_sensitive_file(name):
            continue
        if detect_tool_type(name, raw_content) == "unsupported":
            continue
        ready_files.append((name, raw_content))
    return parse_uploaded_files(ready_files)
