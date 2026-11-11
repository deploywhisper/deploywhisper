"""Local recovery fence metadata, independent of retained effect bindings."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from models.database import Base


class RecoveryState(Base):
    __tablename__ = "infra_automation_recovery_state"
    __table_args__ = (
        CheckConstraint(
            "id=1 AND generation BETWEEN 1 AND 9007199254740991",
            name="ck_recovery_generation",
        ),
        CheckConstraint(
            "phase IN ('ready','reconciliation_required') AND length(installation_id)=32",
            name="ck_recovery_phase",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    installation_id: Mapped[str] = mapped_column(String(32), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    manifest_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class RestoreEvent(Base):
    __tablename__ = "infra_automation_restore_events"
    __table_args__ = (
        CheckConstraint(
            "generation BETWEEN 1 AND 9007199254740991 AND event IN ('restored','completed')",
            name="ck_restore_event",
        ),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    backup_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    event: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
