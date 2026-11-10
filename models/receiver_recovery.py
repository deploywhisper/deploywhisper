"""Current hashed, exact-operation receiver reconciliation credentials."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from models.database import Base


class ReceiverRecoveryCredential(Base):
    __tablename__ = "infra_automation_receiver_recovery_credentials"
    __table_args__ = (
        CheckConstraint(
            "version BETWEEN 1 AND 9007199254740991 AND generation BETWEEN 1 AND 9007199254740991 AND project_restore_epoch BETWEEN 1 AND 9007199254740991 AND receiver_authentication_version BETWEEN 1 AND 9007199254740991 AND issuer_authentication_version BETWEEN 1 AND 9007199254740991 AND issuer_membership_version BETWEEN 1 AND 9007199254740991 AND issue_count BETWEEN 1 AND 100",
            name="ck_receiver_recovery_versions",
        ),
        CheckConstraint(
            "mode IN ('status_only','status_terminal') AND length(installation_id)=32 AND length(token_hash)=64 AND length(binding_digest)=71 AND length(receipt_digest)=71 AND length(credential_digest)=71",
            name="ck_receiver_recovery_binding",
        ),
        CheckConstraint(
            "issued_at <= last_observed_at AND issued_at < expires_at",
            name="ck_receiver_recovery_time",
        ),
    )
    operation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("infra_automation_handoffs.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    workspace_id: Mapped[int] = mapped_column(Integer, nullable=False)
    receiver_id: Mapped[str] = mapped_column(String(128), nullable=False)
    receiver_principal_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("identity_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    installation_id: Mapped[str] = mapped_column(String(32), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    project_restore_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    receiver_authentication_version: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    issuer_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("identity_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    issuer_authentication_version: Mapped[int] = mapped_column(Integer, nullable=False)
    issuer_membership_version: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_count: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    binding_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    receipt_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    credential_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
