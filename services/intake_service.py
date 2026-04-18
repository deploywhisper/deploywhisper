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
) -> list[tuple[str, bytes | None]]:
    used_names: set[str] = set(existing_names)
    duplicate_counts: dict[str, int] = {}
    normalized: list[tuple[str, bytes | None]] = []

    for original_name, raw_content in files:
        candidate = Path(original_name).name or "artifact.bin"
        duplicate_counts.setdefault(candidate, 0)
        unique_name = candidate
        while unique_name in used_names:
            duplicate_counts[candidate] += 1
            base = Path(candidate).stem or "artifact"
            suffix = Path(candidate).suffix
            unique_name = f"{base}#{duplicate_counts[candidate] + 1}{suffix}"
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
