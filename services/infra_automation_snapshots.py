"""Immutable run-snapshot consumer values; no run or execution is created here."""

from __future__ import annotations

from datetime import datetime, timezone

from infra_automation.contracts import RegistryContract
from infra_automation.lifecycle import (
    AuthorityStamp,
    CollectedSnapshotSource,
    LifecycleError,
    SnapshotDocument,
    SnapshotExport,
    UploadedSnapshotSource,
)
from infra_automation.workflow_schema import (
    AdmittedCollectionStep,
    InputReference,
    UploadedIntakeStep,
)
from infra_automation.workflow_validation import (
    ResolutionError,
    prepare_resolution,
    resolve_value,
)
from models.repositories import infra_automation_workflows as repository
from services import infra_automation_support as support
from services import project_service as authorization


def export_run_snapshot(
    workflow_id: str,
    revision_id: str,
    inputs: dict,
    workspace_id: int,
    *,
    registry_contract: RegistryContract | None = None,
) -> SnapshotExport:
    """Capture one validated publication and live human authority atomically.

    The returned stamp is public comparison data, never a credential. A future
    operation must authenticate its caller and recheck live policy before acting.
    """
    with authorization.authorized_session() as session:
        workflow, grant = support.workflow(
            session, workflow_id, "automation.request", mutation=True
        )
        if (
            grant.principal.principal_type != "human"
            or grant.principal.credential_audience != "human"
        ):
            raise authorization.TrustedAuthorizationError()
        if workflow.archived:
            raise LifecycleError(409)
        revision = repository.get_revision(session, support.identifier(revision_id))
        if (
            revision is None
            or revision.workflow_id != workflow.id
            or revision.project_id != workflow.project_id
            or revision.workspace_id != workflow.workspace_id
            or type(workspace_id) is not int
            or workspace_id < 1
            or (
                revision.workspace_id is not None
                and revision.workspace_id != workspace_id
            )
        ):
            raise authorization.TrustedAuthorizationError()
        # A project-scoped definition still needs a real, authorized execution
        # workspace. Never synthesize one or derive it from submitted metadata.
        grant = support.scope(
            session,
            workflow.project_id,
            workspace_id,
            "automation.request",
            mutation=True,
        )
        policy_row, policy = support.policy_state(session, workflow.project_id)
        if not policy.enabled or policy_row is None:
            raise LifecycleError(403)
        raw = revision.canonical_definition
        if type(raw) is not bytes or support.digest(raw) != revision.digest:
            raise LifecycleError(503)
        result = support.validate_definition(
            raw,
            revision.project_id,
            revision.workspace_id,
            registry_contract,
        )
        if not result.valid or result.canonical_bytes != raw:
            raise LifecycleError(503)
        definition = result.definition
        if type(inputs) is not dict:
            raise LifecycleError(422)
        try:
            environment = definition.environment
            if isinstance(environment, InputReference):
                environment = inputs.get(
                    environment.name, definition.inputs[environment.name].default
                )
            context = prepare_resolution(
                definition,
                inputs,
                {
                    "project_id": str(workflow.project_id),
                    "workspace_id": str(workspace_id),
                    "environment": environment,
                },
                registry_contract=registry_contract,
            )
            # Resolution imposes the scalar types/lengths before screening, so
            # caller objects cannot trigger arbitrary nested serialization.
            support.screened(inputs)
            resolved_inputs = support.screened(dict(context.inputs))
            sources: list[UploadedSnapshotSource | CollectedSnapshotSource] = []
            for step in definition.steps:
                if isinstance(step, UploadedIntakeStep):
                    sources.append(
                        UploadedSnapshotSource(
                            step_id=step.id, **step.source.model_dump()
                        )
                    )
                elif isinstance(step, AdmittedCollectionStep):
                    repository_id = resolve_value(step.source.repository_id, context)
                    commit_sha = resolve_value(step.source.commit_sha, context)
                    if not isinstance(repository_id, str) or not isinstance(
                        commit_sha, str
                    ):
                        raise LifecycleError(422)
                    sources.append(
                        CollectedSnapshotSource(
                            kind="collected",
                            step_id=step.id,
                            repository_id=repository_id,
                            commit_sha=commit_sha,
                            profile_digest=step.source.profile_digest,
                        )
                    )
            support.screened([source.model_dump(mode="json") for source in sources])
        except (ResolutionError, ValueError, TypeError):
            raise LifecycleError(422) from None
        advisory = support.advisory_policy(session, workflow.project_id)
        authority = AuthorityStamp(
            workflow_id=workflow.id,
            revision_id=revision.id,
            project_id=workflow.project_id,
            workspace_id=workspace_id,
            principal_id=grant.principal.principal_id,
            authentication_version=grant.principal.authentication_version,
            membership_version=grant.authorization_version,
            authorization_epoch=policy_row.authorization_epoch,
            restore_epoch=policy_row.restore_epoch,
            policy_digest=support.digest(
                support.canonical(policy.model_dump(mode="json"))
            ),
            advisory_policy_digest=support.digest(
                support.canonical(advisory.model_dump(mode="json"))
            ),
        )
        input_digest = support.digest(support.canonical(resolved_inputs))
        snapshot = SnapshotDocument(
            workflow_id=workflow.id,
            revision_id=revision.id,
            revision_number=revision.revision_number,
            project_id=workflow.project_id,
            workspace_id=workspace_id,
            environment=environment,
            definition=definition,
            definition_digest=revision.digest,
            inputs=resolved_inputs,
            input_digest=input_digest,
            sources=sources,
            policy=policy,
            advisory_policy=advisory,
            authority=authority,
            captured_at=support.utc(datetime.now(timezone.utc)),
        )
        canonical_bytes = support.canonical(snapshot.model_dump(mode="json"))
        if len(canonical_bytes) > 512 * 1024:
            raise LifecycleError(429)
        snapshot_digest = support.digest(canonical_bytes)
        support.append_audit(
            session,
            grant,
            workspace_id=workspace_id,
            event_type="snapshot_exported",
            target_id=revision.id,
            reason="Published revision snapshot exported.",
            before_digest=revision.digest,
            after_digest=snapshot_digest,
        )
        return SnapshotExport(
            canonical_bytes=canonical_bytes,
            digest=snapshot_digest,
            definition_digest=revision.digest,
            input_digest=input_digest,
        )
