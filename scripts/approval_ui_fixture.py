"""Disposable Story16.9 browser proof only; synthetic material is not admission.

Mount read-only in the runtime image. --serve seeds a new tmpfs database and
installs a scoped material port in that process before starting the real app.
Other commands are operator-only docker-exec helpers, never HTTP endpoints.
Credentials stay in a private /tmp file; stdout contains only safe case IDs.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import tempfile

CREDENTIALS = Path("/tmp/approval-ui-credentials.json")
MATERIALS = Path("/tmp/approval-ui-materials.json")
BROWSER_FIXTURE = Path("/tmp/approval-ui-browser-fixture.json")
LOCK = Path("/tmp/approval-ui-fixture.lock")
DATABASE = "sqlite:////app/data/deploywhisper.db"
ORIGIN = "http://localhost:8080"
DIGEST = "sha256:" + "a" * 64
CASES = (
    "normal",
    "high",
    "critical",
    "no-go",
    "self",
    "expiry",
    "pending-allowhardblock",
)


def guard() -> str:
    """Check the complete disposable boundary before importing DB-owning code."""
    required = {
        "APPROVAL_UI_DISPOSABLE": "1",
        "DEPLOYWHISPER_IDENTITY_PROFILE": "local-development",
        "DEPLOYWHISPER_IDENTITY_ORIGIN": ORIGIN,
        "DEPLOYWHISPER_AUTHORIZATION_PROFILE": "verified",
        "DATABASE_URL": DATABASE,
        "APP_BASE_URL": ORIGIN,
    }
    profile = os.environ.get("DEPLOYWHISPER_IDENTITY_DECISION_MODE")
    if (
        not Path("/.dockerenv").is_file()
        or os.geteuid() == 0
        or profile not in {"shared", "single-operator"}
        or any(os.environ.get(key) != value for key, value in required.items())
        or Path.cwd() != Path("/app")
        or Path("/app/data").is_symlink()
    ):
        raise RuntimeError("Requires the exact nonroot disposable Compose profile.")
    mounts = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        before, after = line.split(" - ", 1)
        fields = before.split()
        if fields[4] == "/app/data":
            mounts.append(after.split()[0])
    if mounts != ["tmpfs"]:
        raise RuntimeError("The exact /app/data mount must be disposable tmpfs.")
    database = Path("/app/data/deploywhisper.db")
    if database.is_symlink() or database.resolve().parent != Path("/app/data"):
        raise RuntimeError("Unexpected database path.")
    os.umask(0o077)
    sys.path.insert(0, "/app")
    import config

    if (
        config.settings.database_url != DATABASE
        or config.settings.identity_profile != "local-development"
        or config.settings.identity_origin != ORIGIN
        or config.settings.identity_decision_mode != profile
    ):
        raise RuntimeError("Loaded application configuration differs from the fixture.")
    return profile


def read_private(path: Path) -> dict:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or not 0 < metadata.st_size <= 4_194_304
        ):
            raise RuntimeError("Fixture must be an owned bounded mode-0600 file.")
        with os.fdopen(descriptor, "r") as stream:
            descriptor = -1
            value = json.load(stream)
        if type(value) is not dict or value.get("version") != 1:
            raise RuntimeError("Unsupported fixture state.")
        return value
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def write_private(path: Path, value: dict) -> None:
    if path not in {CREDENTIALS, MATERIALS, BROWSER_FIXTURE}:
        raise RuntimeError("Unexpected fixture destination.")
    if path.exists() or path.is_symlink():
        read_private(path)
    descriptor, temporary = tempfile.mkstemp(prefix="approval-ui-", dir="/tmp")
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, separators=(",", ":"), allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def fixture_lock():
    descriptor = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise RuntimeError("Unexpected fixture lock.")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def identity_service():
    from services.identity_service import IdentityService

    return IdentityService(security_profile="local-development", trusted_origin=ORIGIN)


def session_values(issued) -> dict:
    return {
        "token": issued.token.get_secret_value(),
        "csrf": issued.csrf_token.get_secret_value(),
    }


@contextmanager
def requester(state: dict):
    """Reuse real authenticated admin credentials; browser logins may revoke them."""
    from services import project_service
    from services.identity_service import IdentityError

    identity = identity_service()
    session = state.get("requesterSession", {})
    try:
        principal = identity.resolve_session(
            session.get("token", ""), csrf_token=session.get("csrf", "")
        )
        if principal.principal_id != state["accounts"]["admin"]["principalId"]:
            raise IdentityError()
    except IdentityError:
        account = state["accounts"]["admin"]
        session = session_values(
            identity.login(account["username"], account["password"])
        )
        state["requesterSession"] = session
        write_private(CREDENTIALS, state)
    with project_service.credential_context(
        identity, session["token"], csrf_token=session["csrf"], mutation=True
    ):
        yield identity


def registry():
    from infra_automation.contracts import ProfileContract, RegistryContract

    return RegistryContract(
        profiles=(
            ProfileContract(
                digest=DIGEST, tool="opentofu", authorization_kinds=("exact_plan",)
            ),
        )
    )


def workflow(project_id: int, workspace_id: int) -> dict:
    def ref(step, output):
        return {"ref": "step", "step_id": step, "output": output}

    return {
        "workflow_version": 2,
        "project_id": str(project_id),
        "workspace_id": str(workspace_id),
        "environment": "test",
        "inputs": {},
        "steps": [
            {
                "id": "collect",
                "kind": "admitted_collection",
                "depends_on": [],
                "source": {
                    "kind": "collected",
                    "repository_id": "ui-proof-repository",
                    "commit_sha": "a" * 40,
                    "profile_digest": DIGEST,
                },
            },
            {
                "id": "analyze",
                "kind": "shared_analysis",
                "depends_on": ["collect"],
                "artifact": ref("collect", "screened_artifacts"),
            },
            {
                "id": "gate",
                "kind": "policy_evaluation",
                "depends_on": ["analyze"],
                "report": ref("analyze", "report"),
                "target_id": "ui-proof-target",
                "environment": "test",
                "authorization_kind": "exact_plan",
            },
            {
                "id": "decision",
                "kind": "human_decision",
                "depends_on": ["gate"],
                "binding": ref("gate", "action_binding"),
            },
            {
                "id": "handoff",
                "kind": "registered_github_handoff",
                "depends_on": ["decision"],
                "binding": ref("gate", "action_binding"),
                "decision": ref("decision", "decision_receipt"),
                "target_id": "ui-proof-target",
                "environment": "test",
                "authorization_kind": "exact_plan",
            },
        ],
    }


def seed(profile: str) -> None:
    from sqlalchemy import select
    from infra_automation.lifecycle import (
        AutomationSettings,
        CreateWorkflowRequest,
        PublishWorkflowRequest,
        UpdateSettingsRequest,
    )
    from models.database import SessionLocal, init_db
    from models.tables import IdentityAccount
    from services import (
        project_service,
        infra_automation_policy,
        infra_automation_service,
    )
    from services.settings_service import save_policy_adapter_settings

    if CREDENTIALS.exists() or MATERIALS.exists():
        raise RuntimeError(
            "Refusing existing fixture files; start a fresh disposable lane."
        )
    init_db()
    with SessionLocal() as db:
        if db.scalar(select(IdentityAccount.id).limit(1)) is not None:
            raise RuntimeError("Refusing a database with existing accounts.")
    identity = identity_service()
    suffix = secrets.token_hex(5)
    accounts = {
        "admin": {
            "username": f"ui-proof-approval-admin-{suffix}",
            "password": secrets.token_urlsafe(32),
        }
    }
    admin = accounts["admin"]
    setup = identity.issue_setup_credential()
    principal = identity.bootstrap(
        setup.token.get_secret_value(), admin["username"], admin["password"]
    )
    admin["principalId"] = principal.principal_id
    projects = {}
    # Bootstrap invalidates the administrator session. Each subsequent bootstrap
    # authenticates again; no direct membership/audit repository bypass is used.
    session = session_values(identity.login(admin["username"], admin["password"]))
    for label in ("primary", "alternate"):
        with project_service.credential_context(
            identity, session["token"], csrf_token=session["csrf"], mutation=True
        ):
            project = project_service.create_project(
                project_key=f"ui-proof-approval-{label}-{suffix}",
                display_name=f"Approval proof {label}",
            )
            project_service.bootstrap_project_membership(project.id)
        session = session_values(identity.login(admin["username"], admin["password"]))
        with project_service.credential_context(
            identity, session["token"], csrf_token=session["csrf"], mutation=True
        ):
            workspace = project_service.create_workspace(
                project_key=project.project_key,
                workspace_key="synthetic",
                display_name="Synthetic test workspace",
                environment="test",
            )
        projects[label] = {
            "projectId": project.id,
            "workspaceId": workspace.id,
            "projectName": project.display_name,
            "projectKey": project.project_key,
        }
    if profile == "shared":
        for role in ("reviewer", "reviewer2", "readonly", "unassigned"):
            account = {
                "username": f"ui-proof-approval-{role}-{suffix}",
                "password": secrets.token_urlsafe(32),
            }
            created = identity.create_account(
                session["token"],
                account["username"],
                account["password"],
                csrf_token=session["csrf"],
            )
            account["principalId"] = created.principal_id
            accounts[role] = account
        with project_service.credential_context(
            identity, session["token"], csrf_token=session["csrf"], mutation=True
        ):
            for scope in projects.values():
                for role in ("reviewer", "reviewer2", "readonly"):
                    project_service.assign_project_membership(
                        scope["projectId"],
                        accounts[role]["principalId"],
                        "read-only" if role == "readonly" else "reviewer",
                    )
    with project_service.credential_context(
        identity, session["token"], csrf_token=session["csrf"], mutation=True
    ):
        for scope in projects.values():
            infra_automation_policy.update_settings(
                UpdateSettingsRequest(
                    project_id=scope["projectId"],
                    expected_version=0,
                    settings=AutomationSettings(enabled=True),
                    reason="Disposable synthetic browser qualification",
                )
            )
            # Configure only these disposable projects before any immutable run
            # is exported. Use the real authorized settings service so the
            # advisory-policy epoch and audit change are recorded normally.
            # High/critical confirmation cases then exercise eligible evidence;
            # the separate incomplete-evidence case remains a hard gate failure.
            save_policy_adapter_settings(
                project_key=scope["projectKey"],
                warn_at=None,
                soft_block_at=None,
                hard_block_at=None,
                reporting_default="advisory",
                enforcement_mode="advisory",
            )
            draft = infra_automation_service.create_workflow(
                CreateWorkflowRequest(
                    project_id=scope["projectId"],
                    workspace_id=scope["workspaceId"],
                    name="Synthetic approval qualification",
                    definition=json.dumps(
                        workflow(scope["projectId"], scope["workspaceId"])
                    ),
                    reason="Disposable synthetic browser qualification",
                ),
                registry_contract=registry(),
            )
            revision = infra_automation_service.publish_workflow(
                draft["id"],
                PublishWorkflowRequest(
                    expected_version=draft["draft_version"],
                    idempotency_key=secrets.token_hex(16),
                    reason="Disposable synthetic browser qualification",
                ),
                registry_contract=registry(),
            )
            scope.update(workflowId=draft["id"], revisionId=revision["id"])
    write_private(
        CREDENTIALS,
        {
            "version": 1,
            "profile": profile,
            "accounts": accounts,
            "projects": projects,
            "requesterSession": session,
            "cases": {},
        },
    )
    write_private(MATERIALS, {"version": 1, "profile": profile, "cases": {}})


def material_port(session, run, step_id, previous=None):
    from infra_automation.approval_eligibility import EvidenceFacts, LiveBinding
    from infra_automation.contracts import RegistryContract
    from infra_automation.decisions import DecisionBinding, binding_digest
    from infra_automation.lifecycle import LifecycleError
    from services.infra_automation_decisions import DecisionMaterial

    try:
        state = read_private(MATERIALS)
        record = state["cases"].get(run.id)
        if (
            not record
            or (record["projectId"], record["workspaceId"], step_id)
            != (run.project_id, run.workspace_id, "decision")
            or record.get("mutation") == "unavailable"
        ):
            raise LifecycleError(503)
        binding = dict(record["binding"])
        evidence, live = dict(record["evidence"]), dict(record["live"])
        if record.get("mutation") == "target":
            binding["canonical_target"] = "ui-proof-target-changed"
        elif record.get("mutation") == "payload":
            binding["payload_digest"] = "sha256:" + "b" * 64
        elif record.get("mutation") == "hardblock":
            evidence["complete"] = False
        # Persisted material is wire JSON. JSON-mode validation preserves the
        # closed models' strict tuple and aware-datetime boundary.
        binding = DecisionBinding.model_validate_json(json.dumps(binding))
        live.update(
            expected_tuple_digest=binding_digest(binding),
            current_tuple_digest=binding_digest(binding),
        )
        return DecisionMaterial(
            binding=binding,
            evidence=EvidenceFacts.model_validate_json(json.dumps(evidence)),
            live=LiveBinding.model_validate_json(json.dumps(live)),
            registry_contract=RegistryContract.model_validate_json(
                json.dumps(record["registry"])
            ),
        )
    except LifecycleError:
        raise
    except (KeyError, ValueError, TypeError, OSError):
        raise LifecycleError(503) from None


def new_case(case: str, project: str) -> dict:
    from sqlalchemy import func, select
    from evidence.models import ContextCompleteness
    from infra_automation.approval_eligibility import EvidenceFacts, LiveBinding
    from infra_automation.decisions import (
        DecisionBinding,
        binding_digest,
        freeze_report_snapshot,
    )
    from infra_automation.lifecycle import LifecycleError
    from infra_automation.preflight_contracts import SyntheticCollectionEnvelope
    from infra_automation.state import ACTIVE_STATES, AuditActor
    from models.repositories import infra_automation_runs as runs
    from models.tables import (
        AnalysisReport,
        RiskAssessment,
        InfraAutomationAttempt,
        InfraAutomationArtifactManifest,
        InfraAutomationReportLink,
        InfraAutomationRun,
    )
    from services import project_service, infra_automation_support as support
    from services.infra_automation_decisions import DecisionService
    from services.infra_automation_snapshots import export_run_snapshot
    from services.report_service import _serialize_report

    state, materials = read_private(CREDENTIALS), read_private(MATERIALS)
    scope = state["projects"][project]
    with requester(state), project_service.authorized_session() as db:
        grant = support.scope(
            db,
            scope["projectId"],
            scope["workspaceId"],
            "automation.request",
            mutation=True,
        )
        policy_row, policy = support.policy_state(db, scope["projectId"])
        active = (
            db.scalar(
                select(func.count())
                .select_from(InfraAutomationRun)
                .where(
                    InfraAutomationRun.project_id == scope["projectId"],
                    InfraAutomationRun.state.in_(ACTIVE_STATES),
                )
            )
            or 0
        )
        if active >= policy.max_active_runs:
            raise LifecycleError(429)
        exported = export_run_snapshot(
            scope["workflowId"],
            scope["revisionId"],
            {},
            scope["workspaceId"],
            registry_contract=registry(),
        )
        now = datetime.now(timezone.utc).replace(microsecond=0)
        source_deadline = now + timedelta(
            seconds=min(1800, policy.evidence_ttl_seconds)
        )
        approval_deadline = now + timedelta(
            seconds=30 if case == "expiry" else min(600, policy.approval_ttl_seconds)
        )
        run = runs.create_run(
            db,
            snapshot=exported,
            request_digest=support.digest(secrets.token_bytes(32)),
            key_digest=support.digest(secrets.token_bytes(32)),
            requested_by=grant.principal.principal_id,
            deadline_at=now + timedelta(seconds=min(2400, policy.evidence_ttl_seconds)),
            audit_actor=AuditActor(grant.principal.principal_id, "human", grant.role),
            reason="Disposable synthetic browser qualification",
            now=now,
        )
        run = runs.transition_run(
            db,
            run_id=run.id,
            expected_version=run.version,
            state="running",
            audit_actor=AuditActor(grant.principal.principal_id, "human", grant.role),
            reason="Synthetic completed evidence fixture",
            now=now,
        )
        severity = case if case in {"high", "critical"} else "low"
        recommendation = "no-go" if case == "no-go" else "go"
        score = 90 if severity == "critical" else 75 if severity == "high" else 0
        report = AnalysisReport(
            project_id=scope["projectId"],
            workspace_id=scope["workspaceId"],
            authorization_required=True,
            risk_score=score,
            severity=severity,
            recommendation=recommendation,
            top_risk="Synthetic retained evidence for browser qualification.",
            parse_summary="Synthetic collected-envelope contract proof; no collector admission.",
            narrative_opening="Synthetic qualification",
            narrative_explanation="Synthetic retained evidence only.",
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
            overall_severity=severity,
            recommendation=recommendation,
            score=score,
            confidence=1.0,
            context_completeness_json=ContextCompleteness().model_dump_json(),
        )
        db.add(report)
        db.flush()
        _, report_digest = freeze_report_snapshot(_serialize_report(report))
        suffix = secrets.token_hex(12)
        manifest_id, link_id = "manifest-" + suffix, "link-" + suffix
        attempts = {
            step: "attempt-" + step + "-" + suffix
            for step in ("collect", "analyze", "gate")
        }
        raw_artifacts = support.canonical([["plan.json", "{}"]])
        artifact_digest = support.digest(raw_artifacts)
        provenance_bytes = support.canonical(
            {"version": 1, "kind": "synthetic-collected-proof"}
        )
        provenance_digest = support.digest(provenance_bytes)
        for step, kind in (
            ("collect", "admitted_collection"),
            ("analyze", "shared_analysis"),
            ("gate", "policy_evaluation"),
        ):
            output = (
                {
                    "kind": "screened_artifacts",
                    "reference": manifest_id,
                    "digest": artifact_digest,
                }
                if step == "collect"
                else {
                    "kind": "report",
                    "reference": link_id,
                    "digest": provenance_digest,
                }
                if step == "analyze"
                else None
            )
            db.add(
                InfraAutomationAttempt(
                    id=attempts[step],
                    project_id=run.project_id,
                    workspace_id=run.workspace_id,
                    requested_by=run.requested_by,
                    run_id=run.id,
                    step_id=step,
                    step_kind=kind,
                    attempt_number=1,
                    fence=1,
                    handler_id="synthetic-browser-proof",
                    handler_version="1",
                    retry_safe=False,
                    input_digest=DIGEST,
                    created_at=now,
                    deadline_at=source_deadline,
                    state="succeeded",
                    version=1,
                    coordinator_generation=1,
                    last_observed_at=now,
                    logs_json="[]",
                    uploads_json="[]",
                    output_json=support.canonical(output).decode() if output else None,
                    output_digest=support.digest(support.canonical(output))
                    if output
                    else None,
                    log_bytes=0,
                    last_log_sequence=0,
                )
            )
        collection = SyntheticCollectionEnvelope(
            project_id=run.project_id,
            workspace_id=run.workspace_id,
            run_id=run.id,
            step_id="collect",
            attempt_id=attempts["collect"],
            fence=1,
            collector_id="ui-proof-collector",
            repository_id="ui-proof-repository",
            commit_sha="a" * 40,
            profile_digest=DIGEST,
            command_digest=DIGEST,
            argv_digest=DIGEST,
            raw_local_digest=DIGEST,
            sanitized_digest=artifact_digest,
            exit_code=0,
            collected_at=support.utc(now),
            source_deadline=support.utc(source_deadline),
        )
        collection_bytes = support.canonical(collection.model_dump(mode="json"))
        db.add(
            InfraAutomationArtifactManifest(
                id=manifest_id,
                run_id=run.id,
                step_id="collect",
                project_id=run.project_id,
                workspace_id=run.workspace_id,
                requested_by=run.requested_by,
                artifacts_bytes=raw_artifacts,
                digest=artifact_digest,
                collection_bytes=collection_bytes,
                collection_digest=support.digest(collection_bytes),
                created_at=now,
            )
        )
        db.flush()
        db.add(
            InfraAutomationReportLink(
                id=link_id,
                run_id=run.id,
                attempt_id=attempts["analyze"],
                manifest_id=manifest_id,
                report_id=report.id,
                project_id=run.project_id,
                workspace_id=run.workspace_id,
                requested_by=run.requested_by,
                provenance_bytes=provenance_bytes,
                digest=provenance_digest,
                created_at=now,
            )
        )
        db.flush()
        document = exported.snapshot
        binding = DecisionBinding(
            version=1,
            authorization_kind="exact_plan",
            workflow_id=run.workflow_id,
            revision_id=run.revision_id,
            workflow_revision_digest=run.definition_digest,
            input_digest=run.input_digest,
            provenance={
                "authorization_kind": "exact_plan",
                "source": {
                    "kind": "collected",
                    "repository_id": "ui-proof-repository",
                    "commit_sha": "a" * 40,
                    "collector_id": "ui-proof-collector",
                    "profile_digest": DIGEST,
                    "screened_transport_digest": artifact_digest,
                    "redaction_version": 1,
                    "collected_at": support.utc(now),
                    "source_deadline": support.utc(source_deadline),
                },
                "custody": {
                    "handle": "ui-proof-custody-" + suffix,
                    "raw_local_digest": DIGEST,
                    "expires_at": support.utc(source_deadline),
                },
            },
            project_id=run.project_id,
            workspace_id=run.workspace_id,
            environment="test",
            canonical_target="ui-proof-target",
            receiver_id="ui-proof-receiver",
            pipeline_repository_id="ui-proof-pipeline",
            pipeline_workflow_id="ui-proof-workflow",
            pipeline_workflow_revision="a" * 40,
            report_id=report.id,
            report_schema_version="v2",
            report_bytes_digest=report_digest,
            policy_version=policy_row.version,
            policy_result="passed",
            policy_digest=support.digest(
                support.canonical(
                    {
                        "automation": document.policy.model_dump(mode="json"),
                        "advisory": document.advisory_policy.model_dump(mode="json"),
                    }
                )
            ),
            unit_waves_digest=DIGEST,
            screened_artifact_digests=(artifact_digest,),
            redaction_version=1,
            payload_digest=DIGEST,
            evidence_deadline=support.utc(source_deadline),
            approval_deadline=support.utc(approval_deadline),
            authorization_epoch=document.authority.authorization_epoch,
            restore_epoch=document.authority.restore_epoch,
        )
        digest = binding_digest(binding)
        evidence = EvidenceFacts(
            source_kind="collected",
            source_verified=True,
            collected_at=now,
            evidence_deadline=source_deadline,
            complete=True,
            report_available=True,
            recommendation=recommendation,
            policy_status="advisory",
            policy_passed=True,
            artifact_step_id="collect",
            report_step_id="analyze",
        )
        live = LiveBinding(
            expected_tuple_digest=digest,
            current_tuple_digest=digest,
            membership_active=True,
            target_available=True,
            custody_available=True,
            approval_deadline=approval_deadline,
            custody_deadline=source_deadline,
            source_deadline=source_deadline,
            target_id="ui-proof-target",
            environment="test",
            authorization_kind="exact_plan",
        )
        materials["cases"][run.id] = {
            "case": case,
            "projectId": run.project_id,
            "workspaceId": run.workspace_id,
            "binding": binding.model_dump(mode="json"),
            "evidence": evidence.model_dump(mode="json"),
            "live": live.model_dump(mode="json"),
            "registry": registry().model_dump(mode="json"),
            "mutation": None,
        }
        write_private(MATERIALS, materials)
        receipt = DecisionService(material_port=material_port).request_decision(
            run.id, "decision"
        )
        result = {
            "caseId": run.id,
            "case": case,
            "runId": run.id,
            "approvalId": receipt["id"],
            "projectId": run.project_id,
            "workspaceId": run.workspace_id,
            "reportId": report.id,
            "deadline": support.utc(approval_deadline),
            "requesterPrincipalId": run.requested_by,
        }
    if case == "pending-allowhardblock":
        materials["cases"][result["runId"]]["mutation"] = "hardblock"
        write_private(MATERIALS, materials)
    state["cases"][result["caseId"]] = result
    write_private(CREDENTIALS, state)
    return result


def cancel_case(case_id: str) -> None:
    from infra_automation.state import CancelRunRequest, TERMINAL_STATES
    from services import infra_automation_engine_service as engine

    state = read_private(CREDENTIALS)
    if case_id not in state["cases"]:
        raise RuntimeError("Unknown synthetic case.")
    with requester(state):
        run = engine.get_run(case_id)
        if run["state"] not in TERMINAL_STATES and not run["cancel_requested"]:
            engine.cancel_run(
                case_id,
                CancelRunRequest(
                    expected_version=run["version"],
                    reason="Close disposable synthetic browser case",
                ),
            )


def membership(role: str, action: str) -> None:
    from services import project_service

    state = read_private(CREDENTIALS)
    if state["profile"] != "shared" or role not in {"reviewer", "reviewer2"}:
        raise RuntimeError("Only shared synthetic reviewers may be changed.")
    with requester(state):
        for scope in state["projects"].values():
            principal = state["accounts"][role]["principalId"]
            if action in {"restore", "demote"}:
                project_service.assign_project_membership(
                    scope["projectId"],
                    principal,
                    "read-only" if action == "demote" else "reviewer",
                )
            else:
                project_service.revoke_project_membership(scope["projectId"], principal)


def browser_fixture(state: dict) -> dict:
    """Export browser inputs without the seeder session or material authority."""
    return {
        "version": 1,
        "profile": state["profile"],
        "accounts": state["accounts"],
        "projects": state["projects"],
        "cases": state["cases"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--serve", action="store_true")
    action.add_argument("--new-case", choices=CASES)
    action.add_argument("--mutate-case", metavar="CASE_ID")
    action.add_argument("--cancel-case", metavar="CASE_ID")
    action.add_argument("--revoke", choices=("reviewer", "reviewer2"))
    action.add_argument("--restore", choices=("reviewer", "reviewer2"))
    action.add_argument("--demote", choices=("reviewer", "reviewer2"))
    action.add_argument("--export-fixture", action="store_true")
    parser.add_argument(
        "--project", choices=("primary", "alternate"), default="primary"
    )
    parser.add_argument(
        "--mutation", choices=("target", "payload", "unavailable", "restore")
    )
    args = parser.parse_args()
    profile = guard()
    if bool(args.mutate_case) != bool(args.mutation):
        raise RuntimeError("Mutation requires an exact synthetic case and mutation.")
    with fixture_lock():
        if args.serve:
            seed(profile)
        else:
            if (
                read_private(CREDENTIALS)["profile"] != profile
                or read_private(MATERIALS)["profile"] != profile
            ):
                raise RuntimeError("Fixture profile mismatch.")
            if args.new_case:
                print(
                    json.dumps(
                        new_case(args.new_case, args.project), separators=(",", ":")
                    )
                )
            elif args.mutate_case:
                state = read_private(MATERIALS)
                if args.mutate_case not in state["cases"]:
                    raise RuntimeError("Unknown synthetic case.")
                state["cases"][args.mutate_case]["mutation"] = (
                    None if args.mutation == "restore" else args.mutation
                )
                write_private(MATERIALS, state)
            elif args.cancel_case:
                cancel_case(args.cancel_case)
            elif args.export_fixture:
                write_private(
                    BROWSER_FIXTURE, browser_fixture(read_private(CREDENTIALS))
                )
                print(
                    "Browser credentials exported to the protected /tmp fixture file."
                )
            else:
                membership(
                    args.restore or args.demote or args.revoke,
                    "restore"
                    if args.restore
                    else "demote"
                    if args.demote
                    else "revoke",
                )
    if args.serve:
        from services import infra_automation_decisions

        infra_automation_decisions._default_service = (
            infra_automation_decisions.DecisionService(material_port=material_port)
        )
        print(
            "Disposable synthetic approval server ready; private fixture files are under /tmp.",
            flush=True,
        )
        import app

        app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Do not print application/SQL exception text, payloads or credentials.
        status_code = getattr(error, "status_code", None)
        print(
            f"Disposable approval fixture failed ({type(error).__name__}, status={status_code}); inspect the draft locally without dumping credential files.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
