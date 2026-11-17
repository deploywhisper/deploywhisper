"""Cloud-owned snapshot metadata; released core metadata stays untouched."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from models.tables import Project


class CloudSnapshotBase(DeclarativeBase):
    pass


class CloudContextSnapshot(CloudSnapshotBase):
    """Insert-only screened observation, with a one-way payload tombstone."""

    __tablename__ = "cloud_context_snapshots"
    __table_args__ = (
        CheckConstraint(
            "typeof(project_id)='integer' AND project_id > 0 AND length(digest)=64 AND digest NOT GLOB '*[^0-9a-f]*' AND length(provider) BETWEEN 1 AND 32 AND length(scope_id) BETWEEN 1 AND 128 AND mask_accounts IN (0,1)",
            name="ck_cloud_snapshot_identity",
        ),
        CheckConstraint(
            "julianday(read_window_start) IS NOT NULL AND julianday(read_window_end) IS NOT NULL AND julianday(expires_at) IS NOT NULL AND julianday(created_at) IS NOT NULL AND julianday(read_window_start)<=julianday(read_window_end) AND julianday(created_at)>=julianday(read_window_end) AND julianday(expires_at)=julianday(read_window_end,'+7 days')",
            name="ck_cloud_snapshot_times",
        ),
        CheckConstraint(
            "(payload_json IS NOT NULL AND json_valid(payload_json) AND purged_at IS NULL) OR (payload_json IS NULL AND purged_at IS NOT NULL AND julianday(purged_at) IS NOT NULL)",
            name="ck_cloud_snapshot_payload_state",
        ),
        Index("ix_cloud_snapshots_project_expiry", "project_id", "expires_at"),
        {"sqlite_with_rowid": False},
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey(Project.__table__.c.id, ondelete="CASCADE"), primary_key=True
    )
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    read_window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    read_window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    mask_accounts: Mapped[bool] = mapped_column(Boolean, nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    purged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
