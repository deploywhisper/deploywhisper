"""Immutable screened manifests and authenticated relational report linkage."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import uuid4

from sqlalchemy import select

from infra_automation import claims
from infra_automation.artifact_intake import screen_artifacts, screen_metadata
from infra_automation.lifecycle import LifecycleError, SnapshotDocument
from infra_automation.preflight_contracts import (
    PreflightLinkView,
    SyntheticCollectionEnvelope,
    UploadedProvenance,
)
from infra_automation.workflow_schema import UploadedIntakeStep
from infra_automation.workflow_validation import prepare_resolution, resolve_value
from models.repositories import infra_automation_runs as runs
from models.tables import (
    AnalysisReport,
    InfraAutomationArtifactManifest,
    InfraAutomationReportLink,
    Project,
)
from services import infra_automation_support as support
from services import project_service as authorization


def _now(value):
    value = value or datetime.now(timezone.utc)
    if type(value) is not datetime or value.tzinfo is None:
        raise LifecycleError(503)
    return value.astimezone(timezone.utc)


def _manifest_payload(files, maximum=8388608):
    screened = screen_artifacts(files, max_bytes=maximum)
    return support.canonical([[name, raw.decode("utf-8")] for name, raw in screened])


def create_manifest(session, run, step_id, files, *, now=None, bounds=None):
    """Called in the same authenticated admission transaction as create_run."""
    authorization._require_operation(session)
    timestamp = _now(now)
    current = runs.get_run(session, run.id)
    if current is None:
        raise LifecycleError(409)
    grant = support.scope(
        session,
        current.project_id,
        current.workspace_id,
        "automation.request",
        mutation=True,
    )
    if grant.principal.principal_id != current.requested_by:
        raise authorization.TrustedAuthorizationError()
    document = SnapshotDocument.model_validate_json(current.snapshot_bytes)
    if support.digest(current.snapshot_bytes) != current.snapshot_digest or (
        document.project_id,
        document.workspace_id,
        document.authority.principal_id,
    ) != (current.project_id, current.workspace_id, current.requested_by):
        raise LifecycleError(503)
    step = next(
        (item for item in document.definition.steps if item.id == step_id), None
    )
    if not isinstance(step, UploadedIntakeStep):
        raise LifecycleError(422)
    context = prepare_resolution(
        document.definition,
        document.inputs,
        {
            "project_id": str(current.project_id),
            "workspace_id": str(current.workspace_id),
            "environment": document.environment,
        },
    )
    maximum = min(
        document.policy.max_artifact_bytes,
        resolve_value(step.parameters.max_artifact_bytes, context),
    )
    payload = _manifest_payload(files, maximum)
    digest = support.digest(payload)
    existing = get_manifest_for_step(session, current.id, step_id)
    if existing is not None:
        if existing.digest != digest or existing.artifacts_bytes != payload:
            raise LifecycleError(409)
        return existing
    if (
        current.state != "queued"
        or current.cancel_requested
        or timestamp >= runs.utc(current.deadline_at)
    ):
        raise LifecycleError(409)
    claims._charge(session, current, len(payload), timestamp, bounds)
    row = InfraAutomationArtifactManifest(
        id=uuid4().hex,
        run_id=current.id,
        step_id=step_id,
        project_id=current.project_id,
        workspace_id=current.workspace_id,
        requested_by=current.requested_by,
        artifacts_bytes=payload,
        digest=digest,
        created_at=timestamp,
    )
    session.add(row)
    session.flush()
    return row


def manifest_files(row):
    try:
        if (
            type(row.artifacts_bytes) is not bytes
            or not 1 <= len(row.artifacts_bytes) <= 50331648
            or support.digest(row.artifacts_bytes) != row.digest
        ):
            raise ValueError
        document = json.loads(row.artifacts_bytes)
        if (
            type(document) is not list
            or not 1 <= len(document) <= 32
            or any(
                type(item) is not list
                or len(item) != 2
                or any(type(value) is not str for value in item)
                for item in document
            )
        ):
            raise ValueError
        if (row.collection_bytes is None) != (row.collection_digest is None):
            raise ValueError
        if row.collection_bytes is not None:
            if (
                len(row.collection_bytes) > 16384
                or support.digest(row.collection_bytes) != row.collection_digest
            ):
                raise ValueError
            envelope = SyntheticCollectionEnvelope.model_validate_json(
                row.collection_bytes
            )
            if (
                envelope.project_id,
                envelope.workspace_id,
                envelope.run_id,
                envelope.step_id,
                envelope.sanitized_digest,
            ) != (
                row.project_id,
                row.workspace_id,
                row.run_id,
                row.step_id,
                row.digest,
            ):
                raise ValueError
            screen_metadata(envelope.model_dump(mode="json"))
        files = [(name, content.encode("utf-8")) for name, content in document]
        if _manifest_payload(files) != row.artifacts_bytes:
            raise ValueError
        return files
    except (ValueError, TypeError, UnicodeError, RecursionError, LifecycleError):
        raise LifecycleError(503) from None


def get_manifest(session, manifest_id):
    authorization._require_operation(session)
    row = session.get(InfraAutomationArtifactManifest, support.identifier(manifest_id))
    if row is not None:
        manifest_files(row)
    return row


def get_manifest_for_step(session, run_id, step_id):
    authorization._require_operation(session)
    row = session.scalar(
        select(InfraAutomationArtifactManifest).where(
            InfraAutomationArtifactManifest.run_id == run_id,
            InfraAutomationArtifactManifest.step_id == step_id,
        )
    )
    if row is not None:
        manifest_files(row)
    return row


def _bounded_link_summary(identity, provenance, limitations, context_todos):
    """Keep a readable summary; original diagnostic detail stays in the report."""
    originals = (
        list(dict.fromkeys([provenance.limitation, *limitations])),
        list(
            dict.fromkeys(
                [
                    "Verify repository source and collect current complete evidence before any handoff decision.",
                    *context_todos,
                ]
            )
        ),
    )
    selected = [[values[0]] for values in originals]

    def render():
        summaries = []
        for label, values, retained in zip(
            ("limitations", "context TODOs"), originals, selected, strict=True
        ):
            omitted = len(values) - len(retained)
            summaries.append(
                retained
                + (
                    [f"Additional {label} omitted: {omitted}; see the full report."]
                    if omitted
                    else []
                )
            )
        return PreflightLinkView(
            **identity,
            provenance=provenance,
            limitations=summaries[0],
            context_todos=summaries[1],
            approval_eligible=False,
        )

    for index, values in enumerate(originals):
        for item in values[1:]:
            # Reserve a slot for an overflow count whenever entries are omitted.
            maximum = 50 if len(values) <= 50 else 49
            if len(selected[index]) >= maximum:
                continue
            selected[index].append(item)
            candidate = render().model_dump(mode="json")
            if (
                len(
                    json.dumps(candidate, ensure_ascii=False, allow_nan=False).encode(
                        "utf-8"
                    )
                )
                > 16384
            ):
                selected[index].pop()
    value = render()
    screen_metadata(value.model_dump(mode="json"))
    return value


def create_link(
    session,
    handle,
    manifest_id,
    report_id,
    provenance,
    *,
    limitations=(),
    context_todos=(),
    now=None,
    bounds=None,
):
    """Final worker transaction atomically fences report and immutable linkage."""
    authorization._require_operation(session)
    timestamp = _now(now)
    attempt = claims._attempt(session, handle, timestamp)
    if attempt.state != "running" or attempt.step_kind != "shared_analysis":
        raise LifecycleError(409)
    run, document = claims._run(session, handle.run_id, timestamp)
    member = authorization.membership_repository.get_membership(
        session, principal_id=run.requested_by, project_id=run.project_id
    )
    if (
        member is None
        or "analysis.submit"
        not in authorization.PROJECT_ROLE_CAPABILITIES.get(member.role, ())
    ):
        raise authorization.TrustedAuthorizationError()
    manifest = get_manifest(session, manifest_id)
    step = next(
        item for item in document.definition.steps if item.id == attempt.step_id
    )
    report = session.get(AnalysisReport, report_id)
    if (
        manifest is None
        or report is None
        or (
            manifest.run_id,
            manifest.project_id,
            manifest.workspace_id,
            manifest.requested_by,
            manifest.step_id,
        )
        != (
            run.id,
            run.project_id,
            run.workspace_id,
            run.requested_by,
            step.artifact.step_id,
        )
        or (report.project_id, report.workspace_id)
        != (run.project_id, run.workspace_id)
    ):
        raise LifecycleError(409)
    # Successful prerequisite output must bind the exact immutable manifest.
    dependencies = runs.list_attempts(session, run_id=run.id)
    prerequisite = next(
        (
            item
            for item in reversed(dependencies)
            if item.step_id == manifest.step_id and item.state == "succeeded"
        ),
        None,
    )
    expected = {
        "kind": "screened_artifacts",
        "reference": manifest.id,
        "digest": manifest.digest,
    }
    if (
        prerequisite is None
        or json.loads(prerequisite.output_json or "null") != expected
    ):
        raise LifecycleError(409)
    existing = session.scalar(
        select(InfraAutomationReportLink).where(
            InfraAutomationReportLink.attempt_id == attempt.id
        )
    )
    link_id = existing.id if existing is not None else uuid4().hex
    try:
        typed = UploadedProvenance.model_validate(provenance)
        value = _bounded_link_summary(
            dict(
                id=link_id,
                run_id=run.id,
                attempt_id=attempt.id,
                manifest_id=manifest.id,
                report_id=report.id,
                report_url=f"/reports/{report.id}",
            ),
            typed,
            limitations,
            context_todos,
        )
        payload = support.canonical(value.model_dump(mode="json", exclude={"id"}))
    except (ValueError, TypeError):
        raise LifecycleError(422) from None
    if existing is not None:
        if existing.provenance_bytes != payload:
            raise LifecycleError(409)
        return existing
    report.authorization_required = True
    project = session.get(Project, run.project_id)
    project.authorization_required = True
    session.flush()
    from services.report_service import _serialize_report

    report_bytes = support.canonical(_serialize_report(report, include_evidence=True))
    if len(report_bytes) > 8388608:
        raise LifecycleError(429)
    from services.artifact_snapshot_service import retained_report_artifact_bytes

    snapshot_bytes = retained_report_artifact_bytes(
        session, report.id, handle=handle, now=timestamp
    )
    claims._charge(
        session,
        run,
        len(payload) + len(report_bytes) + snapshot_bytes,
        timestamp,
        bounds,
    )
    row = InfraAutomationReportLink(
        id=link_id,
        run_id=run.id,
        attempt_id=attempt.id,
        manifest_id=manifest.id,
        report_id=report.id,
        project_id=run.project_id,
        workspace_id=run.workspace_id,
        requested_by=run.requested_by,
        provenance_bytes=payload,
        digest=support.digest(payload),
        created_at=timestamp,
    )
    session.add(row)
    session.flush()
    return row


def link_view(row):
    try:
        if (
            type(row.provenance_bytes) is not bytes
            or len(row.provenance_bytes) > 16384
            or support.digest(row.provenance_bytes) != row.digest
        ):
            raise ValueError
        value = {"id": row.id, **json.loads(row.provenance_bytes)}
        screen_metadata(value)
        typed = PreflightLinkView.model_validate(value)
        if (
            typed.run_id,
            typed.attempt_id,
            typed.manifest_id,
            typed.report_id,
            typed.report_url,
        ) != (
            row.run_id,
            row.attempt_id,
            row.manifest_id,
            row.report_id,
            f"/reports/{row.report_id}",
        ):
            raise ValueError
        return typed.model_dump(mode="json")
    except (ValueError, TypeError, UnicodeError, RecursionError, LifecycleError):
        raise LifecycleError(503) from None


def list_links(session, run_id):
    authorization._require_operation(session)
    return list(
        session.scalars(
            select(InfraAutomationReportLink)
            .where(InfraAutomationReportLink.run_id == run_id)
            .order_by(
                InfraAutomationReportLink.created_at, InfraAutomationReportLink.id
            )
        )
    )


def verify_collected_envelope(
    session,
    handle,
    envelope,
    files,
    *,
    expected_command_digest,
    expected_argv_digest,
    expected_collector_id,
    now=None,
):
    """Service-only synthetic proof; public comparison stamps never authenticate."""
    authorization._require_operation(session)
    timestamp = _now(now)
    attempt = claims._attempt(session, handle, timestamp)
    if attempt.state != "running" or attempt.step_kind != "admitted_collection":
        raise LifecycleError(409)
    envelope = support.revalidate(envelope, SyntheticCollectionEnvelope)
    screen_metadata(envelope.model_dump(mode="json"))
    run, document = claims._run(session, handle.run_id, timestamp)
    source = next(
        (item for item in document.sources if item.step_id == attempt.step_id), None
    )
    step = next(
        item for item in document.definition.steps if item.id == attempt.step_id
    )
    maximum = step.parameters.max_artifact_bytes
    if not isinstance(maximum, int):
        maximum = document.inputs[maximum.name]
    maximum = min(document.policy.max_artifact_bytes, maximum)
    if (
        source is None
        or source.kind != "collected"
        or envelope.collector_id != expected_collector_id
        or (
            envelope.project_id,
            envelope.workspace_id,
            envelope.run_id,
            envelope.step_id,
            envelope.attempt_id,
            envelope.fence,
        )
        != (
            run.project_id,
            run.workspace_id,
            run.id,
            attempt.step_id,
            attempt.id,
            attempt.fence,
        )
        or (envelope.repository_id, envelope.commit_sha, envelope.profile_digest)
        != (source.repository_id, source.commit_sha, source.profile_digest)
        or (envelope.command_digest, envelope.argv_digest)
        != (expected_command_digest, expected_argv_digest)
        or envelope.sanitized_digest
        != support.digest(_manifest_payload(files, maximum))
    ):
        raise LifecycleError(409)
    collected = datetime.strptime(envelope.collected_at, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    deadline = datetime.strptime(
        envelope.source_deadline, "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=timezone.utc)
    if not runs.utc(run.created_at).replace(
        microsecond=0
    ) <= collected <= timestamp < deadline or deadline > runs.utc(run.deadline_at):
        raise LifecycleError(409)
    return envelope


def create_collected_manifest(
    session,
    handle,
    envelope,
    files,
    *,
    expected_command_digest,
    expected_argv_digest,
    expected_collector_id,
    now=None,
    bounds=None,
):
    """Retain authenticated synthetic provenance without admitting a real collector."""
    timestamp = _now(now)
    envelope = verify_collected_envelope(
        session,
        handle,
        envelope,
        files,
        expected_command_digest=expected_command_digest,
        expected_argv_digest=expected_argv_digest,
        expected_collector_id=expected_collector_id,
        now=timestamp,
    )
    run, document = claims._run(session, handle.run_id, timestamp)
    payload = _manifest_payload(files, document.policy.max_artifact_bytes)
    collection = support.canonical(envelope.model_dump(mode="json"))
    existing = get_manifest_for_step(session, run.id, handle.step_id)
    if existing is not None:
        if (
            existing.artifacts_bytes != payload
            or existing.collection_bytes != collection
        ):
            raise LifecycleError(409)
        return existing
    claims._charge(session, run, len(payload) + len(collection), timestamp, bounds)
    row = InfraAutomationArtifactManifest(
        id=uuid4().hex,
        run_id=run.id,
        step_id=handle.step_id,
        project_id=run.project_id,
        workspace_id=run.workspace_id,
        requested_by=run.requested_by,
        artifacts_bytes=payload,
        digest=support.digest(payload),
        collection_bytes=collection,
        collection_digest=support.digest(collection),
        created_at=timestamp,
    )
    session.add(row)
    session.flush()
    return row
