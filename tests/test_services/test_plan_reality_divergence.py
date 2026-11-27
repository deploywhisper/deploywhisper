"""Keep grounded findings in the retained evidence transaction."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import create_app
from cli.analyze import main
from evidence.models import ContextCompleteness
import services.analysis_service as analysis_service
from services.divergence_service import DivergenceRequestError
from tests.test_cloud.test_reflection import plan
from tests.test_services.test_analysis_cloud_grounding import CloudBudgetFixture


class PlanRealityDivergenceTests(CloudBudgetFixture):
    def observation(self, *, planned_subnet=None, observe_subnet=True):
        source = plan(
            values={"id": "i-0123456789abcdef0", "disable_api_termination": False}
        )
        source["timestamp"] = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat()
        source["resource_changes"][0]["change"]["after"] = {
            "id": "i-0123456789abcdef0",
            "disable_api_termination": False,
        }
        if planned_subnet is not None:
            change = source["resource_changes"][0]["change"]
            change["before"]["subnet_id"] = "subnet-0123456789abcdef0"
            change["after"]["subnet_id"] = planned_subnet

            def response(operation, params):
                result = self.response(operation, params)
                if operation == "DescribeInstances":
                    result["Reservations"][0]["Instances"][0]["SubnetId"] = (
                        "subnet-1123456789abcdef0"
                    )
                return result

            if observe_subnet:
                self.sdk.create_client.return_value._make_api_call.side_effect = (
                    response
                )
        self.artifact.write_text(json.dumps(source))
        saved = self.cloud.collect_plan(self.project.id, source)
        return saved.snapshot.digest

    def test_verified_divergence_is_persisted_without_calling_the_narrative_provider(
        self,
    ):
        digest = self.observation()

        with (
            patch.object(analysis_service, "generate_narrative") as provider,
            patch.object(
                analysis_service,
                "build_parse_batch",
                wraps=analysis_service.build_parse_batch,
            ) as parse,
        ):
            result = analysis_service.analyze_uploaded_files(
                [("plan.json", self.artifact.read_bytes())],
                project_id=self.project.id,
                snapshot_digest=digest,
            )

        provider.assert_not_called()
        parse.assert_called_once()
        self.assertTrue(result.live_context.diverged)
        self.assertTrue(result.live_context.requires_caution)
        self.assertEqual(result.live_context.freshness.status, "stale")
        self.assertIn(result.persisted_report["recommendation"], {"caution", "no-go"})
        self.assertNotEqual(result.persisted_report["severity"], "low")
        self.assertIn("Confirmed plan divergence", result.narrative.opening_sentence)
        self.assertNotIn("Ready to deploy.", json.dumps(result.persisted_report))
        finding = next(
            item
            for item in result.persisted_report["findings"]
            if item["category"] == "plan_reality_divergence"
        )
        evidence = next(
            item
            for item in result.persisted_report["evidence_items"]
            if item["evidence_id"] in finding["evidence_refs"]
        )
        self.assertTrue(evidence["deterministic"])
        self.assertIn(digest, evidence["source_ref"])
        self.assertEqual(evidence["resource"], "aws_instance.example")
        self.assertIn("recorded false", finding["description"])
        self.assertIn("live true", finding["description"])
        self.assertIn("planned false", finding["description"])

    def test_confirmed_drift_preserves_uncertainty_from_missing_observed_facts(self):
        digest = self.observation(
            planned_subnet="subnet-2123456789abcdef0", observe_subnet=False
        )
        with (
            patch.object(
                analysis_service,
                "_build_context_completeness",
                return_value=ContextCompleteness(context_score=1.0),
            ),
            patch.object(
                analysis_service,
                "build_analysis_artifacts",
                side_effect=self.deterministic_build,
            ),
        ):
            result = analysis_service.analyze_uploaded_files(
                [("plan.json", self.artifact.read_bytes())],
                project_id=self.project.id,
                snapshot_digest=digest,
            )

        comparison = result.live_context.resources[0]
        self.assertEqual(comparison.status, "diverged")
        self.assertEqual(comparison.reason, "comparable_facts_incomplete")
        self.assertTrue(result.assessment.partial_context)
        self.assertTrue(
            result.persisted_report["context_completeness"]["insufficient_context"]
        )

    def test_real_cli_gate_returns_distinct_code_and_keeps_advisory_report(self):
        digest = self.observation()
        argv = [
            "deploywhisper",
            "analyze",
            "--project-id",
            str(self.project.id),
            "--snapshot-digest",
            digest,
            "--fail-on-divergence",
            str(self.artifact),
        ]
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch("sys.argv", argv),
            patch.object(
                analysis_service,
                "build_analysis_artifacts",
                side_effect=self.deterministic_build,
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
            self.assertRaises(SystemExit) as failure,
        ):
            main()
        self.assertEqual(failure.exception.code, 3, stderr.getvalue())
        data = json.loads(stdout.getvalue())["data"]
        self.assertTrue(data["live_context"]["diverged"])
        self.assertFalse(data["advisory"]["should_block"])
        self.assertEqual(data["persisted_report"]["report_schema_version"], "v2")

    def test_snapshot_that_ages_during_publication_rolls_back_the_report(self):
        from models.database import SessionLocal
        from models.tables import AnalysisReport

        digest = self.observation()
        with (
            patch(
                "services.divergence_service._observation_status",
                side_effect=["current", "current", "stale"],
            ),
            patch.object(
                analysis_service,
                "build_analysis_artifacts",
                side_effect=self.deterministic_build,
            ),
            self.assertRaises(DivergenceRequestError) as failure,
        ):
            analysis_service.analyze_uploaded_files(
                [("plan.json", self.artifact.read_bytes())],
                project_id=self.project.id,
                snapshot_digest=digest,
            )
        self.assertEqual(failure.exception.code, "grounding_evidence_unavailable")
        with SessionLocal() as session:
            self.assertEqual(session.query(AnalysisReport).count(), 0)

    def test_snapshot_that_ages_during_admission_verification_rolls_back(self):
        from models.database import SessionLocal
        from models.tables import AnalysisReport
        from services.cloud_context_service import _EvidenceAdmission

        digest = self.observation()
        original_verify = _EvidenceAdmission._verify_publication
        aged = False

        def verify(admission):
            nonlocal aged
            original_verify(admission)
            if admission._minted:
                aged = True

        with (
            patch.object(_EvidenceAdmission, "_verify_publication", verify),
            patch(
                "services.divergence_service._observation_status",
                side_effect=lambda snapshot: "stale" if aged else "current",
            ),
            patch.object(
                analysis_service,
                "build_analysis_artifacts",
                side_effect=self.deterministic_build,
            ),
            self.assertRaises(DivergenceRequestError) as failure,
        ):
            analysis_service.analyze_uploaded_files(
                [("plan.json", self.artifact.read_bytes())],
                project_id=self.project.id,
                snapshot_digest=digest,
            )
        self.assertTrue(aged)
        self.assertEqual(failure.exception.code, "grounding_evidence_unavailable")
        with SessionLocal() as session:
            self.assertEqual(session.query(AnalysisReport).count(), 0)

    def _assert_report_failure(
        self,
        digest,
        *,
        status=500,
        exit_code=1,
        error_code="report_persistence_failed",
    ):
        from models.database import SessionLocal
        from models.tables import AnalysisReport

        with self.subTest(surface="api"), TestClient(create_app()) as client:
            response = client.post(
                "/api/v1/analyses",
                data={"project_id": self.project.id, "snapshot_digest": digest},
                files={
                    "files": (
                        "plan.json",
                        self.artifact.read_bytes(),
                        "application/json",
                    )
                },
            )
            self.assertEqual(response.status_code, status, response.text)
            self.assertEqual(response.json()["error"]["code"], error_code)
            self.assertNotIn("synthetic storage failure", response.text)
        with self.subTest(surface="cli"):
            stdout, stderr = io.StringIO(), io.StringIO()
            argv = [
                "deploywhisper",
                "analyze",
                "--project-id",
                str(self.project.id),
                "--snapshot-digest",
                digest,
                "--fail-on-divergence",
                str(self.artifact),
            ]
            with (
                patch("sys.argv", argv),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
                self.assertRaises(SystemExit) as failure,
            ):
                main()
            self.assertEqual(failure.exception.code, exit_code, stderr.getvalue())
            self.assertEqual(json.loads(stderr.getvalue())["error"]["code"], error_code)
            self.assertNotIn("synthetic storage failure", stderr.getvalue())
            self.assertEqual(stdout.getvalue(), "")
        with SessionLocal() as session:
            self.assertEqual(session.query(AnalysisReport).count(), 0)

    def test_report_storage_failure_rolls_back_and_keeps_http_and_cli_error_codes(self):
        digest = self.observation()
        real_persist = analysis_service.persist_analysis_report

        def failed_write(*args, **kwargs):
            real_persist(*args, **kwargs)
            raise PermissionError("synthetic storage failure")

        with (
            patch.object(
                analysis_service, "persist_analysis_report", side_effect=failed_write
            ),
            patch.object(
                analysis_service,
                "build_analysis_artifacts",
                side_effect=self.deterministic_build,
            ),
        ):
            self._assert_report_failure(digest)

    def test_post_write_verification_faults_remain_report_storage_failures(self):
        from sqlalchemy.engine import Connection
        from sqlalchemy.exc import OperationalError
        from sqlalchemy.orm import Session

        from cloud.schema import SCHEMA_KEY
        from models.cloud_snapshots import CloudContextSnapshot
        from models.tables import AnalysisReport
        from services.cloud_context_service import _EvidenceAdmission

        digest = self.observation()
        original_live_rows = _EvidenceAdmission._live_rows
        original_session_get = Session.get
        original_exec = Connection.exec_driver_sql

        def fail_if_report_written(session):
            if session.query(AnalysisReport).count():
                raise OperationalError(
                    "SELECT 1", {}, OSError("synthetic storage failure")
                )

        def load_evidence(admission):
            fail_if_report_written(admission.session)
            return original_live_rows(admission)

        def load_snapshot(session, entity, ident, **kwargs):
            if entity is CloudContextSnapshot:
                fail_if_report_written(session)
            return original_session_get(session, entity, ident, **kwargs)

        def read_schema(connection, statement, parameters=None, **kwargs):
            if (
                parameters == (SCHEMA_KEY,)
                and original_exec(
                    connection, "SELECT EXISTS(SELECT 1 FROM analysis_reports)"
                ).scalar()
            ):
                raise OperationalError(
                    "SELECT 1", {}, OSError("synthetic storage failure")
                )
            return original_exec(connection, statement, parameters, **kwargs)

        faults = (
            ("evidence", patch.object(_EvidenceAdmission, "_live_rows", load_evidence)),
            ("retention row", patch.object(Session, "get", load_snapshot)),
            (
                "retention schema",
                patch.object(Connection, "exec_driver_sql", read_schema),
            ),
        )
        for phase, fault in faults:
            with (
                self.subTest(phase=phase),
                fault,
                patch.object(
                    analysis_service,
                    "build_analysis_artifacts",
                    side_effect=self.deterministic_build,
                ),
            ):
                self._assert_report_failure(digest)

    def test_storage_failure_before_report_write_remains_unavailable_grounding(self):
        from sqlalchemy.exc import OperationalError
        from sqlalchemy.orm import Session

        from models.cloud_snapshots import CloudContextSnapshot

        digest = self.observation()
        original_get = Session.get

        def load_snapshot(session, entity, ident, **kwargs):
            if entity is CloudContextSnapshot:
                raise OperationalError(
                    "SELECT 1", {}, OSError("synthetic storage failure")
                )
            return original_get(session, entity, ident, **kwargs)

        with patch.object(Session, "get", load_snapshot):
            self._assert_report_failure(
                digest,
                status=404,
                exit_code=2,
                error_code="grounding_evidence_unavailable",
            )

    def test_owning_commit_failure_remains_an_analysis_persistence_error(self):
        from sqlalchemy.exc import SQLAlchemyError
        from sqlalchemy.orm import Session

        from models.database import SessionLocal
        from models.tables import AnalysisReport

        digest = self.observation()
        original_commit = Session.commit

        def fail_report_commit(session):
            if session.query(AnalysisReport).count():
                raise SQLAlchemyError("synthetic commit failure")
            return original_commit(session)

        with (
            patch.object(Session, "commit", fail_report_commit),
            patch.object(
                analysis_service,
                "build_analysis_artifacts",
                side_effect=self.deterministic_build,
            ),
            self.assertRaises(analysis_service.AnalysisPersistenceError),
        ):
            analysis_service.analyze_uploaded_files(
                [("plan.json", self.artifact.read_bytes())],
                project_id=self.project.id,
                snapshot_digest=digest,
            )
        with SessionLocal() as session:
            self.assertEqual(session.query(AnalysisReport).count(), 0)

    def test_snapshot_that_ages_in_unit_of_work_finalization_prevents_commit(self):
        from models.database import SessionLocal
        from models.tables import AnalysisReport
        from services.divergence_service import _ReportGroundingAuthority

        digest = self.observation()
        original_session = _ReportGroundingAuthority.session
        aged = False

        @contextmanager
        def age_at_commit(authority, project_id, operation):
            nonlocal aged
            with original_session(authority, project_id, operation) as session:
                yield session
                if session.query(AnalysisReport).count():
                    aged = True

        with (
            patch.object(_ReportGroundingAuthority, "session", age_at_commit),
            patch(
                "services.divergence_service._observation_status",
                side_effect=lambda snapshot: "stale" if aged else "current",
            ),
            patch.object(
                analysis_service,
                "build_analysis_artifacts",
                side_effect=self.deterministic_build,
            ),
            self.assertRaises(DivergenceRequestError) as failure,
        ):
            analysis_service.analyze_uploaded_files(
                [("plan.json", self.artifact.read_bytes())],
                project_id=self.project.id,
                snapshot_digest=digest,
            )
        self.assertTrue(aged)
        self.assertEqual(failure.exception.code, "grounding_evidence_unavailable")
        with SessionLocal() as session:
            self.assertEqual(session.query(AnalysisReport).count(), 0)

    def test_real_api_conflict_includes_the_persisted_report(self):
        digest = self.observation()
        with (
            TestClient(create_app()) as client,
            patch.object(
                analysis_service,
                "build_analysis_artifacts",
                side_effect=self.deterministic_build,
            ),
        ):
            response = client.post(
                "/api/v1/analyses",
                data={
                    "project_id": self.project.id,
                    "snapshot_digest": digest,
                    "fail_on_divergence": "true",
                },
                files={
                    "files": (
                        "plan.json",
                        self.artifact.read_bytes(),
                        "application/json",
                    )
                },
            )
            self.assertEqual(response.status_code, 409, response.text)
            error = response.json()["error"]
            self.assertEqual(error["code"], "plan_reality_divergence")
            self.assertEqual(error["details"]["exit_code"], 3)
            self.assertTrue(error["details"]["live_context"]["diverged"])
            path = f"/api/v1/analyses/{error['details']['report_id']}"
            report = client.get(path)
            self.assertEqual(report.status_code, 200, report.text)
            finding = next(
                item
                for item in report.json()["data"]["findings"]
                if item["category"] == "plan_reality_divergence"
            )
            feedback = client.post(
                f"{path}/findings/{finding['finding_id']}/feedback",
                json={
                    "outcome": "false_positive",
                    "false_positive_reason": "I acknowledge the finding and want to proceed.",
                },
            )
            self.assertEqual(feedback.status_code, 200, feedback.text)
            reviewed = client.get(path)
            self.assertEqual(reviewed.status_code, 200, reviewed.text)
            self.assertNotEqual(reviewed.json()["data"]["recommendation"], "go")
        self.assertIn("plan_reality_divergence", report.text)
        self.assertIn(digest, report.text)

    def test_structured_comparison_screens_private_values_from_other_artifacts(self):
        canary = "subnet-2123456789abcdef0"
        digest = self.observation(planned_subnet=canary)
        files = [
            ("plan.json", self.artifact.read_bytes()),
            ("settings.json", json.dumps({"password": canary}).encode()),
        ]
        with patch.object(
            analysis_service,
            "build_analysis_artifacts",
            side_effect=self.deterministic_build,
        ):
            result = analysis_service.analyze_uploaded_files(
                files, project_id=self.project.id, snapshot_digest=digest
            )
        self.assertTrue(result.live_context.diverged)
        subnet = next(
            difference
            for comparison in result.live_context.resources
            for difference in comparison.differences
            if difference.attribute == "subnet_id"
        )
        self.assertFalse(subnet.planned_known)
        self.assertNotIn(canary, result.live_context.model_dump_json())
