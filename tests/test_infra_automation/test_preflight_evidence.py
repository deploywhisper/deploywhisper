"""Durable failure facts retain versioned preflight recovery guidance."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from infra_automation.lifecycle import LifecycleError, SnapshotDocument
from infra_automation.state import RunRequest
from models.repositories import infra_automation_runs as runs
from services import infra_automation_engine_service as engine
from services.infra_automation_preflight import PREFLIGHT_REGISTRY
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation import test_workflow_snapshots as snapshot_tests


class PreflightEvidenceTests(LifecycleCase):
    enable = snapshot_tests.WorkflowSnapshotTests.enable
    publish_fixture = snapshot_tests.WorkflowSnapshotTests.publish_fixture

    def setUp(self):
        super().setUp()
        self.enable()
        definition = {
            "workflow_version": 2,
            "project_id": "100",
            "workspace_id": "100",
            "environment": "dev",
            "inputs": {},
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
        workflow, revision = self.publish_fixture(definition)
        with self.credentials():
            admitted = engine.request_run(
                RunRequest(
                    workflow_id=workflow,
                    revision_id=revision,
                    workspace_id=100,
                    inputs={},
                    idempotency_key="evidence-status",
                    reason="Synthetic evidence status",
                    total_timeout_seconds=60,
                ),
                registry=PREFLIGHT_REGISTRY,
            )
        self.run_id = admitted["id"]

    def project(self, *, state=None, attempts=(), manifest=False, links=(), now=None):
        from infra_automation.preflight_evidence import build_evidence_status

        with self.factory() as db:
            run = runs.get_run(db, self.run_id)
            document = SnapshotDocument.model_validate_json(run.snapshot_bytes)
            captured = datetime.strptime(
                document.captured_at, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
            if state is not None:
                run.state = state
            return build_evidence_status(
                run,
                document,
                attempts,
                manifest_present=manifest,
                links=list(links),
                now=now or captured,
            )

    def test_queued_missing_manifest_is_pending_and_terminal_missing_is_explicit(self):
        pending = self.project()
        self.assertEqual(pending.status, "pending")
        self.assertIn(
            "Wait for mandatory evidence and analysis to complete.",
            pending.context_todos,
        )
        missing = self.project(state="failed")
        self.assertEqual(missing.status, "missing")
        self.assertIn("Mandatory uploaded evidence is missing.", missing.limitations)
        self.assertIn(
            "Resubmit the mandatory supported artifacts in a new preflight.",
            missing.context_todos,
        )

    def test_failed_timeout_cancel_and_expiry_have_specific_durable_guidance(self):
        cases = {
            "failed": (
                "failed",
                "Analysis did not complete successfully.",
                "Review the failed preflight and submit a new analysis.",
            ),
            "timed_out": (
                "failed",
                "Preflight execution timed out before completing analysis.",
                "Review execution limits and submit a new preflight.",
            ),
            "cancelled": (
                "interrupted",
                "Preflight was cancelled; evidence analysis may be incomplete.",
                "Submit a new preflight if analysis is still required.",
            ),
            "expired": (
                "interrupted",
                "Preflight expired before completing analysis.",
                "Submit a new preflight with current evidence.",
            ),
        }
        for state, (status, limitation, todo) in cases.items():
            with self.subTest(state=state):
                result = self.project(state=state, manifest=True)
                self.assertEqual(result.status, status)
                self.assertIn(limitation, result.limitations)
                self.assertIn(todo, result.context_todos)
                self.assertFalse(result.approval_eligible)

    def test_failed_state_and_snapshot_survive_new_database_session(self):
        with self.factory.begin() as db:
            row = runs.get_run(db, self.run_id)
            row.state = "failed"
            row.version += 1
        first = self.project(manifest=True).model_dump(mode="json")
        self.engine.dispose()
        second = self.project(manifest=True).model_dump(mode="json")
        self.assertEqual(first, second)
        self.assertEqual(second["run_state"], "failed")
        self.assertEqual(second["run_version"], 2)
        self.assertIn("Analysis did not complete successfully.", second["limitations"])

    def test_freshness_uses_evidence_ttl_not_short_execution_timeout(self):
        with self.factory() as db:
            row = runs.get_run(db, self.run_id)
            document = SnapshotDocument.model_validate_json(row.snapshot_bytes)
            captured = datetime.strptime(
                document.captured_at, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
            deadline = captured + timedelta(
                seconds=document.policy.evidence_ttl_seconds
            )
        fresh = self.project(
            state="timed_out", manifest=True, now=captured + timedelta(seconds=61)
        )
        self.assertEqual(fresh.status, "failed")
        self.assertNotIn("Evidence freshness has expired.", fresh.limitations)
        self.assertEqual(
            self.project(manifest=True, now=deadline - timedelta(seconds=1)).status,
            "pending",
        )
        stale = self.project(manifest=True, now=deadline)
        self.assertEqual(stale.status, "stale")
        self.assertIn("Evidence freshness has expired.", stale.limitations)
        self.assertIn(
            "Collect current evidence and submit a new preflight.", stale.context_todos
        )

    def test_latest_analysis_attempt_and_existing_link_uncertainty_are_retained(self):
        attempts = [
            SimpleNamespace(
                id="older", step_id="analysis", attempt_number=1, state="failed"
            ),
            SimpleNamespace(
                id="latest", step_id="analysis", attempt_number=2, state="succeeded"
            ),
        ]
        link = {
            "limitations": ["Parser coverage is partial."],
            "context_todos": ["Review parser errors."],
        }
        result = self.project(
            state="succeeded", attempts=attempts, manifest=True, links=[link]
        )
        self.assertEqual(result.status, "available")
        self.assertEqual(result.attempt_id, "latest")
        self.assertTrue(result.report_available)
        self.assertIn("Parser coverage is partial.", result.limitations)
        self.assertIn("Review parser errors.", result.context_todos)
        self.assertFalse(result.approval_eligible)
        interrupted = self.project(
            state="timed_out", attempts=attempts, manifest=True, links=[link]
        )
        self.assertEqual(interrupted.status, "failed")
        self.assertTrue(interrupted.report_available)
        self.assertIn("Parser coverage is partial.", interrupted.limitations)
        self.assertNotIn(
            "Preflight execution timed out before completing analysis.",
            interrupted.limitations,
        )

    def test_unknown_states_and_sensitive_link_metadata_fail_closed(self):
        with self.assertRaises(LifecycleError):
            self.project(state="future_state")
        attempt = SimpleNamespace(
            id="unknown", step_id="analysis", attempt_number=1, state="future_state"
        )
        with self.assertRaises(LifecycleError):
            self.project(attempts=[attempt])
        with self.assertRaises(LifecycleError):
            self.project(
                links=[{"limitations": ["ghp_" + "X" * 36], "context_todos": []}]
            )

    def test_terminal_missing_report_and_failed_intake_attempt_are_explicit(self):
        missing = self.project(state="succeeded", manifest=True)
        self.assertEqual(missing.status, "missing")
        self.assertIn("Mandatory analysis report is missing.", missing.limitations)
        self.assertIn(
            "Submit a new preflight to produce a linked analysis report.",
            missing.context_todos,
        )
        attempt = SimpleNamespace(
            id="failed-intake", step_id="upload", attempt_number=1, state="failed"
        )
        failed = self.project(state="failed", attempts=[attempt])
        self.assertEqual(failed.status, "missing")
        self.assertEqual(failed.attempt_id, "failed-intake")
        self.assertEqual(failed.attempt_state, "failed")
        self.assertIn("Analysis did not complete successfully.", failed.limitations)
        self.assertIn("Mandatory uploaded evidence is missing.", failed.limitations)

    def test_projection_is_closed_advisory_and_rejects_naive_clock(self):
        from pydantic import ValidationError
        from infra_automation.preflight_evidence import PreflightEvidenceStatus

        payload = self.project().model_dump(mode="json")
        self.assertEqual(payload["version"], 1)
        self.assertFalse(payload["approval_eligible"])
        self.assertNotIn("confidence", payload)
        with self.assertRaises(ValidationError):
            PreflightEvidenceStatus.model_validate({**payload, "confidence": 1})
        with self.assertRaises(ValidationError):
            PreflightEvidenceStatus.model_validate(
                {**payload, "approval_eligible": True}
            )
        with self.assertRaises(LifecycleError):
            self.project(now=datetime(2026, 10, 27))
