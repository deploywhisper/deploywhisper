"""Seeded collected-evidence service proof; no production collector is admitted."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from importlib import import_module
import json

from sqlalchemy import select
from infra_automation.approval_eligibility import EvidenceFacts, LiveBinding
from infra_automation.contracts import ProfileContract, RegistryContract
from infra_automation.decisions import (
    DecisionBinding,
    binding_digest,
    freeze_report_snapshot,
)
from infra_automation.lifecycle import LifecycleError
from infra_automation.preflight_contracts import SyntheticCollectionEnvelope
from infra_automation.state import AuditActor
from models.repositories import infra_automation_runs as runs
from models.repositories import infra_automation_decisions as decisions
from models.tables import (
    AnalysisReport,
    RiskAssessment,
    InfraAutomationAttempt,
    InfraAutomationArtifactManifest,
    InfraAutomationReportLink,
    IdentitySession,
)
from services import infra_automation_support as support
from services import project_service as auth
from services.infra_automation_decisions import (
    DecisionService,
    DecisionMaterial,
    DecisionRequest,
)
from services.infra_automation_snapshots import export_run_snapshot
from services.report_service import _serialize_report
from evidence.models import ContextCompleteness
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation import test_workflow_snapshots as snapshots
from tests.test_infra_automation import test_approval_eligibility as eligibility_tests
from tests.test_infra_automation.test_decisions import binding_payload, D


class DecisionServiceTests(LifecycleCase):
    enable = snapshots.WorkflowSnapshotTests.enable
    publish_fixture = snapshots.WorkflowSnapshotTests.publish_fixture

    def setUp(self):
        LifecycleCase.setUp(self)
        self.now = (self.now + timedelta(seconds=1)).replace(microsecond=0)
        self.principal("reviewer")
        self.member("reviewer", principal="reviewer")
        self.enable()
        workflow = eligibility_tests.ApprovalEligibilityTests().workflow()
        workflow.update(project_id="100", workspace_id="100")
        if getattr(self, "serial_decisions", False):
            import copy

            first = copy.deepcopy(workflow["steps"][3])
            first["id"] = "decision-a"
            first_handoff = copy.deepcopy(workflow["steps"][4])
            first_handoff["id"] = "handoff-a"
            first_handoff["depends_on"] = ["decision-a", "decision"]
            first_handoff["decision"]["step_id"] = "decision-a"
            workflow["steps"][3]["depends_on"].append("decision-a")
            workflow["steps"][3:3] = (
                [first]
                if getattr(self, "indirect_decisions", False)
                else [first, first_handoff]
            )

        self.registry = RegistryContract(
            profiles=(
                ProfileContract(
                    digest=D, tool="opentofu", authorization_kinds=("exact_plan",)
                ),
            )
        )
        ids = self.publish_fixture(workflow)
        with self.credentials():
            exported = export_run_snapshot(
                *ids, {}, 100, registry_contract=self.registry
            )
        self.document = exported.snapshot
        self.raw_artifacts = support.canonical([["plan.json", "{}"]])
        artifact_digest = support.digest(self.raw_artifacts)
        self.collected_at = support.utc(self.now)
        self.deadline = self.now + timedelta(minutes=10)
        with self.factory.begin() as db:
            self.run = runs.create_run(
                db,
                snapshot=exported,
                request_digest=D,
                key_digest=D,
                requested_by="human-a",
                deadline_at=self.now + timedelta(minutes=15),
                audit_actor=AuditActor("human-a", "human", "admin"),
                reason="synthetic",
                now=self.now,
            )
            self.run.state = "running"
            report = AnalysisReport(
                id=1,
                project_id=100,
                workspace_id=100,
                authorization_required=True,
                risk_score=0,
                severity="low",
                recommendation="go",
                top_risk="No detected risk.",
                parse_summary="Parsed synthetic.",
                narrative_opening="Go",
                narrative_explanation="Synthetic.",
                submission_manifest_json=json.dumps(
                    {
                        "items": [],
                        "redaction": {
                            "filenames_redacted": False,
                            "sensitive_content_excluded": False,
                        },
                    }
                ),
            )
            report.risk_assessment = RiskAssessment(
                overall_severity="low",
                recommendation="go",
                score=0,
                confidence=1.0,
                context_completeness_json=ContextCompleteness().model_dump_json(),
            )
            db.add(report)
            db.flush()
            self.raw_report, report_digest = freeze_report_snapshot(
                _serialize_report(report)
            )
            for step, kind in [
                ("collect", "admitted_collection"),
                ("analyze", "shared_analysis"),
                ("gate", "policy_evaluation"),
            ]:
                output = (
                    {"kind": "report", "reference": "link", "digest": D}
                    if step == "analyze"
                    else {
                        "kind": "screened_artifacts",
                        "reference": "manifest",
                        "digest": artifact_digest,
                    }
                    if step == "collect"
                    else None
                )
                db.add(
                    InfraAutomationAttempt(
                        id="attempt-" + step,
                        project_id=100,
                        workspace_id=100,
                        requested_by="human-a",
                        run_id=self.run.id,
                        step_id=step,
                        step_kind=kind,
                        attempt_number=1,
                        fence=1,
                        handler_id="synthetic",
                        handler_version="1",
                        retry_safe=False,
                        input_digest=D,
                        created_at=self.now,
                        deadline_at=self.deadline,
                        state="succeeded",
                        version=1,
                        coordinator_generation=1,
                        last_observed_at=self.now,
                        logs_json="[]",
                        uploads_json="[]",
                        output_json=json.dumps(output) if output else None,
                        output_digest=support.digest(support.canonical(output))
                        if output
                        else None,
                        log_bytes=0,
                        last_log_sequence=0,
                    )
                )
            collection = SyntheticCollectionEnvelope(
                project_id=100,
                workspace_id=100,
                run_id=self.run.id,
                step_id="collect",
                attempt_id="attempt-collect",
                fence=1,
                collector_id="collector",
                repository_id="repo",
                commit_sha="a" * 40,
                profile_digest=D,
                command_digest=D,
                argv_digest=D,
                raw_local_digest=D,
                sanitized_digest=artifact_digest,
                exit_code=0,
                collected_at=self.collected_at,
                source_deadline=support.utc(self.deadline),
            )
            collection_bytes = support.canonical(collection.model_dump(mode="json"))
            db.add(
                InfraAutomationArtifactManifest(
                    id="manifest",
                    run_id=self.run.id,
                    step_id="collect",
                    project_id=100,
                    workspace_id=100,
                    requested_by="human-a",
                    artifacts_bytes=self.raw_artifacts,
                    digest=artifact_digest,
                    collection_bytes=collection_bytes,
                    collection_digest=support.digest(collection_bytes),
                    created_at=self.now,
                )
            )
            db.flush()
            link_bytes = support.canonical(
                {"version": 1, "kind": "synthetic-collected-proof"}
            )
            link_digest = support.digest(link_bytes)
            db.add(
                InfraAutomationReportLink(
                    id="link",
                    run_id=self.run.id,
                    attempt_id="attempt-analyze",
                    manifest_id="manifest",
                    report_id=1,
                    project_id=100,
                    workspace_id=100,
                    requested_by="human-a",
                    provenance_bytes=link_bytes,
                    digest=link_digest,
                    created_at=self.now,
                )
            )
            attempt = db.scalar(
                select(InfraAutomationAttempt).where(
                    InfraAutomationAttempt.id == "attempt-analyze"
                )
            )
            attempt.output_json = support.canonical(
                {"kind": "report", "reference": "link", "digest": link_digest}
            ).decode()
            attempt.output_digest = support.digest(attempt.output_json.encode())
            policy_row, _ = support.policy_state(db, 100)
            policy_version = policy_row.version
        values = binding_payload()
        values.update(
            authorization_kind="exact_plan",
            workflow_id=self.run.workflow_id,
            revision_id=self.run.revision_id,
            workflow_revision_digest=self.run.definition_digest,
            input_digest=self.run.input_digest,
            environment="test",
            report_bytes_digest=report_digest,
            screened_artifact_digests=[artifact_digest],
            policy_version=policy_version,
            policy_digest=support.digest(
                support.canonical(
                    {
                        "automation": self.document.policy.model_dump(mode="json"),
                        "advisory": self.document.advisory_policy.model_dump(
                            mode="json"
                        ),
                    }
                )
            ),
            evidence_deadline=support.utc(self.deadline),
            approval_deadline=support.utc(self.now + timedelta(minutes=5)),
            authorization_epoch=self.document.authority.authorization_epoch,
            restore_epoch=self.document.authority.restore_epoch,
            provenance={
                "authorization_kind": "exact_plan",
                "source": {
                    "kind": "collected",
                    "repository_id": "repo",
                    "commit_sha": "a" * 40,
                    "collector_id": "collector",
                    "profile_digest": D,
                    "screened_transport_digest": artifact_digest,
                    "redaction_version": 1,
                    "collected_at": self.collected_at,
                    "source_deadline": support.utc(self.deadline),
                },
                "custody": {
                    "handle": "synthetic-custody",
                    "raw_local_digest": D,
                    "expires_at": support.utc(self.deadline),
                },
            },
        )
        binding = DecisionBinding.model_validate_json(json.dumps(values))
        digest = binding_digest(binding)
        self.material = DecisionMaterial(
            binding=binding,
            evidence=EvidenceFacts(
                source_kind="collected",
                source_verified=True,
                collected_at=self.now,
                evidence_deadline=self.deadline,
                complete=True,
                report_available=True,
                recommendation="go",
                policy_status="advisory",
                policy_passed=True,
                artifact_step_id="collect",
                report_step_id="analyze",
            ),
            live=LiveBinding(
                expected_tuple_digest=digest,
                current_tuple_digest=digest,
                membership_active=True,
                target_available=True,
                custody_available=True,
                approval_deadline=self.now + timedelta(minutes=5),
                custody_deadline=self.deadline,
                source_deadline=self.deadline,
                target_id="target",
                environment="test",
                authorization_kind="exact_plan",
            ),
            registry_contract=self.registry,
        )
        self.service = DecisionService(
            material_port=lambda *args: self.material, clock=lambda: self.now
        )
        with self.engine.begin() as db:
            for name, body in import_module(
                "migrations.versions.034_add_infra_decisions"
            ).GUARDS.items():
                db.exec_driver_sql(f"CREATE TRIGGER {name} {body}")

    def pending(self):
        with self.credentials():
            return self.service.request_decision(self.run.id, "decision")

    def request(self, row, outcome="approve"):
        return DecisionRequest(
            expected_version=row["version"],
            binding_digest=row["binding_digest"],
            outcome=outcome,
            reason="Synthetic review",
        )

    def test_real_http_receipt_roundtrip_requires_csrf_and_keeps_snapshot_private(self):
        from unittest.mock import patch

        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes import infra_automation as routes
        from services import infra_automation_decisions as decision_service

        row = self.pending()
        with self.credentials("reviewer"):
            page = decision_service.list_approvals(100, 100)
            from api.schemas import AutomationApprovalListResponse, build_meta

            AutomationApprovalListResponse.model_validate(
                {"data": page, "meta": build_meta(correlation_id="a" * 32)}
            )
        app = FastAPI()
        app.include_router(routes.router)
        token, csrf = self.tokens["reviewer"]
        headers = {
            "Cookie": f"__Host-dw-session={token}",
            "Origin": self.origin,
            "X-CSRF-Token": csrf,
        }
        with (
            patch("api.dependencies.identity_service", return_value=self.identity),
            patch.object(decision_service, "_default_service", self.service),
            TestClient(app, base_url=self.origin) as client,
        ):
            listing = client.get(
                "/api/v1/infra-automation/approvals?project_id=100&workspace_id=100",
                headers=headers,
            )
            self.assertEqual(listing.status_code, 200, listing.text)
            self.assertEqual(listing.json()["data"]["items"][0]["id"], row["id"])
            path = f"/api/v1/infra-automation/approvals/{row['id']}/decision"
            payload = self.request(row).model_dump(mode="json")
            denied = client.post(
                path,
                json=payload,
                headers={
                    key: value
                    for key, value in headers.items()
                    if key != "X-CSRF-Token"
                },
            )
            self.assertEqual(denied.status_code, 403, denied.text)
            response = client.post(path, json=payload, headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            receipt = response.json()["data"]
            self.assertEqual(receipt["status"], "approved")
            self.assertEqual(receipt["decision_kind"], "independent-approval")
            self.assertEqual(receipt["binding_digest"], row["binding_digest"])
            self.assertFalse(receipt["eligibility"]["eligible"])
            self.assertNotIn("report_bytes", receipt)
            self.assertEqual(response.headers["cache-control"], "no-store")
        with self.factory() as db:
            self.assertEqual(
                decisions.get_request(db, row["id"]).report_bytes, self.raw_report
            )

    def test_pending_restart_then_distinct_reviewer_approves(self):
        row = self.pending()
        self.assertEqual(row["status"], "pending")
        restarted = DecisionService(
            material_port=lambda *args: self.material, clock=lambda: self.now
        )
        with self.credentials("reviewer"):
            result = restarted.decide(row["id"], self.request(row))
        self.assertEqual(result["status"], "approved")
        with self.factory() as db:
            self.assertEqual(runs.get_run(db, self.run.id).state, "ready_handoff")
            self.assertEqual(
                decisions.get_request(db, row["id"]).report_bytes, self.raw_report
            )

    def test_explicit_rejection_is_distinct(self):
        row = self.pending()
        with self.credentials("reviewer"):
            result = self.service.decide(row["id"], self.request(row, "reject"))
        self.assertEqual(result["status"], "rejected")
        with self.factory() as db:
            self.assertEqual(runs.get_run(db, self.run.id).state, "rejected")

    def test_missing_and_self_reviewer_cannot_decide(self):
        row = self.pending()
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.service.decide(row["id"], self.request(row))
        with self.credentials(), self.assertRaises(auth.TrustedAuthorizationError):
            self.service.decide(row["id"], self.request(row))

    def test_expiry_equality_is_durable_invalidation(self):
        row = self.pending()
        from infra_automation.decisions import instant

        self.now = instant(row["deadline_at"])
        # Keep the verified session active while reaching the decision deadline.
        with self.factory.begin() as db:
            for item in db.scalars(
                select(IdentitySession).where(
                    IdentitySession.principal_id == "reviewer"
                )
            ):
                item.last_seen_at = self.now
        with self.credentials("reviewer"), self.assertRaises(LifecycleError):
            self.service.decide(row["id"], self.request(row))
        with self.factory() as db:
            self.assertEqual(decisions.get_request(db, row["id"]).status, "expired")

    def test_changed_custody_fails_closed(self):
        row = self.pending()
        self.material = replace(
            self.material,
            live=self.material.live.model_copy(update={"custody_available": False}),
        )
        with self.credentials("reviewer"), self.assertRaises(LifecycleError):
            self.service.decide(row["id"], self.request(row))
        with self.factory() as db:
            self.assertEqual(decisions.get_request(db, row["id"]).status, "invalidated")

    def assert_material_change_denied(self, *, live_changes=None, binding_changes=None):
        row = self.pending()
        if binding_changes:
            raw = self.material.binding.model_dump(mode="json")
            raw.update(binding_changes)
            self.material = replace(
                self.material,
                binding=DecisionBinding.model_validate_json(json.dumps(raw)),
            )
        if live_changes:
            self.material = replace(
                self.material, live=self.material.live.model_copy(update=live_changes)
            )
        with self.credentials("reviewer"), self.assertRaises(LifecycleError):
            self.service.decide(row["id"], self.request(row))
        with self.factory() as db:
            self.assertEqual(decisions.get_request(db, row["id"]).status, "invalidated")

    def test_changed_live_target_denies(self):
        self.assert_material_change_denied(live_changes={"target_available": False})

    def test_changed_live_membership_denies(self):
        self.assert_material_change_denied(live_changes={"membership_active": False})

    def test_changed_payload_denies(self):
        self.assert_material_change_denied(
            binding_changes={"payload_digest": "sha256:" + "b" * 64}
        )

    def test_changed_epoch_denies(self):
        self.assert_material_change_denied(binding_changes={"authorization_epoch": 2})

    def test_changed_policy_version_denies(self):
        self.assert_material_change_denied(binding_changes={"policy_version": 999})

    def test_wrong_branch_report_link_never_creates_request(self):
        with self.factory.begin() as db:
            manifest = db.get(InfraAutomationArtifactManifest, "manifest")
            manifest.step_id = "other-collection"
        with self.credentials(), self.assertRaises(LifecycleError):
            self.service.request_decision(self.run.id, "decision")
        with self.factory() as db:
            self.assertEqual(decisions.list_requests(db, 100), [])

    def test_stale_version_never_decides(self):
        row = self.pending()
        stale = self.request(row).model_copy(update={"expected_version": 2})
        with self.credentials("reviewer"), self.assertRaises(LifecycleError):
            self.service.decide(row["id"], stale)
        with self.factory() as db:
            self.assertEqual(decisions.get_request(db, row["id"]).status, "pending")

    def test_two_actual_service_reviewers_race_for_one_generation(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        row = self.pending()
        barrier = Barrier(2)

        def contender(_):
            with self.credentials("reviewer"):
                barrier.wait(timeout=5)
                try:
                    return self.service.decide(row["id"], self.request(row))["status"]
                except LifecycleError:
                    return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(
                list(pool.map(contender, range(2))), ["approved", "conflict"]
            )

    def approve(self):
        row = self.pending()
        with self.credentials("reviewer"):
            return self.service.decide(row["id"], self.request(row))

    def recheck(self, row, phase="dispatch"):
        with self.credentials(), auth.authorized_session() as db:
            return self.service.recheck_approved(db, row["id"], phase=phase)

    def test_approved_receipt_rechecks_at_dispatch_and_consume(self):
        row = self.approve()
        self.assertEqual(row["decision_kind"], "independent-approval")
        for phase in ("dispatch", "consume"):
            self.assertTrue(self.recheck(row, phase).eligible)
        self.material = replace(
            self.material,
            live=self.material.live.model_copy(update={"target_available": False}),
        )
        for phase in ("dispatch", "consume"):
            self.assertIn("target_unavailable", self.recheck(row, phase).reasons)

    def test_revoked_and_regranted_reviewer_cannot_revive_receipt(self):
        row = self.approve()
        with self.credentials():
            auth.revoke_project_membership(100, "reviewer")
        self.member("reviewer", principal="reviewer")
        self.assertIn("membership_revoked", self.recheck(row).reasons)
        with self.factory() as db:
            self.assertEqual(decisions.get_request(db, row["id"]).status, "approved")

    def test_recheck_uses_earliest_deadline_even_after_success(self):
        from infra_automation.decisions import instant

        row = self.approve()
        self.now = instant(row["deadline_at"])
        with self.factory.begin() as db:
            for item in db.scalars(
                select(IdentitySession).where(IdentitySession.principal_id == "human-a")
            ):
                item.last_seen_at = self.now
        for phase in ("dispatch", "consume"):
            self.assertIn("approval_expired", self.recheck(row, phase).reasons)

    def test_single_operator_records_acknowledgement_honestly(self):
        from unittest.mock import patch
        import config
        from models.tables import IdentityAccount

        with self.factory.begin() as db:
            db.get(IdentityAccount, "reviewer").enabled = False
        with patch(
            "config.settings",
            replace(config.settings, identity_decision_mode="single-operator"),
        ):
            row = self.pending()
            with self.credentials():
                result = self.service.decide(row["id"], self.request(row))
            self.assertEqual(result["decision_kind"], "acknowledgement")
            self.assertTrue(self.recheck(result).eligible)

    def test_partial_mandatory_collection_records_typed_denial_and_recovery(self):
        self.material = replace(
            self.material,
            evidence=self.material.evidence.model_copy(update={"complete": False}),
        )
        with self.credentials(), self.assertRaises(LifecycleError):
            self.service.request_decision(self.run.id, "decision")
        from services.infra_automation_decisions import _view

        with self.factory() as db:
            row = decisions.list_requests(db, 100)[0]
            self.assertEqual(row.status, "invalidated")
            projection = _view(row)
            self.assertIn("incomplete_evidence", projection["eligibility"]["reasons"])
            self.assertTrue(projection["eligibility"]["limitations"])
            self.assertTrue(projection["eligibility"]["context_todos"])
            self.assertEqual(row.report_bytes, self.raw_report)
            self.assertEqual(runs.get_run(db, self.run.id).state, "stopped_by_gate")

    def test_approval_transition_uses_exact_run_generations_without_history_page(self):
        from unittest.mock import patch

        row = self.pending()
        # Inbox pagination cannot bound the decisions used to authorize this run.
        # Any use of the capped project history here would hide older run rows.
        with patch.object(
            decisions,
            "list_requests",
            side_effect=AssertionError("History is not an authorization query"),
        ):
            with self.credentials("reviewer"):
                result = self.service.decide(row["id"], self.request(row))
        self.assertEqual(result["status"], "approved")
        with self.factory() as db:
            self.assertEqual(runs.get_run(db, self.run.id).state, "ready_handoff")

    def test_superseding_generation_invalidates_older_approved_receipt(self):
        approved = self.approve()
        self.assertTrue(self.recheck(approved).eligible)
        with self.credentials(), auth.authorized_session() as db:
            old = decisions.get_request(db, approved["id"])
            replacement = decisions.create_request(
                db,
                self.material.binding,
                run_id=self.run.id,
                step_id="decision",
                requested_by="human-a",
                report_bytes=old.report_bytes,
                now=self.now,
            )
            self.assertGreater(replacement.generation, old.generation)
            self.assertEqual(replacement.status, "pending")
        for phase in ("dispatch", "consume"):
            self.assertIn("binding_changed", self.recheck(approved, phase).reasons)


class SerialDecisionServiceTests(LifecycleCase):
    """Approved predecessor receipts satisfy a validated serial decision DAG."""

    serial_decisions = True
    enable = DecisionServiceTests.enable
    publish_fixture = DecisionServiceTests.publish_fixture
    setUp = DecisionServiceTests.setUp
    request = DecisionServiceTests.request

    def test_serial_decisions_pause_until_each_current_receipt_is_approved(self):
        from infra_automation.workflow_validation import validate_workflow

        checked = validate_workflow(
            support.canonical(self.document.definition.model_dump(mode="json")),
            registry_contract=self.registry,
        )
        self.assertTrue(checked.valid, checked.errors)
        with self.credentials():
            first = self.service.request_decision(self.run.id, "decision-a")
        with self.credentials("reviewer"):
            self.service.decide(first["id"], self.request(first))
        with self.factory() as db:
            self.assertEqual(runs.get_run(db, self.run.id).state, "waiting_approval")
        for phase in ("dispatch", "consume"):
            with self.credentials(), auth.authorized_session() as db:
                self.assertIn(
                    "prerequisite_unsuccessful",
                    self.service.recheck_approved(db, first["id"], phase=phase).reasons,
                )
        with self.credentials():
            second = self.service.request_decision(self.run.id, "decision")
        with self.credentials("reviewer"):
            result = self.service.decide(second["id"], self.request(second))
        self.assertEqual(result["status"], "approved")
        with self.factory() as db:
            self.assertEqual(runs.get_run(db, self.run.id).state, "ready_handoff")
        for approved in (first, second):
            for phase in ("dispatch", "consume"):
                with self.credentials(), auth.authorized_session() as db:
                    self.assertTrue(
                        self.service.recheck_approved(
                            db, approved["id"], phase=phase
                        ).eligible
                    )


class IndirectDecisionServiceTests(SerialDecisionServiceTests):
    """A mandatory predecessor decision need not own a handoff receipt reference."""

    indirect_decisions = True
