"""Identity queries within caller-owned atomic transactions."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from collections.abc import Iterator

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from models.tables import IdentityAccount, IdentitySession


@contextmanager
def transaction(session_factory) -> Iterator[Session]:
    """Serialize identity state on the supported SQLite deployment.

    BEGIN IMMEDIATE obtains the writer reservation before reads, so independent
    processes cannot both bootstrap or consume recovery authority. Password work
    inside this transaction has fixed cost and a nonblocking process-wide slot.
    """
    with session_factory() as session:
        if session.get_bind().dialect.name != "sqlite":
            raise RuntimeError(
                "Identity persistence requires the qualified SQLite backend"
            )
        try:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def account_by_username(session: Session, username: str) -> IdentityAccount | None:
    return session.scalar(
        select(IdentityAccount).where(IdentityAccount.username == username)
    )


def revoke_sessions(session: Session, principal_id: str, now: datetime) -> None:
    session.execute(
        update(IdentitySession)
        .where(
            IdentitySession.principal_id == principal_id,
            IdentitySession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
