"""Real upload/shared-core linkage and private-worker authority regressions."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import os
import json
import config

from unittest.mock import patch

from sqlalchemy import select, func

from infra_automation import claims
from infra_automation.lifecycle import LifecycleError
from infra_automation.local_workers import WorkerInput
from infra_automation.preflight_contracts import ArtifactUpload, PreflightRequest
from infra_automation.state import RunRequest
from models.repositories import infra_automation_runs as runs
from models.tables import AnalysisReport, InfraAutomationArtifactManifest
from services import project_service as auth
from services import infra_automation_preflight as service
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation import test_workflow_snapshots as snapshot_tests


FILES = [("main.tf", b'resource "aws_s3_bucket" "logs" { bucket = "synthetic-logs" }')]


class PreflightServiceTests(LifecycleCase):
    enable = snapshot_tests.WorkflowSnapshotTests.enable
    publish_fixture = snapshot_tests.WorkflowSnapshotTests.publish_fixture

    def setUp(self):
        super().setUp()
        self.enterContext(patch("services.report_service.SessionLocal", self.factory))
        self.provider = self.enterContext(
            patch(
                "llm.adapters.ollama_adapter.OllamaProviderAdapter.generate_completion",
                side_effect=RuntimeError("synthetic provider unavailable"),
            )
        )
        self.enterContext(
            patch.dict(
                os.environ,
                {"ARTIFACT_SNAPSHOT_DIR": str(Path(self.temp.name) / "artifacts")},
            )
        )
        self.enterContext(
            patch(
                "services.artifact_snapshot_service.settings",
                replace(
                    config.settings,
                    artifact_snapshot_dir=str(Path(self.temp.name) / "artifacts"),
                ),
            )
        )
        self.enterContext(
            patch("services.artifact_snapshot_service.SessionLocal", self.factory)
        )
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
        ids = self.publish_fixture(definition)
        self.request = PreflightRequest(
            run=RunRequest(
                workflow_id=ids[0],
                revision_id=ids[1],
                workspace_id=100,
                idempotency_key="upload-one",
                reason="Synthetic preflight",
            ),
            artifacts=[
                ArtifactUpload(name=name, content=raw.decode()) for name, raw in FILES
            ],
        )

    def admit(self, request=None):
        with self.credentials():
            return service.request_preflight(request or self.request)

    def execute(self, run, *, before_analysis=None):
        from infra_automation.analysis_context import _bind_worker

        with auth.authorized_session(self.factory) as db:
            owner = claims.acquire_coordinator(db, project_id=100, workspace_id=100)
            row = runs.get_run(db, run["id"])
            claims.start_run(db, owner, run_id=row.id, expected_version=row.version)
        for step_id in ("upload", "analysis"):
            with auth.authorized_session(self.factory) as db:
                registration = service.PREFLIGHT_REGISTRY.get(
                    "uploaded_intake" if step_id == "upload" else "shared_analysis"
                )
                attempt = claims.prepare_attempt(
                    db,
                    owner,
                    run_id=run["id"],
                    step_id=step_id,
                    handler_id=registration.handler_id,
                    handler_version=registration.handler_version,
                    retry_safe=True,
                )
                handle = claims.claim_attempt(
                    db, owner, attempt_id=attempt.id, expected_version=attempt.version
                )
                claims.start_attempt(db, handle, expected_version=attempt.version)
                row = runs.get_run(db, run["id"])
                previous = [
                    a
                    for a in runs.list_attempts(db, run_id=row.id)
                    if a.state == "succeeded"
                ]
                value = WorkerInput(
                    row.snapshot_bytes,
                    step_id,
                    tuple((a.step_id, a.output_json.encode()) for a in previous),
                )
            if before_analysis and step_id == "analysis":
                before_analysis(handle)
            with _bind_worker(handle, self.factory):
                result = service.execute_preflight_step(value)
            with auth.authorized_session(self.factory) as db:
                attempt = runs.get_attempt(db, handle.attempt_id)
                attempt = claims.register_upload(
                    db,
                    handle,
                    expected_version=attempt.version,
                    reference=result.output,
                )
                attempt = claims.commit_output(
                    db, handle, expected_version=attempt.version, output=result.output
                )
                claims.complete_attempt(
                    db, handle, expected_version=attempt.version, state="succeeded"
                )
        with self.credentials():
            links = service.list_run_reports(run["id"])
        self.assertEqual(len(links["items"]), 1)
        return links["items"][0]

    def test_admission_replay_binds_bytes_and_rejects_before_persistence(self):
        run = self.admit()
        self.assertEqual(self.admit(), run)
        changed = self.request.model_copy(
            update={
                "artifacts": [
                    ArtifactUpload(
                        name="main.tf", content='resource "aws_s3_bucket" "other" {}'
                    )
                ]
            }
        )
        with self.assertRaises(LifecycleError):
            self.admit(changed)
        with self.factory() as db:
            self.assertEqual(
                db.scalar(
                    select(func.count()).select_from(InfraAutomationArtifactManifest)
                ),
                1,
            )
            self.assertEqual(
                db.scalar(select(func.count()).select_from(AnalysisReport)), 0
            )
        bad = self.request.model_copy(
            update={
                "artifacts": [
                    ArtifactUpload(name="../main.tf", content=FILES[0][1].decode())
                ]
            }
        )
        with self.assertRaises(LifecycleError):
            self.admit(bad)

    def test_shared_pipeline_link_ai_off_and_no_report_schema_change(self):
        with patch(
            "llm.narrator.settings", replace(config.settings, narrator_enabled=False)
        ):
            link = self.execute(self.admit())
        self.assertEqual(link["report_url"], f"/reports/{link['report_id']}")
        self.assertFalse(link["approval_eligible"])
        self.assertEqual(link["provenance"]["repository_source"], "unavailable")
        self.assertTrue(link["limitations"])
        with self.credentials():
            from services.report_service import fetch_analysis_report

            report = fetch_analysis_report(link["report_id"])
        self.assertEqual(report["report_schema_version"], "v2")
        self.assertNotIn("infra_automation_provenance", report)
        with self.factory() as db:
            self.assertTrue(
                db.get(AnalysisReport, link["report_id"]).authorization_required
            )

    def test_forged_or_cancelled_capability_cannot_analyze(self):
        def corrupt(handle):
            # Run cancellation takes effect independently of the public stamp.
            with auth.authorized_session(self.factory) as db:
                row = runs.get_run(db, handle.run_id)
                row.cancel_requested = True
                row.version += 1

        with self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)):
            self.execute(self.admit(), before_analysis=corrupt)
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(AnalysisReport)), 0
            )

    def test_private_operation_rechecks_scope_role_secret_and_global_denial(self):
        from infra_automation.analysis_context import _bind_worker

        def probe(handle):
            for project, workspace, capability in (
                (200, 200, "analysis.submit"),
                (100, 101, "report.read"),
                (100, None, "report.read"),
                (100, 100, "settings.manage"),
                (100, 100, "automation.decision"),
            ):
                with self.subTest(
                    capability=capability, project=project, workspace=workspace
                ):
                    with (
                        _bind_worker(handle, self.factory),
                        auth.authorized_session() as db,
                    ):
                        with self.assertRaises(auth.TrustedAuthorizationError):
                            auth.guard_project(db, project, workspace, capability)
                        with self.assertRaises(auth.TrustedAuthorizationError):
                            auth.guard_global_configuration(db, mutation=True)
            with _bind_worker(replace(handle, owner_secret="a" * 64), self.factory):
                with auth.authorized_session() as db, self.assertRaises(LifecycleError):
                    auth.guard_project(db, 100, 100, "analysis.submit")
            with _bind_worker(handle, self.factory), auth.authorized_session() as db:
                self.assertEqual(auth.resolve_project_reference(project_id=100).id, 100)
                with self.assertRaises(auth.TrustedAuthorizationError):
                    auth.resolve_project_reference(project_id=200)

        self.execute(self.admit(), before_analysis=probe)

    def test_final_link_failure_rolls_back_report_and_artifact_files(self):
        from services.analysis_service import AnalysisPersistenceError

        with patch.object(
            service.reports, "create_link", side_effect=LifecycleError(409)
        ):
            with self.assertRaises(AnalysisPersistenceError):
                self.execute(self.admit())
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(AnalysisReport)), 0
            )
        self.assertFalse((Path(self.temp.name) / "artifacts" / "1").exists())

    def test_revocation_during_analysis_prevents_final_report(self):
        from services import analysis_service
        from services.analysis_service import AnalysisPersistenceError

        original = analysis_service.build_analysis_artifacts

        def revoke(*args, **kwargs):
            value = original(*args, **kwargs)
            with self.factory.begin() as db:
                from models.tables import ProjectMembership

                member = db.scalar(
                    select(ProjectMembership).where(
                        ProjectMembership.principal_id == "human-a",
                        ProjectMembership.project_id == 100,
                    )
                )
                member.enabled = False
                member.authorization_version += 1
            return value

        with patch.object(
            analysis_service, "build_analysis_artifacts", side_effect=revoke
        ):
            with self.assertRaises(
                (
                    LifecycleError,
                    AnalysisPersistenceError,
                    auth.TrustedAuthorizationError,
                )
            ):
                self.execute(self.admit())
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(AnalysisReport)), 0
            )

    def test_partial_input_keeps_advisory_link_and_context_todos(self):
        changed = self.request.model_copy(
            update={
                "artifacts": [
                    ArtifactUpload(
                        name="main.tf", content='resource "aws_s3_bucket" "bad" {'
                    )
                ]
            }
        )
        link = self.execute(self.admit(changed))
        self.assertFalse(link["approval_eligible"])
        self.assertTrue(link["limitations"])
        self.assertTrue(link["context_todos"])

    def test_provider_receives_structured_summary_and_parity_with_ordinary_upload(self):
        from services.analysis_service import analyze_uploaded_files
        from services.report_service import fetch_analysis_report

        with self.credentials(), auth.authorized_session():
            ordinary = analyze_uploaded_files(
                FILES, project_id=100, workspace_id=100
            ).persisted_report
        link = self.execute(self.admit())
        with self.credentials():
            linked = fetch_analysis_report(link["report_id"])
        for key in ("risk_score", "severity", "recommendation"):
            self.assertEqual(linked[key], ordinary[key])
        self.assertEqual(
            [(f["severity"], f["evidence_classification"]) for f in linked["findings"]],
            [
                (f["severity"], f["evidence_classification"])
                for f in ordinary["findings"]
            ],
        )
        self.assertNotIn("exact_plan", json.dumps(link))
        from services.confidence_ledger import evidence_law_status

        self.assertNotEqual(evidence_law_status(linked)[0], "Needs review")
        self.assertTrue(self.provider.called)
        for call in self.provider.call_args_list:
            self.assertNotIn(FILES[0][1].decode(), json.dumps(call.args[0]))

    def test_split_log_secret_rejected_before_second_chunk_is_retained(self):
        from infra_automation.state import LogChunk

        def probe(handle):
            with auth.authorized_session(self.factory) as db:
                row = runs.get_attempt(db, handle.attempt_id)
                claims.append_log(
                    db,
                    handle,
                    expected_version=row.version,
                    chunk=LogChunk(sequence=1, text="ghp_" + "X" * 10),
                )
            with auth.authorized_session(self.factory) as db:
                row = runs.get_attempt(db, handle.attempt_id)
                with self.assertRaises(LifecycleError):
                    claims.append_log(
                        db,
                        handle,
                        expected_version=row.version,
                        chunk=LogChunk(sequence=2, text="X" * 20),
                    )
                self.assertEqual(json.loads(row.logs_json)[0]["sequence"], 1)

        self.execute(self.admit(), before_analysis=probe)

    def test_real_spawned_worker_creates_link_off_loop_without_credentials(self):
        from infra_automation.coordinator import Coordinator
        from infra_automation.local_workers import SpawnProcessWorkers
        from infra_automation.storage import configure_engine_sqlite
        import time

        self.enterContext(
            patch.dict(
                os.environ,
                {
                    "NARRATOR_ENABLED": "false",
                    "LLM_PROVIDER": "ollama",
                    "LLM_MODEL": "ollama/synthetic",
                    "LLM_API_BASE": "http://127.0.0.1:9",
                    "LLM_REQUEST_TIMEOUT_SECONDS": "1",
                },
            )
        )
        configure_engine_sqlite(self.engine)
        run = self.admit()
        workers = SpawnProcessWorkers(str(self.engine.url))
        coordinator = Coordinator(
            self.factory, workers, registry=service.PREFLIGHT_REGISTRY
        )
        try:
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                coordinator.tick()
                with self.factory() as db:
                    state = runs.get_run(db, run["id"]).state
                if state in {"succeeded", "failed", "timed_out"}:
                    break
                time.sleep(0.05)
            self.assertEqual(state, "succeeded")
            with self.credentials():
                links = service.list_run_reports(run["id"])["items"]
            self.assertEqual(len(links), 1)
            self.assertFalse(links[0]["approval_eligible"])
        finally:
            coordinator.close()

    def test_linked_legacy_routes_and_artifacts_reject_actor_header_bypass(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.analyses import router
        from api.errors import (
            ApiError,
            api_error_handler,
            trusted_authorization_error_handler,
        )
        from services.artifact_snapshot_service import load_report_artifact

        link = self.execute(self.admit())
        app = FastAPI()
        app.include_router(router)
        app.add_exception_handler(ApiError, api_error_handler)
        app.add_exception_handler(
            auth.TrustedAuthorizationError, trusted_authorization_error_handler
        )
        with (
            patch("api.dependencies.identity_service", return_value=self.identity),
            TestClient(app) as client,
        ):
            for suffix in (
                "",
                "/shared",
                "/policy-adapter?integration=github-actions",
                "/enforcement-decision?integration=github-actions",
            ):
                with self.subTest(suffix=suffix):
                    response = client.get(
                        f"/api/v1/analyses/{link['report_id']}{suffix}",
                        headers={
                            "X-Actor": "human-a",
                            "X-Role": "admin",
                            "X-Project-Role": "admin",
                        },
                    )
                    self.assertEqual(response.status_code, 403, response.text)
                    self.assertNotIn("synthetic-logs", response.text)
            response = client.request(
                "DELETE", "/api/v1/analyses", json={"ids": [link["report_id"]]}
            )
            self.assertEqual(response.status_code, 403, response.text)
        with self.assertRaises(auth.TrustedAuthorizationError):
            load_report_artifact(link["report_id"], "main.tf")
        with self.factory() as db:
            self.assertIsNotNone(db.get(AnalysisReport, link["report_id"]))

    def test_linked_artifact_snapshots_cannot_be_replaced_or_deleted(self):
        from services.artifact_snapshot_service import (
            save_report_artifacts,
            delete_report_artifacts,
            load_report_artifact,
        )

        link = self.execute(self.admit())
        with self.credentials():
            original = load_report_artifact(link["report_id"], "main.tf").content
            with self.assertRaises(auth.TrustedAuthorizationError):
                save_report_artifacts(link["report_id"], {"main.tf": b"changed"})
            with self.assertRaises(auth.TrustedAuthorizationError):
                delete_report_artifacts(link["report_id"])
            self.assertEqual(
                load_report_artifact(link["report_id"], "main.tf").content, original
            )

            class ReloadedAuthorizationError(auth.TrustedAuthorizationError):
                pass

            with patch.object(
                auth, "TrustedAuthorizationError", ReloadedAuthorizationError
            ):
                with self.assertRaises(ReloadedAuthorizationError):
                    save_report_artifacts(link["report_id"], {"main.tf": b"changed"})
                with self.assertRaises(ReloadedAuthorizationError):
                    delete_report_artifacts(link["report_id"])
