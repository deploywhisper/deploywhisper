"""Scoped durable collection observations; reads never assert live process control."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr
from sqlalchemy import select

from infra_automation.contracts import ClosedModel, CommitSha, Digest, Identifier
from infra_automation.collection_contracts import CollectionProvenance, CollectionUpload
from infra_automation.lifecycle import LifecycleError, Positive
from infra_automation.state import UTCText, TERMINAL_STATES
from models.repositories import infra_automation_runs as runs
from models.repositories import infra_automation_reports as reports
from services import infra_automation_engine_service as engine
from services import infra_automation_support as support
from services import project_service as auth


class Diagnosis(ClosedModel):
    code: Literal[
        "eligible",
        "execution_disabled",
        "profile_unavailable",
        "no_runner",
        "runner_inactive",
        "profile_mismatch",
        "tool_mismatch",
        "runner_version_mismatch",
        "protocol_mismatch",
        "tags_mismatch",
        "credential_unavailable",
        "heartbeat_stale",
        "runner_busy",
        "details_unavailable",
    ]
    correction: StrictStr
    eligible: StrictBool = False


_CORRECTIONS = {
    "execution_disabled": "Ask an administrator to enable InfraFlow execution for this project.",
    "eligible": "A compatible runner is currently available; admission rechecks live authority.",
    "profile_unavailable": "Ask an administrator to install the approved collection profile.",
    "no_runner": "Ask an administrator to enroll a runner in this project workspace.",
    "runner_inactive": "Ask an administrator to enroll or restore an active runner.",
    "profile_mismatch": "Configure a runner with the exact approved profile digest.",
    "tool_mismatch": "Configure the tool declared by the approved collection profile.",
    "runner_version_mismatch": "Install the runner version required by the approved profile.",
    "protocol_mismatch": "Use a runner supporting protocol version 1.",
    "tags_mismatch": "Configure all runner tags required by the approved profile.",
    "credential_unavailable": "Ask an administrator to restore current runner credentials and authority.",
    "heartbeat_stale": "Reconnect the compatible runner and wait for a current heartbeat.",
    "runner_busy": "Wait for the compatible runner to finish, then request a new collection.",
    "details_unavailable": "Ask a project administrator to check runner eligibility for this collection.",
}


def diagnosis(code):
    return Diagnosis(
        code=code, correction=_CORRECTIONS[code], eligible=code == "eligible"
    )


class Observation(ClosedModel):
    kind: Literal["source_bound", "collection", "screened_upload", "analysis"]
    state: Literal[
        "not_observed",
        "bound",
        "pending",
        "claimed",
        "running",
        "received",
        "finalized",
        "succeeded",
        "failed",
        "timed_out",
        "cancelled",
        "stale",
    ]
    event_at: UTCText | None = None


class CollectionItem(ClosedModel):
    step_id: Identifier
    repository_id: Identifier
    commit_sha: CommitSha
    profile_digest: Digest
    attempt_id: Identifier | None
    attempt_number: Positive | None
    attempt_state: StrictStr | None
    lease_until: UTCText | None
    observations: Annotated[list[Observation], Field(min_length=4, max_length=4)]
    diagnosis: Diagnosis
    routing_failure: Literal["no_eligible_runner"] | None = None


class CancellationFacts(ClosedModel):
    can_cancel: StrictBool
    requested: StrictBool
    requested_at: UTCText | None
    owned_processes: Literal["not_confirmed"] = "not_confirmed"
    external_stop: Literal["not_confirmed"] = "not_confirmed"
    external_possible: StrictBool


class CollectionView(ClosedModel):
    version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    run_id: Identifier
    project_id: Positive
    workspace_id: Positive
    run_version: Positive
    observed_at: UTCText
    finite_wait_seconds: Literal[0] = 0
    items: Annotated[list[CollectionItem], Field(max_length=50)]
    cancellation: CancellationFacts
    limitations: Annotated[list[StrictStr], Field(max_length=8)]


class ReadinessSource(ClosedModel):
    step_id: Identifier
    repository_id: Identifier | None
    commit_sha: CommitSha | None
    profile_digest: Digest
    inputs_required: StrictBool
    diagnosis: Diagnosis


class CollectionReadiness(ClosedModel):
    version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    workflow_id: Identifier
    revision_id: Identifier
    project_id: Positive
    workspace_id: Positive
    observed_at: UTCText
    finite_wait_seconds: Literal[0] = 0
    execution_enabled: StrictBool
    can_request: StrictBool
    items: Annotated[list[ReadinessSource], Field(max_length=50)]


def _now(value):
    value = value or datetime.now(timezone.utc)
    if type(value) is not datetime or value.tzinfo is None:
        raise LifecycleError(503)
    return value.astimezone(timezone.utc)


def _routing(
    session, project_id, workspace_id, profile_digest, grant, now, *, own_attempt=None
):
    from models.tables import (
        InfraAutomationRunner,
        InfraAutomationRunnerTask,
        InfraAutomationAttempt,
    )
    from services.infra_automation_collection import configured_requirements
    from services import infra_automation_runners as runners

    if grant.role not in {"admin", "maintainer"}:
        return diagnosis("details_unavailable")
    _, settings = support.policy_state(session, project_id)
    if not settings.enabled:
        return diagnosis("execution_disabled")
    try:
        requirements = configured_requirements().get(profile_digest)
    except LifecycleError:
        requirements = None
    if requirements is None:
        return diagnosis("profile_unavailable")
    candidates = list(
        session.scalars(
            select(InfraAutomationRunner)
            .where(
                InfraAutomationRunner.project_id == project_id,
                InfraAutomationRunner.workspace_id == workspace_id,
                InfraAutomationRunner.status == "active",
            )
            # Current credential slots are capped at100 per project. Sort live
            # credentials first so retained expired/revoked history cannot hide
            # an eligible runner behind the read ceiling.
            .order_by(
                InfraAutomationRunner.credential_expires_at.desc(),
                InfraAutomationRunner.created_at.desc(),
            )
            .limit(1000)
        )
    )
    if not candidates:
        retained = session.scalar(
            select(InfraAutomationRunner.id)
            .where(
                InfraAutomationRunner.project_id == project_id,
                InfraAutomationRunner.workspace_id == workspace_id,
            )
            .limit(1)
        )
        return diagnosis("runner_inactive" if retained else "no_runner")
    filters = (
        ("runner_inactive", lambda r: r.status == "active"),
        ("profile_mismatch", lambda r: r.profile_digest == requirements.profile_digest),
        ("tool_mismatch", lambda r: r.tool == requirements.tool),
        (
            "runner_version_mismatch",
            lambda r: r.runner_version == requirements.runner_version,
        ),
        ("protocol_mismatch", lambda r: r.protocol_version == 1),
        (
            "tags_mismatch",
            lambda r: set(requirements.tags).issubset(json.loads(r.tags_json)),
        ),
    )
    for code, predicate in filters:
        candidates = [r for r in candidates if predicate(r)]
        if not candidates:
            return diagnosis(code)
    current = []
    for runner in candidates:
        try:
            runners.validate_runner(session, runner, now=now)
        except (LifecycleError, auth.TrustedAuthorizationError):
            continue
        current.append(runner)
    if not current:
        return diagnosis("credential_unavailable")
    current = [
        r
        for r in current
        if r.last_seen_at is not None
        and now - timedelta(seconds=60) <= runs.utc(r.last_seen_at) <= now
    ]
    if not current:
        return diagnosis("heartbeat_stale")
    busy = set(
        session.scalars(
            select(InfraAutomationRunnerTask.runner_id)
            .join(
                InfraAutomationAttempt,
                InfraAutomationAttempt.id == InfraAutomationRunnerTask.attempt_id,
            )
            .where(
                InfraAutomationAttempt.state.in_(("claimed", "running")),
                InfraAutomationAttempt.id != (own_attempt or ""),
            )
        )
    )
    return diagnosis(
        "eligible" if any(r.id not in busy for r in current) else "runner_busy"
    )


def _same_scope(row, project_id, workspace_id):
    if (row.project_id, row.workspace_id) != (project_id, workspace_id):
        raise auth.TrustedAuthorizationError()


def _analysis_observation(attempts, step_ids, now):
    latest = [
        max(
            (a for a in attempts if a.step_id == step_id),
            key=lambda a: a.attempt_number,
            default=None,
        )
        for step_id in step_ids
    ]
    states = []
    for attempt in latest:
        state = attempt.state if attempt else "not_observed"
        if (
            attempt
            and state in {"claimed", "running"}
            and (
                now >= runs.utc(attempt.deadline_at)
                or attempt.lease_until is None
                or now >= runs.utc(attempt.lease_until)
            )
        ):
            state = "stale"
        states.append(state)
    if not states:
        return Observation(kind="analysis", state="not_observed")
    for state in (
        "failed",
        "timed_out",
        "cancelled",
        "stale",
        "not_observed",
        "running",
        "claimed",
        "pending",
    ):
        if state in states:
            return Observation(kind="analysis", state=state)
    return Observation(kind="analysis", state="succeeded")


def get_collection(run_id, *, project_id, workspace_id, now=None):
    from models.tables import InfraAutomationRunnerTask, InfraAutomationAudit

    with auth.authorized_session() as session:
        run, grant = engine._authorized_run(session, run_id)
        _same_scope(run, project_id, workspace_id)
        document = engine._document(run)
        timestamp = _now(now)
        attempts = runs.list_attempts(session, run_id=run.id)
        if len(attempts) > 150:
            raise LifecycleError(503)
        items = []
        for source in document.sources:
            if source.kind != "collected":
                continue
            attempt = max(
                (a for a in attempts if a.step_id == source.step_id),
                key=lambda a: a.attempt_number,
                default=None,
            )
            collection_state = attempt.state if attempt else "not_observed"
            if (
                attempt
                and attempt.state in {"claimed", "running"}
                and (
                    timestamp >= runs.utc(attempt.deadline_at)
                    or attempt.lease_until is None
                    or timestamp >= runs.utc(attempt.lease_until)
                )
            ):
                collection_state = "stale"
            uploaded = "not_observed"
            upload_time = None
            manifest = reports.get_manifest_for_step(session, run.id, source.step_id)
            if manifest:
                reports.manifest_files(manifest)
                provenance = CollectionProvenance.model_validate_json(
                    manifest.collection_bytes
                )
                if (
                    provenance.repository_id,
                    provenance.commit_sha,
                    provenance.profile_digest,
                ) != (source.repository_id, source.commit_sha, source.profile_digest):
                    raise LifecycleError(503)
                uploaded = "finalized"
                upload_time = support.utc(manifest.created_at)
                if (
                    attempt is None
                    or (
                        provenance.scope.attempt,
                        provenance.scope.fence,
                        provenance.scope.coordinator_generation,
                    )
                    != (
                        attempt.attempt_number,
                        attempt.fence,
                        attempt.coordinator_generation,
                    )
                    or timestamp
                    >= min(
                        datetime.strptime(
                            provenance.source_deadline, "%Y-%m-%dT%H:%M:%SZ"
                        ).replace(tzinfo=timezone.utc),
                        datetime.strptime(
                            provenance.custody.expires_at, "%Y-%m-%dT%H:%M:%SZ"
                        ).replace(tzinfo=timezone.utc),
                    )
                ):
                    uploaded = "stale"
            elif attempt:
                binding = session.get(InfraAutomationRunnerTask, attempt.id)
                if binding and binding.upload_bytes:
                    if support.digest(binding.upload_bytes) != binding.upload_digest:
                        raise LifecycleError(503)
                    value = CollectionUpload.model_validate_json(binding.upload_bytes)
                    if (
                        value.provenance.scope.run_id,
                        value.provenance.scope.step_id,
                        value.provenance.scope.project_id,
                        value.provenance.scope.workspace_id,
                        value.provenance.scope.runner_id,
                        value.provenance.scope.attempt,
                        value.provenance.scope.fence,
                        value.provenance.scope.coordinator_generation,
                        value.provenance.repository_id,
                        value.provenance.commit_sha,
                        value.provenance.profile_digest,
                    ) != (
                        run.id,
                        source.step_id,
                        str(project_id),
                        str(workspace_id),
                        binding.runner_id,
                        attempt.attempt_number,
                        attempt.fence,
                        attempt.coordinator_generation,
                        source.repository_id,
                        source.commit_sha,
                        source.profile_digest,
                    ):
                        raise LifecycleError(503)
                    uploaded = (
                        "received"
                        if collection_state in {"claimed", "running"}
                        and timestamp
                        < min(
                            datetime.strptime(
                                value.provenance.source_deadline, "%Y-%m-%dT%H:%M:%SZ"
                            ).replace(tzinfo=timezone.utc),
                            datetime.strptime(
                                value.provenance.custody.expires_at,
                                "%Y-%m-%dT%H:%M:%SZ",
                            ).replace(tzinfo=timezone.utc),
                        )
                        else "stale"
                    )
            analysis_ids = {
                s.id
                for s in document.definition.steps
                if s.kind == "shared_analysis" and s.artifact.step_id == source.step_id
            }
            analysis = _analysis_observation(attempts, analysis_ids, timestamp)
            items.append(
                CollectionItem(
                    step_id=source.step_id,
                    repository_id=source.repository_id,
                    commit_sha=source.commit_sha,
                    profile_digest=source.profile_digest,
                    routing_failure=(
                        "no_eligible_runner"
                        if attempt
                        and session.scalar(
                            select(InfraAutomationAudit.id)
                            .where(
                                InfraAutomationAudit.project_id == project_id,
                                InfraAutomationAudit.workspace_id == workspace_id,
                                InfraAutomationAudit.target_id == attempt.id,
                                InfraAutomationAudit.event_type
                                == "runner.no_eligible_runner",
                            )
                            .limit(1)
                        )
                        else None
                    ),
                    attempt_id=attempt.id if attempt else None,
                    attempt_number=attempt.attempt_number if attempt else None,
                    attempt_state=attempt.state if attempt else None,
                    lease_until=support.utc(attempt.lease_until)
                    if attempt and attempt.lease_until
                    else None,
                    observations=[
                        Observation(
                            kind="source_bound",
                            state="bound",
                            event_at=document.captured_at,
                        ),
                        Observation(kind="collection", state=collection_state),
                        Observation(
                            kind="screened_upload", state=uploaded, event_at=upload_time
                        ),
                        analysis,
                    ],
                    diagnosis=_routing(
                        session,
                        project_id,
                        workspace_id,
                        source.profile_digest,
                        grant,
                        timestamp,
                        own_attempt=attempt.id if attempt else None,
                    ),
                )
            )
        return CollectionView(
            run_id=run.id,
            project_id=project_id,
            workspace_id=workspace_id,
            run_version=run.version,
            observed_at=support.utc(timestamp),
            items=items,
            cancellation=CancellationFacts(
                can_cancel=(
                    auth.trusted_capability_allowed(
                        grant.principal, grant.role, "automation.cancel"
                    )
                    and (
                        grant.role == "admin"
                        or run.requested_by == grant.principal.principal_id
                    )
                    and run.state not in TERMINAL_STATES
                    and not run.cancel_requested
                ),
                requested=run.cancel_requested,
                requested_at=support.utc(run.cancellation_requested_at)
                if run.cancellation_requested_at
                else None,
                external_possible=run.external_possible,
            ),
            limitations=[
                "Source binding is the immutable run snapshot, not a live collector phase signal.",
                "Screening and upload are reported only after retained server evidence; intermediate collector phases are not observed.",
                "Cancellation does not prove owned processes or external work have stopped.",
            ],
        ).model_dump(mode="json")


def get_readiness(workflow_id, revision_id, *, project_id, workspace_id, now=None):
    from services import infra_automation_service as lifecycle
    from infra_automation.workflow_schema import Workflow

    with auth.authorized_session() as session:
        workflow, _ = support.workflow(
            session, workflow_id, "automation.read", mutation=False
        )
        if workflow.project_id != project_id or workflow.workspace_id not in (
            None,
            workspace_id,
        ):
            raise auth.TrustedAuthorizationError()
        grant = support.scope(
            session, project_id, workspace_id, "automation.read", mutation=False
        )
        revision = lifecycle._revision(session, workflow, revision_id)
        timestamp = _now(now)
        document = Workflow.model_validate(
            support.stored_definition(
                revision.canonical_definition,
                revision.digest,
                project_id,
                workflow.workspace_id,
            )
        )
        _, settings = support.policy_state(session, project_id)
        can_request = auth.trusted_capability_allowed(
            grant.principal, grant.role, "automation.request"
        )
        items = []
        for step in document.steps:
            if step.kind != "admitted_collection":
                continue
            source = step.source
            items.append(
                ReadinessSource(
                    step_id=step.id,
                    repository_id=source.repository_id
                    if type(source.repository_id) is str
                    else None,
                    commit_sha=source.commit_sha
                    if type(source.commit_sha) is str
                    else None,
                    profile_digest=source.profile_digest,
                    inputs_required=type(source.repository_id) is not str
                    or type(source.commit_sha) is not str,
                    diagnosis=_routing(
                        session,
                        project_id,
                        workspace_id,
                        source.profile_digest,
                        grant,
                        timestamp,
                    ),
                )
            )
        return CollectionReadiness(
            workflow_id=workflow.id,
            revision_id=revision.id,
            project_id=project_id,
            workspace_id=workspace_id,
            observed_at=support.utc(timestamp),
            execution_enabled=settings.enabled,
            can_request=can_request,
            items=items,
        ).model_dump(mode="json")
