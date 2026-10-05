"""Local-only storage for uploaded report artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field

from config import settings
from services.content_security import (
    BLOCKED_CONTENT,
    redact_text,
    sensitive_artifact_values,
)
from services.intake_service import is_sensitive_file


class ArtifactSnapshot(BaseModel):
    """Decoded artifact snapshot stored for report review flows."""

    report_id: int = Field(..., ge=1)
    artifact_name: str = Field(..., min_length=1)
    content: str = Field(..., description="UTF-8 decoded artifact content")


def _artifact_root(*, create: bool) -> Path:
    root = Path(settings.artifact_snapshot_dir)
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def _report_dir(report_id: int, *, create: bool) -> Path:
    return _artifact_root(create=create) / str(report_id)


def _manifest_path(report_id: int) -> Path:
    return _report_dir(report_id, create=False) / "manifest.json"


def _stored_name(artifact_name: str) -> str:
    digest = hashlib.sha256(artifact_name.encode("utf-8")).hexdigest()[:16]
    suffix = Path(artifact_name).suffix or ".txt"
    return f"{digest}{suffix}"


def save_report_artifacts(
    report_id: int,
    artifact_snapshots: dict[str, bytes | None] | None,
    *,
    sensitive_values: Iterable[str] = (),
) -> None:
    """Persist uploaded artifact snapshots for one report."""
    if not artifact_snapshots:
        return
    if not any(content is not None for content in artifact_snapshots.values()):
        return
    report_dir = _report_dir(report_id, create=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    sensitive_values = tuple(sensitive_values)
    for artifact_name, raw_content in artifact_snapshots.items():
        if raw_content is None or is_sensitive_file(artifact_name):
            continue
        stored_name = _stored_name(artifact_name)
        decoded_content = raw_content.decode("utf-8", errors="replace")
        content = (
            BLOCKED_CONTENT.encode("utf-8")
            if sensitive_artifact_values(raw_content)
            or redact_text(decoded_content, sensitive_values=sensitive_values)
            != decoded_content
            else raw_content
        )
        (report_dir / stored_name).write_bytes(content)
        manifest[artifact_name] = stored_name
    _manifest_path(report_id).write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_report_artifact(report_id: int, artifact_name: str) -> ArtifactSnapshot | None:
    """Return one decoded artifact snapshot when available."""
    manifest_path = _manifest_path(report_id)
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stored_name = manifest.get(artifact_name)
    if not stored_name:
        return None
    artifact_path = _report_dir(report_id, create=False) / stored_name
    if not artifact_path.exists():
        return None
    raw_content = artifact_path.read_bytes()
    sensitive_values = sensitive_artifact_values(raw_content)
    decoded_content = raw_content.decode("utf-8", errors="replace")
    return ArtifactSnapshot(
        report_id=report_id,
        artifact_name=redact_text(artifact_name, sensitive_values=sensitive_values),
        content=(
            BLOCKED_CONTENT
            if is_sensitive_file(artifact_name)
            or sensitive_values
            or redact_text(decoded_content) != decoded_content
            else decoded_content
        ),
    )


def delete_report_artifacts(report_id: int) -> None:
    """Remove local artifact snapshots for one report."""
    report_dir = _report_dir(report_id, create=False)
    if report_dir.exists():
        shutil.rmtree(report_dir)
