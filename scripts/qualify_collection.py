"""Exercise real pinned collection, private custody and receiver verification.

Only screened facts/digests are retained. Saved plans and synthetic source are
owned disposable local files, never application/public artifacts. This harness
qualifies the named offline OpenTofu profile, not Terraform or cloud IAM.
"""

from __future__ import annotations

import argparse
from importlib import import_module
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
isolation = import_module("scripts.qualify_runner_isolation")

canonical = isolation.canonical
digest = isolation.digest
FIXTURE = ROOT / "tests/fixtures/infra_automation/qualification/16_14"
IMAGE = "dw16-14-qualification:1"
CASES = {
    "no-change": b'terraform { required_version = "= 1.13.1" }\n',
    "change": b'resource "terraform_data" "example" { input = "synthetic-public-value" }\n',
    "output-limit": b'resource "terraform_data" "example" { input = "synthetic-public-value" }\n',
    "cancel-at-finalization": b'resource "terraform_data" "example" { input = "synthetic-public-value" }\n',
    "error": b'resource "terraform_data" "example" { unknown_argument = true }\n',
    "credential-reflection": b'output "public_marker" { value = "synthetic-collector-sentinel" }\n',
    "sensitive": b'output "private" {\n value = "synthetic-sensitive-marker"\n sensitive = true\n}\n',
}


KEY_CREDENTIAL = 'synthetic-collector-"sentinel'
CASES["credential-key-reflection"] = (
    'output "public_marker" { value = {'
    + json.dumps(KEY_CREDENTIAL)
    + ' = "innocent"} }\n'
).encode()


def utc(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def binding(source, custody):
    from infra_automation.receiver_protocol import ReceiverBinding

    value = json.loads(
        (
            ROOT
            / "tests/fixtures/infra_automation/qualification/16_0/contracts/valid.json"
        ).read_text()
    )["receiver"][0]["binding"]
    value.update(
        authorization_kind="exact_plan",
        screened_artifact_digests=[source["screened_transport_digest"]],
        evidence_deadline=source["source_deadline"],
        approval_deadline=source["source_deadline"],
        provenance={
            "version": 1,
            "authorization_kind": "exact_plan",
            "source": source,
            "custody": custody,
        },
    )
    return ReceiverBinding.model_validate(value)


def denied(store, value):
    try:
        with store.verify(value):
            return False
    except (ValueError, OSError):
        return True


def receiver_receipt(root, value, *, run_id="qualification-run"):
    """Real durable receiver with a local durable qualification server port."""
    from infra_automation.receiver_protocol import (
        ReceiverMessage,
        receiver_binding_digest,
        receiver_binding_from_decision,
    )
    from infra_automation.decisions import DecisionBinding
    from infra_automation.targets import (
        TargetDefinition,
        TargetSnapshot,
        semantic_payload,
    )
    from infra_automation.receiver_runtime import ReferenceReceiver
    from tests.test_infra_automation.test_receiver_runtime import Server, SECRET

    directory = root / ("receipt-server-" + value.provenance.custody.handle)
    directory.mkdir(mode=0o700)
    decision = DecisionBinding.model_validate_json(
        canonical(
            value.model_dump(mode="json")
            | {
                "project_id": int(value.project_id),
                "workspace_id": int(value.workspace_id),
                "revision_id": "qualification-revision",
            }
        )
    )
    target = TargetDefinition.model_validate_json(
        canonical(
            {
                "canonical_target": decision.canonical_target,
                "allowed_scopes": [
                    {
                        "project_id": decision.project_id,
                        "workspace_id": decision.workspace_id,
                    }
                ],
                "environment": decision.environment,
                "receiver_id": decision.receiver_id,
                "pipeline_repository_id": decision.pipeline_repository_id,
                "pipeline_workflow_id": decision.pipeline_workflow_id,
                "pipeline_workflow_revision": decision.pipeline_workflow_revision,
                "github_owner": "qualification-owner",
                "github_repository": "qualification-repository",
                "github_workflow": "receipt.yml",
                "workflow_ref": "qualification",
                "credential_ref": "qualification-dispatch",
                "receiver_credential_ref": "qualification-receiver",
            }
        )
    )
    snapshot = TargetSnapshot(
        definition=target,
        target_version=1,
        target_epoch=1,
        receiver_principal_id="qualification-receiver",
        receiver_authentication_version=1,
        captured_at=value.provenance.source.collected_at,
    )
    payload = json.loads(semantic_payload(decision, snapshot))
    decision = decision.model_copy(
        update={"payload_digest": digest(canonical(payload))}
    )
    bound = receiver_binding_from_decision(decision).model_dump(mode="json")
    message = ReceiverMessage.model_validate(
        {
            "version": 1,
            "operation": "consume",
            "operation_id": "receipt-" + value.provenance.custody.handle,
            "audience": "receiver-operation-v1",
            "binding": bound,
            "binding_digest": receiver_binding_digest(bound),
            "sequence": 1,
            "state": "consumed",
        }
    )
    (directory / "bootstrap.json").write_bytes(
        canonical(
            {
                "message": message.model_dump(mode="json"),
                "payload": payload,
                "grant_token": "never-store-grant",
                "run_id": run_id,
            }
        )
    )
    with sqlite3.connect(directory / "server.sqlite3") as db:
        db.executescript(
            "CREATE TABLE authority(receipt TEXT,allowed INTEGER); INSERT INTO authority VALUES(NULL,1); CREATE TABLE calls(name TEXT); CREATE TABLE callbacks(envelope BLOB);"
        )
    server = Server(directory)
    receiver = ReferenceReceiver(
        root / "receiver", server, SECRET, action_mode="saved_plan_receipt"
    )
    result = receiver.run(message.operation_id, message.binding_digest)
    restarted = ReferenceReceiver(
        root / "receiver", server, SECRET, action_mode="saved_plan_receipt"
    )
    again = restarted.run(message.operation_id, message.binding_digest)
    return {
        "canonical_registered_payload": payload["kind"] == "registered_github_handoff"
        and "receiver_action" not in payload,
        "same_report_identity": message.binding.report_id == value.report_id
        and message.binding.report_bytes_digest == value.report_bytes_digest,
        "real_saved_plan_receipt": result.get("verified_plan_receipts") == 1,
        "exact_digest": result.get("verified_plan_digest")
        == value.provenance.custody.raw_local_digest,
        "restart_no_duplicate": again.get("verified_plan_receipts") == 1,
        "no_deployment": result.get("deployment_performed") is False
        and result.get("counted_actions") == 0,
    }


def run(args):
    from infra_automation.receiver_custody import ProtectedCustody
    from infra_automation.runner.catalog import CatalogDocument
    from infra_automation.runner.execution import CollectorCredentials, ExecutionRunner
    from infra_automation.runner.execution_profile import ExecutionProfile
    from infra_automation.runner.protocol import TaskScope
    from infra_automation.runner.sandbox import DockerSandbox
    from infra_automation.runner.source import (
        SourceRegistration,
        load_registration,
        materialize_source,
    )

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    paths = [
        *(ROOT / "infra_automation/runner").glob("*.py"),
        ROOT / "infra_automation/receiver_custody.py",
        ROOT / "infra_automation/receiver_runtime.py",
        ROOT / "infra_automation/collection_contracts.py",
        ROOT / "infra_automation/artifact_intake.py",
        ROOT / "infra_automation/targets.py",
        ROOT / "infra_automation/receiver_protocol.py",
        ROOT / "services/content_security.py",
        ROOT / "services/infra_automation_collection.py",
        ROOT / "infra_automation/claims.py",
        ROOT / "infra_automation/unit_map.py",
        ROOT / "infra_automation/unit_contracts.py",
        ROOT / "services/infra_automation_units.py",
        ROOT / "models/repositories/infra_automation_units.py",
        ROOT / "infra_automation/trigger_contracts.py",
        ROOT / "infra_automation/trigger_signing.py",
        ROOT / "infra_automation/lifecycle.py",
        ROOT / "infra_automation/state.py",
        ROOT / "services/infra_automation_trigger_authority.py",
        ROOT / "services/infra_automation_triggers.py",
        ROOT / "services/infra_automation_policy.py",
        ROOT / "services/infra_automation_snapshots.py",
        ROOT / "services/infra_automation_engine_service.py",
        ROOT / "services/infra_automation_engine_support.py",
        ROOT / "services/project_service.py",
        ROOT / "models/repositories/infra_automation_triggers.py",
        ROOT / "config.py",
        ROOT / "infra_automation/preflight_evidence.py",
        ROOT / "models/repositories/infra_automation_reports.py",
        ROOT / "models/repositories/infra_automation_runs.py",
        ROOT / "services/infra_automation_preflight.py",
        ROOT / "services/infra_automation_decisions.py",
        ROOT / "services/infra_automation_runners.py",
        ROOT / "services/infra_automation_runner_tasks.py",
        ROOT / "services/infra_automation_collection_views.py",
        ROOT / "models/repositories/infra_automation_runners.py",
        ROOT / "tests/test_infra_automation/test_collection_intake.py",
        Path(__file__).resolve(),
        FIXTURE / "Dockerfile",
    ]
    hashes = {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in paths}
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker unavailable.")
    original_fixture, original_image = isolation.FIXTURE, isolation.IMAGE
    try:
        isolation.FIXTURE, isolation.IMAGE = FIXTURE, IMAGE
        image, pins = isolation.prepare_image(docker, args.build, output)
    finally:
        isolation.FIXTURE, isolation.IMAGE = original_fixture, original_image
    context = json.loads(isolation.command([docker, "context", "inspect"]))[0]
    host = context["Endpoints"]["docker"]["Host"]
    checks = {
        "image_source_pins": all(
            pins.get("/opt/deploywhisper/" + name)
            == digest((ROOT / "infra_automation/runner" / name).read_bytes())
            for name in ("bootstrap.py", "collector.py")
        )
    }
    cases = []
    with tempfile.TemporaryDirectory(prefix="dw16-14-qualified-") as temporary:
        root = Path(temporary).resolve()
        root.chmod(0o700)
        (root / "receiver").mkdir(mode=0o700)
        custody = ProtectedCustody(root / "receiver" / "custody")
        file_pins = []
        for path, checksum in pins.items():
            kind = (
                "provider"
                if "terraform-provider" in path
                else "lock"
                if path.endswith((".terraform.lock.hcl", "/tofurc", "/source.lock"))
                else "probe"
                if path.endswith(".py")
                else "tool"
                if path.startswith("/usr/local/")
                else "module"
            )
            file_pins.append({"path": path, "sha256": checksum, "kind": kind})
        document = CatalogDocument(
            version=1,
            image_id=image["Id"],
            files=file_pins,
            tool_versions=[{"tool": "opentofu", "version": "1.13.1"}],
        )
        catalog = root / "catalog.json"
        catalog.write_bytes(canonical(document.model_dump(mode="json")))
        catalog.chmod(0o600)
        profile = ExecutionProfile(
            image_id=image["Id"],
            memory_bytes=536870912,
            output_bytes=131072,
            credential_names=("COLLECTOR_TOKEN",),
        )
        sandbox = DockerSandbox(docker, host, profile)
        runner = ExecutionRunner(
            sandbox, catalog, digest(catalog.read_bytes()), root / "journal"
        )
        for label, content in CASES.items():
            case_root = root / label
            case_root.mkdir(mode=0o700)
            contents = {
                "main.tf": content,
                ".terraform.lock.hcl": b"# Builtin-only qualification has no external providers.\n",
                "source.lock": b"builtin-opentofu-1.13.1\n",
            }
            repository, commit, files = isolation.make_repository(case_root, contents)
            registration = SourceRegistration(
                repository_path=str(repository),
                commit=commit,
                tree_digest=digest(canonical(files)),
                lock_digests={
                    name: files[name] for name in (".terraform.lock.hcl", "source.lock")
                },
                trust="protected_revision",
            )
            registered = case_root / "source-registration.json"
            registered.write_bytes(canonical(registration.model_dump(mode="json")))
            registered.chmod(0o600)
            staging = case_root / "snapshots"
            staging.mkdir(mode=0o700)
            case_profile = (
                profile.model_copy(update={"output_bytes": 128})
                if label == "output-limit"
                else profile
            )

            class ObservedSandbox(DockerSandbox):
                def remove(self, name):
                    if label == "cancel-at-finalization":
                        runner.cancel(scope)
                    return super().remove(name)

            case_sandbox = ObservedSandbox(docker, host, case_profile)
            runner = ExecutionRunner(
                case_sandbox, catalog, digest(catalog.read_bytes()), root / "journal"
            )
            now = datetime.now(timezone.utc).replace(microsecond=0)
            expiry = utc(now + timedelta(minutes=10))
            scope = TaskScope(
                runner_id="qualification-runner",
                project_id="1",
                workspace_id="1",
                run_id="qualification-run",
                step_id=label,
                attempt=1,
                fence=1,
                coordinator_generation=1,
                authorization_epoch=1,
                restore_epoch=1,
                lease_deadline=utc(now + timedelta(seconds=90)),
                audience="runner-task-v1",
            )
            retained = []

            def finalize(raw, screened, plan_exit, argv_digest):
                source = {
                    "version": 1,
                    "kind": "collected",
                    "repository_id": "qualification-source",
                    "commit_sha": commit,
                    "collector_id": scope.runner_id,
                    "profile_digest": runner.profile_digest,
                    "screened_transport_digest": digest(
                        canonical([["plan.json", screened.decode()]])
                    ),
                    "redaction_version": 1,
                    "collected_at": utc(now),
                    "source_deadline": expiry,
                }
                record = custody.publish(label, raw, source, expiry)
                retained.append((source, record, digest(raw), len(raw)))
                return record.model_dump(mode="json")

            with materialize_source(
                load_registration(registered, digest(registered.read_bytes())), staging
            ) as snapshot:
                acceptance = None
                if label == "change":
                    from infra_automation.runner.collection_client import (
                        CollectionHandler,
                    )
                    from tests.test_infra_automation.test_collection_intake import (
                        real_collection_session,
                    )

                    executed = []

                    class ObservedRunner:
                        profile_digest = runner.profile_digest

                        def execute(self, *args, **kwargs):
                            value = runner.execute(*args, **kwargs)
                            executed.append(value)
                            return value

                    class ObservedCustody:
                        def publish(self, handle, raw, source, expiry):
                            record = custody.publish(handle, raw, source, expiry)
                            retained.append((source, record, digest(raw), len(raw)))
                            return record

                    with real_collection_session(
                        source_commit=commit,
                        profile_digest=runner.profile_digest,
                        repository_id="qualification-source",
                    ) as local:
                        handler = CollectionHandler(
                            scope=local.assignment.message.scope,
                            evidence_ttl_seconds=600,
                            execution_timeout_seconds=case_profile.timeout_seconds,
                            repository_id="qualification-source",
                            snapshot=snapshot,
                            runner=ObservedRunner(),
                            custody=ObservedCustody(),
                            tool="opentofu",
                            credential_resolver=lambda: CollectorCredentials(
                                "qualification-collector",
                                {"COLLECTOR_TOKEN": "synthetic-collector-sentinel"},
                            ),
                        )
                        handler(local.client, local.assignment)
                        result = executed[0]
                        acceptance = local.finish()
                else:
                    result = runner.execute(
                        scope,
                        "collect_plan",
                        {"tool": "opentofu"},
                        snapshot,
                        expected_profile_digest=runner.profile_digest,
                        credential_resolver=lambda: CollectorCredentials(
                            "qualification-collector",
                            {
                                "COLLECTOR_TOKEN": KEY_CREDENTIAL
                                if label == "credential-key-reflection"
                                else "synthetic-collector-sentinel"
                            },
                        ),
                        authority_check=lambda: True,
                        custody_finalizer=finalize,
                    )
            facts = {
                "case": label,
                "state": result.state,
                "finalizable": result.finalizable,
                "cleanup_complete": result.cleanup_complete,
                "exit_code": result.exit_code,
                "source_commit": commit,
                "profile_digest": runner.profile_digest,
                "screened_output_digest": result.output_digest,
                "screened_output_bytes": len(result.output.encode()),
                "custody_published": bool(retained),
            }
            checks[label + ":cleanup"] = result.cleanup_complete
            checks[label + ":screened"] = all(
                marker not in result.output
                for marker in (
                    "synthetic-sensitive-marker",
                    "synthetic-collector-sentinel",
                )
            )
            if label in ("no-change", "change"):
                checks[label + ":success"] = result.finalizable and bool(retained)
                checks[label + ":plan_exit"] = (
                    result.collection is not None
                    and result.collection.get("exit_code")
                    == (0 if label == "no-change" else 2)
                )
                if retained:
                    source, record, raw_hash, raw_size = retained[0]
                    if label == "change":
                        facts["local_service_acceptance"] = acceptance
                        for name in (
                            "authenticated_intake",
                            "shared_analysis",
                            "advisory",
                            "same_task_provenance",
                        ):
                            checks["local_service:" + name] = (
                                acceptance.get(name) is True
                            )
                    receiver_binding = binding(source, record.model_dump(mode="json"))
                    if label == "change":
                        receiver_binding = type(receiver_binding).model_validate(
                            receiver_binding.model_dump(mode="json")
                            | {
                                "report_bytes_digest": acceptance["report_digest"],
                                "report_id": acceptance["report_id"],
                                "project_id": acceptance["provenance"]["scope"][
                                    "project_id"
                                ],
                                "workspace_id": acceptance["provenance"]["scope"][
                                    "workspace_id"
                                ],
                            }
                        )
                        receiver_facts = receiver_receipt(
                            root,
                            receiver_binding,
                            run_id=acceptance["provenance"]["scope"]["run_id"],
                        )
                        facts["receiver_receipt"] = receiver_facts
                        for name, passed in receiver_facts.items():
                            checks["receiver:" + name] = passed
                    restarted = ProtectedCustody(root / "receiver" / "custody")
                    with restarted.verify(receiver_binding) as verified:
                        checks[label + ":actual_file_digest"] = (
                            digest(verified.data) == raw_hash
                            and os.fstat(verified.fd).st_size == raw_size
                        )
                    facts.update(
                        raw_local_digest=raw_hash,
                        raw_local_bytes=raw_size,
                        custody_handle=record.handle,
                    )
                    changed = receiver_binding.model_dump(mode="json")
                    changed["provenance"]["source"]["commit_sha"] = "f" * 40
                    checks[label + ":changed_source_denied"] = denied(
                        restarted, type(receiver_binding).model_validate(changed)
                    )
                    changed = receiver_binding.model_dump(mode="json")
                    changed["evidence_deadline"] = utc(now - timedelta(seconds=1))
                    checks[label + ":expired_denied"] = denied(
                        restarted, type(receiver_binding).model_validate(changed)
                    )
                    artifact = (
                        root / "receiver" / "custody" / record.handle / "artifact"
                    )
                    artifact.chmod(0o600)
                    artifact.write_bytes(b"synthetic-overwrite")
                    artifact.chmod(0o400)
                    checks[label + ":overwritten_denied"] = denied(
                        restarted, receiver_binding
                    )
                    artifact.unlink()
                    artifact.symlink_to(root / "catalog.json")
                    checks[label + ":symlink_denied"] = denied(
                        restarted, receiver_binding
                    )
            else:
                checks[label + ":no_partial_evidence"] = (
                    not result.finalizable
                    and not result.output
                    and result.output_digest is None
                    and not retained
                )
            cases.append(facts)
        checks["journal_secret_free"] = all(
            value not in (root / "journal" / "executions.sqlite3").read_bytes()
            for value in (
                b"synthetic-sensitive-marker",
                b"synthetic-collector-sentinel",
                b"synthetic-public-value",
                KEY_CREDENTIAL.encode(),
            )
        )
    checks["source_hashes_unchanged"] = hashes == {
        str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in paths
    }
    report = {
        "version": 1,
        "qualified": all(checks.values()),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "tool": "opentofu",
        "tool_version": "1.13.1",
        "image_id": image["Id"],
        "catalog": document.model_dump(mode="json"),
        "source_hashes": hashes,
        "cases": cases,
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "limitations": [
            "Offline Linux ARM64 Docker29.1.3/LinuxKit6.12.54 profile only.",
            "Terraform is not qualified; no Terraform binary was supplied.",
            "No remote backend/state or real cloud IAM/provider credential qualification.",
            "Receiver binding verification is actual protected-file admission; this harness does not dispatch GitHub actions or manufacture approval authority.",
        ],
    }
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    isolation.emit_status(report["qualified"])
    return 0 if report["qualified"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/verification/infra-automation/16-14"
    )
    raise SystemExit(run(parser.parse_args()))
