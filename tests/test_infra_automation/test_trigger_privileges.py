"""Real signed identities retain their privilege ceiling through engine effects.

Databases, secrets and handler registrations are synthetic and isolated. These
tests prove server authorization, not TLS, collector or external delivery support.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from sqlalchemy import func, select

import config
from infra_automation import claims
from infra_automation.decisions import binding_digest, freeze_report_snapshot
from infra_automation.lifecycle import (
    LifecycleError,
    PublishWorkflowRequest,
    ValidateWorkflowRequest,
)
from infra_automation.trigger_contracts import TriggerListRequest, TriggerStatusRequest
from infra_automation.trigger_contracts import TriggerRequest
from infra_automation.trigger_signing import sign_request
from infra_automation.targets import BreakLockRequest, semantic_payload
from models.repositories import infra_automation_runs as runs
from models.repositories import project_memberships
from models.tables import (
    AnalysisReport,
    IdentityAccount,
    IdentitySession,
    InfraAutomationArtifactManifest,
    InfraAutomationAttempt,
    InfraAutomationGrant,
    InfraAutomationPolicy,
    InfraAutomationReportLink,
    RiskAssessment,
)
from services import infra_automation_service as workflows
from services import infra_automation_triggers as triggers
from services.infra_automation_trigger_authority import TriggerAuthority
from services import project_service as auth
from services import infra_automation_engine_service as engine
from services import infra_automation_support as support
from services import infra_automation_targets as targets
from services.infra_automation_decisions import DecisionRequest
from services.identity_service import IdentityError, password_verifier
from services.report_service import _serialize_report
from tests.test_infra_automation import test_handoff_service as handoff_fixture
from tests.test_infra_automation.test_engine_service import AvailableHandlers
from tests.test_infra_automation import test_trigger_intake as intake_fixture


@contextmanager
def isolated_case():
    case = intake_fixture.TriggerIntakeTests()
    try:
        case.setUp()
        yield case
    finally:
        case.doCleanups()


def provision_variant(case, principal_type, role):
    with case.credentials():
        machine = triggers.provision_principal(
            triggers.ProvisionPrincipalRequest(
                project_id=100,
                workspace_id=100,
                username=f"synthetic-{principal_type}-{role}",
                principal_type=principal_type,
                role=role,
                reason="Exercise actual signed credential privileges",
            )
        )
    case.machine = machine
    case.key.update(
        principal_id=machine["principal_id"],
        principal_type=principal_type,
        authentication_version=machine["authentication_version"],
        membership_version=machine["membership_version"],
        restore_epoch=machine["restore_epoch"],
    )
    case.write_key()


def operation(case, function, *args, **kwargs):
    with auth.authorized_session(case.factory) as db:
        return function(db, *args, now=case.now, **kwargs)


def start_machine_attempt(case, *, stop_before_claim=False):
    run = case.admit()
    # Admission uses the application's actual UTC clock. Advance the fixture's
    # injected clock to that same observed instant before exercising workers.
    case.now = datetime.now(timezone.utc)
    owner = operation(
        case, claims.acquire_coordinator, project_id=100, workspace_id=100
    )
    started = operation(
        case, claims.start_run, owner, run_id=run["id"], expected_version=run["version"]
    )
    if started is None:
        raise AssertionError("The signed run did not start.")
    attempt = operation(
        case,
        claims.prepare_attempt,
        owner,
        run_id=run["id"],
        step_id="collect",
        handler_id="synthetic-registered-collector",
        handler_version="1",
        retry_safe=False,
    )
    if stop_before_claim:
        return run, owner, attempt, None
    handle = operation(
        case, claims.claim_attempt, owner, attempt_id=attempt.id, expected_version=1
    )
    return run, owner, attempt, handle


def _copy_columns(row, **changes):
    values = {column.key: getattr(row, column.key) for column in row.__table__.columns}
    values.update(changes)
    return values


@contextmanager
def signed_handoff_case(principal_type="service"):
    """Actual signed admission/human approval, with explicitly synthetic evidence.

    The existing fixture supplies a registered target, receiver credential and
    qualified-shape material double. We create a new machine run through the real
    signed admission service; no human snapshot or principal is rewritten.
    """
    case = handoff_fixture.HandoffServiceTests()
    try:
        case.setUp()
        # The inherited fixture uses a next-second clock. Let actual admission
        # reach that instant rather than weakening any monotonic time checks.
        time.sleep(
            max(0, (case.now - datetime.now(timezone.utc)).total_seconds()) + 0.01
        )
        with case.credentials():
            machine = triggers.provision_principal(
                triggers.ProvisionPrincipalRequest(
                    project_id=100,
                    workspace_id=100,
                    username=f"synthetic-{principal_type}-handoff",
                    principal_type=principal_type,
                    role="contributor",
                    reason="Test real signed authority with a material double",
                )
            )
            targets.break_lock(
                case.snapshot.definition.canonical_target,
                BreakLockRequest(
                    project_id=100,
                    workspace_id=100,
                    expected_lock_id="held-lock",
                    expected_version=1,
                    acknowledge_uncertainty=True,
                    reason="Release the isolated template reservation",
                ),
                now=case.now,
            )
        case.machine, case.secret, case.counter = machine, b"k" * 32, 0
        case.key = {
            "key_id": "key-one",
            "principal_id": machine["principal_id"],
            "principal_type": principal_type,
            "project_id": 100,
            "workspace_id": 100,
            "allowed_revision_ids": [case.run.revision_id],
            "allowed_sources": [{"repository_id": "repo", "commit_sha": "a" * 40}],
            "allowed_origins": ["webhook"],
            "authentication_version": machine["authentication_version"],
            "membership_version": machine["membership_version"],
            "restore_epoch": machine["restore_epoch"],
            "expires_at": support.utc(case.now + timedelta(hours=1)),
            "secret_env_ref": "SYNTHETIC_TRIGGER_KEY",
        }
        path = Path(case.temp.name).resolve() / "handoff-keys.json"
        raw = json.dumps({"version": 1, "keys": [case.key]}).encode()
        path.write_bytes(raw)
        path.chmod(0o600)
        for context in (
            patch(
                "config.settings",
                replace(
                    config.settings,
                    trigger_keys_path=str(path),
                    trigger_keys_sha256=support.digest(raw),
                    identity_decision_mode="shared",
                ),
            ),
            patch.dict(os.environ, {"SYNTHETIC_TRIGGER_KEY": case.secret.hex()}),
        ):
            context.start()
            case.addCleanup(context.stop)
        payload = {
            "version": 1,
            "workflow_revision_id": case.run.revision_id,
            "project_id": 100,
            "workspace_id": 100,
            "source": {
                "repository_id": "repo",
                "commit_sha": "a" * 40,
                "origin": "webhook",
            },
            "inputs": {},
            "idempotency_key": "machine-handoff",
        }
        proof = intake_fixture.TriggerIntakeTests.signed(case, payload)
        with proof.credentials():
            admitted = triggers.request_trigger(
                TriggerRequest.model_validate(payload),
                registry=AvailableHandlers(),
                registry_contract=case.registry,
            )
        case.now = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(
            seconds=1
        )
        owner = operation(
            case, claims.acquire_coordinator, project_id=100, workspace_id=100
        )
        operation(
            case,
            claims.start_run,
            owner,
            run_id=admitted["id"],
            expected_version=admitted["version"],
        )
        # Seed only the collector/report proof, just as the existing handoff
        # fixture does. The run, requester, snapshot and target lock are real.
        with case.factory.begin() as db:
            old_report = db.get(AnalysisReport, 1)
            report = AnalysisReport(
                **_copy_columns(old_report, id=2, created_at=case.now)
            )
            report.risk_assessment = RiskAssessment(
                **_copy_columns(old_report.risk_assessment, analysis_id=None)
            )
            db.add(report)
            db.flush()
            _, report_digest = freeze_report_snapshot(_serialize_report(report))
            old_manifest = db.get(InfraAutomationArtifactManifest, "manifest")
            collection = json.loads(old_manifest.collection_bytes)
            collection.update(
                run_id=admitted["id"],
                attempt_id="signed-attempt-collect",
                collected_at=support.utc(case.now),
                source_deadline=support.utc(case.now + timedelta(minutes=10)),
            )
            collection_bytes = support.canonical(collection)
            old_link = db.get(InfraAutomationReportLink, "link")
            for step in ("collect", "analyze", "gate"):
                old = db.scalar(
                    select(InfraAutomationAttempt).where(
                        InfraAutomationAttempt.id == "attempt-" + step
                    )
                )
                output = json.loads(old.output_json) if old.output_json else None
                if output:
                    output["reference"] = (
                        "signed-link" if step == "analyze" else "signed-manifest"
                    )
                output_json = support.canonical(output).decode() if output else None
                db.add(
                    InfraAutomationAttempt(
                        **_copy_columns(
                            old,
                            sequence=None,
                            id="signed-attempt-" + step,
                            run_id=admitted["id"],
                            requested_by=machine["principal_id"],
                            input_digest=admitted["input_digest"],
                            created_at=case.now,
                            last_observed_at=case.now,
                            deadline_at=case.now + timedelta(minutes=10),
                            output_json=output_json,
                            output_digest=support.digest(output_json.encode())
                            if output_json
                            else None,
                        )
                    )
                )
            db.add(
                InfraAutomationArtifactManifest(
                    **_copy_columns(
                        old_manifest,
                        id="signed-manifest",
                        run_id=admitted["id"],
                        requested_by=machine["principal_id"],
                        collection_bytes=collection_bytes,
                        collection_digest=support.digest(collection_bytes),
                        created_at=case.now,
                    )
                )
            )
            db.flush()
            db.add(
                InfraAutomationReportLink(
                    **_copy_columns(
                        old_link,
                        id="signed-link",
                        run_id=admitted["id"],
                        requested_by=machine["principal_id"],
                        attempt_id="signed-attempt-analyze",
                        manifest_id="signed-manifest",
                        report_id=2,
                        created_at=case.now,
                    )
                )
            )
            case.run = runs.get_run(db, admitted["id"])
            case.document = engine._document(case.run)
        with case.credentials(), auth.authorized_session() as db:
            run = runs.get_run(db, admitted["id"])
            snapshot = targets.target_for_decision(
                db, run, engine._document(run), "decision"
            )
        provenance = case.material.binding.provenance.model_dump(mode="json")
        provenance["source"].update(
            collected_at=support.utc(case.now),
            source_deadline=support.utc(case.now + timedelta(minutes=10)),
        )
        provenance["custody"]["expires_at"] = support.utc(
            case.now + timedelta(minutes=10)
        )
        values = case.material.binding.model_dump(mode="json")
        values.update(
            report_id=2,
            report_bytes_digest=report_digest,
            provenance=provenance,
            evidence_deadline=support.utc(case.now + timedelta(minutes=10)),
            approval_deadline=support.utc(case.now + timedelta(minutes=5)),
        )
        binding = type(case.material.binding).model_validate_json(json.dumps(values))
        binding = binding.model_copy(
            update={
                "payload_digest": support.digest(semantic_payload(binding, snapshot))
            }
        )
        digest = binding_digest(binding)
        case.material = replace(
            case.material,
            binding=binding,
            evidence=case.material.evidence.model_copy(
                update={
                    "collected_at": case.now,
                    "evidence_deadline": case.now + timedelta(minutes=10),
                }
            ),
            live=case.material.live.model_copy(
                update={
                    "expected_tuple_digest": digest,
                    "current_tuple_digest": digest,
                    "approval_deadline": case.now + timedelta(minutes=5),
                    "custody_deadline": case.now + timedelta(minutes=10),
                    "source_deadline": case.now + timedelta(minutes=10),
                }
            ),
        )
        with case.credentials():
            pending = case.service.request_decision(case.run.id, "decision")
        with case.credentials("reviewer"):
            case.approval = case.service.decide(
                pending["id"],
                DecisionRequest(
                    expected_version=pending["version"],
                    binding_digest=pending["binding_digest"],
                    outcome="approve",
                    reason="Human review of the signed machine request",
                ),
            )
        yield case
    finally:
        case.doCleanups()


class TriggerPrivilegeTests(unittest.TestCase):
    def test_real_issuer_matrix_never_grants_human_authority(self):
        for principal_type in ("service", "agent"):
            for role in ("contributor", "read-only"):
                with (
                    self.subTest(kind=principal_type, role=role),
                    isolated_case() as case,
                ):
                    provision_variant(case, principal_type, role)
                    validation = ValidateWorkflowRequest(
                        project_id=100,
                        workspace_id=100,
                        definition=json.dumps(case.definition()),
                    )
                    proof = case.signed(
                        validation.model_dump(mode="json"),
                        path="/api/v1/infra-automation/triggers/validate",
                    )
                    with proof.credentials():
                        result = triggers.validate_signed(validation)
                        self.assertTrue(result["valid"])
                        with self.assertRaises(auth.TrustedAuthorizationError):
                            workflows.publish_workflow(
                                case.workflow,
                                PublishWorkflowRequest(
                                    expected_version=2,
                                    idempotency_key="forbidden-publication",
                                    reason="A machine must not publish",
                                ),
                                registry_contract=case.registry,
                            )
                        with auth.authorized_session() as db:
                            for capability in (
                                "automation.decision",
                                "automation.admin",
                                "role.manage",
                                "settings.manage",
                            ):
                                with self.subTest(capability=capability):
                                    with self.assertRaises(
                                        auth.TrustedAuthorizationError
                                    ):
                                        auth.guard_project(
                                            db, 100, 100, capability, mutation=True
                                        )
                    page_request = TriggerListRequest(version=1)
                    listing = case.signed(
                        page_request.model_dump(mode="json"),
                        path="/api/v1/infra-automation/triggers/list",
                    )
                    with listing.credentials():
                        self.assertEqual(
                            triggers.signed_list(page_request)["items"], []
                        )
                    if role == "contributor":
                        run = case.admit()
                        status_request = TriggerStatusRequest(
                            version=1, run_id=run["id"]
                        )
                        read = case.signed(
                            status_request.model_dump(mode="json"),
                            path="/api/v1/infra-automation/triggers/status",
                        )
                        with read.credentials():
                            result = triggers.signed_status(status_request)
                        self.assertEqual(
                            result["origin"]["principal_type"], principal_type
                        )
                    else:
                        with self.assertRaises(auth.TrustedAuthorizationError):
                            case.admit()
                    # Correct password material still cannot turn a nonhuman
                    # account into a human login or recovery/session credential.
                    password = "synthetic human-password denial proof"
                    with case.factory.begin() as db:
                        row = db.get(IdentityAccount, case.machine["principal_id"])
                        row.password_verifier = password_verifier(password)
                        username = row.username
                    with self.assertRaises(IdentityError):
                        case.identity.login(username, password)
                    with self.assertRaises(IdentityError):
                        case.identity.issue_recovery_credential(username)
                    with self.assertRaises(IdentityError):
                        case.identity.resolve_session(proof.token)
                    with case.factory() as db:
                        self.assertEqual(
                            db.scalar(
                                select(func.count())
                                .select_from(IdentitySession)
                                .where(
                                    IdentitySession.principal_id
                                    == case.machine["principal_id"]
                                )
                            ),
                            0,
                        )

    def test_read_only_rotation_can_observe_its_previously_admitted_run(self):
        for principal_type in ("service", "agent"):
            with self.subTest(kind=principal_type), isolated_case() as case:
                provision_variant(case, principal_type, "contributor")
                run = case.admit()
                with case.credentials():
                    member = auth.assign_project_membership(
                        100, case.machine["principal_id"], "read-only", 100
                    )
                with case.factory() as db:
                    case.key["authentication_version"] = db.get(
                        IdentityAccount, case.machine["principal_id"]
                    ).authentication_version
                case.key["membership_version"] = member.authorization_version
                case.write_key()
                status_request = TriggerStatusRequest(version=1, run_id=run["id"])
                proof = case.signed(
                    status_request.model_dump(mode="json"),
                    path="/api/v1/infra-automation/triggers/status",
                )
                with proof.credentials():
                    self.assertEqual(
                        triggers.signed_status(status_request)["id"],
                        run["id"],
                    )
                case.payload["idempotency_key"] = "cannot-request-after-downscope"
                with self.assertRaises(auth.TrustedAuthorizationError):
                    case.admit()

    def test_verified_context_rechecks_all_live_credential_and_scope_versions(self):
        mutations = (
            "disabled",
            "authentication_version",
            "membership_version",
            "membership_disabled",
            "membership_scope",
            "membership_role",
            "restore_epoch",
            "expiry",
            "rotation",
        )
        for principal_type in ("service", "agent"):
            for mutation in mutations:
                with (
                    self.subTest(kind=principal_type, mutation=mutation),
                    isolated_case() as case,
                ):
                    provision_variant(case, principal_type, "contributor")
                    proof = case.signed()
                    with case.factory.begin() as db:
                        account = db.get(IdentityAccount, case.machine["principal_id"])
                        member = project_memberships.get_membership(
                            db, principal_id=account.id, project_id=100
                        )
                        if mutation == "disabled":
                            account.enabled = False
                        elif mutation == "authentication_version":
                            account.authentication_version += 1
                        elif mutation == "membership_version":
                            member.authorization_version += 1
                        elif mutation == "membership_disabled":
                            member.enabled = False
                        elif mutation == "membership_scope":
                            member.workspace_id = 101
                        elif mutation == "membership_role":
                            member.role = "admin"
                        elif mutation == "restore_epoch":
                            db.get(InfraAutomationPolicy, 100).restore_epoch += 1
                    if mutation == "expiry":
                        case.now += timedelta(hours=1)
                    environment = (
                        {"SYNTHETIC_TRIGGER_KEY": (b"x" * 32).hex()}
                        if mutation == "rotation"
                        else {}
                    )
                    with patch.dict(os.environ, environment), proof.credentials():
                        with auth.authorized_session() as db:
                            with self.assertRaises(
                                (auth.TrustedAuthorizationError, LifecycleError)
                            ):
                                auth.guard_project(db, 100, 100, "automation.read")

    def test_real_machine_authority_reaches_attempt_start(self):
        for principal_type in ("service", "agent"):
            with self.subTest(kind=principal_type), isolated_case() as case:
                provision_variant(case, principal_type, "contributor")
                run, _, _, handle = start_machine_attempt(case)
                self.assertIsNotNone(handle)
                started = operation(
                    case, claims.start_attempt, handle, expected_version=2
                )
                self.assertEqual(started.state, "running")
                with case.factory() as db:
                    self.assertEqual(
                        runs.get_run(db, run["id"]).requested_by,
                        case.machine["principal_id"],
                    )

    def test_human_review_and_real_handoff_preserve_machine_request_origin(self):
        for principal_type in ("service", "agent"):
            with (
                self.subTest(kind=principal_type),
                signed_handoff_case(principal_type) as case,
            ):
                operation_view = case.prepare()
                case.dispatch(operation_view)
                envelope = case.sent[0]
                receipt = case.handoffs.consume(
                    envelope.message_bytes, envelope.grant_token, case.receiver
                )
                self.assertEqual(receipt["receipt"]["state"], "consumed")
                with case.credentials():
                    view = engine.get_run(case.run.id)
                self.assertEqual(view["origin"]["principal_type"], principal_type)
                self.assertEqual(view["requested_by"], case.machine["principal_id"])
                self.assertEqual(case.approval["reviewer_id"], "reviewer")
                self.assertEqual(case.approval["decision_kind"], "independent-approval")

    def test_key_revocation_blocks_real_dispatch_and_consume_without_releasing_lock(
        self,
    ):
        for boundary in ("dispatch", "consume"):
            with self.subTest(boundary=boundary), signed_handoff_case() as case:
                operation_view = case.prepare()
                if boundary == "consume":
                    case.dispatch(operation_view)
                with patch.dict(
                    os.environ, {"SYNTHETIC_TRIGGER_KEY": (b"x" * 32).hex()}
                ):
                    with self.assertRaises(
                        (auth.TrustedAuthorizationError, LifecycleError)
                    ):
                        if boundary == "dispatch":
                            case.dispatch(operation_view)
                        else:
                            envelope = case.sent[0]
                            case.handoffs.consume(
                                envelope.message_bytes,
                                envelope.grant_token,
                                case.receiver,
                            )
                self.assertEqual(len(case.sent), 0 if boundary == "dispatch" else 1)
                with case.factory() as db:
                    grant = db.scalar(
                        select(InfraAutomationGrant).where(
                            InfraAutomationGrant.operation_id == operation_view["id"]
                        )
                    )
                    self.assertEqual(grant.status, "available")
                    self.assertIsNone(grant.receipt_bytes)
                    held = targets.repository.get_held_lock(
                        db, case.material.binding.canonical_target
                    )
                    self.assertEqual(held.run_id, case.run.id)

    def test_observed_future_clock_cannot_revive_dispatch_or_consumption(self):
        for boundary in ("dispatch", "consume"):
            with self.subTest(boundary=boundary), signed_handoff_case() as case:
                prepared = case.prepare()
                if boundary == "consume":
                    case.dispatch(prepared)
                original_now = case.now
                later_key = {
                    **case.key,
                    "key_id": "later-clock-key",
                    "expires_at": support.utc(case.now + timedelta(hours=3)),
                }
                raw = json.dumps({"version": 1, "keys": [case.key, later_key]}).encode()
                Path(config.settings.trigger_keys_path).write_bytes(raw)
                with patch(
                    "config.settings",
                    replace(config.settings, trigger_keys_sha256=support.digest(raw)),
                ):
                    case.now += timedelta(hours=2)
                    fields = dict(
                        key_id=later_key["key_id"],
                        method="POST",
                        path="/api/v1/infra-automation/triggers/list",
                        timestamp=str(int(case.now.timestamp())),
                        nonce="future-clock-control-000000",
                        body=b'{"version":1}',
                    )
                    later = TriggerAuthority(
                        **fields,
                        signature=sign_request(secret=case.secret, **fields),
                        session_factory=case.factory,
                        now=lambda: case.now,
                    )
                    later.reserve_nonce()
                    case.now = original_now
                    with self.assertRaises(LifecycleError) as caught:
                        if boundary == "dispatch":
                            case.dispatch(prepared)
                        else:
                            envelope = case.sent[0]
                            case.handoffs.consume(
                                envelope.message_bytes,
                                envelope.grant_token,
                                case.receiver,
                            )
                    self.assertEqual(caught.exception.status_code, 503)
                    with case.factory() as db:
                        grant = db.scalar(
                            select(InfraAutomationGrant).where(
                                InfraAutomationGrant.operation_id == prepared["id"]
                            )
                        )
                        self.assertEqual(grant.status, "available")
                        self.assertIsNone(grant.receipt_bytes)
                self.assertEqual(len(case.sent), 0 if boundary == "dispatch" else 1)

    def test_revocation_blocks_real_claim_and_attempt_start_without_progress(self):
        for boundary in ("claim", "start"):
            for mutation in (
                "rotation",
                "disabled",
                "authentication_version",
                "membership_version",
                "membership_disabled",
                "membership_scope",
                "membership_role",
                "restore_epoch",
            ):
                with (
                    self.subTest(boundary=boundary, mutation=mutation),
                    isolated_case() as case,
                ):
                    run, owner, attempt, handle = start_machine_attempt(
                        case, stop_before_claim=boundary == "claim"
                    )
                    with case.factory.begin() as db:
                        account = db.get(IdentityAccount, case.machine["principal_id"])
                        member = project_memberships.get_membership(
                            db, principal_id=account.id, project_id=100
                        )
                        if mutation == "disabled":
                            account.enabled = False
                        elif mutation == "authentication_version":
                            account.authentication_version += 1
                        elif mutation == "membership_version":
                            member.authorization_version += 1
                        elif mutation == "membership_disabled":
                            member.enabled = False
                        elif mutation == "membership_scope":
                            member.workspace_id = 101
                        elif mutation == "membership_role":
                            member.role = "admin"
                        elif mutation == "restore_epoch":
                            db.get(InfraAutomationPolicy, 100).restore_epoch += 1
                    with patch.dict(
                        os.environ,
                        {"SYNTHETIC_TRIGGER_KEY": (b"x" * 32).hex()}
                        if mutation == "rotation"
                        else {},
                    ):
                        with self.assertRaises(
                            (auth.TrustedAuthorizationError, LifecycleError)
                        ):
                            if boundary == "claim":
                                operation(
                                    case,
                                    claims.claim_attempt,
                                    owner,
                                    attempt_id=attempt.id,
                                    expected_version=1,
                                )
                            else:
                                operation(
                                    case,
                                    claims.start_attempt,
                                    handle,
                                    expected_version=2,
                                )
                    with case.factory() as db:
                        row = runs.get_attempt(db, attempt.id)
                        self.assertEqual(
                            row.state, "pending" if boundary == "claim" else "claimed"
                        )
                        self.assertEqual(
                            runs.get_run(db, run["id"]).requested_by,
                            case.machine["principal_id"],
                        )

    def test_real_decision_entrypoint_denies_each_machine_kind_and_role(self):
        for principal_type in ("service", "agent"):
            for role in ("contributor", "read-only"):
                with (
                    self.subTest(kind=principal_type, role=role),
                    signed_handoff_case(principal_type) as case,
                ):
                    if role == "read-only":
                        with case.credentials():
                            member = auth.assign_project_membership(
                                100, case.machine["principal_id"], role, 100
                            )
                        with case.factory() as db:
                            case.key["authentication_version"] = db.get(
                                IdentityAccount, case.machine["principal_id"]
                            ).authentication_version
                        case.key["membership_version"] = member.authorization_version
                        intake_fixture.TriggerIntakeTests.write_key(case)
                    time.sleep(
                        max(0, (case.now - datetime.now(timezone.utc)).total_seconds())
                        + 0.01
                    )
                    proof = intake_fixture.TriggerIntakeTests.signed(case, body=b"{}")
                    with proof.credentials():
                        with auth.authorized_session() as db:
                            grant = auth.guard_project(db, 100, 100, "automation.read")
                            self.assertEqual(
                                grant.principal.principal_type, principal_type
                            )
                        with self.assertRaises(auth.TrustedAuthorizationError):
                            case.service.decide(
                                case.approval["id"],
                                DecisionRequest(
                                    expected_version=case.approval["version"],
                                    binding_digest=case.approval["binding_digest"],
                                    outcome="approve",
                                    reason="Machine decision must remain forbidden",
                                ),
                            )
