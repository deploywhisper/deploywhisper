"""Co-located material authority derives and fences retained production facts."""

from pathlib import Path
import json
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from infra_automation.collection_contracts import CollectionProvenance
from infra_automation.decisions import binding_digest
from infra_automation.material_authority import (
    MaterialAuthorityCheckpoint,
    MaterialAuthorityDocument,
    MaterialAuthorityLedger,
    MaterialAuthorityRecord,
    document_digest,
)
from infra_automation.lifecycle import LifecycleError
from infra_automation.preflight_contracts import SyntheticCollectionEnvelope
from infra_automation.runner.protocol import TaskScope
from models.repositories import infra_automation_runs as runs
from models.tables import InfraAutomationArtifactManifest
from services import infra_automation_support as support
from services import project_service as auth
from services.infra_automation_material_authority import CoLocatedMaterialAuthority


class MaterialAuthorityProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger_path = Path(self.temp.name) / "authority" / "ledger.json"
        self.private_key = Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()

    def ledger(self):
        return MaterialAuthorityLedger(
            self.ledger_path,
            signing_key=self.private_key,
            verification_key=self.public_key,
        )

    def record(self, **changes):
        values = dict(
            run_id="run-one",
            step_id="decision",
            binding_digest="sha256:" + "a" * 64,
            source_digest="sha256:" + "b" * 64,
            custody_handle="custody-one",
            raw_local_digest="sha256:" + "c" * 64,
            expires_at="2030-01-01T00:00:00Z",
            generation=1,
        )
        values.update(changes)
        return MaterialAuthorityRecord(**values)

    def test_ledger_is_owner_only_atomic_and_bound_to_recovery_domain(self):
        with self.assertRaises(ValueError):
            MaterialAuthorityLedger(
                self.ledger_path,
                signing_key=self.private_key,
                verification_key=Ed25519PrivateKey.generate().public_key(),
            )
        ledger = self.ledger()
        document = MaterialAuthorityDocument(
            source_id="installation-one",
            recovery_generation=7,
            records=(self.record(),),
        )
        ledger.write(document)
        self.assertEqual(
            ledger.read(source_id="installation-one", recovery_generation=7),
            document,
        )
        self.assertEqual(self.ledger_path.stat().st_mode & 0o777, 0o600)
        reader = MaterialAuthorityLedger(
            self.ledger_path, verification_key=self.public_key
        )
        self.assertEqual(
            reader.read(source_id="installation-one", recovery_generation=7),
            document,
        )
        with self.assertRaises(ValueError):
            reader.write(document)
        original_raw = self.ledger_path.read_bytes()
        envelope = json.loads(original_raw)
        envelope["signature"] = (
            "0" if envelope["signature"][0] != "0" else "1"
        ) + envelope["signature"][1:]
        self.ledger_path.write_text(json.dumps(envelope))
        with self.assertRaises(ValueError):
            reader.read(source_id="installation-one", recovery_generation=7)
        self.ledger_path.write_bytes(original_raw)
        ledger.write(document)
        with self.assertRaises(ValueError):
            ledger.write(
                document.model_copy(
                    update={
                        "records": (
                            document.records[0].model_copy(update={"state": "revoked"}),
                        )
                    }
                )
            )
        advanced = document.model_copy(
            update={
                "records": (
                    document.records[0].model_copy(
                        update={"state": "revoked", "generation": 2}
                    ),
                )
            }
        )
        ledger.write(advanced)
        with self.assertRaises(ValueError):
            ledger.write(advanced.model_copy(update={"records": ()}))
        with self.assertRaises(ValueError):
            ledger.write(advanced.model_copy(update={"source_id": "installation-two"}))
        reset = advanced.model_copy(
            update={"source_id": "installation-two", "recovery_generation": 8}
        )
        ledger.write(reset)
        self.assertEqual(
            ledger.read(source_id="installation-two", recovery_generation=8), reset
        )
        with self.assertRaises(ValueError):
            ledger.read(source_id="installation-two", recovery_generation=7)
        self.ledger_path.unlink()
        self.ledger_path.symlink_to(Path(self.temp.name) / "outside")
        with self.assertRaises(OSError):
            ledger.read(source_id="installation-one", recovery_generation=7)

    def test_actual_retained_material_and_witness_match_operator_ledger(self):
        from tests.test_infra_automation.test_handoff_service import HandoffServiceTests

        case = HandoffServiceTests(
            "test_prepare_is_atomic_replay_stable_and_only_verifier_persists"
        )
        case.setUp()
        self.addCleanup(case.doCleanups)
        with case.factory.begin() as db:
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

        authority = CoLocatedMaterialAuthority(
            self.ledger_path,
            verification_key=self.public_key,
            recovery_status=lambda session: {
                "installation_id": "installation-one",
                "generation": 7,
            },
            custody_probe=lambda record, collection, binding: True,
            clock=lambda: case.now,
        )
        with case.credentials(), auth.authorized_session(case.factory) as session:
            run = runs.get_run(session, case.run.id)
            proposed = authority.propose_record(session, run, "decision", generation=11)
        with case.factory.begin() as db:
            manifest = db.get(InfraAutomationArtifactManifest, "manifest")
            valid_collection_digest = manifest.collection_digest
            manifest.collection_digest = "sha256:" + "0" * 64
        with case.credentials(), auth.authorized_session(case.factory) as session:
            run = runs.get_run(session, case.run.id)
            with self.assertRaises(LifecycleError):
                authority.propose_record(session, run, "decision", generation=11)
        with case.factory.begin() as db:
            manifest = db.get(InfraAutomationArtifactManifest, "manifest")
            manifest.collection_digest = valid_collection_digest
            gate = next(
                item
                for item in runs.list_attempts(db, run_id=case.run.id)
                if item.step_id == "gate"
            )
            valid_policy_output = gate.output_json
            valid_policy_output_digest = gate.output_digest
            gate.output_json = json.dumps(
                {
                    "kind": "action_binding",
                    "reference": "link",
                    "digest": "sha256:" + "0" * 64,
                }
            )
            gate.output_digest = support.digest(gate.output_json.encode())
        with case.credentials(), auth.authorized_session(case.factory) as session:
            run = runs.get_run(session, case.run.id)
            with self.assertRaises(LifecycleError):
                authority.propose_record(session, run, "decision", generation=11)
        with case.factory.begin() as db:
            gate = next(
                item
                for item in runs.list_attempts(db, run_id=case.run.id)
                if item.step_id == "gate"
            )
            gate.output_json = valid_policy_output
            gate.output_digest = valid_policy_output_digest
        wrong_custody = CoLocatedMaterialAuthority(
            self.ledger_path,
            verification_key=self.public_key,
            recovery_status=lambda session: {
                "installation_id": "installation-one",
                "generation": 7,
            },
            custody_probe=lambda record, collection, binding: False,
            clock=lambda: case.now,
        )
        with case.credentials(), auth.authorized_session(case.factory) as session:
            run = runs.get_run(session, case.run.id)
            with self.assertRaises(LifecycleError) as rejected:
                wrong_custody.propose_record(session, run, "decision", generation=11)
        self.assertEqual(rejected.exception.status_code, 503)
        self.ledger().write(
            MaterialAuthorityDocument(
                source_id="installation-one",
                recovery_generation=7,
                records=(proposed,),
            )
        )
        with case.credentials(), auth.authorized_session(case.factory) as session:
            run = runs.get_run(session, case.run.id)
            material = authority.material(session, run, "decision")
        self.assertEqual(binding_digest(material.binding), proposed.binding_digest)
        unavailable = CoLocatedMaterialAuthority(
            self.ledger_path,
            verification_key=self.public_key,
            recovery_status=lambda session: {
                "installation_id": "installation-one",
                "generation": 7,
            },
            clock=lambda: case.now,
        )
        with case.credentials(), auth.authorized_session(case.factory) as session:
            run = runs.get_run(session, case.run.id)
            with self.assertRaises(LifecycleError) as denied:
                unavailable.material(session, run, "decision")
        self.assertEqual(denied.exception.status_code, 503)
        from services.infra_automation_decisions import MaterialReadScope

        witness_scope = MaterialReadScope(
            run_id=case.run.id,
            project_id=100,
            workspace_id=100,
            receipts=(("approval", "decision", proposed.binding_digest),),
        )
        with case.credentials(), auth.authorized_session(case.factory) as session:
            witness = authority.witness(session, witness_scope)
        self.assertEqual(witness.source_id, "installation-one:g7")
        self.assertEqual(witness.generations, (11,))

    def test_revoked_records_require_a_monotonic_signed_checkpoint(self):
        ledger = self.ledger()
        first = self.record(state="revoked", generation=4)
        second = self.record(run_id="run-two", step_id="decision-two", generation=5)
        original = MaterialAuthorityDocument(
            source_id="installation-one",
            recovery_generation=7,
            records=(first, second),
        )
        ledger.write(original)
        checkpoint = MaterialAuthorityCheckpoint(
            prior_document_digest=document_digest(original),
            source_id=original.source_id,
            recovery_generation=original.recovery_generation,
            max_generation=5,
            compacted_records=1,
        )
        compacted = original.model_copy(
            update={"checkpoint": checkpoint, "records": (second,)}
        )
        ledger.write(compacted)
        self.assertEqual(ledger.read_any(), compacted)
        with self.assertRaisesRegex(ValueError, "checkpoint"):
            ledger.write(
                compacted.model_copy(
                    update={
                        "checkpoint": checkpoint.model_copy(
                            update={"compacted_records": 2}
                        )
                    }
                )
            )
        with self.assertRaisesRegex(ValueError, "retained history"):
            ledger.write(
                compacted.model_copy(
                    update={
                        "records": (
                            *compacted.records,
                            self.record(
                                run_id="run-three",
                                step_id="decision-three",
                                generation=3,
                            ),
                        )
                    }
                )
            )

    def test_cli_compacts_revoked_records_before_the_251st_publication(self):
        from cli.material_authority import _with_record

        records = tuple(
            self.record(
                run_id=f"run-{index}",
                step_id=f"decision-{index}",
                generation=index + 1,
                state="revoked",
            )
            for index in range(250)
        )
        current = MaterialAuthorityDocument(
            source_id="installation-one",
            recovery_generation=7,
            records=records,
        )
        proposed = self.record(run_id="run-new", step_id="decision-new", generation=251)
        compacted = _with_record(current, proposed)
        self.assertEqual(compacted.records, (proposed,))
        self.assertEqual(compacted.checkpoint.compacted_records, 250)
        self.assertEqual(compacted.checkpoint.max_generation, 250)
        ledger = self.ledger()
        ledger.write(current)
        ledger.write(compacted)
        self.assertEqual(ledger.read_any(), compacted)


if __name__ == "__main__":
    unittest.main()
