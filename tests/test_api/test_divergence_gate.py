"""HTTP adapter coverage for the opt-in retained-snapshot gate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import create_app
from cloud.base import (
    ReadStatus,
    ResourceIdentity,
    ResourceRead,
    SnapshotFact,
    build_snapshot,
)
import services.analysis_service as analysis_service
from tests.test_cloud.test_reflection import plan
from tests.test_services.test_analysis_cloud_grounding import CloudBudgetFixture


class DivergenceGateApiTests(CloudBudgetFixture):
    endpoint = "/api/v1/analyses"

    def post(self, client, **fields):
        return client.post(
            self.endpoint,
            data={"project_id": str(self.project.id), **fields},
            files={"files": ("plan.json", self.raw_plan, "application/json")},
        )

    def test_gate_and_staleness_require_a_snapshot_digest(self):
        with (
            TestClient(create_app()) as client,
            patch("api.routes.analyses.analyze_uploaded_files") as analyze,
        ):
            for fields in (
                {"fail_on_divergence": "true"},
                {"plan_stale_after_seconds": "600"},
            ):
                with self.subTest(fields=fields):
                    response = self.post(client, **fields)
                    self.assertEqual(response.status_code, 400, response.text)
                    self.assertEqual(
                        response.json()["error"]["code"], "snapshot_digest_required"
                    )
            analyze.assert_not_called()

    def test_snapshot_opt_in_checks_project_report_read(self):
        def check_permission(**kwargs):
            if kwargs["capability"] == "report.read":
                raise PermissionError("Denied for this project.")

        with (
            TestClient(create_app()) as client,
            patch(
                "api.routes.analyses._require_api_project_permission",
                side_effect=check_permission,
            ) as permission,
            patch("api.routes.analyses.analyze_uploaded_files") as analyze,
        ):
            response = self.post(client, snapshot_digest="d" * 64)

        self.assertEqual(response.status_code, 403, response.text)
        self.assertIn(
            "report.read",
            [call.kwargs["capability"] for call in permission.call_args_list],
        )
        analyze.assert_not_called()

    def test_legacy_calls_keep_shape_and_service_arguments(self):
        with (
            TestClient(create_app()) as client,
            patch.object(
                analysis_service,
                "build_analysis_artifacts",
                side_effect=self.deterministic_build,
            ),
            patch(
                "api.routes.analyses.analyze_uploaded_files",
                side_effect=self.real_analyze,
            ) as analyze,
        ):
            response = self.post(client)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("live_context", response.json()["data"])
        self.assertNotIn("snapshot_digest", analyze.call_args.kwargs)
        self.assertNotIn("plan_stale_after_seconds", analyze.call_args.kwargs)

    def test_comparison_request_errors_use_closed_codes(self):
        from services.divergence_service import DivergenceRequestError

        digest = "d" * 64
        with TestClient(create_app()) as client:
            for code, expected_status in (
                ("invalid_grounding_snapshot", 400),
                ("invalid_grounding_plan", 400),
                ("invalid_plan_staleness", 400),
                ("grounding_evidence_unavailable", 404),
            ):
                with self.subTest(code=code):
                    with patch(
                        "api.routes.analyses.analyze_uploaded_files",
                        side_effect=DivergenceRequestError(code),
                    ):
                        response = self.post(client, snapshot_digest=digest)
                    self.assertEqual(
                        response.status_code, expected_status, response.text
                    )
                    self.assertEqual(response.json()["error"]["code"], code)
                    self.assertNotIn(digest, response.text)

    def comparison(self, *, status):
        from analysis.divergence import compare_plan

        recorded = {"id": "i-00000000000000001", "disable_api_termination": True}
        source = plan(values=recorded)
        source["resource_changes"][0]["change"]["after"] = recorded.copy()
        observed_at = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
        source["timestamp"] = "2026-11-20T11:30:00Z"
        unreadable = status == "unreadable"
        outcome = ResourceRead(
            identity=ResourceIdentity(
                address="aws_instance.example",
                resource_type="aws_instance",
                physical_id="i-00000000000000001",
            ),
            status=ReadStatus.UNREADABLE if unreadable else ReadStatus.READ,
            cause="permission_denied" if unreadable else None,
            facts=()
            if unreadable
            else (
                SnapshotFact(
                    name="termination_protection.DisableApiTermination.Value",
                    value=status == "match",
                ),
            ),
        )
        snapshot = build_snapshot(
            provider="aws",
            project_id=self.project.id,
            scope_id="http-adapter-fixture",
            scope="000000000000",
            read_window_start=observed_at,
            read_window_end=observed_at,
            resources=(outcome,),
        )
        return compare_plan(source, snapshot, stale_after_seconds=600)

    def test_tag_edit_cannot_clear_gate_with_unobserved_security_group_rules(self):
        group_id = "sg-0123456789abcdef0"
        recorded = {
            "id": group_id,
            "vpc_id": "vpc-0123456789abcdef0",
            "ingress": [],
            "egress": [],
            "tags": {"stage": "previous"},
        }
        source = plan("aws_security_group", values=recorded)
        source["timestamp"] = (
            datetime.now(timezone.utc) - timedelta(minutes=1)
        ).isoformat()
        source["resource_changes"][0]["change"]["after"] = {
            **recorded,
            "tags": {"stage": "planned"},
        }
        self.raw_plan = json.dumps(source).encode()
        group = {
            "GroupId": group_id,
            "VpcId": recorded["vpc_id"],
            "IpPermissions": [],
            "IpPermissionsEgress": [],
            "Tags": [{"Key": "stage", "Value": "previous"}],
        }

        def response(operation, parameters):
            if operation == "DescribeNetworkInterfaces":
                return {"NetworkInterfaces": []}
            return {"SecurityGroups": [group] if "GroupIds" in parameters else []}

        self.sdk.create_client.return_value._make_api_call.side_effect = response
        before = self.cloud.collect_plan(self.project.id, source).snapshot
        group["IpPermissions"] = [
            {
                "IpProtocol": "tcp",
                "FromPort": 443,
                "ToPort": 443,
                "IpRanges": [{"CidrIp": "192.0.2.0/24"}],
            }
        ]
        after = self.cloud.collect_plan(self.project.id, source).snapshot
        self.assertEqual(
            before.resources[0].status, ReadStatus.READ, before.resources[0].cause
        )
        self.assertEqual(
            after.resources[0].status, ReadStatus.READ, after.resources[0].cause
        )
        self.assertEqual(before.resources[0].facts, after.resources[0].facts)

        with (
            TestClient(create_app()) as client,
            patch.object(
                analysis_service,
                "build_analysis_artifacts",
                side_effect=self.deterministic_build,
            ),
        ):
            result = self.post(
                client, snapshot_digest=after.digest, fail_on_divergence="true"
            )

        self.assertEqual(result.status_code, 409, result.text)
        error = result.json()["error"]
        self.assertEqual(error["code"], "divergence_unverified")
        self.assertEqual(error["details"]["exit_code"], 2)
        (comparison,) = error["details"]["live_context"]["resources"]
        self.assertEqual(comparison["status"], "unknown")
        self.assertIn("tags.stage", comparison["checked_attributes"])

    def test_ec2_attachment_drift_fails_tag_edit_and_publishes_evidence(self):
        recorded_groups = ["sg-0123456789abcdef0", "sg-2123456789abcdef0"]
        live_groups = ["sg-1123456789abcdef0", recorded_groups[1]]
        recorded = {
            "id": "i-0123456789abcdef0",
            "vpc_security_group_ids": recorded_groups,
            "tags": {"stage": "previous"},
        }
        source = plan(values=recorded)
        source["timestamp"] = (
            datetime.now(timezone.utc) - timedelta(minutes=1)
        ).isoformat()
        source["resource_changes"][0]["change"]["after"] = {
            **recorded,
            "tags": {"stage": "planned"},
        }
        self.raw_plan = json.dumps(source).encode()

        def response(operation, parameters):
            result = self.response(operation, parameters)
            if operation == "DescribeInstances":
                instance = result["Reservations"][0]["Instances"][0]
                instance["SecurityGroups"] = [
                    {"GroupId": group_id} for group_id in live_groups
                ]
                instance["Tags"] = [{"Key": "stage", "Value": "previous"}]
            return result

        self.sdk.create_client.return_value._make_api_call.side_effect = response
        snapshot = self.cloud.collect_plan(self.project.id, source).snapshot
        (instance,) = snapshot.resources
        self.assertEqual(instance.status, ReadStatus.READ, instance.cause)
        self.assertEqual(
            [fact.value for fact in instance.facts if fact.name.endswith(".GroupId")],
            live_groups,
        )

        with (
            TestClient(create_app()) as client,
            patch.object(
                analysis_service,
                "build_analysis_artifacts",
                side_effect=self.deterministic_build,
            ),
        ):
            result = self.post(
                client, snapshot_digest=snapshot.digest, fail_on_divergence="true"
            )
            self.assertEqual(result.status_code, 409, result.text)
            error = result.json()["error"]
            self.assertEqual(error["code"], "plan_reality_divergence")
            self.assertEqual(error["details"]["exit_code"], 3)
            comparison = error["details"]["live_context"]
            self.assertTrue(comparison["requires_caution"])
            (resource,) = comparison["resources"]
            self.assertEqual(resource["status"], "diverged")
            (difference,) = resource["differences"]
            self.assertEqual(difference["attribute"], "vpc_security_group_ids")
            self.assertEqual(difference["recorded"], ", ".join(recorded_groups))
            self.assertEqual(difference["live"], ", ".join(live_groups))
            self.assertEqual(difference["planned"], ", ".join(recorded_groups))

            report = client.get(f"{self.endpoint}/{error['details']['report_id']}")
        self.assertEqual(report.status_code, 200, report.text)
        detail = report.json()["data"]
        self.assertIn(detail["recommendation"], {"caution", "no-go"})
        finding = next(
            item
            for item in detail["findings"]
            if item["category"] == "plan_reality_divergence"
        )
        evidence = [
            item
            for item in detail["evidence_items"]
            if item["evidence_id"] in finding["evidence_refs"]
        ]
        self.assertEqual(len(evidence), 2)
        self.assertTrue(all(snapshot.digest in item["source_ref"] for item in evidence))
        for group_id in live_groups:
            self.assertTrue(any(group_id in item["summary"] for item in evidence))

    def test_ci_gate_envelopes_preserve_report_and_comparison(self):
        with (
            TestClient(create_app()) as client,
            patch.object(
                analysis_service,
                "build_analysis_artifacts",
                side_effect=self.deterministic_build,
            ),
        ):
            for status, code, exit_code in (
                ("diverged", "plan_reality_divergence", 3),
                ("unreadable", "divergence_unverified", 2),
                ("match", None, 0),
            ):
                with self.subTest(status=status):
                    comparison = self.comparison(status=status)

                    def analyzed(
                        files, *, snapshot_digest, plan_stale_after_seconds, **kwargs
                    ):
                        self.assertEqual(snapshot_digest, comparison.snapshot_digest)
                        self.assertEqual(plan_stale_after_seconds, 600)
                        result = self.real_analyze(files, **kwargs)
                        return result.model_copy(update={"live_context": comparison})

                    with patch(
                        "api.routes.analyses.analyze_uploaded_files",
                        side_effect=analyzed,
                    ) as analyze:
                        response = self.post(
                            client,
                            snapshot_digest=comparison.snapshot_digest,
                            plan_stale_after_seconds="600",
                            fail_on_divergence="true",
                        )
                        advisory = self.post(
                            client,
                            snapshot_digest=comparison.snapshot_digest,
                            plan_stale_after_seconds="600",
                        )
                    self.assertEqual(analyze.call_count, 2)
                    if code is None:
                        self.assertEqual(response.status_code, 200, response.text)
                        live_context = response.json()["data"]["live_context"]
                    else:
                        self.assertEqual(response.status_code, 409, response.text)
                        error = response.json()["error"]
                        self.assertEqual(error["code"], code)
                        self.assertEqual(error["details"]["exit_code"], exit_code)
                        self.assertGreater(error["details"]["report_id"], 0)
                        live_context = error["details"]["live_context"]
                    self.assertEqual(
                        live_context["snapshot_digest"], comparison.snapshot_digest
                    )
                    self.assertEqual(live_context["resources"][0]["status"], status)
                    self.assertEqual(live_context["freshness"]["status"], "stale")
                    self.assertEqual(advisory.status_code, 200, advisory.text)
                    self.assertFalse(
                        advisory.json()["data"]["advisory"]["should_block"]
                    )
                    self.assertEqual(
                        advisory.json()["data"]["live_context"],
                        comparison.model_dump(mode="json"),
                    )
