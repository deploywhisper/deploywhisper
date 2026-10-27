"""Uploaded advisory preflights using the existing fenced worker and analysis core."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from infra_automation import claims
from infra_automation.analysis_context import current, validate
from infra_automation.artifact_intake import screen_artifacts
from infra_automation.preflight_evidence import build_evidence_status
from infra_automation.lifecycle import LifecycleError
from infra_automation.local_workers import HandlerRegistration, HandlerRegistry
from infra_automation.preflight_contracts import PreflightRequest, UploadedProvenance
from infra_automation.state import OutputReference, WorkerResult
from models.repositories import infra_automation_reports as reports
from models.repositories import infra_automation_runs as runs
from models.tables import InfraAutomationArtifactManifest
from services import infra_automation_engine_service as engine
from services import infra_automation_support as support
from services import project_service as auth


def request_preflight(request: PreflightRequest):
    request = support.revalidate(request, PreflightRequest)
    try:
        files: list[tuple[str, bytes | None]] = [
            (item.name, item.content.encode("utf-8")) for item in request.artifacts
        ]
    except UnicodeError:
        raise LifecycleError(422) from None
    files = list(screen_artifacts(files))
    with auth.authorized_session() as session:
        result = engine.request_run(request.run, registry=PREFLIGHT_REGISTRY)
        run = runs.get_run(session, result["id"])
        if run is None:
            raise LifecycleError(503)
        document = engine._document(run)
        intake = [s for s in document.definition.steps if s.kind == "uploaded_intake"]
        analysis = [s for s in document.definition.steps if s.kind == "shared_analysis"]
        # This bounded entrypoint has one explicit upload and its shared analysis.
        # Later multi-unit workflows need their own unambiguous upload binding.
        if (
            len(intake) != 1
            or len(analysis) != 1
            or len(document.definition.steps) != 2
        ):
            raise LifecycleError(422)
        auth.guard_project(
            session, run.project_id, run.workspace_id, "analysis.submit", mutation=True
        )
        reports.create_manifest(session, run, intake[0].id, files)
        return engine._view(run)


def list_run_reports(run_id, *, now: datetime | None = None):
    with auth.authorized_session() as session:
        run, _ = engine._authorized_run(session, run_id)
        auth.guard_project(session, run.project_id, run.workspace_id, "report.read")
        items = []
        for row in reports.list_links(session, run.id):
            if auth.guard_report(session, row.report_id, "report.read") is None:
                raise auth.TrustedAuthorizationError()
            items.append(reports.link_view(row))
        document = engine._document(run)
        intake_steps = {
            step.id
            for step in document.definition.steps
            if step.kind == "uploaded_intake"
        }
        present = set(
            session.scalars(
                select(InfraAutomationArtifactManifest.step_id).where(
                    InfraAutomationArtifactManifest.run_id == run.id,
                    InfraAutomationArtifactManifest.project_id == run.project_id,
                    InfraAutomationArtifactManifest.workspace_id == run.workspace_id,
                    InfraAutomationArtifactManifest.requested_by == run.requested_by,
                )
            )
        )
        evidence_status = build_evidence_status(
            run,
            document,
            runs.list_attempts(session, run_id=run.id),
            manifest_present=bool(intake_steps) and intake_steps <= present,
            links=items,
            now=now or datetime.now(timezone.utc),
        )
        return support.bounded_payload(
            {"items": items, "evidence_status": evidence_status.model_dump(mode="json")}
        )


def execute_preflight_step(value):
    """Fixed trusted handler; only a wrapper-installed private operation may call."""
    operation = current()
    if operation is None:
        raise auth.TrustedAuthorizationError()
    with auth.authorized_session() as session:
        handle, _ = validate(session)
        run = runs.get_run(session, handle.run_id)
        if (
            value.snapshot_bytes != run.snapshot_bytes
            or value.step_id != handle.step_id
        ):
            raise LifecycleError(409)
        document = engine._document(run)
        step = next(s for s in document.definition.steps if s.id == handle.step_id)
        if step.kind == "uploaded_intake":
            manifest = reports.get_manifest_for_step(session, run.id, step.id)
            if manifest is None:
                raise LifecycleError(422)
            output = OutputReference(
                kind="screened_artifacts", reference=manifest.id, digest=manifest.digest
            )
            return WorkerResult(outcome="local_success", output=output)
        if step.kind != "shared_analysis":
            raise LifecycleError(422)
        prerequisite = dict(value.prerequisites).get(step.artifact.step_id)
        if prerequisite is None:
            raise LifecycleError(409)
        reference = OutputReference.model_validate_json(prerequisite)
        manifest = reports.get_manifest(session, reference.reference)
        if (
            manifest is None
            or reference.kind != "screened_artifacts"
            or reference.digest != manifest.digest
            or (
                manifest.run_id,
                manifest.step_id,
                manifest.project_id,
                manifest.workspace_id,
            )
            != (run.id, step.artifact.step_id, run.project_id, run.workspace_id)
        ):
            raise LifecycleError(409)
        files = reports.manifest_files(manifest)
        manifest_id = manifest.id
        project_id, workspace_id = run.project_id, run.workspace_id
    committed = []

    def link_report(report):
        with auth.authorized_session() as session:
            validate(session)
            context = report.get("context_completeness") or {}
            limitations = list(report.get("warnings") or [])
            if context.get("insufficient_context") is not False:
                limitations.append("Analysis has insufficient or unknown context.")
            if report.get("partial_context") or context.get("partial_context"):
                limitations.append(
                    "Mandatory evidence is partial; collect complete current input."
                )
            row = reports.create_link(
                session,
                operation.handle,
                manifest_id,
                report["id"],
                UploadedProvenance().model_dump(),
                limitations=limitations,
                context_todos=context.get("context_todos") or (),
            )
            output = OutputReference(kind="report", reference=row.id, digest=row.digest)
            attempt = runs.get_attempt(session, operation.handle.attempt_id)
            attempt = claims.register_upload(
                session,
                operation.handle,
                expected_version=attempt.version,
                reference=output,
            )
            claims.commit_output(
                session,
                operation.handle,
                expected_version=attempt.version,
                output=output,
            )
            committed.append(output)

    from services.analysis_service import analyze_uploaded_files

    analyze_uploaded_files(
        files,
        project_id=project_id,
        workspace_id=workspace_id,
        audit_context={
            "source_interface": "api",
            "trigger_type": "infra_preflight",
            "trigger_id": operation.handle.run_id,
            "actor": operation.handle.principal_id,
        },
        _on_persisted=link_report,
    )
    return WorkerResult(outcome="local_success", output=committed[0])


PREFLIGHT_REGISTRY = HandlerRegistry(
    tuple(
        HandlerRegistration(
            handler_id=f"preflight-{kind}",
            handler_version="1",
            step_kind=kind,
            output_kind=output,
            retry_safe=True,
            handler=execute_preflight_step,
        )
        for kind, output in (
            ("uploaded_intake", "screened_artifacts"),
            ("shared_analysis", "report"),
        )
    )
)
