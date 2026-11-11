"""Fixed policy-step worker over retained report, policy, and target facts."""

from __future__ import annotations

from datetime import datetime, timezone

from infra_automation import claims
from infra_automation.lifecycle import LifecycleError
from infra_automation.run_resolution import runtime_workflow
from infra_automation.state import AttemptHandle, OutputReference, WorkerResult
from models.tables import InfraAutomationReportLink
from services import infra_automation_support as support
from services import project_service as authorization


def execute_policy_step(value, handle=None, factory=None):
    """Evaluate only the server-retained policy input; mint no approval authority."""
    if type(handle) is not AttemptHandle or not callable(factory):
        raise authorization.TrustedAuthorizationError()
    now = datetime.now(timezone.utc)
    with authorization.authorized_session(factory) as session:
        attempt = claims._attempt(session, handle, now)
        run, document = claims._run(session, handle.run_id, now)
        if (
            attempt.state != "running"
            or attempt.step_kind != "policy_evaluation"
            or value.snapshot_bytes != run.snapshot_bytes
            or value.step_id != handle.step_id
        ):
            raise authorization.TrustedAuthorizationError()
        member = authorization.membership_repository.get_membership(
            session,
            principal_id=handle.principal_id,
            project_id=handle.project_id,
        )
        if (
            member is None
            or not member.enabled
            or "automation.request"
            not in authorization.PROJECT_ROLE_CAPABILITIES.get(member.role, ())
        ):
            raise authorization.TrustedAuthorizationError()
        workflow = runtime_workflow(document)
        step = next(
            (item for item in workflow.steps if item.id == handle.step_id), None
        )
        if step is None or step.kind != "policy_evaluation":
            raise LifecycleError(409)
        prerequisite = dict(value.prerequisites).get(step.report.step_id)
        if prerequisite is None:
            raise LifecycleError(409)
        report_reference = OutputReference.model_validate_json(prerequisite)
        link = session.get(InfraAutomationReportLink, report_reference.reference)
        if (
            report_reference.kind != "report"
            or link is None
            or report_reference.digest != link.digest
            or (link.run_id, link.project_id, link.workspace_id)
            != (run.id, run.project_id, run.workspace_id)
        ):
            raise LifecycleError(409)
        from services.infra_automation_policy import check_live_policy

        check_live_policy(session, document.authority, "dispatch")
        policy_row, settings = support.policy_state(session, run.project_id)
        if policy_row is None:
            raise LifecycleError(409)
        decisions = [
            item
            for item in workflow.steps
            if item.kind == "human_decision" and item.binding.step_id == step.id
        ]
        if not decisions:
            raise LifecycleError(409)
        from infra_automation.targets import target_snapshot_bytes
        from services.infra_automation_targets import target_for_decision

        snapshots = [
            target_for_decision(session, run, document, decision.id)
            for decision in decisions
        ]
        if any(snapshot is None for snapshot in snapshots):
            raise LifecycleError(409)
        target_digests = {
            support.digest(target_snapshot_bytes(snapshot)) for snapshot in snapshots
        }
        if len(target_digests) != 1:
            raise LifecycleError(409)
        digest = support.digest(
            support.canonical(
                {
                    "version": 1,
                    "run_id": run.id,
                    "step_id": step.id,
                    "report_link_id": link.id,
                    "report_link_digest": link.digest,
                    "policy_version": policy_row.version,
                    "policy": settings.model_dump(mode="json"),
                    "advisory_policy": document.advisory_policy.model_dump(mode="json"),
                    "target_snapshot_digest": next(iter(target_digests)),
                    "authorization_kind": step.authorization_kind,
                    "environment": step.environment,
                }
            )
        )
        return WorkerResult(
            outcome="local_success",
            output=OutputReference(
                kind="action_binding", reference=link.id, digest=digest
            ),
        )
