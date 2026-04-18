"""Database engine and session helpers."""

from __future__ import annotations

from importlib import import_module

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

engine = create_engine(settings.database_url, future=True)

existing_session_local = globals().get("SessionLocal")

if existing_session_local is not None:
    existing_session_local.configure(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    SessionLocal = existing_session_local
else:
    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )

if "Base" not in globals():
    Base = declarative_base()


def init_db() -> None:
    """Create database tables for the current metadata set."""
    import_module("models.tables")
    Base.metadata.create_all(bind=engine)
