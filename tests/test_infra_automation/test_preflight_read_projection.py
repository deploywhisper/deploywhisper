"""Authorized readback of durable missing, failed and stale preflight evidence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from sqlalchemy import func, select

from infra_automation import claims
from models.repositories import infra_automation_runs as runs
from models.tables import AnalysisReport
from services import project_service as auth
from services import infra_automation_engine_service as engine
from services import infra_automation_preflight as service
from tests.test_infra_automation import test_preflight_service as fixtures


class PreflightReadProjectionTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.PreflightServiceTests(methodName="runTest")
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()

    def read(self, run_id, **kwargs):
        with self.case.credentials():
            return service.list_run_reports(run_id, **kwargs)

    def test_pending_projection_is_typed_and_based_on_committed_facts(self):
        from api.schemas import AutomationPreflightLinksResponse, build_meta

        run = self.case.admit()
        data = self.read(run["id"])
        status = data["evidence_status"]
        self.assertEqual(status["version"], 1)
        self.assertEqual(status["status"], "pending")
        self.assertTrue(status["manifest_present"])
        self.assertFalse(status["report_available"])
        self.assertFalse(status["approval_eligible"])
        self.assertEqual(status["run_version"], run["version"])
        self.assertIn("Wait for mandatory evidence", " ".join(status["context_todos"]))
        AutomationPreflightLinksResponse.model_validate(
            {"data": data, "meta": build_meta(correlation_id="synthetic")}
        )

    def test_actual_analysis_failure_retains_specific_recovery_after_parent_cleanup(
        self,
    ):
        from services import analysis_service

        run = self.case.admit()
        owners, handles = [], []
        original_acquire = claims.acquire_coordinator

        def acquire(*args, **kwargs):
            owner = original_acquire(*args, **kwargs)
            owners.append(owner)
            return owner

        with (
            patch.object(claims, "acquire_coordinator", side_effect=acquire),
            patch.object(
                analysis_service,
                "build_analysis_artifacts",
                side_effect=RuntimeError("synthetic analysis failure"),
            ),
        ):
            with self.assertRaises(RuntimeError):
                self.case.execute(run, before_analysis=handles.append)
        with auth.authorized_session(self.case.factory) as db:
            attempt = runs.get_attempt(db, handles[0].attempt_id)
            claims.complete_attempt(
                db, handles[0], expected_version=attempt.version, state="failed"
            )
            row = runs.get_run(db, run["id"])
            claims.stop_run(
                db,
                owners[0],
                run_id=row.id,
                expected_version=row.version,
                state="failed",
            )
        data = self.read(run["id"])
        self.assertEqual(data["items"], [])
        status = data["evidence_status"]
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["run_state"], "failed")
        self.assertEqual(status["attempt_state"], "failed")
        self.assertIn("Analysis did not complete", " ".join(status["limitations"]))
        self.assertIn("submit a new analysis", " ".join(status["context_todos"]))
        with self.case.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(AnalysisReport)), 0
            )

    def test_terminal_missing_manifest_read_needs_no_worker_authority(self):
        with self.case.credentials():
            run = engine.request_run(
                self.case.request.run, registry=service.PREFLIGHT_REGISTRY
            )
        with auth.authorized_session(self.case.factory) as db:
            owner = claims.acquire_coordinator(db, project_id=100, workspace_id=100)
            row = runs.get_run(db, run["id"])
            claims.stop_run(
                db, owner, run_id=row.id, expected_version=row.version, state="failed"
            )
        status = self.read(run["id"])["evidence_status"]
        self.assertEqual(status["status"], "missing")
        self.assertFalse(status["manifest_present"])
        self.assertIn(
            "Mandatory uploaded evidence is missing", " ".join(status["limitations"])
        )
        self.assertIn(
            "Resubmit the mandatory supported artifacts",
            " ".join(status["context_todos"]),
        )

    def test_freshness_uses_evidence_ttl_instead_of_execution_timeout(self):
        request = self.case.request.model_copy(
            update={
                "run": self.case.request.run.model_copy(
                    update={"total_timeout_seconds": 60}
                )
            }
        )
        run = self.case.admit(request)
        link = self.case.execute(run)
        with self.case.factory() as db:
            document = engine._document(runs.get_run(db, run["id"]))
        captured = datetime.strptime(
            document.captured_at, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        fresh = self.read(run["id"], now=captured + timedelta(seconds=120))
        self.assertEqual(fresh["evidence_status"]["status"], "available")
        deadline = captured + timedelta(seconds=document.policy.evidence_ttl_seconds)
        stale = self.read(run["id"], now=deadline)
        self.assertEqual(stale["evidence_status"]["status"], "stale")
        self.assertEqual(stale["items"][0]["report_id"], link["report_id"])
        self.assertIn(
            "Collect current evidence",
            " ".join(stale["evidence_status"]["context_todos"]),
        )
        self.assertFalse(stale["evidence_status"]["approval_eligible"])
