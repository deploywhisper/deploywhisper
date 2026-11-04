"""Collected transport is authenticated evidence, never caller-minted authority."""

from __future__ import annotations

from datetime import timedelta
from dataclasses import replace, dataclass
from contextlib import contextmanager
from pathlib import Path
import json
import config
from unittest.mock import patch
import unittest

from infra_automation.lifecycle import LifecycleError
from services.infra_automation_support import canonical, digest
from tests.test_infra_automation import test_runner_attempts as existing
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class CollectionIntakeTests(LifecycleCase):
    enable = existing.RunnerAttemptTests.enable
    admit = existing.RunnerAttemptTests.admit
    attempt = existing.RunnerAttemptTests.attempt
    operation = existing.RunnerAttemptTests.operation
    acquire = existing.RunnerAttemptTests.acquire
    export = existing.RunnerAttemptTests.export
    profile = existing.RunnerAttemptTests.profile
    message = existing.RunnerAttemptTests.message
    act = existing.RunnerAttemptTests.act
    source_commit = "b" * 40
    repository_id = "synthetic-repo"
    actual_custody = None
    actual_collected_at = None
    actual_deadline = None
    plan_text = None

    def setUp(self):
        existing.RunnerAttemptTests.setUp(self)

    def publish_fixture(self):
        from tests.test_infra_automation import test_workflow_snapshots as snapshots

        return snapshots.WorkflowSnapshotTests.publish_fixture(
            self,
            {
                "workflow_version": 2,
                "project_id": "100",
                "workspace_id": "100",
                "environment": "dev",
                "inputs": {"note": {"type": "string", "max_length": 100}},
                "steps": [
                    {
                        "id": "upload",
                        "kind": "admitted_collection",
                        "depends_on": [],
                        "source": {
                            "kind": "collected",
                            "repository_id": self.repository_id,
                            "commit_sha": self.source_commit,
                            "profile_digest": self.profile,
                        },
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
            },
        )

    def install_profile(self):
        manifest = canonical(
            [
                dict(
                    profile_digest=self.profile,
                    tool="opentofu",
                    tool_version="1.13.1",
                    runner_version="1.0",
                    tags=["isolated"],
                )
            ]
        )
        path = Path(self.temp.name).resolve() / "profiles.json"
        path.write_bytes(manifest)
        path.chmod(0o600)
        self.enterContext(
            patch.object(
                config,
                "settings",
                replace(
                    config.settings,
                    collection_profiles_path=str(path),
                    collection_profiles_sha256=digest(manifest),
                ),
            )
        )

    def send(self, message, **kwargs):
        from services import infra_automation_runner_tasks as tasks

        result = tasks.operate(
            message,
            self.credential,
            self.assignment["task_token"],
            now=self.now,
            **kwargs,
        )
        self.assignment["scope"] = result["scope"]
        return result

    # Reuse setup/helpers without inheriting unrelated protocol test methods below.
    def payload(self):
        from infra_automation.runner.collector import command_digests

        command, argv = command_digests("opentofu")
        artifacts = [
            {
                "name": "plan.json",
                "content": '{"format_version":"1.2","terraform_version":"1.13.1","resource_changes":[]}',
            }
        ]
        if self.plan_text is not None:
            artifacts[0]["content"] = self.plan_text
        raw_digest = digest(b"synthetic-local-plan")
        provenance = dict(
            version=1,
            kind="collected",
            scope=self.assignment["scope"],
            repository_id=self.repository_id,
            commit_sha=self.source_commit,
            profile_digest=self.profile,
            tool="opentofu",
            tool_version="1.13.1",
            command_digest=command,
            argv_digest=argv,
            raw_local_digest=raw_digest,
            sanitized_digest=digest(
                canonical([[x["name"], x["content"]] for x in artifacts])
            ),
            redaction_version=1,
            exit_code=2,
            collected_at=self.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            source_deadline=(self.now + timedelta(minutes=5)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            custody=dict(
                version=1,
                handle="opaque-original",
                raw_local_digest=raw_digest,
                expires_at=(self.now + timedelta(minutes=5)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
            ),
        )
        if self.actual_custody is not None:
            provenance["custody"] = self.actual_custody
            provenance["raw_local_digest"] = self.actual_custody["raw_local_digest"]
        if self.actual_collected_at is not None:
            # The real collection may precede this disposable analysis run.
            # Keep actual artifact/profile/custody but record service receipt time.
            provenance["collected_at"] = self.now.strftime("%Y-%m-%dT%H:%M:%SZ")
        if self.actual_deadline is not None:
            provenance["source_deadline"] = self.actual_deadline
        return dict(version=1, provenance=provenance, artifacts=artifacts)

    def test_collection_contract_rejects_unauthenticated_profile(self):
        from services.infra_automation_collection import parse_upload

        raw = canonical(self.payload())
        with self.assertRaises(LifecycleError):
            parse_upload(raw, digest(raw))

    def test_collection_wire_rejects_tampered_digest(self):
        from services.infra_automation_collection import parse_upload

        raw = canonical(self.payload())
        with self.assertRaises(LifecycleError):
            parse_upload(raw, digest(b"tampered"))

    def collect(self, payload=None):
        self.install_profile()
        self.send(self.message("claim", 1))
        raw = canonical(payload or self.payload())
        self.send(
            self.message(
                "upload", 2, atomic_upload_id="batch", upload_digest=digest(raw)
            ),
            upload_bytes=raw,
        )
        return self.send(
            self.message("complete", 3, atomic_upload_id="batch", state="succeeded")
        )

    def test_authenticated_complete_publishes_manifest_and_clears_staging(self):
        from models.tables import InfraAutomationRunnerTask
        from models.repositories import infra_automation_reports as reports
        from models.repositories import infra_automation_runs as runs
        from services import project_service as auth

        self.assertEqual(self.collect()["state"], "succeeded")
        with auth.authorized_session(self.factory) as db:
            row = runs.get_attempt(db, self.pending.id)
            output = json.loads(row.output_json)
            manifest = reports.get_manifest(db, output["reference"])
            self.assertEqual(
                manifest.digest, self.payload()["provenance"]["sanitized_digest"]
            )
            self.assertEqual(
                json.loads(manifest.collection_bytes)["scope"]["runner_id"],
                self.runner.id,
            )
            self.assertIsNone(
                db.get(InfraAutomationRunnerTask, self.pending.id).upload_bytes
            )

    def escaped_bearer_payload(self, secret, *, key):
        escaped = "".join("\\u%04x" % ord(char) for char in secret)
        reflected = (
            ('"' + escaped + '":"innocent"')
            if key
            else ('"observed":"' + escaped + '"')
        )
        text = (
            '{"format_version":"1.2","terraform_version":"1.13.1","resource_changes":[],"nested":{'
            + reflected
            + "}}"
        )
        payload = self.payload()
        payload["artifacts"][0]["content"] = text
        payload["provenance"]["sanitized_digest"] = digest(
            canonical([["plan.json", text]])
        )
        return canonical(payload)

    def test_escaped_bearers_rejected_before_artifact_persistence(self):
        from sqlalchemy import select, func
        from models.tables import (
            InfraAutomationRunnerTask,
            InfraAutomationArtifactManifest,
            InfraAutomationReportLink,
        )

        self.install_profile()
        self.send(self.message("claim", 1))
        for kind, secret in (
            ("task", self.assignment["task_token"]),
            ("runner", self.credential.token),
            ("enrollment", "enroll-v1-disposable-sentinel"),
        ):
            for key in (False, True):
                with self.subTest(kind=kind, key=key):
                    raw = self.escaped_bearer_payload(secret, key=key)
                    with self.assertRaises(LifecycleError):
                        self.send(
                            self.message(
                                "upload",
                                2,
                                atomic_upload_id="rejected",
                                upload_digest=digest(raw),
                            ),
                            upload_bytes=raw,
                        )
                    with self.factory() as db:
                        binding = db.get(InfraAutomationRunnerTask, self.pending.id)
                        self.assertIsNone(binding.upload_bytes)
                        self.assertEqual(binding.sequence, 1)
                        self.assertEqual(
                            db.scalar(
                                select(func.count()).select_from(
                                    InfraAutomationArtifactManifest
                                )
                            ),
                            0,
                        )
                        self.assertEqual(
                            db.scalar(
                                select(func.count()).select_from(
                                    InfraAutomationReportLink
                                )
                            ),
                            0,
                        )

    def test_previously_staged_escaped_bearer_cannot_finalize(self):
        from sqlalchemy import select, func
        from models.tables import (
            InfraAutomationRunnerTask,
            InfraAutomationArtifactManifest,
            InfraAutomationReportLink,
        )
        from models.repositories import infra_automation_runs as runs

        self.install_profile()
        self.send(self.message("claim", 1))
        raw = self.escaped_bearer_payload(self.assignment["task_token"], key=True)
        with self.factory.begin() as db:
            binding = db.get(InfraAutomationRunnerTask, self.pending.id)
            binding.upload_id, binding.upload_digest, binding.upload_bytes = (
                "prior-staging",
                digest(raw),
                raw,
            )
            binding.sequence = 2
        with self.assertRaises(LifecycleError):
            self.send(
                self.message(
                    "complete", 3, atomic_upload_id="prior-staging", state="succeeded"
                )
            )
        with self.factory() as db:
            self.assertIsNone(runs.get_attempt(db, self.pending.id).output_json)
            self.assertEqual(
                db.get(InfraAutomationRunnerTask, self.pending.id).sequence, 2
            )
            self.assertEqual(
                db.scalar(
                    select(func.count()).select_from(InfraAutomationArtifactManifest)
                ),
                0,
            )
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraAutomationReportLink)),
                0,
            )

    def test_legacy_artifact_list_cannot_complete_collection(self):
        from models.tables import InfraAutomationRunnerTask

        self.send(self.message("claim", 1))
        raw = canonical(
            [{"name": "main.tf", "content": 'resource "null_resource" "example" {}'}]
        )
        with self.assertRaises(LifecycleError):
            self.send(
                self.message(
                    "upload", 2, atomic_upload_id="legacy", upload_digest=digest(raw)
                ),
                upload_bytes=raw,
            )
        with self.factory() as db:
            binding = db.get(InfraAutomationRunnerTask, self.pending.id)
            self.assertIsNone(binding.upload_bytes)
            self.assertEqual(binding.sequence, 1)

    def test_prior_version_legacy_staging_cannot_finalize(self):
        from models.tables import InfraAutomationRunnerTask
        from models.repositories import infra_automation_runs as runs

        self.send(self.message("claim", 1))
        raw = canonical(
            [{"name": "main.tf", "content": 'resource "null_resource" "example" {}'}]
        )
        with self.factory.begin() as db:
            binding = db.get(InfraAutomationRunnerTask, self.pending.id)
            binding.upload_id, binding.upload_digest, binding.upload_bytes = (
                "legacy",
                digest(raw),
                raw,
            )
            binding.sequence = 2
        with self.assertRaises(LifecycleError):
            self.send(
                self.message(
                    "complete", 3, atomic_upload_id="legacy", state="succeeded"
                )
            )
        with self.factory() as db:
            self.assertEqual(runs.get_attempt(db, self.pending.id).state, "running")
            self.assertIsNone(runs.get_attempt(db, self.pending.id).output_json)
            self.assertEqual(
                db.get(InfraAutomationRunnerTask, self.pending.id).sequence, 2
            )

    def test_failed_without_upload_has_no_evidence(self):
        from models.tables import InfraAutomationRunnerTask
        from models.repositories import infra_automation_runs as runs

        self.send(self.message("claim", 1))
        self.assertEqual(
            self.send(self.message("complete", 2, state="failed"))["state"], "failed"
        )
        with self.factory() as db:
            self.assertIsNone(runs.get_attempt(db, self.pending.id).output_json)
            self.assertIsNone(
                db.get(InfraAutomationRunnerTask, self.pending.id).upload_bytes
            )

    def test_mutated_provenance_is_rejected_before_staging(self):
        from models.tables import InfraAutomationRunnerTask

        self.install_profile()
        self.send(self.message("claim", 1))
        for field, value in (
            ("commit_sha", "c" * 40),
            ("argv_digest", digest(b"wrong")),
            ("sanitized_digest", digest(b"wrong")),
            ("exit_code", 1),
            ("tool_version", "0.0.1"),
            ("source_deadline", "2020-01-01T00:00:00Z"),
        ):
            with self.subTest(field=field):
                payload = self.payload()
                payload["provenance"][field] = value
                raw = canonical(payload)
                with self.assertRaises(LifecycleError):
                    self.send(
                        self.message(
                            "upload",
                            2,
                            atomic_upload_id="batch",
                            upload_digest=digest(raw),
                        ),
                        upload_bytes=raw,
                    )
                with self.factory() as db:
                    self.assertEqual(
                        db.get(InfraAutomationRunnerTask, self.pending.id).sequence, 1
                    )
                    self.assertIsNone(
                        db.get(InfraAutomationRunnerTask, self.pending.id).upload_bytes
                    )

    def stage(self):
        self.install_profile()
        self.send(self.message("claim", 1))
        raw = canonical(self.payload())
        self.send(
            self.message(
                "upload", 2, atomic_upload_id="batch", upload_digest=digest(raw)
            ),
            upload_bytes=raw,
        )

    def test_terminal_safety_cleanup_erases_staging(self):
        from infra_automation import claims
        from models.tables import InfraAutomationRunnerTask
        from models.repositories import infra_automation_runs as runs

        self.stage()
        with self.factory() as db:
            attempt = runs.get_attempt(db, self.pending.id)
            version = attempt.version
        self.operation(
            claims.safety_cleanup,
            self.owner,
            attempt_id=self.pending.id,
            expected_version=version,
            state="timed_out",
        )
        with self.factory() as db:
            self.assertIsNone(
                db.get(InfraAutomationRunnerTask, self.pending.id).upload_bytes
            )
            self.assertEqual(runs.get_attempt(db, self.pending.id).uploads_json, "[]")

    def test_run_cancellation_erases_staging(self):
        from infra_automation import claims
        from models.tables import InfraAutomationRunnerTask
        from models.repositories import infra_automation_runs as runs

        self.stage()
        with self.factory() as db:
            version = runs.get_run(db, self.run.id).version
        self.operation(
            claims.stop_run,
            self.owner,
            run_id=self.run.id,
            expected_version=version,
            state="cancelled",
        )
        with self.factory() as db:
            self.assertIsNone(
                db.get(InfraAutomationRunnerTask, self.pending.id).upload_bytes
            )
            self.assertEqual(runs.get_attempt(db, self.pending.id).uploads_json, "[]")

    def test_revocation_erases_staging_without_minting_output(self):
        from services import infra_automation_runners as runners
        from models.tables import InfraAutomationRunnerTask
        from models.repositories import infra_automation_runs as runs

        self.stage()
        with self.credentials():
            runners.revoke(self.runner.id, reason="Synthetic revoke", now=self.now)
        with self.factory() as db:
            self.assertIsNone(
                db.get(InfraAutomationRunnerTask, self.pending.id).upload_bytes
            )
            self.assertEqual(runs.get_attempt(db, self.pending.id).uploads_json, "[]")
            self.assertIsNone(runs.get_attempt(db, self.pending.id).output_json)

    def test_sensitive_partial_and_nonfinite_plans_never_stage(self):
        self.install_profile()
        self.send(self.message("claim", 1))
        plans = [
            '{"format_version":"1.2","terraform_version":"1.13.1","resource_changes":[],"outputs":{"result":{"sensitive":true,"value":"canary"}}}',
            '{"format_version":"1.2","terraform_version":"1.13.1","resource_changes":[],"complete":false}',
            '{"format_version":"1.2","terraform_version":"1.13.1","resource_changes":[],"errored":true}',
            '{"format_version":"1.2","terraform_version":"1.13.1","resource_changes":[],"x":NaN}',
            '{"format_version":"1.2","terraform_version":"1.13.1","resource_changes":[],"x":1,"x":2}',
        ]
        for text in plans:
            with self.subTest(plan=plans.index(text)):
                payload = self.payload()
                payload["artifacts"][0]["content"] = text
                payload["provenance"]["sanitized_digest"] = digest(
                    canonical([["plan.json", text]])
                )
                raw = canonical(payload)
                with self.assertRaises(LifecycleError):
                    self.send(
                        self.message(
                            "upload",
                            2,
                            atomic_upload_id="batch",
                            upload_digest=digest(raw),
                        ),
                        upload_bytes=raw,
                    )

    def analyze_collection(self):
        from infra_automation import claims
        from infra_automation.analysis_context import _bind_worker
        from infra_automation.local_workers import WorkerInput
        from models.repositories import infra_automation_runs as runs
        from services import project_service as auth
        from services import infra_automation_preflight as service

        self.enterContext(patch("services.report_service.SessionLocal", self.factory))
        self.enterContext(
            patch("services.artifact_snapshot_service.SessionLocal", self.factory)
        )
        self.enterContext(
            patch(
                "llm.narrator.settings",
                replace(config.settings, narrator_enabled=False),
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
        with auth.authorized_session(self.factory) as db:
            reg = service.PREFLIGHT_REGISTRY.get("shared_analysis")
            attempt = claims.prepare_attempt(
                db,
                self.owner,
                run_id=self.run.id,
                step_id="analysis",
                handler_id=reg.handler_id,
                handler_version=reg.handler_version,
                retry_safe=True,
            )
            handle = claims.claim_attempt(
                db, self.owner, attempt_id=attempt.id, expected_version=attempt.version
            )
            claims.start_attempt(db, handle, expected_version=attempt.version)
            previous = runs.get_attempt(db, self.pending.id)
            value = WorkerInput(
                runs.get_run(db, self.run.id).snapshot_bytes,
                "analysis",
                (("upload", previous.output_json.encode()),),
            )
        with _bind_worker(handle, self.factory):
            result = service.execute_preflight_step(value)
        with auth.authorized_session(self.factory) as db:
            attempt = runs.get_attempt(db, handle.attempt_id)
            claims.complete_attempt(
                db, handle, expected_version=attempt.version, state="succeeded"
            )
        with self.credentials():
            links = service.list_run_reports(self.run.id)
            from services.report_service import fetch_analysis_report

            report = fetch_analysis_report(links["items"][0]["report_id"])
        self.assertEqual(links["items"][0]["provenance"]["kind"], "collected")
        self.assertEqual(report["report_schema_version"], "v2")
        self.assertEqual(result.output.kind, "report")
        return report

    def test_collected_artifact_reuses_shared_analysis_and_relational_provenance(self):
        self.collect()
        report = self.analyze_collection()
        self.assertFalse(report.get("should_block", False))


def run_real_collection_acceptance(
    plan_json, *, tool_version="1.13.1", source_commit="b" * 40, **kwargs
):
    """Actual artifact + local authenticated service proof; no live TLS claim."""
    case = CollectionIntakeTests(
        "test_collected_artifact_reuses_shared_analysis_and_relational_provenance"
    )
    case.source_commit = source_commit
    case.repository_id = kwargs.get("repository_id", "synthetic-repo")
    case.profile = kwargs.get("profile_digest", case.profile)
    case.actual_custody = kwargs.get("custody")
    case.actual_collected_at = kwargs.get("collected_at")
    case.actual_deadline = kwargs.get("source_deadline")
    case.plan_text = plan_json.decode() if isinstance(plan_json, bytes) else plan_json
    try:
        case.setUp()
        case.collect()
        report = case.analyze_collection()
        return {
            "authenticated_intake": True,
            "shared_analysis": True,
            "report_schema_version": report["report_schema_version"],
            "report_digest": digest(canonical(report)),
            "advisory": not report.get("should_block", False),
        }
    finally:
        case.doCleanups()


if __name__ == "__main__":
    unittest.main()


@dataclass
class LocalCollectionAcceptance:
    case: CollectionIntakeTests
    client: object
    assignment: object

    def finish(self):
        from models.repositories import infra_automation_runs as runs
        from models.repositories import infra_automation_reports as reports
        from services import project_service as auth

        with auth.authorized_session(self.case.factory) as db:
            attempt = runs.get_attempt(db, self.case.pending.id)
            self.case.assertEqual(attempt.state, "succeeded")
            manifest = reports.get_manifest(
                db, json.loads(attempt.output_json)["reference"]
            )
            provenance = json.loads(manifest.collection_bytes)
        report = self.case.analyze_collection()
        return {
            "authenticated_intake": True,
            "shared_analysis": True,
            "same_task_provenance": True,
            "report_id": report["id"],
            "report_schema_version": report["report_schema_version"],
            "report_digest": digest(canonical(report)),
            "advisory": not report.get("should_block", False),
            "provenance": provenance,
        }


@contextmanager
def real_collection_session(
    *, source_commit, profile_digest, repository_id="qualification-source"
):
    """Prepare actual local authenticated assignment before real tool execution.

    Uses production RunnerClient serialization and service credential checks via a
    local transport adapter. This qualifies same-task continuity, not HTTPS/TLS.
    """
    import base64
    from infra_automation.runner.client import RunnerClient, TaskAssignment
    from infra_automation.runner.protocol import parse_message
    from services import infra_automation_runner_tasks as tasks

    case = CollectionIntakeTests(
        "test_collected_artifact_reuses_shared_analysis_and_relational_provenance"
    )
    case.source_commit, case.profile, case.repository_id = (
        source_commit,
        profile_digest,
        repository_id,
    )
    try:
        case.setUp()
        case.install_profile()
        case.send(case.message("claim", 1))

        def transport(method, url, headers, body, timeout):
            case.assertEqual(
                headers["Authorization"], "Bearer " + case.credential.token
            )
            case.assertEqual(headers["X-Runner-Id"], case.runner.id)
            value = json.loads(body)
            content = None
            if url.endswith("/uploads"):
                content = base64.b64decode(value["screened_content"], validate=True)
                value = value["message"]
            result = tasks.operate(
                parse_message(value),
                case.credential,
                headers["X-Runner-Task-Token"],
                upload_bytes=content,
            )
            return 200, canonical({"data": result})

        client = RunnerClient(
            "https://local-service.invalid",
            case.runner.id,
            case.credential.token,
            transport=transport,
        )
        assignment = TaskAssignment(
            case.message("heartbeat", 2), case.assignment["task_token"]
        )
        yield LocalCollectionAcceptance(case, client, assignment)
    finally:
        case.doCleanups()
