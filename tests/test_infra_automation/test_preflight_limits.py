"""Bounded summaries and exact local snapshot quota accounting."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select

from models.repositories import infra_automation_reports as reports
from models.tables import AnalysisReport, InfraAutomationReportLink
from services import project_service as auth
from services import artifact_snapshot_service as snapshots
from tests.test_infra_automation import test_preflight_service as fixtures


class PreflightLimitsTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.PreflightServiceTests(methodName="runTest")
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.addCleanup(self.case.tearDown)

    def __getattr__(self, name):
        case = self.__dict__.get("case")
        if case is None:
            raise AttributeError(name)
        return getattr(case, name)

    def test_many_warnings_and_todos_keep_bounded_recoverable_summary(self):
        from services import analysis_service
        from services.report_service import fetch_analysis_report

        original = analysis_service.build_analysis_artifacts
        warnings = [f"Warning {i}: " + "w" * 400 for i in range(70)]
        todos = [f"Todo {i}: " + "t" * 400 for i in range(70)]

        def build(*args, **kwargs):
            artifacts = original(*args, **kwargs)
            artifacts.assessment.warnings.extend(warnings)
            artifacts.assessment.context_completeness.context_todos.extend(todos)
            return artifacts

        with patch.object(
            analysis_service, "build_analysis_artifacts", side_effect=build
        ):
            link = self.execute(self.admit())
        with self.credentials():
            report = fetch_analysis_report(link["report_id"])
        self.assertTrue(set(warnings) <= set(report["warnings"]))
        self.assertTrue(
            set(todos) <= set(report["context_completeness"]["context_todos"])
        )
        self.assertLessEqual(len(link["limitations"]), 50)
        self.assertLessEqual(len(link["context_todos"]), 50)
        self.assertIn("Repository and immutable commit", link["limitations"][0])
        self.assertIn("Verify repository source", link["context_todos"][0])
        for key in ("limitations", "context_todos"):
            self.assertIn("omitted:", link[key][-1])
        self.assertLessEqual(len(json.dumps(link, ensure_ascii=False).encode()), 16384)

    def test_final_id_is_included_in_summary_byte_limit(self):
        original = reports.create_link

        def create(*args, **kwargs):
            from infra_automation.preflight_contracts import UploadedProvenance

            provenance = UploadedProvenance()
            handle, manifest_id, report_id = args[1:4]
            payload = {
                "run_id": handle.run_id,
                "attempt_id": handle.attempt_id,
                "manifest_id": manifest_id,
                "report_id": report_id,
                "report_url": f"/reports/{report_id}",
                "provenance": provenance.model_dump(),
                "limitations": [provenance.limitation, ""],
                "context_todos": [
                    "Verify repository source and collect current complete evidence before any handoff decision."
                ],
                "approval_eligible": False,
            }
            length = 16384 - len(json.dumps(payload, ensure_ascii=False).encode())
            kwargs.update(limitations=["x" * length], context_todos=[])
            return original(*args, **kwargs)

        with patch.object(reports, "create_link", side_effect=create):
            link = self.execute(self.admit())
        self.assertLessEqual(len(json.dumps(link, ensure_ascii=False).encode()), 16384)
        self.assertTrue(link["id"])

    def test_snapshot_payload_and_sidecar_are_charged_exactly_once(self):
        charges = []
        original = reports.claims._charge

        def charge(session, run, amount, *args):
            charges.append(amount)
            return original(session, run, amount, *args)

        with patch.object(reports.claims, "_charge", side_effect=charge):
            link = self.execute(self.admit())
        directory = Path(self.temp.name) / "artifacts" / str(link["report_id"])
        snapshot_bytes = sum(path.stat().st_size for path in directory.iterdir())
        self.assertGreater(snapshot_bytes, len(fixtures.FILES[0][1]))
        with self.credentials(), auth.authorized_session(self.factory) as db:
            from services.report_service import _serialize_report

            row = db.scalar(select(InfraAutomationReportLink))
            report = db.get(AnalysisReport, link["report_id"])
            expected = (
                len(row.provenance_bytes)
                + len(
                    reports.support.canonical(
                        _serialize_report(report, include_evidence=True)
                    )
                )
                + snapshot_bytes
            )
            self.assertIn(expected, charges)
            self.assertEqual(
                snapshots.retained_report_artifact_bytes(db, report.id), snapshot_bytes
            )

    def test_snapshot_counter_rejects_symlink(self):
        link = self.execute(self.admit())
        directory = Path(self.temp.name) / "artifacts" / str(link["report_id"])
        (directory / "escape.txt").symlink_to(Path(self.temp.name) / "outside.txt")
        with self.credentials(), auth.authorized_session(self.factory) as db:
            with self.assertRaises(ValueError):
                snapshots.retained_report_artifact_bytes(db, link["report_id"])

    def test_snapshot_charge_quota_failure_rolls_back_report_and_files(self):
        from infra_automation.state import EngineBounds
        from services.analysis_service import AnalysisPersistenceError

        original = reports.claims._charge
        checked = []

        def charge(session, run, amount, now, bounds=None):
            directory = Path(self.temp.name) / "artifacts" / "1"
            if directory.exists():
                # All earlier charges fit; this final charge exceeds by one
                # byte only when the snapshot and sidecar copy are included.
                copies = sum(path.stat().st_size for path in directory.iterdir())
                checked.append(copies)
                bounds = EngineBounds(
                    project_bytes=run.retained_bytes + amount - copies
                )
            return original(session, run, amount, now, bounds)

        with patch.object(reports.claims, "_charge", side_effect=charge):
            with self.assertRaises(AnalysisPersistenceError):
                self.execute(self.admit())
        self.assertTrue(checked)
        with self.factory() as db:
            self.assertIsNone(db.scalar(select(AnalysisReport)))
            self.assertIsNone(db.scalar(select(InfraAutomationReportLink)))
        self.assertFalse((Path(self.temp.name) / "artifacts" / "1").exists())

    def test_snapshot_counter_absent_and_replayed_link_does_not_charge(self):
        original = reports.create_link

        def replay(*args, **kwargs):
            first = original(*args, **kwargs)
            with patch.object(
                reports.claims, "_charge", side_effect=AssertionError("recharged")
            ):
                second = original(*args, **kwargs)
            self.assertEqual(first.id, second.id)
            return first

        with patch.object(reports, "create_link", side_effect=replay):
            link = self.execute(self.admit())
        import shutil

        shutil.rmtree(Path(self.temp.name) / "artifacts" / str(link["report_id"]))
        with self.credentials(), auth.authorized_session(self.factory) as db:
            self.assertEqual(
                snapshots.retained_report_artifact_bytes(db, link["report_id"]), 0
            )

    def test_snapshot_absence_requires_live_report_authority(self):
        link = self.execute(self.admit())
        import shutil

        shutil.rmtree(Path(self.temp.name) / "artifacts" / str(link["report_id"]))
        with auth.authorized_session(self.factory) as db:
            with self.assertRaises(auth.TrustedAuthorizationError):
                snapshots.retained_report_artifact_bytes(db, link["report_id"])

    def test_private_snapshot_counter_rejects_stale_and_wrong_scope_handles(self):
        from dataclasses import replace
        from infra_automation.lifecycle import LifecycleError

        original = reports.create_link
        checked = []

        def create(*args, **kwargs):
            db, handle, _, report_id = args[:4]
            with self.assertRaises(LifecycleError):
                snapshots.retained_report_artifact_bytes(
                    db, report_id, handle=replace(handle, fence=handle.fence + 1)
                )
            report = db.get(AnalysisReport, report_id)
            report.project_id, report.workspace_id = 200, 200
            db.flush()
            with self.assertRaises(auth.TrustedAuthorizationError):
                snapshots.retained_report_artifact_bytes(db, report_id, handle=handle)
            report.project_id, report.workspace_id = 100, 100
            db.flush()
            checked.append(True)
            return original(*args, **kwargs)

        with patch.object(reports, "create_link", side_effect=create):
            self.execute(self.admit())
        self.assertEqual(checked, [True])
