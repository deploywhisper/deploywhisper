"""Real SQLite commit compensation and spawned committed-output recovery proofs."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError

import config
from infra_automation import claims
from infra_automation.local_workers import SpawnProcessWorkers, WorkerInput
from infra_automation.storage import configure_engine_sqlite
from models.repositories import infra_automation_runs as runs
from models.tables import AnalysisReport, InfraAutomationReportLink
from services import infra_automation_preflight as preflight
from services import project_service as auth
from services.analysis_service import AnalysisPersistenceError, analyze_uploaded_files
from services.artifact_snapshot_service import load_report_artifact
from tests.test_infra_automation import test_preflight_service as fixtures


class _SimulatedCrash(Exception):
    pass


class PreflightAtomicRecoveryTests(unittest.TestCase):
    def setUp(self):
        # Compose the fixture without inheriting or recollecting its test methods.
        self.fixture = fixtures.PreflightServiceTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.enterContext(
            patch(
                "llm.narrator.settings",
                replace(config.settings, narrator_enabled=False),
            )
        )

    def counts(self):
        with self.fixture.factory() as db:
            return tuple(
                db.scalar(select(func.count()).select_from(model))
                for model in (AnalysisReport, InfraAutomationReportLink)
            )

    def test_real_commit_failure_compensates_snapshots_before_report_id_reuse(self):
        fixture = self.fixture
        with fixture.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE commit_failure_probe ("
                "project_id INTEGER REFERENCES projects(id) "
                "DEFERRABLE INITIALLY DEFERRED)"
            )
        flushed_ids = []
        commit_failures = []

        def observe_failure(context):
            if "FOREIGN KEY constraint failed" in str(context.original_exception):
                driver = context.connection.connection.driver_connection
                commit_failures.append(
                    (
                        driver.in_transaction,
                        driver.execute(
                            "SELECT count(*) FROM infra_automation_attempts "
                            "WHERE step_id='analysis' AND output_json IS NOT NULL"
                        ).fetchone()[0],
                    )
                )

        event.listen(fixture.engine, "handle_error", observe_failure)
        self.addCleanup(event.remove, fixture.engine, "handle_error", observe_failure)
        real_create_link = preflight.reports.create_link

        def invalidate_at_commit(session, *args, **kwargs):
            link = real_create_link(session, *args, **kwargs)
            flushed_ids.append(link.report_id)
            self.assertTrue(
                (Path(fixture.temp.name) / "artifacts" / str(link.report_id)).is_dir()
            )
            # This succeeds now; SQLite rejects the actual outer COMMIT later.
            session.connection().exec_driver_sql(
                "INSERT INTO commit_failure_probe(project_id) VALUES (-1)"
            )
            self.assertEqual(
                session.scalar(
                    select(func.count()).select_from(InfraAutomationReportLink)
                ),
                1,
            )
            return link

        run = fixture.admit()
        with patch.object(
            preflight.reports, "create_link", side_effect=invalidate_at_commit
        ):
            with self.assertRaises(AnalysisPersistenceError) as caught:
                fixture.execute(run)
        self.assertIsInstance(caught.exception.__cause__, IntegrityError)
        self.assertEqual(commit_failures, [(True, 1)])
        self.assertEqual(len(flushed_ids), 1)
        self.assertEqual(self.counts(), (0, 0))
        with fixture.factory() as db:
            analysis = next(
                attempt
                for attempt in runs.list_attempts(db, run_id=run["id"])
                if attempt.step_id == "analysis"
            )
            self.assertIsNone(analysis.output_json)
            self.assertEqual(analysis.uploads_json, "[]")
        report_dir = Path(fixture.temp.name) / "artifacts" / str(flushed_ids[0])
        self.assertFalse(report_dir.exists())
        replacement_name = "replacement.tf"
        with fixture.credentials(), auth.authorized_session(fixture.factory):
            replacement = analyze_uploaded_files(
                [(replacement_name, b'resource "aws_s3_bucket" "replacement" {}')],
                project_id=100,
                workspace_id=100,
            ).persisted_report
            self.assertEqual(replacement["id"], flushed_ids[0])
            self.assertIsNone(load_report_artifact(replacement["id"], "main.tf"))
            snapshot = load_report_artifact(replacement["id"], replacement_name)
            self.assertIsNotNone(snapshot)
            self.assertIn("replacement", snapshot.content)
        self.assertEqual(self.counts(), (1, 0))

    def test_spawned_retry_adopts_committed_report_without_reexecuting_analysis(self):
        fixture = self.fixture
        configure_engine_sqlite(fixture.engine)
        owners, handles = [], []
        real_acquire = claims.acquire_coordinator
        real_complete = claims.complete_attempt

        def capture_owner(*args, **kwargs):
            owner = real_acquire(*args, **kwargs)
            owners.append(owner)
            return owner

        def crash_before_completion(session, handle, **kwargs):
            if handle.step_id == "analysis":
                raise _SimulatedCrash()
            return real_complete(session, handle, **kwargs)

        run = fixture.admit()
        with (
            patch.object(claims, "acquire_coordinator", side_effect=capture_owner),
            patch.object(
                claims, "complete_attempt", side_effect=crash_before_completion
            ),
            self.assertRaises(_SimulatedCrash),
        ):
            fixture.execute(run, before_analysis=handles.append)
        self.assertEqual(self.counts(), (1, 1))
        with auth.authorized_session(fixture.factory) as db:
            prior = runs.get_attempt(db, handles[0].attempt_id)
            committed_output = prior.output_json
            self.assertIsNotNone(committed_output)
            claims.complete_attempt(
                db, handles[0], expected_version=prior.version, state="failed"
            )
            retry = claims.prepare_retry(
                db,
                owners[0],
                previous_attempt_id=prior.id,
                expected_version=prior.version,
            )
            self.assertIsNotNone(retry)
            retry_handle = claims.claim_attempt(
                db, owners[0], attempt_id=retry.id, expected_version=retry.version
            )
            row = runs.get_run(db, run["id"])
            upload = next(
                attempt
                for attempt in runs.list_attempts(db, run_id=row.id)
                if attempt.step_id == "upload" and attempt.state == "succeeded"
            )
            value = WorkerInput(
                row.snapshot_bytes,
                "analysis",
                (("upload", upload.output_json.encode()),),
            )
        workers = SpawnProcessWorkers(str(fixture.engine.url), max_workers=1)
        self.addCleanup(workers.close)
        workers.submit(
            retry_handle, preflight.PREFLIGHT_REGISTRY.get("shared_analysis"), value
        )
        deadline = time.monotonic() + 20
        completions = ()
        while time.monotonic() < deadline:
            workers.heartbeat(time.monotonic() + 2)
            completions = workers.poll()
            if completions:
                break
            time.sleep(0.05)
        self.assertEqual(len(completions), 1)
        self.assertFalse(completions[0].crashed)
        self.assertEqual(completions[0].result.outcome, "local_success")
        self.assertEqual(self.counts(), (1, 1))
        with fixture.factory() as db:
            adopted = runs.get_attempt(db, retry_handle.attempt_id)
            self.assertEqual(adopted.output_json, committed_output)
            self.assertEqual(
                completions[0].result.output.model_dump(), json.loads(committed_output)
            )
            link = db.scalar(select(InfraAutomationReportLink))
            self.assertEqual(link.attempt_id, handles[0].attempt_id)
