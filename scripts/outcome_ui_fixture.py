"""Disposable Story16.11 composed browser proof using real application services.

Start: docker compose -f scripts/compose-story16-11.yaml up -d --build
Export: docker compose -f scripts/compose-story16-11.yaml exec -T deploywhisper \
    python /tmp/outcome_fixture.py --export-fixture
Copy: docker cp deploywhisper-story16-11-deploywhisper-1:/tmp/outcome-ui-browser-fixture.json /tmp/story16-11-outcome-ui-fixture.json
Protect: chmod 600 /tmp/story16-11-outcome-ui-fixture.json
Set OUTCOME_UI_FIXTURE=/tmp/story16-11-outcome-ui-fixture.json for browser tests.
Wait for http://localhost:8080/api/v1/health before starting those tests. Never retain credentials, HTTP traces or tokens
in verification artifacts. Stop this exact Compose project after qualification.
The synthetic server ports establish contract proof, never production admission.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sys

# Read-only helper mounted beside this launcher; no existing approval lane files
# or operator database are accessed. Its complete guard runs before DB imports.
import approval_fixture as base

base.CREDENTIALS = Path("/tmp/outcome-ui-credentials.json")
base.MATERIALS = Path("/tmp/outcome-ui-materials.json")
base.BROWSER_FIXTURE = Path("/tmp/outcome-ui-browser-fixture.json")
base.LOCK = Path("/tmp/outcome-ui-fixture.lock")
ORIGINAL_MATERIAL_PORT = base.material_port
CASES = (
    "unknown",
    "accepted",
    "running",
    "observed_success",
    "verified_success",
    "verified_failure",
    "cancellation",
    "reconcile",
    "reconcile_ambiguous",
    "reconcile_corrected",
    "reconcile_lifecycle",
)
RECEIVER = "ui-proof-receiver-service"


def material_port(db, run, step_id, previous=None):
    """Build scoped synthetic custody and exact target capture before approval."""
    from infra_automation.targets import (
        TargetDefinition,
        TargetSnapshot,
        semantic_payload,
        target_definition_bytes,
        target_snapshot_bytes,
    )
    from infra_automation.decisions import binding_digest
    from models.repositories import infra_automation_targets as targets
    from services.infra_automation_engine_service import _document
    from services import infra_automation_support as support

    material = ORIGINAL_MATERIAL_PORT(db, run, step_id, previous)
    target_id = next(
        step.target_id
        for step in _document(run).definition.steps
        if step.kind == "registered_github_handoff"
    )
    now = datetime.now(timezone.utc)
    definition = TargetDefinition.model_validate_json(
        json.dumps(
            dict(
                canonical_target=target_id,
                allowed_scopes=[
                    dict(project_id=run.project_id, workspace_id=run.workspace_id)
                ],
                environment="test",
                receiver_id=material.binding.receiver_id,
                pipeline_repository_id=material.binding.pipeline_repository_id,
                pipeline_workflow_id=material.binding.pipeline_workflow_id,
                pipeline_workflow_revision=material.binding.pipeline_workflow_revision,
                github_owner="synthetic",
                github_repository="outcome-proof",
                github_workflow="deploy.yml",
                workflow_ref="main",
                credential_ref="github",
                receiver_credential_ref="receiver",
            )
        )
    )
    snapshot = TargetSnapshot(
        definition=definition,
        target_version=1,
        target_epoch=1,
        receiver_principal_id=RECEIVER,
        receiver_authentication_version=1,
        captured_at=support.utc(now),
    )
    if targets.get_target(db, target_id) is None:
        raw = target_definition_bytes(definition)
        targets.create_target(
            db,
            target_id=target_id,
            definition_bytes=raw,
            definition_digest=support.digest(raw),
            enabled=True,
            receiver_principal_id=RECEIVER,
            created_by=run.requested_by,
            aliases=(),
            scopes=[(run.project_id, run.workspace_id)],
            now=now,
        )
        lock_id = "proof-lock-" + run.id
        targets.acquire_lock(
            db,
            lock_id=lock_id,
            target_id=target_id,
            run_id=run.id,
            project_id=run.project_id,
            workspace_id=run.workspace_id,
            now=now,
        )
        raw = target_snapshot_bytes(snapshot)
        targets.capture_run_target(
            db,
            run_id=run.id,
            handoff_step_id="handoff",
            project_id=run.project_id,
            workspace_id=run.workspace_id,
            target_id=target_id,
            target_epoch=1,
            requested_alias=target_id,
            lock_id=lock_id,
            snapshot_bytes=raw,
            snapshot_digest=support.digest(raw),
            now=now,
        )
    else:
        from services.infra_automation_targets import captured_target

        _, snapshot = captured_target(db, run.id, "handoff", live=False)
    binding = material.binding.model_copy(update={"canonical_target": target_id})
    binding = binding.model_copy(
        update={"payload_digest": support.digest(semantic_payload(binding, snapshot))}
    )
    digest = binding_digest(binding)
    return replace(
        material,
        binding=binding,
        live=material.live.model_copy(
            update={
                "target_id": target_id,
                "expected_tuple_digest": digest,
                "current_tuple_digest": digest,
            }
        ),
    )


def material_witness(db, scope):
    from services.infra_automation_decisions import MaterialWitness

    # Immutable synthetic material has one generation for each retained receipt.
    return MaterialWitness(
        source_id="outcome-proof-immutable-material",
        scope_digest=scope.digest,
        generations=tuple(1 for _ in scope.receipts),
    )


def observation_port(acceptance, snapshot):
    from infra_automation.github_contracts import GithubRunObservation

    value = acceptance.model_dump(mode="json")
    for key in ("state", "operation_id", "binding_digest"):
        value.pop(key)
    return GithubRunObservation(**value, status="completed", conclusion="success")


def make_service():
    from infra_automation.github_contracts import DispatchAcceptance
    from infra_automation.receiver_protocol import validate_receiver_message
    from services.infra_automation_decisions import DecisionService
    from services.infra_automation_handoffs import HandoffService

    def deliver(envelope, credential):
        message = validate_receiver_message(envelope.message_bytes)
        binding = message.binding
        number = (
            int(hashlib.sha256(envelope.operation_id.encode()).hexdigest()[:8], 16) + 1
        )
        url = f"https://github.com/synthetic/outcome-proof/actions/runs/{number}"
        return DispatchAcceptance(
            operation_id=envelope.operation_id,
            binding_digest=message.binding_digest,
            repository_id=binding.pipeline_repository_id,
            workflow_id=binding.pipeline_workflow_id,
            workflow_revision=binding.pipeline_workflow_revision,
            workflow_ref="main",
            run_id=number,
            run_url=url,
            html_url=url,
        )

    decisions = DecisionService(
        material_port=material_port, material_witness_port=material_witness
    )
    return HandoffService(
        decision_service=decisions,
        delivery_port=deliver,
        ref_port=lambda snapshot: snapshot.definition.pipeline_workflow_revision,
        observation_port=observation_port,
    )


@contextmanager
def browser_read_sidecars():
    """Complete the older approval proof's insert-only browser read contracts.

    The approval helper deliberately retains only its decision-proof minimum.
    Normalize pending rows before their first insert; committed immutable outputs
    and retained report links are never patched after seeding.
    """
    from sqlalchemy import event, select
    from sqlalchemy.orm import Session
    from infra_automation.preflight_contracts import (
        PreflightLinkView,
        UploadedProvenance,
    )
    from models.tables import (
        AnalysisReport,
        InfraAutomationAttempt,
        InfraAutomationReportLink,
    )
    from services import infra_automation_support as support

    prepared_links = {}

    def before_flush(db, flush_context, instances):
        attempts = [row for row in db.new if isinstance(row, InfraAutomationAttempt)]
        if attempts:
            collect = next((row for row in attempts if row.step_id == "collect"), None)
            if collect is None:
                raise RuntimeError("Unexpected synthetic attempt batch.")
            manifest_id = json.loads(collect.output_json)["reference"]
            report_id = db.scalar(
                select(AnalysisReport.id)
                .where(
                    AnalysisReport.project_id == collect.project_id,
                    AnalysisReport.workspace_id == collect.workspace_id,
                )
                .order_by(AnalysisReport.id.desc())
                .limit(1)
            )
            for row in attempts:
                if not row.output_json:
                    continue
                output = json.loads(row.output_json)
                if row.step_id == "analyze":
                    link = PreflightLinkView(
                        id=output["reference"],
                        run_id=row.run_id,
                        attempt_id=row.id,
                        manifest_id=manifest_id,
                        report_id=report_id,
                        report_url=f"/reports/{report_id}",
                        provenance=UploadedProvenance(),
                        limitations=[
                            "Disposable synthetic collection proof; no production collector admission."
                        ],
                        context_todos=[],
                    )
                    raw = support.canonical(
                        link.model_dump(mode="json", exclude={"id"})
                    )
                    prepared_links[link.id] = raw
                    output["digest"] = support.digest(raw)
                    row.output_json = support.canonical(output).decode()
                row.output_digest = output["digest"]
        for row in db.new:
            if isinstance(row, InfraAutomationReportLink):
                raw = prepared_links.get(row.id)
                if raw is None:
                    raise RuntimeError("Unexpected synthetic report link.")
                row.provenance_bytes = raw
                row.digest = support.digest(raw)

    event.listen(Session, "before_flush", before_flush)
    try:
        yield
    finally:
        event.remove(Session, "before_flush", before_flush)


def seed_case(label, service):
    from infra_automation.lifecycle import CreateWorkflowRequest, PublishWorkflowRequest
    from infra_automation.handoff import (
        PrepareHandoffRequest,
        DispatchHandoffRequest,
        ReceiverCredential,
    )
    from infra_automation.receiver_http_contracts import (
        CallbackEnvelope,
        ReconcileRequest,
        callback_signing_bytes,
        source_identity_digest,
    )
    from infra_automation.receiver_protocol import ReceiverMessage
    from services import infra_automation_service, project_service
    from services.infra_automation_decisions import DecisionRequest, list_approvals

    state = base.read_private(base.CREDENTIALS)
    project = "alternate" if label == "reconcile_lifecycle" else "primary"
    scope = state["projects"][project]
    definition = base.workflow(scope["projectId"], scope["workspaceId"])
    target = "outcome-proof-" + label.replace("_", "-")
    for step in definition["steps"]:
        if "target_id" in step:
            step["target_id"] = target
    with base.requester(state):
        draft = infra_automation_service.create_workflow(
            CreateWorkflowRequest(
                project_id=scope["projectId"],
                workspace_id=scope["workspaceId"],
                name="Synthetic outcome " + label,
                definition=json.dumps(definition),
                reason="Disposable synthetic outcome qualification",
            ),
            registry_contract=base.registry(),
        )
        revision = infra_automation_service.publish_workflow(
            draft["id"],
            PublishWorkflowRequest(
                expected_version=draft["draft_version"],
                idempotency_key=secrets.token_hex(16),
                reason="Disposable synthetic outcome qualification",
            ),
            registry_contract=base.registry(),
        )
    scope.update(workflowId=draft["id"], revisionId=revision["id"])
    base.write_private(base.CREDENTIALS, state)
    with browser_read_sidecars():
        result = base.new_case("normal", project)
    state = base.read_private(base.CREDENTIALS)
    account = state["accounts"]["reviewer"]
    identity = base.identity_service()
    session = state.get("reviewerSession")
    if session is None:
        session = base.session_values(
            identity.login(account["username"], account["password"])
        )
        state["reviewerSession"] = session
        base.write_private(base.CREDENTIALS, state)
    with project_service.credential_context(
        identity, session["token"], csrf_token=session["csrf"], mutation=True
    ):
        pending = next(
            item
            for item in list_approvals(result["projectId"], result["workspaceId"])[
                "items"
            ]
            if item["id"] == result["approvalId"]
        )
        service.decision_service.decide(
            pending["id"],
            DecisionRequest(
                expected_version=pending["version"],
                binding_digest=pending["binding_digest"],
                outcome="approve",
                reason="Review synthetic outcome fixture",
            ),
        )
    with base.requester(state):
        operation = service.prepare(
            PrepareHandoffRequest(
                project_id=result["projectId"],
                workspace_id=result["workspaceId"],
                approval_id=result["approvalId"],
                handoff_step_id="handoff",
                idempotency_key=secrets.token_hex(16),
                reason="Prepare synthetic outcome fixture",
            )
        )
        operation = service.dispatch(
            operation["id"],
            DispatchHandoffRequest(
                project_id=result["projectId"],
                workspace_id=result["workspaceId"],
                expected_version=operation["version"],
                reason="Dispatch synthetic outcome fixture",
            ),
        )
    if label != "unknown":
        credential = ReceiverCredential(
            "ui-proof-receiver", os.environ["OUTCOME_UI_RECEIVER_SECRET"]
        )
        bootstrap = service.bootstrap(
            operation["id"], operation["receiver_binding_digest"], credential
        )
        service.consume(bootstrap["message"], bootstrap["grant_token"], credential)
        receiver_state = (
            "succeeded"
            if label == "verified_success"
            else "failed"
            if label == "verified_failure"
            else "running"
            if label in {"running", "cancellation"}
            else "accepted"
        )
        message = ReceiverMessage.model_validate(bootstrap["message"]).model_copy(
            update={
                "operation": "outcome"
                if receiver_state in {"succeeded", "failed"}
                else "status",
                "state": receiver_state,
                "sequence": 2,
            }
        )
        value = dict(
            version=1,
            operation_id=operation["id"],
            run_id=result["runId"],
            binding_digest=operation["receiver_binding_digest"],
            source_identity_digest=source_identity_digest(message.binding),
            nonce=secrets.token_hex(16),
            sequence=1,
            message=message.model_dump(mode="json"),
        )
        value["signature"] = (
            "sha256:"
            + hmac.new(
                credential.secret.encode(),
                callback_signing_bytes(value),
                hashlib.sha256,
            ).hexdigest()
        )
        service.callback(CallbackEnvelope.model_validate(value), credential)
    if label == "observed_success":
        with base.requester(state):
            current = service.get_operation(
                operation["id"], result["projectId"], result["workspaceId"]
            )
            service.reconcile(
                operation["id"],
                ReconcileRequest(
                    project_id=result["projectId"],
                    workspace_id=result["workspaceId"],
                    expected_version=current["version"],
                    reason="Observe synthetic carrier outcome",
                ),
            )
    if label == "cancellation":
        base.cancel_case(result["runId"])
    return dict(result, operationId=operation["id"], case=label)


def seed(profile):
    from models.database import SessionLocal
    from models.tables import IdentityAccount

    base.seed(profile)
    with SessionLocal.begin() as db:
        db.add(
            IdentityAccount(
                id=RECEIVER,
                username=RECEIVER,
                password_verifier="unusable-synthetic-service",
                principal_type="service",
                is_admin=False,
                enabled=True,
                authentication_version=1,
                created_at=datetime.now(timezone.utc),
            )
        )
    service = make_service()
    cases = {label: seed_case(label, service) for label in CASES}
    # The browser revokes this nonadmin reader during the real revocation test.
    base.membership("reviewer2", "demote")
    state = base.read_private(base.CREDENTIALS)
    state["outcomeCases"] = cases
    base.write_private(base.CREDENTIALS, state)
    from services import infra_automation_service

    with base.requester(state):
        for case in cases.values():
            infra_automation_service.list_steps(case["runId"])
            infra_automation_service.list_run_reports(case["runId"])
            service.list_for_run(case["runId"], case["projectId"], case["workspaceId"])
    return service


def reset_fixture_login_attempts():
    """Exclude seed-only logins from the unchanged real browser login budget.

    This operator-only helper is reached after the complete disposable guard.
    The same exact nonsecret limiter record remains subject to normal limits
    as soon as the browser begins authenticating.
    """
    from models.database import SessionLocal
    from models.tables import AppSetting
    from services.identity_service import LIMIT_KEY

    if LIMIT_KEY != "identity.login_limits.v1":
        raise RuntimeError("Unexpected synthetic login limiter key.")
    with SessionLocal.begin() as db:
        row = db.get(AppSetting, LIMIT_KEY)
        if row is not None:
            db.delete(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--serve", action="store_true")
    command.add_argument("--export-fixture", action="store_true")
    command.add_argument("--diagnose", action="store_true")
    args = parser.parse_args()
    if os.environ.get("OUTCOME_UI_DISPOSABLE") != "1":
        raise RuntimeError("Requires the exact disposable outcome profile.")
    profile = base.guard()
    if profile != "shared":
        raise RuntimeError("Outcome qualification requires shared identity.")
    base.material_port = material_port
    with base.fixture_lock():
        if args.serve:
            # These fresh, process-local synthetic credentials never enter public fixtures.
            receiver, dispatch = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            os.environ["OUTCOME_UI_RECEIVER_SECRET"] = receiver
            os.environ["DEPLOYWHISPER_INFRA_RECEIVER_CREDENTIALS"] = json.dumps(
                {"receiver": receiver}
            )
            os.environ["DEPLOYWHISPER_INFRA_DISPATCH_CREDENTIALS"] = json.dumps(
                {"github": dispatch}
            )
            os.environ["DEPLOYWHISPER_INFRA_GRANT_KEY"] = secrets.token_urlsafe(32)
            service = seed(profile)
            reset_fixture_login_attempts()
        elif args.diagnose:
            import traceback
            from services import infra_automation_service

            state = base.read_private(base.CREDENTIALS)
            case = state["outcomeCases"]["unknown"]
            service = make_service()
            with base.requester(state):
                for label, operation in (
                    (
                        "steps",
                        lambda: infra_automation_service.list_steps(case["runId"]),
                    ),
                    (
                        "reports",
                        lambda: infra_automation_service.list_run_reports(
                            case["runId"]
                        ),
                    ),
                    (
                        "handoffs",
                        lambda: service.list_for_run(
                            case["runId"], case["projectId"], case["workspaceId"]
                        ),
                    ),
                ):
                    try:
                        operation()
                        print(label + ": ok")
                    except Exception as error:
                        print(
                            f"{label}: {type(error).__name__} status={getattr(error, 'status_code', None)}"
                        )
                        for frame in traceback.extract_tb(error.__traceback__):
                            print(
                                f"Frame: {Path(frame.filename).name}:{frame.lineno} {frame.name}"
                            )
        else:
            state = base.read_private(base.CREDENTIALS)
            base.write_private(
                base.BROWSER_FIXTURE,
                dict(
                    version=1,
                    profile=profile,
                    accounts=dict(
                        operator=state["accounts"]["admin"],
                        revoked=state["accounts"]["reviewer2"],
                    ),
                    project=state["projects"]["primary"],
                    cases=state["outcomeCases"],
                ),
            )
            reset_fixture_login_attempts()
            print("Private browser fixture exported under /tmp (mode0600).")
    if args.serve:
        from services import infra_automation_handoffs, infra_automation_decisions

        infra_automation_handoffs._default_service = service
        infra_automation_decisions._default_service = service.decision_service
        print(
            "Disposable synthetic outcome app ready; browser fixture export is operator-only.",
            flush=True,
        )
        import app

        app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        import traceback

        for frame in traceback.extract_tb(error.__traceback__):
            print(
                f"Fixture frame: {Path(frame.filename).name}:{frame.lineno} {frame.name}",
                file=sys.stderr,
            )
        print(
            f"Disposable outcome fixture failed ({type(error).__name__}, status={getattr(error, 'status_code', None)}).",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
