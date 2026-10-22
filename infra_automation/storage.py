"""Physical capacity and explicit file-SQLite engine durability qualification."""

from __future__ import annotations

from pathlib import Path
import shutil
import sqlite3

from sqlalchemy import event
from sqlalchemy.exc import OperationalError

import config
from infra_automation.lifecycle import LifecycleError
from infra_automation.state import EngineBounds
from services import project_service as authorization
from services import infra_automation_support as support


def _database_path(engine):
    engine = getattr(engine, "engine", engine)
    database = engine.url.database
    if (
        engine.dialect.name != "sqlite"
        or not database
        or database == ":memory:"
        or database.startswith("file:")
    ):
        raise LifecycleError(503)
    try:
        return Path(database).expanduser().resolve()
    except (OSError, RuntimeError):
        raise LifecycleError(503) from None


def ensure_capacity(session, *, additional_bytes=0, bounds=None):
    """Reserve remains available before new effects; cleanup never calls this."""
    authorization._require_operation(session)
    bounds = (
        config.engine_bounds()
        if bounds is None
        else support.revalidate(bounds, EngineBounds)
    )
    if (
        type(additional_bytes) is not int
        or not 0 <= additional_bytes <= bounds.global_bytes
    ):
        raise LifecycleError(429)
    path = _database_path(session.get_bind())
    try:
        free = shutil.disk_usage(path.parent).free
    except OSError:
        raise LifecycleError(503) from None
    if type(free) is not int or free < 0:
        raise LifecycleError(503)
    if free < bounds.disk_reserve_bytes + additional_bytes:
        raise LifecycleError(429)


def _verify_checkout(connection, record, proxy):
    cursor = connection.cursor()
    try:
        if connection.in_transaction:
            raise LifecycleError(503)
        cursor.execute("PRAGMA synchronous=FULL")
        if cursor.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
            raise LifecycleError(503)
        if cursor.execute("PRAGMA synchronous").fetchone()[0] != 2:
            raise LifecycleError(503)
    finally:
        cursor.close()


def configure_engine_sqlite(engine):
    """Opt in only after a trusted handler catalog is installed, never at import."""
    _database_path(engine)
    if event.contains(engine, "checkout", _verify_checkout):
        return
    try:
        with engine.connect() as connection:
            dbapi = connection.connection.driver_connection
            if dbapi.in_transaction:
                raise LifecycleError(503)
            cursor = dbapi.cursor()
            try:
                if (
                    cursor.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower()
                    != "wal"
                ):
                    raise LifecycleError(503)
                cursor.execute("PRAGMA synchronous=FULL")
                if cursor.execute("PRAGMA synchronous").fetchone()[0] != 2:
                    raise LifecycleError(503)
            finally:
                cursor.close()
        event.listen(engine, "checkout", _verify_checkout)
    except (LifecycleError, OperationalError, sqlite3.OperationalError):
        # Preserve coded SQLite storage failures for the trusted worker wrapper.
        raise
    except Exception:
        raise LifecycleError(503) from None
