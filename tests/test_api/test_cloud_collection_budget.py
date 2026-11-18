"""Existing HTTP analysis reports trusted collection metrics additively."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from app import create_app
import services.analysis_service as analysis_service
from tests.test_services.test_analysis_cloud_grounding import CloudBudgetFixture


class CloudCollectionBudgetApiTests(CloudBudgetFixture):
    def test_real_http_completion_failure_and_cancellation_report_actual_metrics(self):
        with TestClient(create_app()) as client:
            for path in ("/api/v1/analyses", "/api/v1/agent/analyses"):
                for cancelled, failed in ((False, False), (True, False), (False, True)):
                    with self.subTest(path=path, cancelled=cancelled, failed=failed):
                        self.sdk.reset_mock()
                        observed = self.collect(cancelled=cancelled, failed=failed)
                        calls = self.sdk.create_client.return_value._make_api_call.call_count
                        with (
                            patch.object(
                                analysis_service,
                                "build_analysis_artifacts",
                                side_effect=self.deterministic_build,
                            ),
                            patch(
                                "api.routes.analyses.analyze_uploaded_files",
                                side_effect=self.analyze_with(observed),
                            ),
                        ):
                            response = client.post(
                                path,
                                data={"project_id": str(self.project.id)},
                                files=[
                                    (
                                        "files",
                                        (
                                            "plan.json",
                                            self.raw_plan,
                                            "application/json",
                                        ),
                                    )
                                ],
                            )
                        self.assertEqual(response.status_code, 200, response.text)
                        payload = response.json()
                        data = payload["data"]
                        budget = data["cloud_collection"]
                        self.assertEqual(budget["actual_call_count"], calls)
                        self.assertEqual(
                            budget, observed.budget.model_dump(mode="json")
                        )
                        self.assertEqual(budget["cancelled"], cancelled)
                        if path == "/api/v1/analyses":
                            self.assertEqual(
                                payload["meta"]["report_schema_version"], "v2"
                            )
                            self.assertFalse(data["advisory"]["should_block"])
                        else:
                            self.assertEqual(data["report_schema_version"], "v2")
                            self.assertEqual(data["schema_version"], "v1")
                            self.assertFalse(data["deployment_approval"])
                        self.assertNotIn(
                            "synthetic-provider-credential-canary", response.text
                        )

    def test_disabled_budget_absent_on_existing_http_and_agent_contracts(self):
        observed = self.collect(disabled=True)
        with (
            TestClient(create_app()) as client,
            patch.object(
                analysis_service,
                "build_analysis_artifacts",
                side_effect=self.deterministic_build,
            ),
            patch(
                "api.routes.analyses.analyze_uploaded_files",
                side_effect=self.analyze_with(observed),
            ),
        ):
            for path in ("/api/v1/analyses", "/api/v1/agent/analyses"):
                with self.subTest(path=path):
                    response = client.post(
                        path,
                        data={"project_id": str(self.project.id)},
                        files=[
                            ("files", ("plan.json", self.raw_plan, "application/json"))
                        ],
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertNotIn("cloud_collection", response.json()["data"])
