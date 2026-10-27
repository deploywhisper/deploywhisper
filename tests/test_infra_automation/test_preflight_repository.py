"""Immutable screened manifest and relational provenance regression proofs."""

from __future__ import annotations

from datetime import timedelta
from importlib import import_module

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from infra_automation.lifecycle import LifecycleError
from infra_automation.state import AuditActor
from models.repositories import infra_automation_reports as reports
from services import infra_automation_engine_support as engine_support
from services import infra_automation_support as support
from services import project_service as auth
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation import test_engine_repository as engine_tests


class PreflightRepositoryTests(LifecycleCase):
    publish_fixture = engine_tests.EngineRepositoryTests.publish_fixture
    enable = engine_tests.EngineRepositoryTests.enable
    export = engine_tests.EngineRepositoryTests.export
    admit = engine_tests.EngineRepositoryTests.admit

    def setUp(self):
        super().setUp()
        self.enable()
        self.snapshot = self.export(self.publish_fixture())
        self.actor = AuditActor("human-a", "human", "admin")
        self.request = dict(
            snapshot=self.snapshot,
            request_digest=support.digest(b"request"),
            key_digest=support.digest(b"key"),
            requested_by="human-a",
            deadline_at=self.now + timedelta(minutes=10),
            audit_actor=self.actor,
            reason="synthetic",
            now=self.now,
        )
        with self.credentials(), auth.authorized_session() as db:
            grant = support.scope(db, 100, 100, "automation.request", mutation=True)
            engine_support.ensure_engine_actor(db, grant)
        self.run = self.admit()
        self.files = [("main.tf", b'resource "aws_s3_bucket" "test" {}')]
        with self.engine.begin() as db:
            for name, body in import_module(
                "migrations.versions.033_add_infra_preflight"
            ).GUARDS.items():
                db.exec_driver_sql(f"CREATE TRIGGER {name} {body}")

    def create(self, files=None, step_id="upload"):
        with self.credentials(), auth.authorized_session(self.factory) as db:
            return reports.create_manifest(
                db,
                self.run,
                step_id,
                self.files if files is None else files,
                now=self.now,
            )

    def test_manifest_roundtrip_digest_idempotency_and_changed_replay(self):
        first = self.create()
        self.assertEqual(self.create().id, first.id)
        self.assertEqual(first.digest, support.digest(first.artifacts_bytes))
        with auth.authorized_session(self.factory) as db:
            row = reports.get_manifest(db, first.id)
            self.assertEqual(reports.manifest_files(row), self.files)
        with self.assertRaises(LifecycleError):
            self.create([("other.tf", self.files[0][1])])

    def test_reject_sensitive_and_wrong_step_without_writes(self):
        for files, step in (
            ([("state.tfstate", b"synthetic")], "upload"),
            (self.files, "missing"),
        ):
            with self.subTest(step=step), self.assertRaises(LifecycleError):
                self.create(files, step)
        from models.tables import InfraAutomationArtifactManifest

        with self.factory() as db:
            self.assertEqual(
                list(db.scalars(select(InfraAutomationArtifactManifest))), []
            )

    def test_manifest_immutable_under_sql_update_delete_and_replace(self):
        row = self.create()
        for statement in (
            "UPDATE infra_automation_artifact_manifests SET digest='changed' WHERE id=:id",
            "DELETE FROM infra_automation_artifact_manifests WHERE id=:id",
            "INSERT OR REPLACE INTO infra_automation_artifact_manifests SELECT * FROM infra_automation_artifact_manifests WHERE id=:id",
        ):
            with (
                self.subTest(statement=statement),
                self.assertRaises(IntegrityError),
                self.engine.begin() as db,
            ):
                from sqlalchemy import text

                db.execute(text(statement), {"id": row.id})

    def test_contract_keeps_uploaded_provenance_separate_and_closed(self):
        from pydantic import ValidationError
        from infra_automation.preflight_contracts import UploadedProvenance

        value = UploadedProvenance()
        self.assertEqual(value.version, 1)
        self.assertEqual(value.repository_source, "unavailable")
        with self.assertRaises(ValidationError):
            UploadedProvenance(commit_sha="a" * 40)

    def _admit_definition(self, definition, inputs=None, registry=None):
        ids = self.publish_fixture(definition)
        self.snapshot = self.export(
            ids, inputs or {"note": "original"}, registry_contract=registry
        )
        self.request.update(
            snapshot=self.snapshot, key_digest=support.digest(ids[0].encode())
        )
        self.run = self.admit()
        return self.run

    def _start_step(self, step_id):
        from infra_automation import claims
        from models.repositories import infra_automation_runs as runs

        with auth.authorized_session(self.factory) as db:
            if not hasattr(self, "owner"):
                self.owner = claims.acquire_coordinator(
                    db, project_id=100, workspace_id=100, now=self.now
                )
            run = runs.get_run(db, self.run.id)
            if run.state == "queued":
                claims.start_run(
                    db,
                    self.owner,
                    run_id=run.id,
                    expected_version=run.version,
                    now=self.now,
                )
            attempt = claims.prepare_attempt(
                db,
                self.owner,
                run_id=run.id,
                step_id=step_id,
                handler_id="synthetic",
                handler_version="1",
                retry_safe=True,
                now=self.now,
            )
            handle = claims.claim_attempt(
                db,
                self.owner,
                attempt_id=attempt.id,
                expected_version=attempt.version,
                now=self.now,
            )
            current = runs.get_attempt(db, handle.attempt_id)
            claims.start_attempt(
                db, handle, expected_version=current.version, now=self.now
            )
            return handle

    def test_synthetic_collection_persists_verified_envelope_and_rejects_tampering(
        self,
    ):
        from dataclasses import replace
        from infra_automation.contracts import ProfileContract, RegistryContract
        from infra_automation.preflight_contracts import SyntheticCollectionEnvelope

        profile = support.digest(b"synthetic-profile")
        definition = {
            "workflow_version": 2,
            "project_id": "100",
            "workspace_id": "100",
            "environment": "dev",
            "inputs": {"note": {"type": "string", "max_length": 100}},
            "steps": [
                {
                    "id": "collect",
                    "kind": "admitted_collection",
                    "depends_on": [],
                    "source": {
                        "kind": "collected",
                        "repository_id": "synthetic-repository",
                        "commit_sha": "b" * 40,
                        "profile_digest": profile,
                    },
                }
            ],
        }
        registry = RegistryContract(
            profiles=(
                ProfileContract(
                    digest=profile,
                    tool="opentofu",
                    authorization_kinds=("advisory_request",),
                ),
            )
        )
        self._admit_definition(definition, registry=registry)
        handle = self._start_step("collect")
        envelope = SyntheticCollectionEnvelope(
            project_id=100,
            workspace_id=100,
            run_id=self.run.id,
            step_id="collect",
            attempt_id=handle.attempt_id,
            fence=handle.fence,
            collector_id="synthetic-collector",
            repository_id="synthetic-repository",
            commit_sha="b" * 40,
            profile_digest=profile,
            command_digest=support.digest(b"command"),
            argv_digest=support.digest(b"argv"),
            raw_local_digest=support.digest(b"local-only"),
            sanitized_digest=support.digest(reports._manifest_payload(self.files)),
            exit_code=0,
            collected_at=support.utc(self.now),
            source_deadline=support.utc(self.now + timedelta(minutes=2)),
        )
        expected = dict(
            expected_command_digest=envelope.command_digest,
            expected_argv_digest=envelope.argv_digest,
            expected_collector_id=envelope.collector_id,
            now=self.now,
        )
        with auth.authorized_session(self.factory) as db:
            row = reports.create_collected_manifest(
                db, handle, envelope, self.files, **expected
            )
            self.assertEqual(
                row.collection_digest, support.digest(row.collection_bytes)
            )
            self.assertEqual(
                SyntheticCollectionEnvelope.model_validate_json(row.collection_bytes),
                envelope,
            )
        for key, value in (
            ("sanitized_digest", support.digest(b"tampered")),
            ("attempt_id", "stale"),
            ("fence", handle.fence + 1),
            ("project_id", 200),
            ("collector_id", "other"),
            ("commit_sha", "a" * 40),
            ("command_digest", support.digest(b"different")),
            ("source_deadline", support.utc(self.now - timedelta(seconds=1))),
        ):
            with (
                self.subTest(key=key),
                self.assertRaises(LifecycleError),
                auth.authorized_session(self.factory) as db,
            ):
                reports.create_collected_manifest(
                    db,
                    handle,
                    envelope.model_copy(update={key: value}),
                    self.files,
                    **expected,
                )
        with (
            self.assertRaises(LifecycleError),
            auth.authorized_session(self.factory) as db,
        ):
            reports.create_collected_manifest(
                db,
                replace(handle, owner_secret="a" * 64),
                envelope,
                self.files,
                **expected,
            )

    def test_link_requires_current_analysis_capability_and_locks_report(self):
        from dataclasses import replace
        from infra_automation import claims
        from infra_automation.preflight_contracts import UploadedProvenance
        from infra_automation.state import OutputReference
        from models.repositories import infra_automation_runs as runs
        from models.tables import AnalysisReport

        definition = {
            "workflow_version": 2,
            "project_id": "100",
            "workspace_id": "100",
            "environment": "dev",
            "inputs": {"note": {"type": "string", "max_length": 100}},
            "steps": [
                {
                    "id": "upload",
                    "kind": "uploaded_intake",
                    "depends_on": [],
                    "source": {"kind": "uploaded"},
                },
                {
                    "id": "analysis",
                    "kind": "shared_analysis",
                    "depends_on": ["upload"],
                    "artifact": {
                        "ref": "step",
                        "step_id": "upload",
                        "output": "screened_artifacts",
                    },
                },
            ],
        }
        self._admit_definition(definition)
        manifest = self.create()
        upload = self._start_step("upload")
        with auth.authorized_session(self.factory) as db:
            reference = OutputReference(
                kind="screened_artifacts", reference=manifest.id, digest=manifest.digest
            )
            row = runs.get_attempt(db, upload.attempt_id)
            row = claims.register_upload(
                db,
                upload,
                expected_version=row.version,
                reference=reference,
                now=self.now,
            )
            row = claims.commit_output(
                db, upload, expected_version=row.version, output=reference, now=self.now
            )
            claims.complete_attempt(
                db,
                upload,
                expected_version=row.version,
                state="succeeded",
                now=self.now,
            )
        analysis = self._start_step("analysis")
        with auth.authorized_session(self.factory) as db:
            report = AnalysisReport(
                project_id=100,
                workspace_id=100,
                risk_score=0,
                severity="low",
                recommendation="go",
                top_risk="Synthetic report",
                parse_summary="Synthetic",
                narrative_opening="",
                narrative_explanation="",
            )
            db.add(report)
            db.flush()
            report_id = report.id
        for changed in (replace(analysis, fence=analysis.fence + 1), upload):
            with (
                self.assertRaises(LifecycleError),
                auth.authorized_session(self.factory) as db,
            ):
                reports.create_link(
                    db,
                    changed,
                    manifest.id,
                    report_id,
                    UploadedProvenance().model_dump(),
                    now=self.now,
                )
        with auth.authorized_session(self.factory) as db:
            row = reports.create_link(
                db,
                analysis,
                manifest.id,
                report_id,
                UploadedProvenance().model_dump(),
                now=self.now,
            )
            self.assertEqual(
                reports.link_view(row)["report_url"], f"/reports/{report_id}"
            )
            self.assertFalse(reports.link_view(row)["approval_eligible"])
        for statement in (
            "UPDATE analysis_reports SET risk_score=99 WHERE id=:id",
            "DELETE FROM analysis_reports WHERE id=:id",
            "INSERT OR REPLACE INTO analysis_reports SELECT * FROM analysis_reports WHERE id=:id",
            "UPDATE infra_automation_report_links SET digest='changed' WHERE report_id=:id",
            "DELETE FROM infra_automation_report_links WHERE report_id=:id",
        ):
            with (
                self.subTest(statement=statement),
                self.assertRaises(IntegrityError),
                self.engine.begin() as db,
            ):
                from sqlalchemy import text

                db.execute(text(statement), {"id": report_id})

    def test_migration_contract_matches_metadata_and_detects_missing_guard(self):
        from sqlalchemy import inspect
        from unittest.mock import patch
        from models import database

        with self.engine.begin() as db:
            tables = set(inspect(db).get_table_names())
            self.assertTrue(
                database._infra_automation_schema_complete(
                    db, tables, "033_add_infra_preflight"
                )
            )
            db.exec_driver_sql("DROP TRIGGER infra_preflight_report_scope")
            with self.assertRaisesRegex(
                RuntimeError, "partial infra automation schema"
            ):
                database._infra_automation_schema_complete(
                    db, tables, "033_add_infra_preflight"
                )
        # Verified migration-history compatibility is a separate startup gate.
        with patch.object(database, "engine", self.engine):
            with self.assertRaisesRegex(
                RuntimeError, "partial infra automation schema"
            ):
                database._bootstrap_brownfield_revision()

    def test_manifest_quota_failure_is_atomic_and_reads_recompute_digest(self):
        from types import SimpleNamespace
        from infra_automation.state import EngineBounds
        from models.repositories import infra_automation_runs as runs

        with self.credentials(), auth.authorized_session(self.factory) as db:
            before = runs.get_run(db, self.run.id).retained_bytes
        with (
            self.assertRaises(LifecycleError),
            self.credentials(),
            auth.authorized_session(self.factory) as db,
        ):
            reports.create_manifest(
                db,
                self.run,
                "upload",
                self.files,
                now=self.now,
                bounds=EngineBounds(project_bytes=1),
            )
        with auth.authorized_session(self.factory) as db:
            self.assertIsNone(reports.get_manifest_for_step(db, self.run.id, "upload"))
            self.assertEqual(runs.get_run(db, self.run.id).retained_bytes, before)
        row = self.create()
        with self.assertRaises(LifecycleError):
            reports.manifest_files(
                SimpleNamespace(
                    artifacts_bytes=row.artifacts_bytes + b" ",
                    digest=row.digest,
                    collection_bytes=None,
                    collection_digest=None,
                )
            )

    def test_real_upgrade_from_engine_preserves_history_and_bootstraps(self):
        import os
        import sys
        from pathlib import Path
        import subprocess
        from unittest.mock import patch
        from sqlalchemy import create_engine, inspect
        from models import database

        url = "sqlite:///" + str(Path(self.temp.name) / "migration.db")
        environment = {**os.environ, "DATABASE_URL": url}
        for target in ("032_add_infra_automation_engine", "head"):
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", target],
                cwd=Path(__file__).resolve().parents[2],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            engine = create_engine(url)
            try:
                with patch.object(database, "engine", engine):
                    database._bootstrap_brownfield_revision()
                with engine.connect() as db:
                    revision = db.exec_driver_sql(
                        "SELECT version_num FROM alembic_version"
                    ).scalar()
                    self.assertEqual(
                        revision,
                        target if target != "head" else "033_add_infra_preflight",
                    )
                    if target == "head":
                        self.assertTrue(
                            database._infra_automation_schema_complete(
                                db,
                                set(inspect(db).get_table_names()),
                                "033_add_infra_preflight",
                            )
                        )
            finally:
                engine.dispose()

    def test_child_sql_guards_reject_reparenting_and_conflicting_replace(self):
        """Exercise real guards with SQLite's default nonrecursive REPLACE behavior.

        The minimal SQL tables isolate trigger predicates from foreign-key errors;
        the actual ORM primary/unique identities are asserted before the probe.
        """
        import sqlite3
        from contextlib import closing
        from models.database import Base
        from sqlalchemy import UniqueConstraint

        guards = import_module("migrations.versions.033_add_infra_preflight").GUARDS
        for table, primary_key in (
            ("findings", "finding_id"),
            ("evidence_items", "evidence_id"),
            ("risk_assessments", "analysis_id"),
            ("context_snapshots", "analysis_id"),
        ):
            metadata = Base.metadata.tables[table]
            self.assertEqual(
                tuple(column.name for column in metadata.primary_key), (primary_key,)
            )
            # Findings' composite UNIQUE includes its globally unique primary key;
            # no other conflict identity can implicitly delete a protected child.
            self.assertTrue(
                all(
                    primary_key in {column.name for column in constraint.columns}
                    for constraint in metadata.constraints
                    if isinstance(constraint, UniqueConstraint)
                )
            )
            with self.subTest(table=table), closing(sqlite3.connect(":memory:")) as db:
                db.execute("PRAGMA recursive_triggers=0")
                self.assertEqual(
                    db.execute("PRAGMA recursive_triggers").fetchone()[0], 0
                )
                db.execute(
                    "CREATE TABLE infra_automation_report_links (report_id INTEGER)"
                )
                db.execute("INSERT INTO infra_automation_report_links VALUES (1)")
                if primary_key == "analysis_id":
                    db.execute(
                        f"CREATE TABLE {table} (analysis_id INTEGER PRIMARY KEY, payload TEXT)"
                    )
                    db.execute(
                        f"INSERT INTO {table} VALUES (1, 'protected'), (2, 'unlinked')"
                    )
                    attacks = [
                        f"INSERT OR REPLACE INTO {table} VALUES (1, 'changed')",
                        f"UPDATE {table} SET analysis_id=1 WHERE analysis_id=2",
                        f"UPDATE OR REPLACE {table} SET analysis_id=1 WHERE analysis_id=2",
                    ]
                else:
                    db.execute(
                        f"CREATE TABLE {table} ({primary_key} TEXT PRIMARY KEY, analysis_id INTEGER, payload TEXT)"
                    )
                    db.execute(
                        f"INSERT INTO {table} VALUES ('protected', 1, 'protected'), ('unlinked', 2, 'unlinked')"
                    )
                    attacks = [
                        f"INSERT OR REPLACE INTO {table} VALUES ('protected', 2, 'changed')",
                        f"UPDATE {table} SET analysis_id=1 WHERE {primary_key}='unlinked'",
                        f"UPDATE OR REPLACE {table} SET {primary_key}='protected' WHERE {primary_key}='unlinked'",
                        f"UPDATE {table} SET analysis_id=2 WHERE {primary_key}='protected'",
                    ]
                for operation in ("insert", "update", "delete"):
                    name = f"infra_preflight_{table}_no_{operation}"
                    db.execute(f"CREATE TRIGGER {name} {guards[name]}")
                before = db.execute(
                    f"SELECT * FROM {table} ORDER BY {primary_key}"
                ).fetchall()
                for sql in attacks:
                    with (
                        self.subTest(sql=sql),
                        self.assertRaisesRegex(
                            sqlite3.IntegrityError, "Immutable linked report"
                        ),
                    ):
                        db.execute(sql)
                    self.assertEqual(
                        db.execute(
                            f"SELECT * FROM {table} ORDER BY {primary_key}"
                        ).fetchall(),
                        before,
                    )
                allowed_key = 2 if primary_key == "analysis_id" else "unlinked"
                self.assertEqual(
                    db.execute(
                        f"UPDATE {table} SET payload='updated' WHERE {primary_key}=?",
                        (allowed_key,),
                    ).rowcount,
                    1,
                )
