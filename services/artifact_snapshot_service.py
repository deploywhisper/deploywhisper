"""Local-only storage for uploaded report artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import shutil
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field

from config import settings
from models.database import SessionLocal
from services.project_service import (
    authorized_session,
    guard_report,
    TrustedAuthorizationError,
)
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
    if type(report_id) is not int or report_id < 1:
        raise ValueError("Artifact snapshots require a positive integer report ID.")
    root = _artifact_root(create=create).resolve()
    report_dir = root / str(report_id)
    if report_dir.is_symlink() or report_dir.resolve().parent != root:
        raise ValueError("Artifact snapshot report directory is unsafe.")
    return report_dir


def _snapshot_path(report_dir: Path, stored_name: str) -> Path:
    # Historical manifests may contain ordinary basenames such as old.txt.
    # Never let manifest contents select a directory or follow a symlink.
    if (
        not isinstance(stored_name, str)
        or not stored_name
        or stored_name in {".", ".."}
        or "/" in stored_name
        or "\\" in stored_name
        or "\x00" in stored_name
    ):
        raise ValueError("Artifact snapshot filename is unsafe.")
    path = report_dir / stored_name
    if path.is_symlink() or path.resolve().parent != report_dir:
        raise ValueError("Artifact snapshot path is unsafe.")
    return path


def _manifest_path(report_id: int) -> Path:
    return _snapshot_path(_report_dir(report_id, create=False), "manifest.json")


def _stored_name(artifact_name: str) -> str:
    digest = hashlib.sha256(artifact_name.encode("utf-8")).hexdigest()[:16]
    suffix = Path(artifact_name).suffix or ".txt"
    return f"{digest}{suffix}"


def _require_mutable_artifacts(session, report_id: int) -> None:
    from sqlalchemy import select
    from models.tables import InfraAutomationReportLink
    from services import project_service as authorization

    if (
        session.scalar(
            select(InfraAutomationReportLink.id)
            .where(InfraAutomationReportLink.report_id == report_id)
            .limit(1)
        )
        is not None
    ):
        raise authorization.TrustedAuthorizationError()


def save_report_artifacts(
    report_id: int,
    artifact_snapshots: dict[str, bytes | None] | None,
    *,
    sensitive_values: Iterable[str] = (),
) -> None:
    """Persist uploaded artifact snapshots for one report."""
    if type(report_id) is not int or report_id < 1:
        raise ValueError("Artifact snapshots require a positive integer report ID.")
    with authorized_session(SessionLocal) as session:
        if guard_report(session, report_id, "analysis.submit", mutation=True) is None:
            raise TrustedAuthorizationError()
        _require_mutable_artifacts(session, report_id)
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
            _snapshot_path(report_dir, stored_name).write_bytes(content)
            manifest[artifact_name] = stored_name
        _manifest_path(report_id).write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def load_report_artifact(report_id: int, artifact_name: str) -> ArtifactSnapshot | None:
    """Return one decoded artifact snapshot when available."""
    if type(report_id) is not int or report_id < 1:
        raise ValueError("Artifact snapshots require a positive integer report ID.")
    with authorized_session(SessionLocal) as session:
        if guard_report(session, report_id, "report.read") is None:
            raise TrustedAuthorizationError()
        report_dir = _report_dir(report_id, create=False)
        try:
            manifest_path = _snapshot_path(report_dir, "manifest.json")
        except ValueError:
            return None
        if not manifest_path.exists():
            return None
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            return None
        stored_name = manifest.get(artifact_name)
        if not stored_name:
            return None
        try:
            artifact_path = _snapshot_path(report_dir, stored_name)
        except ValueError:
            return None
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


def _delete_report_artifacts_after_authorization(report_id: int) -> None:
    """Remove local artifact snapshots for one report."""
    report_dir = _report_dir(report_id, create=False)
    if report_dir.exists():
        shutil.rmtree(report_dir)


def delete_report_artifacts(report_id: int) -> None:
    """Remove snapshots only while their live report authorizes mutation."""
    if type(report_id) is not int or report_id < 1:
        raise ValueError("Artifact snapshots require a positive integer report ID.")
    with authorized_session(SessionLocal) as session:
        if guard_report(session, report_id, "report.review", mutation=True) is None:
            raise TrustedAuthorizationError()
        _require_mutable_artifacts(session, report_id)
        _delete_report_artifacts_after_authorization(report_id)


def retained_report_artifact_bytes(
    session, report_id: int, *, handle=None, now=None
) -> int:
    """Count retained payload files and their sidecar under current report authority."""
    from services import project_service as authorization

    authorization._require_operation(session)
    if handle is None:
        if authorization.guard_report(session, report_id, "analysis.submit") is None:
            raise authorization.TrustedAuthorizationError()
    else:
        from datetime import datetime, timezone
        from infra_automation import claims
        from models.tables import AnalysisReport

        attempt = claims._attempt(session, handle, now or datetime.now(timezone.utc))
        report = session.get(AnalysisReport, report_id)
        member = authorization.membership_repository.get_membership(
            session, principal_id=handle.principal_id, project_id=handle.project_id
        )
        if (
            attempt.state != "running"
            or attempt.step_kind != "shared_analysis"
            or report is None
            or (report.project_id, report.workspace_id)
            != (handle.project_id, handle.workspace_id)
            or member is None
            or not member.enabled
            or "analysis.submit"
            not in authorization.PROJECT_ROLE_CAPABILITIES.get(member.role, ())
        ):
            raise authorization.TrustedAuthorizationError()
    report_dir = _report_dir(report_id, create=False)
    if not report_dir.exists():
        return 0
    # Descriptors keep a replaced path from redirecting the byte accounting to
    # another directory or following a symlink between validation and open.
    directory_fd = os.open(report_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        total = 0
        for name in os.listdir(directory_fd):
            _snapshot_path(report_dir, name)
            descriptor = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd
            )
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError("Artifact snapshot payload is unsafe.")
                total += info.st_size
            finally:
                os.close(descriptor)
        return total
    finally:
        os.close(directory_fd)
