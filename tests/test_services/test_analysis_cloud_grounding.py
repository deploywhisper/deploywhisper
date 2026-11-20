"""Shared analysis consumes service-produced collection budgets without new flows."""

from __future__ import annotations

from contextlib import contextmanager
from importlib import reload
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import config as config_module
import models.database as database_module
import models.repositories.analysis_reports as reports_repository
import models.repositories.settings as settings_repository
import models.tables as tables_module
import services.analysis_service as analysis_service
import services.project_service as project_service
import services.report_service as report_service
from cloud.collection import AwsPlanCollector
from cloud.reflection import ReflectionTarget
from services.cloud_context_service import CloudContextService
from tests.snapshot_isolation import isolate_artifact_snapshots
from tests.test_cloud.test_reflection import plan


class CloudBudgetFixture(unittest.TestCase):
    """Install synthetic server authority over the same isolated project DB."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "DATABASE_URL": "sqlite:///" + str(Path(self.temp.name) / "budget.db"),
                "APP_BASE_URL": "https://budget.invalid",
                "DEPLOYWHISPER_IDENTITY_PROFILE": "disabled",
                "DEPLOYWHISPER_AUTHORIZATION_PROFILE": "legacy-evaluation",
            },
        )
        self.env.start()
        for module in (
            config_module,
            tables_module,
            database_module,
            reports_repository,
            settings_repository,
            project_service,
            report_service,
        ):
            reload(module)
        database_module.init_db()
        isolate_artifact_snapshots(self, self.temp.name)
        self.project = project_service.create_project(
            project_key="budget", display_name="Budget"
        )
        self.sdk = Mock()
        self.response = lambda operation, parameters: (
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": parameters["InstanceIds"][0],
                                "State": {"Name": "running"},
                            }
                        ]
                    }
                ]
            }
            if operation == "DescribeInstances"
            else {
                "InstanceId": parameters["InstanceId"],
                "DisableApiTermination": {"Value": True},
            }
        )
        self.sdk.create_client.return_value._make_api_call.side_effect = self.response
        project_id = self.project.id

        class TestAuthority:
            @contextmanager
            def session(port, requested, operation):
                with database_module.SessionLocal() as session:
                    session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
                    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                    try:
                        port.check(session, requested, operation)
                        yield session
                        port.check(session, requested, operation)
                        session.commit()
                    except BaseException:
                        session.rollback()
                        raise

            def check(port, session, requested, operation):
                if requested != project_id or operation not in {
                    "configure",
                    "collect",
                    "read",
                    "admit",
                    "purge",
                }:
                    raise PermissionError("test authority denied")

        collector = AwsPlanCollector(
            target=ReflectionTarget(account_id="000000000000", regions=("us-east-1",)),
            session=self.sdk,
        )
        self.cloud = CloudContextService(
            unit_of_work=TestAuthority(), plan_collector_factory=lambda *args: collector
        )
        self.cloud.configure(self.project.id, enabled=True, provider="aws")
        self.raw_plan = json.dumps(plan()).encode()
        self.files = [("plan.json", self.raw_plan)]
        self.artifact = Path(self.temp.name) / "plan.json"
        self.artifact.write_bytes(self.raw_plan)
        self.real_build = analysis_service.build_analysis_artifacts
        self.real_analyze = analysis_service.analyze_uploaded_files

    def tearDown(self):
        database_module.engine.dispose()
        self.env.stop()
        for module in (
            config_module,
            tables_module,
            database_module,
            reports_repository,
            settings_repository,
            project_service,
            report_service,
        ):
            reload(module)
        self.temp.cleanup()

    def collect(self, *, cancelled=False, failed=False, disabled=False):
        if disabled:
            self.cloud.configure(self.project.id, enabled=False)
        self.sdk.create_client.return_value._make_api_call.side_effect = (
            RuntimeError("synthetic-provider-credential-canary")
            if failed
            else self.response
        )
        event = threading.Event()
        if cancelled:
            event.set()
        return self.cloud.collect_plan(self.project.id, plan(), cancel=event)

    def deterministic_build(self, *args, **kwargs):
        kwargs.update(
            include_topology_context=False,
            include_incident_context=False,
            include_narrative=False,
            allow_llm_assistance=False,
        )
        return self.real_build(*args, **kwargs)

    def analyze_with(self, observed):
        def installed_analysis(files, **kwargs):
            # Trusted composition in the test server; no request parameter can
            # install this object or its synthetic authority.
            return self.real_analyze(files, **kwargs, grounding_outcome=observed)

        return installed_analysis


class AnalysisCloudGroundingTests(CloudBudgetFixture):
    def test_actual_service_budget_survives_shared_analysis_and_persistence_result(
        self,
    ):
        observed = self.collect()
        with patch.object(
            analysis_service,
            "build_analysis_artifacts",
            side_effect=self.deterministic_build,
        ):
            result = self.real_analyze(
                self.files, project_id=self.project.id, grounding_outcome=observed
            )
        self.assertEqual(result.cloud_collection, observed.budget)
        self.assertEqual(
            result.cloud_collection.actual_call_count,
            self.sdk.create_client.return_value._make_api_call.call_count,
        )
        self.assertEqual(result.model_dump()["cloud_collection"]["budget_consumed"], 2)
        self.assertNotIn("snapshot", result.model_dump())
        self.assertEqual(result.persisted_report["report_schema_version"], "v2")

    def test_cancelled_collection_returns_zero_actual_calls_and_insufficiency(self):
        observed = self.collect(cancelled=True)
        artifacts = self.deterministic_build(
            self.files, project_id=self.project.id, grounding_outcome=observed
        )
        self.assertTrue(artifacts.cloud_collection.cancelled)
        self.assertEqual(artifacts.cloud_collection.actual_call_count, 0)
        self.assertEqual(artifacts.cloud_collection.planned_calls, 2)
        self.assertTrue(artifacts.assessment.context_completeness.insufficient_context)

    def test_disabled_and_absent_preserve_legacy_artifact_bytes(self):
        baseline = self.deterministic_build(self.files, project_id=self.project.id)
        disabled = self.deterministic_build(
            self.files,
            project_id=self.project.id,
            grounding_outcome=self.collect(disabled=True),
        )
        self.assertEqual(disabled.model_dump_json(), baseline.model_dump_json())
        self.assertNotIn("cloud_collection", baseline.model_dump())

    def test_outcome_from_other_project_is_rejected(self):
        observed = self.collect()
        with self.assertRaisesRegex(ValueError, "grounding_scope_mismatch"):
            self.deterministic_build(
                self.files, project_id=self.project.id + 1, grounding_outcome=observed
            )

    def test_real_failed_collection_cannot_improve_a_strong_baseline(self):
        from evidence.models import ContextCompleteness
        from analysis.risk_scorer import SEVERITY_ORDER

        strong = ContextCompleteness(context_score=0.95, insufficient_context=False)
        observed = self.collect(failed=True)
        with patch.object(
            analysis_service,
            "_build_context_completeness",
            side_effect=lambda *a, **kw: strong.model_copy(deep=True),
        ):
            baseline = self.deterministic_build(self.files, project_id=self.project.id)
            grounded = self.deterministic_build(
                self.files, project_id=self.project.id, grounding_outcome=observed
            )
        self.assertFalse(baseline.assessment.context_completeness.insufficient_context)
        self.assertTrue(grounded.assessment.context_completeness.insufficient_context)
        self.assertLessEqual(
            grounded.assessment.confidence, baseline.assessment.confidence
        )
        self.assertGreaterEqual(
            SEVERITY_ORDER[grounded.assessment.severity],
            SEVERITY_ORDER[baseline.assessment.severity],
        )
        self.assertNotIn(
            "synthetic-provider-credential-canary", grounded.model_dump_json()
        )
