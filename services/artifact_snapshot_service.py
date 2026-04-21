"""Local-only storage for uploaded report artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from pydantic import BaseModel, Field

from config import settings


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
    report_id: int, artifact_snapshots: dict[str, bytes | None] | None
) -> None:
    """Persist uploaded artifact snapshots for one report."""
    if not artifact_snapshots:
        return
    report_dir = _report_dir(report_id, create=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    for artifact_name, raw_content in artifact_snapshots.items():
        if raw_content is None:
            continue
        stored_name = _stored_name(artifact_name)
        (report_dir / stored_name).write_bytes(raw_content)
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
    return ArtifactSnapshot(
        report_id=report_id,
        artifact_name=artifact_name,
        content=artifact_path.read_text(encoding="utf-8", errors="replace"),
    )


def delete_report_artifacts(report_id: int) -> None:
    """Remove local artifact snapshots for one report."""
    report_dir = _report_dir(report_id, create=False)
    if report_dir.exists():
        shutil.rmtree(report_dir)
