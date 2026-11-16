"""Opt-in cloud namespace is atomic and independent of released core metadata."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from cloud.schema import (
    CloudSnapshotSchemaError,
    GUARDS,
    SCHEMA_KEY,
    initialize_snapshot_schema,
    require_snapshot_schema,
    snapshot_schema_available,
)
from models.cloud_snapshots import CloudContextSnapshot, CloudSnapshotBase
from models.database import Base
from models.tables import (
    AnalysisReport,
    AppSetting,
    EvidenceItem,
    Finding,
    Project,
    ProjectWorkspace,
)


class CloudSnapshotMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "namespace.db"
        self.engine = create_engine(
            f"sqlite:///{self.path}", connect_args={"timeout": 5}
        )

        @event.listens_for(self.engine, "connect")
        def enable_fk(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(
            self.engine,
            tables=[
                item.__table__
                for item in (
                    Project,
                    ProjectWorkspace,
                    AnalysisReport,
                    Finding,
                    EvidenceItem,
                    AppSetting,
                )
            ],
        )
        self.factory = sessionmaker(self.engine)
        self.session = self.factory()
        self.session.connection().exec_driver_sql("BEGIN IMMEDIATE")

    def tearDown(self):
        self.session.rollback()
        self.session.close()
        self.engine.dispose()
        self.temp.cleanup()

    def test_absent_reads_do_not_create_any_cloud_state(self):
        from models.repositories.cloud_snapshots import (
            get_snapshot,
            purge_expired_snapshots,
        )

        self.assertFalse(snapshot_schema_available(self.session))
        self.assertIsNone(get_snapshot(self.session, project_id=1, digest="a" * 64))
        self.assertEqual(purge_expired_snapshots(self.session, project_id=1), 0)
        self.assertNotIn(
            "cloud_context_snapshots",
            inspect(self.session.connection()).get_table_names(),
        )
        self.assertIsNone(self.session.get(AppSetting, SCHEMA_KEY))
        with self.assertRaises(CloudSnapshotSchemaError):
            require_snapshot_schema(self.session)

    def test_initializer_is_idempotent_and_does_not_commit_the_session(self):
        before = set(Base.metadata.tables)
        commits = []
        event.listen(
            self.session, "before_commit", lambda _session: commits.append(True)
        )
        initialize_snapshot_schema(self.session)
        self.assertTrue(snapshot_schema_available(self.session))
        require_snapshot_schema(self.session)
        marker = self.session.get(AppSetting, SCHEMA_KEY)
        self.assertEqual(marker.value, '{"version":1}')
        initialize_snapshot_schema(self.session)
        self.assertEqual(commits, [])
        self.assertTrue(self.session.in_transaction())
        self.assertEqual(set(Base.metadata.tables), before)
        self.assertNotIn("cloud_context_snapshots", Base.metadata.tables)
        self.assertIsNot(CloudContextSnapshot.__table__.metadata, Base.metadata)
        self.assertEqual(
            set(CloudSnapshotBase.metadata.tables), {"cloud_context_snapshots"}
        )
        self.session.rollback()
        self.session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        self.assertFalse(snapshot_schema_available(self.session))

    def test_implicit_sqlalchemy_transaction_is_not_a_reserved_database_transaction(
        self,
    ):
        self.session.rollback()
        self.session.execute(text("SELECT 1"))
        self.assertTrue(self.session.in_transaction())
        self.assertFalse(
            self.session.connection().connection.driver_connection.in_transaction
        )
        with self.assertRaises(CloudSnapshotSchemaError):
            initialize_snapshot_schema(self.session)

    def test_late_marker_failure_rolls_back_all_namespace_objects_even_if_caught(self):
        self.session.execute(
            text(
                "CREATE TRIGGER reject_schema_marker BEFORE INSERT ON app_settings WHEN NEW.key='cloud_context:schema' BEGIN SELECT RAISE(ABORT,'synthetic marker failure'); END"
            )
        )
        with self.assertRaises(CloudSnapshotSchemaError):
            initialize_snapshot_schema(self.session)
        self.assertFalse(snapshot_schema_available(self.session))
        self.session.execute(text("DROP TRIGGER reject_schema_marker"))
        initialize_snapshot_schema(self.session)
        self.assertTrue(snapshot_schema_available(self.session))

    def test_creation_failure_rolls_back_before_marker_and_allows_clean_retry(self):
        import cloud.schema as schema

        create = schema._create_schema_objects

        def fail_after_creation(connection):
            create(connection)
            raise OperationalError(
                "synthetic DDL failure", None, sqlite3.OperationalError("synthetic")
            )

        with patch.object(schema, "_create_schema_objects", fail_after_creation):
            with self.assertRaises(CloudSnapshotSchemaError):
                initialize_snapshot_schema(self.session)
        self.assertFalse(snapshot_schema_available(self.session))
        initialize_snapshot_schema(self.session)
        self.assertTrue(snapshot_schema_available(self.session))

    def test_marker_only_unknown_noncanonical_or_case_variant_is_never_adopted(self):
        for key, value in [
            (SCHEMA_KEY, '{"version":1}'),
            (SCHEMA_KEY, '{"version":2}'),
            (SCHEMA_KEY, '{"version":true}'),
            (SCHEMA_KEY, '{"version": 1}'),
            ("CLOUD_CONTEXT:SCHEMA", '{"version":1}'),
        ]:
            with self.subTest(key=key, value=value):
                with self.session.begin_nested():
                    self.session.add(AppSetting(key=key, value=value))
                    self.session.flush()
                    with self.assertRaises(CloudSnapshotSchemaError):
                        initialize_snapshot_schema(self.session)
                    self.assertNotIn(
                        "cloud_context_snapshots",
                        inspect(self.session.connection()).get_table_names(),
                    )
                    self.session.execute(text("DELETE FROM app_settings"))

    def test_complete_objects_without_marker_are_not_adopted(self):
        initialize_snapshot_schema(self.session)
        self.session.execute(
            text("DELETE FROM app_settings WHERE key=:key"), {"key": SCHEMA_KEY}
        )
        for operation in (snapshot_schema_available, initialize_snapshot_schema):
            with self.assertRaises(CloudSnapshotSchemaError):
                operation(self.session)

    def test_partial_casefold_and_unknown_namespace_objects_fail_closed(self):
        for sql in (
            "CREATE TABLE CLOUD_CONTEXT_SNAPSHOTS(x)",
            "CREATE TABLE cloud_context_snapshots_extra(x)",
            "CREATE TRIGGER CLOUD_SNAPSHOTS_UNKNOWN AFTER INSERT ON projects BEGIN SELECT 1; END",
        ):
            with self.subTest(sql=sql):
                with self.session.begin_nested() as savepoint:
                    self.session.execute(text(sql))
                    with self.assertRaises(CloudSnapshotSchemaError):
                        initialize_snapshot_schema(self.session)
                    savepoint.rollback()

    def test_missing_extra_and_casefold_guard_fail_without_repair(self):
        initialize_snapshot_schema(self.session)
        mutations = [
            "DROP TRIGGER cloud_snapshots_initial_payload",
            "DROP TRIGGER cloud_snapshots_project_cleanup",
            "DROP INDEX ix_cloud_snapshots_project_expiry",
            "CREATE UNIQUE INDEX other_conflict ON cloud_context_snapshots(provider)",
            "CREATE TRIGGER extra_guard AFTER INSERT ON cloud_context_snapshots BEGIN SELECT 1; END",
        ]
        for sql in mutations:
            with self.subTest(sql=sql), self.session.begin_nested() as savepoint:
                self.session.execute(text(sql))
                with self.assertRaises(CloudSnapshotSchemaError):
                    initialize_snapshot_schema(self.session)
                savepoint.rollback()
        with self.session.begin_nested() as savepoint:
            self.session.execute(text("DROP TRIGGER cloud_snapshots_initial_payload"))
            self.session.execute(
                text(
                    GUARDS["cloud_snapshots_initial_payload"].replace(
                        "cloud_snapshots_initial_payload",
                        "CLOUD_SNAPSHOTS_INITIAL_PAYLOAD",
                    )
                )
            )
            with self.assertRaises(CloudSnapshotSchemaError):
                snapshot_schema_available(self.session)
            savepoint.rollback()

    def test_duplicate_casefold_marker_and_future_version_fail(self):
        initialize_snapshot_schema(self.session)
        with self.session.begin_nested() as savepoint:
            self.session.add(
                AppSetting(key="CLOUD_CONTEXT:SCHEMA", value='{"version":1}')
            )
            self.session.flush()
            with self.assertRaises(CloudSnapshotSchemaError):
                snapshot_schema_available(self.session)
            savepoint.rollback()
        self.session.execute(
            text("UPDATE app_settings SET value=:value WHERE key=:key"),
            {"key": SCHEMA_KEY, "value": '{"version":2}'},
        )
        with self.assertRaises(CloudSnapshotSchemaError):
            initialize_snapshot_schema(self.session)

    def test_concurrent_explicit_enable_initializes_one_namespace(self):
        self.session.rollback()
        barrier = threading.Barrier(2)

        def initialize():
            with self.factory.begin() as session:
                barrier.wait(timeout=5)
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                initialize_snapshot_schema(session)
                return snapshot_schema_available(session)

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(
                list(pool.map(lambda _: initialize(), range(2))), [True, True]
            )
        self.session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        self.assertTrue(snapshot_schema_available(self.session))
        self.assertEqual(
            self.session.scalar(
                text(
                    "SELECT count(*) FROM app_settings WHERE lower(key)='cloud_context:schema'"
                )
            ),
            1,
        )

    def test_installed_cloud_namespace_does_not_change_core_head_on_restart(self):
        self.session.rollback()
        self.engine.dispose()
        full_path = Path(self.temp.name) / "released-core.db"
        env = dict(os.environ, DATABASE_URL=f"sqlite:///{full_path}")
        script = "from models.database import init_db; init_db()"
        subprocess.run(
            [sys.executable, "-c", script], env=env, check=True, capture_output=True
        )
        with closing(sqlite3.connect(full_path)) as db:
            before = db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        engine = create_engine(f"sqlite:///{full_path}")

        @event.listens_for(engine, "connect")
        def enable_fk(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        with Session(engine) as session, session.begin():
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            initialize_snapshot_schema(session)
        engine.dispose()
        subprocess.run(
            [sys.executable, "-c", script], env=env, check=True, capture_output=True
        )
        with closing(sqlite3.connect(full_path)) as db:
            self.assertEqual(
                db.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                before,
            )
            self.assertEqual(before, "042_add_receiver_recovery")
            self.assertIsNotNone(
                db.execute(
                    "SELECT name FROM sqlite_master WHERE name='cloud_context_snapshots'"
                ).fetchone()
            )
        self.assertNotIn("cloud_context_snapshots", Base.metadata.tables)
