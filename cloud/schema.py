"""Strict opt-in SQLite schema namespace for screened cloud observations."""

from __future__ import annotations

import re

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models.cloud_snapshots import CloudContextSnapshot

SCHEMA_KEY = "cloud_context:schema"
SCHEMA_VALUE = '{"version":1}'


class CloudSnapshotSchemaError(ValueError):
    code = "cloud_snapshot_schema_unavailable"

    def __init__(self):
        super().__init__("Cloud snapshot schema unavailable.")


class CloudSnapshotSchemaStorageError(CloudSnapshotSchemaError):
    """A database operation failed while inspecting the snapshot schema."""


TABLE = "cloud_context_snapshots"
IDENTITY_CHECK = "typeof(project_id)='integer' AND project_id > 0 AND length(digest)=64 AND digest NOT GLOB '*[^0-9a-f]*' AND length(provider) BETWEEN 1 AND 32 AND length(scope_id) BETWEEN 1 AND 128 AND mask_accounts IN (0,1)"
TIME_CHECK = "julianday(read_window_start) IS NOT NULL AND julianday(read_window_end) IS NOT NULL AND julianday(expires_at) IS NOT NULL AND julianday(created_at) IS NOT NULL AND julianday(read_window_start)<=julianday(read_window_end) AND julianday(created_at)>=julianday(read_window_end) AND julianday(expires_at)=julianday(read_window_end,'+7 days')"
STATE_CHECK = "(payload_json IS NOT NULL AND json_valid(payload_json) AND purged_at IS NULL) OR (payload_json IS NULL AND purged_at IS NOT NULL AND julianday(purged_at) IS NOT NULL)"
_REFERENCE = """EXISTS (
 SELECT 1 FROM evidence_items e JOIN analysis_reports a ON a.id=e.analysis_id
 WHERE a.project_id=OLD.project_id AND e.source_type='live_state'
 AND (e.source_ref='live_state://' || OLD.project_id || '/' || OLD.digest
 OR e.source_ref LIKE 'live_state://' || OLD.project_id || '/' || OLD.digest || '#%')
)"""
_UNCHANGED = " AND ".join(
    f"NEW.{name} IS OLD.{name}"
    for name in (
        "project_id",
        "digest",
        "provider",
        "scope_id",
        "read_window_start",
        "read_window_end",
        "expires_at",
        "created_at",
        "mask_accounts",
    )
)
GUARDS = {
    "cloud_snapshots_project_insert_cleanup": """CREATE TRIGGER cloud_snapshots_project_insert_cleanup AFTER INSERT ON projects
 BEGIN DELETE FROM app_settings WHERE key='cloud_context:' || NEW.id; END""",
    "cloud_snapshots_project_cleanup": """CREATE TRIGGER cloud_snapshots_project_cleanup AFTER DELETE ON projects
 BEGIN DELETE FROM app_settings WHERE key='cloud_context:' || OLD.id; END""",
    "cloud_snapshots_initial_payload": f"""CREATE TRIGGER cloud_snapshots_initial_payload BEFORE INSERT ON {TABLE}
 WHEN NEW.payload_json IS NULL OR NEW.purged_at IS NOT NULL
 OR EXISTS(SELECT 1 FROM cloud_context_snapshots WHERE project_id=NEW.project_id AND digest=NEW.digest)
 BEGIN SELECT RAISE(ABORT,'Cloud snapshot insert requires a new observation'); END""",
    "cloud_snapshots_immutable_update": f"""CREATE TRIGGER cloud_snapshots_immutable_update BEFORE UPDATE ON {TABLE}
 WHEN NOT (OLD.payload_json IS NOT NULL AND OLD.purged_at IS NULL
 AND NEW.payload_json IS NULL AND NEW.purged_at IS NOT NULL
 AND {_UNCHANGED}
 AND julianday('now')>=julianday(OLD.expires_at)
 AND CAST(strftime('%s',NEW.purged_at) AS INTEGER)>=CAST(strftime('%s',OLD.expires_at) AS INTEGER)
 AND CAST(strftime('%s',NEW.purged_at) AS INTEGER)<=CAST(strftime('%s','now') AS INTEGER)
 AND NOT {_REFERENCE})
 BEGIN SELECT RAISE(ABORT,'Cloud snapshot is immutable or retained'); END""",
    "cloud_snapshots_immutable_delete": f"""CREATE TRIGGER cloud_snapshots_immutable_delete BEFORE DELETE ON {TABLE}
 WHEN EXISTS(SELECT 1 FROM projects WHERE id=OLD.project_id)
 BEGIN SELECT RAISE(ABORT,'Cloud snapshot tombstone is immutable'); END""",
}


def _normalized(value):
    # Whitespace/casing outside quoted literals is immaterial. Preserve literal
    # case: changing live_state to LIVE_STATE would disable the retention guard.
    tokens = re.findall(r"'(?:''|[^'])*'|[^']+", value or "")
    return "".join(
        token
        if token.startswith("'")
        else re.sub(r"\s+", "", token).lower().replace('"', "")
        for token in tokens
    ).rstrip(";")


def _schema_complete(connection, tables=None):
    """Fail closed on any partially installed observation table or guard."""
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names()) if tables is None else tables
    triggers = dict(
        connection.exec_driver_sql(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name GLOB 'cloud_snapshots_*'"
        ).all()
    )
    if TABLE not in tables and not triggers:
        return False
    expected_names = {
        "project_id",
        "digest",
        "provider",
        "scope_id",
        "read_window_start",
        "read_window_end",
        "expires_at",
        "created_at",
        "mask_accounts",
        "payload_json",
        "purged_at",
    }
    if TABLE not in tables or not {
        "projects",
        "analysis_reports",
        "evidence_items",
        "app_settings",
    }.issubset(tables):
        raise RuntimeError(
            "Detected a partial cloud snapshot schema. Manual recovery is required."
        )
    columns = {column["name"]: column for column in inspector.get_columns(TABLE)}
    checks = {
        item["name"]: _normalized(item["sqltext"])
        for item in inspector.get_check_constraints(TABLE)
    }
    foreign = inspector.get_foreign_keys(TABLE)
    indexes = inspector.get_indexes(TABLE)
    table_sql = (
        connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
        ).scalar()
        or ""
    )
    # No implicit rowid aliases or alternate uniqueness conflicts may delete a
    # different observation through REPLACE with recursive_triggers disabled.
    without_rowid = (
        "--" not in table_sql
        and "/*" not in table_sql
        and _normalized(table_sql).endswith(")withoutrowid")
    )
    complete = (
        without_rowid
        and not inspector.get_unique_constraints(TABLE)
        and not any(index["unique"] for index in indexes)
        and set(columns) == expected_names
        and inspector.get_pk_constraint(TABLE)["constrained_columns"]
        == ["project_id", "digest"]
        and all(
            columns[name]["nullable"] == (name in {"payload_json", "purged_at"})
            for name in expected_names
        )
        and isinstance(columns["project_id"]["type"], sa.Integer)
        and isinstance(columns["mask_accounts"]["type"], sa.Boolean)
        and all(
            isinstance(columns[name]["type"], sa.DateTime)
            for name in (
                "read_window_start",
                "read_window_end",
                "expires_at",
                "created_at",
                "purged_at",
            )
        )
        and all(
            isinstance(columns[name]["type"], sa.String)
            for name in ("digest", "provider", "scope_id", "payload_json")
        )
        and columns["digest"]["type"].length == 64
        and columns["provider"]["type"].length == 32
        and columns["scope_id"]["type"].length == 128
        and checks
        == {
            "ck_cloud_snapshot_identity": _normalized(IDENTITY_CHECK),
            "ck_cloud_snapshot_times": _normalized(TIME_CHECK),
            "ck_cloud_snapshot_payload_state": _normalized(STATE_CHECK),
        }
        and len(foreign) == 1
        and foreign[0]["constrained_columns"] == ["project_id"]
        and foreign[0]["referred_table"] == "projects"
        and foreign[0]["referred_columns"] == ["id"]
        and foreign[0]["options"].get("ondelete", "").upper() == "CASCADE"
        and any(
            index["name"] == "ix_cloud_snapshots_project_expiry"
            and index["column_names"] == ["project_id", "expires_at"]
            and not index["unique"]
            for index in indexes
        )
        and set(triggers) == set(GUARDS)
        and all(
            _normalized(triggers[name]) == _normalized(sql)
            for name, sql in GUARDS.items()
        )
    )
    if not complete:
        raise RuntimeError(
            "Detected a partial cloud snapshot schema. Manual recovery is required."
        )
    return True


def _connection(session):
    if not isinstance(session, Session) or not session.in_transaction():
        raise CloudSnapshotSchemaError()
    try:
        if session.get_bind().dialect.name != "sqlite":
            raise CloudSnapshotSchemaError()
        connection = session.connection()
        if connection.exec_driver_sql("PRAGMA foreign_keys").scalar() != 1:
            raise CloudSnapshotSchemaError()
        if not connection.connection.driver_connection.in_transaction:
            raise CloudSnapshotSchemaError()
        return connection
    except SQLAlchemyError:
        raise CloudSnapshotSchemaStorageError() from None


def _namespace_objects(connection):
    owned = []
    shared = {"projects", "app_settings", "analysis_reports", "evidence_items"}
    for catalog in ("sqlite_master", "sqlite_temp_master"):
        rows = connection.exec_driver_sql(
            f"SELECT type,name,tbl_name,sql FROM {catalog}"
        ).mappings()
        for row in rows:
            name = row["name"].casefold()
            table = row["tbl_name"].casefold()
            reserved = (
                name.startswith((TABLE, "cloud_snapshots_", "ix_cloud_snapshots_"))
                or table == TABLE
            )
            if catalog == "sqlite_temp_master" and (reserved or name in shared):
                raise CloudSnapshotSchemaError()
            if not reserved:
                continue
            if (
                row["type"] == "index"
                and name.startswith("sqlite_autoindex_")
                and row["sql"] is None
            ):
                continue
            owned.append((row["type"], row["name"], row["tbl_name"]))
    return set(owned)


def _marker_rows(connection):
    return connection.exec_driver_sql(
        "SELECT key,value FROM app_settings WHERE lower(key)=lower(?)", (SCHEMA_KEY,)
    ).all()


def _shared_schema(connection):
    inspector = sa.inspect(connection)
    required = {
        "projects": {"id"},
        "app_settings": {"key", "value", "updated_at"},
        "analysis_reports": {"id", "project_id"},
        "evidence_items": {"analysis_id", "source_type", "source_ref"},
    }
    tables = set(inspector.get_table_names())
    for table, columns in required.items():
        if table not in tables or not columns.issubset(
            {column["name"] for column in inspector.get_columns(table)}
        ):
            raise CloudSnapshotSchemaError()


def snapshot_schema_available(session):
    """Only a wholly absent namespace is missing; every partial state is an error."""
    connection = _connection(session)
    try:
        owned = _namespace_objects(connection)
        marker = _marker_rows(connection)
        if not owned and not marker:
            return False
        expected = {
            ("table", TABLE, TABLE),
            ("index", "ix_cloud_snapshots_project_expiry", TABLE),
        }
        expected.update(
            (
                "trigger",
                name,
                "projects" if name.startswith("cloud_snapshots_project_") else TABLE,
            )
            for name in GUARDS
        )
        if owned != expected or marker != [(SCHEMA_KEY, SCHEMA_VALUE)]:
            raise CloudSnapshotSchemaError()
        _shared_schema(connection)
        if not _schema_complete(connection):
            raise CloudSnapshotSchemaError()
        return True
    except SQLAlchemyError:
        raise CloudSnapshotSchemaStorageError() from None
    except (RuntimeError, ValueError, TypeError):
        raise CloudSnapshotSchemaError() from None


def require_snapshot_schema(session):
    if not snapshot_schema_available(session):
        raise CloudSnapshotSchemaError()


def _create_schema_objects(connection):
    # A single cloud-owned Table, not CoreBase.metadata.create_all().
    CloudContextSnapshot.__table__.create(connection, checkfirst=False)
    for sql in GUARDS.values():
        connection.exec_driver_sql(sql)


def initialize_snapshot_schema(session):
    """Atomically initialize only from absence within the caller's writer UOW."""
    connection = _connection(session)
    if snapshot_schema_available(session):
        return
    try:
        _shared_schema(connection)
        session.flush()
        # Connection savepoints do not fire Session.before_commit. The checked
        # outer Session transaction and physical SQLite writer reservation stay.
        with connection.begin_nested():
            _create_schema_objects(connection)
            connection.exec_driver_sql(
                "INSERT INTO app_settings(key,value,updated_at) VALUES (?,?,CURRENT_TIMESTAMP)",
                (SCHEMA_KEY, SCHEMA_VALUE),
            )
            require_snapshot_schema(session)
    except (SQLAlchemyError, RuntimeError, ValueError, TypeError):
        session.expire_all()
        raise CloudSnapshotSchemaError() from None
