"""Persist named accounts and hashed local identity authority.

Revision ID: 029_add_identity_lifecycle
Revises: 028_add_narrative_guidance_payload
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "029_add_identity_lifecycle"
down_revision = "028_add_narrative_guidance_payload"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "identity_accounts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("username", sa.String(128), nullable=False, unique=True),
        sa.Column("principal_type", sa.String(20), nullable=False),
        sa.Column("password_verifier", sa.String(160), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("authentication_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "identity_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "principal_id",
            sa.String(64),
            sa.ForeignKey("identity_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("audience", sa.String(20), nullable=False),
        sa.Column("security_profile", sa.String(30), nullable=False),
        sa.Column("trusted_origin", sa.String(512), nullable=False),
        sa.Column("authentication_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_identity_sessions_principal_id", "identity_sessions", ["principal_id"]
    )
    op.create_table(
        "identity_credentials",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column(
            "principal_id",
            sa.String(64),
            sa.ForeignKey("identity_accounts.id", ondelete="CASCADE"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_identity_credentials_principal_id", "identity_credentials", ["principal_id"]
    )


def downgrade() -> None:
    op.drop_table("identity_credentials")
    op.drop_table("identity_sessions")
    op.drop_table("identity_accounts")
    op.execute("DELETE FROM app_settings WHERE key = 'identity.login_limits.v1'")
