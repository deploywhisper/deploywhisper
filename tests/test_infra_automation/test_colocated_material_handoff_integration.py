"""Production-derived material drives a real decision and durable handoff prepare."""

from dataclasses import replace
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from importlib import import_module
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import config
from infra_automation.collection_contracts import CollectionProvenance
from infra_automation.decisions import DecisionBinding
from infra_automation.handoff import PrepareHandoffRequest
from infra_automation.lifecycle import LifecycleError
from infra_automation.material_authority import MaterialAuthorityLedger
from infra_automation.material_probe import MaterialCustodyProbeServer
from infra_automation.preflight_contracts import SyntheticCollectionEnvelope
from infra_automation.receiver_custody import ProtectedCustody
from infra_automation.receiver_protocol import receiver_binding_from_decision
from infra_automation.runner.protocol import TaskScope
from infra_automation.targets import (
    TargetDefinition,
    TargetSnapshot,
    target_definition_bytes,
    target_snapshot_bytes,
)
from models.repositories import infra_automation_targets as targets
from models.tables import InfraAutomationArtifactManifest
from services import infra_automation_support as support
from services import project_service as auth
from services.infra_automation_decisions import DecisionRequest
from services.infra_automation_material_authority import configure_colocated_defaults
from tests.test_infra_automation.test_decisions import D


class ColocatedMaterialHandoffIntegrationTests(unittest.TestCase):
    def test_actual_retained_material_drives_review_and_handoff_prepare(self):
        from tests.test_infra_automation.test_decision_service import (
            DecisionServiceTests as _DecisionServiceTests,
        )

        case = _DecisionServiceTests(
            "test_collected_runner_provenance_matches_decision_and_rejects_new_fence"
        )
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.principal(
            "receiver-actor",
            principal_type="service",
            audience="receiver-operation-v1",
        )
        case.enterContext(patch("config.handoff_grant_key", return_value=b"g" * 32))
        case.enterContext(
            patch(
                "config.handoff_credentials",
                return_value={
                    "receiver": "receiver-secret",
                    "github": "dispatch-secret",
                },
            )
        )
        binding = case.material.binding
        definition = TargetDefinition.model_validate(
            {
                "canonical_target": binding.canonical_target,
                "allowed_scopes": ({"project_id": 100, "workspace_id": 100},),
                "environment": binding.environment,
                "receiver_id": binding.receiver_id,
                "pipeline_repository_id": binding.pipeline_repository_id,
                "pipeline_workflow_id": binding.pipeline_workflow_id,
                "pipeline_workflow_revision": binding.pipeline_workflow_revision,
                "github_owner": "owner",
                "github_repository": "repository",
                "github_workflow": "deploy.yml",
                "workflow_ref": "main",
                "credential_ref": "github",
                "receiver_credential_ref": "receiver",
            }
        )
        snapshot = TargetSnapshot(
            definition=definition,
            target_version=1,
            target_epoch=1,
            receiver_principal_id="receiver-actor",
            receiver_authentication_version=1,
            captured_at=support.utc(case.now),
        )
        snapshot_raw = target_snapshot_bytes(snapshot)
        with case.factory.begin() as db:
            targets.create_target(
                db,
                target_id=definition.canonical_target,
                definition_bytes=target_definition_bytes(definition),
                definition_digest=support.digest(target_definition_bytes(definition)),
                enabled=True,
                receiver_principal_id="receiver-actor",
                created_by="human-a",
                aliases=(),
                scopes=[(100, 100)],
                now=case.now,
            )
            targets.acquire_lock(
                db,
                lock_id="held-lock",
                target_id=definition.canonical_target,
                run_id=case.run.id,
                project_id=100,
                workspace_id=100,
                now=case.now,
            )
            targets.capture_run_target(
                db,
                run_id=case.run.id,
                handoff_step_id="handoff",
                project_id=100,
                workspace_id=100,
                target_id=definition.canonical_target,
                target_epoch=1,
                requested_alias="target",
                lock_id="held-lock",
                snapshot_bytes=snapshot_raw,
                snapshot_digest=support.digest(snapshot_raw),
                now=case.now,
            )
            manifest = db.get(InfraAutomationArtifactManifest, "manifest")
            old = SyntheticCollectionEnvelope.model_validate_json(
                manifest.collection_bytes
            )
            collection = CollectionProvenance(
                scope=TaskScope(
                    runner_id="collector",
                    project_id="100",
                    workspace_id="100",
                    run_id=case.run.id,
                    step_id="collect",
                    attempt=1,
                    fence=1,
                    coordinator_generation=1,
                    authorization_epoch=case.document.authority.authorization_epoch,
                    restore_epoch=case.document.authority.restore_epoch,
                    lease_deadline=support.utc(case.deadline),
                    audience="runner-task-v1",
                ),
                repository_id=old.repository_id,
                commit_sha=old.commit_sha,
                profile_digest=old.profile_digest,
                tool="opentofu",
                tool_version="1.13.1",
                command_digest=old.command_digest,
                argv_digest=old.argv_digest,
                raw_local_digest=old.raw_local_digest,
                sanitized_digest=old.sanitized_digest,
                exit_code=0,
                collected_at=old.collected_at,
                source_deadline=old.source_deadline,
                custody=case.material.binding.provenance.custody.model_dump(
                    mode="json"
                ),
            )
            manifest.collection_bytes = support.canonical(
                collection.model_dump(mode="json")
            )
            manifest.collection_digest = support.digest(manifest.collection_bytes)
            from infra_automation.run_resolution import runtime_workflow
            from infra_automation.state import OutputReference
            from models.repositories import infra_automation_runs as run_repository
            from models.tables import InfraAutomationReportLink
            from services.infra_automation_policy_worker import policy_output_digest

            gate = next(
                step
                for step in runtime_workflow(case.document).steps
                if step.id == "gate"
            )
            link = db.get(InfraAutomationReportLink, "link")
            policy, settings = support.policy_state(db, 100)
            output = OutputReference(
                kind="action_binding",
                reference=link.id,
                digest=policy_output_digest(
                    case.run,
                    case.document,
                    gate,
                    link,
                    policy,
                    settings,
                    snapshot,
                ),
            ).model_dump(mode="json")
            attempt = next(
                item
                for item in run_repository.list_attempts(db, run_id=case.run.id)
                if item.step_id == "gate"
            )
            attempt.output_json = support.canonical(output).decode()
            attempt.output_digest = support.digest(attempt.output_json.encode())

        with tempfile.TemporaryDirectory() as temporary:
            private_key = Ed25519PrivateKey.generate()
            root = Path(temporary).resolve()
            ledger_path = root / "material" / "ledger.json"
            profile_path = root / "profiles.json"
            private_path = root / "material-private.pem"
            public_path = root / "material-public.pem"
            probe_path = root / "probe" / "custody.sock"
            private_path.write_bytes(
                private_key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            public_path.write_bytes(
                private_key.public_key().public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )
            private_path.chmod(0o600)
            public_path.chmod(0o600)
            profiles = support.canonical(
                [
                    {
                        "profile_digest": D,
                        "tool": "opentofu",
                        "tool_version": "1.13.1",
                        "runner_version": "1.0",
                        "tags": ["isolated"],
                    }
                ]
            )
            profile_path.write_bytes(profiles)
            profile_path.chmod(0o600)
            custody = ProtectedCustody(root / "custody")
            raw_plan = b"actual protected non-destructive plan bytes"
            collected_at = datetime.now(timezone.utc).replace(
                microsecond=0
            ) - timedelta(seconds=1)
            source_deadline = collected_at + timedelta(minutes=5)
            source = {
                **case.material.binding.provenance.source.model_dump(mode="json"),
                "collected_at": support.utc(collected_at),
                "source_deadline": support.utc(source_deadline),
            }
            custody_record = custody.publish(
                "actual-custody",
                raw_plan,
                source,
                support.utc(source_deadline),
            )
            with case.factory.begin() as db:
                manifest = db.get(InfraAutomationArtifactManifest, "manifest")
                collected = CollectionProvenance.model_validate_json(
                    manifest.collection_bytes
                ).model_copy(
                    update={
                        "raw_local_digest": custody_record.raw_local_digest,
                        "collected_at": support.utc(collected_at),
                        "source_deadline": support.utc(source_deadline),
                        "custody": custody_record,
                    }
                )
                manifest.collection_bytes = support.canonical(
                    collected.model_dump(mode="json")
                )
                manifest.collection_digest = support.digest(manifest.collection_bytes)

            server = MaterialCustodyProbeServer(
                probe_path, root / "custody", private_key, timeout=0.1
            )
            server.__enter__()
            stop_probe = threading.Event()

            def serve_probe():
                while not stop_probe.is_set():
                    try:
                        server.serve_once()
                    except TimeoutError:
                        continue

            probe_thread = threading.Thread(target=serve_probe, daemon=True)
            probe_thread.start()

            def stop_server():
                stop_probe.set()
                probe_thread.join(1)
                server.__exit__(None, None, None)

            self.addCleanup(stop_server)

            recovery_status = {
                "installation_id": "installation-one",
                "generation": 7,
                "phase": "ready",
                "database": str(case.engine.url.database),
                "roots": {"custody": str(root / "custody")},
            }

            class RecoveryStore:
                def assert_ready(self, *, effects=False, session=None):
                    return recovery_status

                @contextmanager
                def participate(self):
                    yield

            store = RecoveryStore()
            case.enterContext(
                patch.object(
                    config,
                    "settings",
                    replace(
                        config.settings,
                        material_authority_profile="colocated-v1",
                        material_ledger_path=str(ledger_path),
                        material_signing_key_path=str(private_path),
                        material_verification_key_path=str(public_path),
                        material_custody_root=str(root / "custody"),
                        material_probe_socket_path=str(probe_path),
                        recovery_control_path=str(root / "recovery"),
                        collection_profiles_path=str(profile_path),
                        collection_profiles_sha256=support.digest(profiles),
                    ),
                )
            )
            case.enterContext(
                patch(
                    "infra_automation.operator_recovery.configured_store",
                    return_value=store,
                )
            )
            case.enterContext(
                patch("cli.material_authority.SessionLocal", case.factory)
            )
            from cli.material_authority import prepare as prepare_material

            publication = prepare_material(case.run.id, "decision", generation=11)
            self.assertEqual(publication["source_id"], "installation-one")
            ledger = MaterialAuthorityLedger(
                ledger_path,
                signing_key=private_key,
                verification_key=private_key.public_key(),
            )
            document = ledger.read(source_id="installation-one", recovery_generation=7)
            record = document.records[0]
            from services import infra_automation_decisions as decisions_module
            from services import infra_automation_handoffs as handoffs_module
            from services import infra_automation_material_authority as material_module

            originals = (
                material_module._configured_signature,
                decisions_module._default_service,
                handoffs_module._default_service,
            )
            self.addCleanup(
                setattr, material_module, "_configured_signature", originals[0]
            )
            self.addCleanup(setattr, decisions_module, "_default_service", originals[1])
            self.addCleanup(setattr, handoffs_module, "_default_service", originals[2])
            material_module._configured_signature = None
            service, handoffs = configure_colocated_defaults(
                ledger_path=ledger_path,
                verification_key_path=public_path,
                probe_socket_path=probe_path,
                session_factory=case.factory,
                clock=lambda: case.now,
            )
            self.assertIs(service, decisions_module._default_service)
            self.assertIs(handoffs, handoffs_module._default_service)
            self.assertIs(handoffs.decision_service, service)
            sent = []
            handoffs.ref_port = lambda value: (
                value.definition.pipeline_workflow_revision
            )
            handoffs.delivery_port = lambda envelope, credential: sent.append(envelope)
            with case.credentials():
                pending = service.request_decision(case.run.id, "decision")
            with case.credentials("reviewer"):
                approval = service.decide(
                    pending["id"],
                    DecisionRequest(
                        expected_version=pending["version"],
                        binding_digest=pending["binding_digest"],
                        outcome="approve",
                        reason="Independent production-derived review",
                    ),
                )
            with case.engine.begin() as db:
                for name, body in import_module(
                    "migrations.versions.035_add_infra_handoffs"
                ).GUARDS.items():
                    db.exec_driver_sql(f"CREATE TRIGGER {name} {body}")
            with case.credentials():
                operation = handoffs.prepare(
                    PrepareHandoffRequest(
                        project_id=100,
                        workspace_id=100,
                        approval_id=approval["id"],
                        handoff_step_id="handoff",
                        idempotency_key="production-derived",
                        reason="Prepare non-destructive qualified handoff",
                    )
                )
            self.assertEqual(operation["state"], "prepared")
            self.assertEqual(
                operation["decision_binding_digest"], record.binding_digest
            )
            self.assertEqual(sent, [])
            approved_binding = DecisionBinding.model_validate_json(
                json.dumps(approval["binding"])
            )
            with custody.verify(
                receiver_binding_from_decision(approved_binding)
            ) as held:
                self.assertEqual(held.data, raw_plan)
            ledger.write(
                document.model_copy(
                    update={
                        "records": (
                            record.model_copy(
                                update={"state": "revoked", "generation": 12}
                            ),
                        )
                    }
                )
            )
            with case.credentials(), auth.authorized_session(case.factory) as session:
                with self.assertRaises(LifecycleError):
                    service.recheck_approved(session, approval["id"])


if __name__ == "__main__":
    unittest.main()
