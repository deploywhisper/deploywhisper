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

def is_sensitive_file(name: str) -> bool:
    lower_name = name.lower()
    path = Path(lower_name)
    if path.name in SENSITIVE_FILE_MARKERS:
        return True
    if any(marker in lower_name for marker in SENSITIVE_FILE_MARKERS):
        return True
    return False
def build_pending_analysis(files: Iterable[tuple[str, bytes | None]]) -> PendingAnalysis:
    latest_by_name: dict[str, bytes | None] = {}
    for name, raw_content in files:
        latest_by_name[name] = raw_content

    items: list[IntakeItem] = []
    for name, raw_content in latest_by_name.items():
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
    latest_by_name: dict[str, bytes | None] = {}
    for name, raw_content in files:
        latest_by_name[name] = raw_content
    ready_files = []
    for name, raw_content in latest_by_name.items():
        if is_sensitive_file(name):
            continue
        if detect_tool_type(name, raw_content) == "unsupported":
            continue
        ready_files.append((name, raw_content))
    return parse_uploaded_files(ready_files)
