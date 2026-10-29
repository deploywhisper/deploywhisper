"""Authorized historical approval packets with separate current reviewer context."""

from __future__ import annotations

import json
from typing import get_args

from sqlalchemy import select

import config
from infra_automation.approval_eligibility import (
    EligibilityReason,
    eligibility_from_reasons,
)
from infra_automation.decisions import binding_digest, effective_deadline
from infra_automation.lifecycle import LifecycleError
from infra_automation.review_contracts import (
    ApprovalActionSummary,
    ApprovalAttribution,
    ApprovalDeadlines,
    ApprovalDecisionContext,
    ApprovalReceipt,
    ApprovalReportSummary,
    ApprovalReviewPacket,
    ConfirmationRequirements,
)
from infra_automation.state import AuditActor
from models.repositories import infra_automation_decisions as repository
from models.repositories import infra_automation_runs as runs
from models.tables import InfraAutomationAudit
from services import infra_automation_decisions as decisions
from services import infra_automation_support as support
from services import project_service as authorization
from services.infra_automation_engine_service import _document
from services.infra_automation_policy import check_live_policy

_MESSAGES = {
    "requester_excluded": (
        "Shared requesters cannot review their own decision.",
        "Ask a distinct authorized reviewer to review this packet.",
    ),
    "reviewer_unavailable": (
        "Current reviewer authority could not be established.",
        "Sign in with an eligible scoped human reviewer account.",
    ),
    "authority_unavailable": (
        "Current decision eligibility is unavailable.",
        "Reload the packet after authority is available; do not replay a decision.",
    ),
    "feature_disabled": (
        "Workflow execution is disabled; historical evidence remains readable.",
        "Restore the approved execution policy before requesting a new decision.",
    ),
    "decision_recorded": (
        "This generation is no longer awaiting a human decision.",
        "Use the durable receipt; never resubmit a recorded generation.",
    ),
}


def _safe_text(value, *, limit=512):
    if type(value) is not str:
        raise ValueError("Expected retained text")
    # The decision view is a bounded summary, not an artifact/path inspector.
    # Preserve the retained bytes; screen only the independently typed projection.
    if "/" in value or "\\" in value:
        return "Screened text unavailable.", True
    try:
        support.screened({"text": value})
    except LifecycleError:
        return "Screened text unavailable.", True
    encoded = value.encode("utf-8", errors="strict")
    if len(encoded) > limit:
        return encoded[: limit - 3].decode("utf-8", errors="ignore") + "…", True
    return value, False


def _report_summary(payload, binding):
    limited = False

    def text(value, limit=512):
        nonlocal limited
        result, changed = _safe_text(value, limit=limit)
        limited = limited or changed
        return result

    def optional(value):
        return text(value) if value is not None else None

    def items(value):
        nonlocal limited
        if type(value) is not list:
            raise ValueError("Expected retained list")
        limited = limited or len(value) > 20
        return value[:20]

    if (
        type(payload.get("id")) is not int
        or payload.get("id") != binding.report_id
        or payload.get("report_schema_version") != "v2"
    ):
        raise ValueError("Report identity mismatch")
    context = payload.get("context_completeness")
    blast = payload.get("blast_radius")
    rollback = payload.get("rollback_plan")
    if any(type(value) is not dict for value in (context, blast, rollback)):
        raise ValueError("Incomplete retained report summary")
    summary = ApprovalReportSummary.model_validate(
        {
            "report_id": binding.report_id,
            "schema_version": "v2",
            "report_bytes_digest": binding.report_bytes_digest,
            "report_url": f"/reports/{binding.report_id}",
            "recommendation": payload["recommendation"],
            "severity": payload["severity"],
            "should_block": False,
            "confidence": {
                "score": payload["confidence"],
                "level": context["confidence_level"],
                "context_score": context["context_score"],
                "uncertainty": optional(context.get("uncertainty")),
                "context_todos": tuple(
                    text(value) for value in items(context.get("context_todos", []))
                ),
                "partial_context": context["partial_context"],
                "insufficient_context": context["insufficient_context"],
            },
            "blast_radius": {
                "direct_count": blast["direct_count"],
                "transitive_count": blast["transitive_count"],
                "affected_services": tuple(
                    text(value["label"]) for value in items(blast.get("affected", []))
                ),
                "unmatched_resource_count": len(blast.get("unmatched_resources", [])),
                "warning": optional(blast.get("warning")),
            },
            "rollback": {
                "complexity": rollback["complexity"],
                "complexity_score": rollback["complexity_score"],
                "explanation": text(rollback["complexity_explanation"]),
                "warning": optional(rollback.get("warning")),
                "steps": tuple(
                    {
                        "order": step["order"],
                        "title": text(step["title"]),
                        "estimated_minutes": step["estimated_minutes"],
                        "critical": step["critical"],
                    }
                    for step in items(rollback.get("steps", []))
                ),
            },
            "summary_limited": limited,
        }
    )
    return summary


def _action(binding):
    source = binding.provenance.source
    return ApprovalActionSummary(
        authorization_kind=binding.authorization_kind,
        canonical_target=binding.canonical_target,
        environment=binding.environment,
        receiver_id=binding.receiver_id,
        pipeline_repository_id=binding.pipeline_repository_id,
        pipeline_workflow_id=binding.pipeline_workflow_id,
        pipeline_workflow_revision=binding.pipeline_workflow_revision,
        source_kind=source.kind,
        source_repository_id=source.repository_id
        if source.kind == "collected"
        else None,
        source_commit_sha=source.commit_sha if source.kind == "collected" else None,
        unit_waves_digest=binding.unit_waves_digest,
        payload_digest=binding.payload_digest,
    )


def _guidance(reasons):
    limitations, todos = [], []
    for reason in reasons:
        if reason in _MESSAGES:
            limitation, todo = _MESSAGES[reason]
        elif reason in get_args(EligibilityReason):
            projection = eligibility_from_reasons((reason,))
            limitation, todo = projection.limitations[0], projection.context_todos[0]
        else:
            raise ValueError("Unknown decision context reason")
        limitations.append(limitation)
        todos.append(todo)
    return tuple(limitations), tuple(todos)


def _context(session, row, run, document, binding, payload, service):
    try:
        now = service._now()
    except (LifecycleError, ValueError, TypeError):
        now = None
    mode = config.settings.identity_decision_mode
    kind = {"shared": "independent-approval", "single-operator": "acknowledgement"}.get(
        mode
    )
    confirmation = (
        decisions.confirmation_requirements(binding, payload, kind)
        if kind is not None
        else ConfirmationRequirements(
            required=payload["severity"] in {"high", "critical"}
        )
    )
    status = "blocked"
    reasons = []
    policy_status = policy_passed = None
    if now is None:
        status, reasons = "unavailable", ["invalid_clock"]
    elif row.status != "pending":
        status, reasons = "decided", ["decision_recorded"]
    else:
        reasons.extend(decisions._run_time_reasons(run, now, row))
        reasons.extend(decisions._expiry_reasons(binding, now))
        latest = next(
            (
                value
                for value in repository.list_latest_for_run(session, run.id)
                if value.step_id == row.step_id
            ),
            None,
        )
        if (
            latest is None
            or latest.id != row.id
            or run.state != "waiting_approval"
            or run.cancel_requested
        ):
            reasons.append("binding_changed")
        if not reasons:
            try:
                result = authorization.check_automation_decision(
                    authorization.DecisionContext(
                        project_id=row.project_id,
                        workspace_id=row.workspace_id,
                        report_id=binding.report_id,
                        requester_principal_id=run.requested_by,
                        object_id=row.id,
                    ),
                    mutation=False,
                )
                kind = result["decision_kind"]
                confirmation = decisions.confirmation_requirements(
                    binding, payload, kind
                )
                _, settings = support.policy_state(session, row.project_id)
                if not settings.enabled:
                    reasons.append("feature_disabled")
                else:
                    check_live_policy(session, document.authority, "dispatch")
                    material, _ = service._material(
                        session, run, document, row.step_id, binding, row.report_bytes
                    )
                    if binding_digest(material.binding) != row.binding_digest:
                        reasons.append("binding_changed")
                    else:
                        results, now = service._eligibility(
                            session, run, document, row.step_id, material
                        )
                        reasons.extend(
                            reason for result in results for reason in result.reasons
                        )
                        policy_status, policy_passed = (
                            material.evidence.policy_status,
                            material.evidence.policy_passed,
                        )
            except authorization.TrustedAuthorizationError:
                principal = authorization._verified_principal(session, mutation=False)
                reasons.append(
                    "requester_excluded"
                    if kind == "independent-approval"
                    and principal.principal_id == run.requested_by
                    else "reviewer_unavailable"
                )
            except LifecycleError as error:
                if error.status_code == 503:
                    status = "unavailable"
                    reasons.append("authority_unavailable")
                else:
                    reasons.append("binding_changed")
            except (ValueError, TypeError, KeyError, AttributeError):
                status = "unavailable"
                reasons.append("authority_unavailable")
        if "invalid_clock" in reasons:
            status = "unavailable"
        if not reasons:
            status = "eligible"
    reasons = tuple(dict.fromkeys(reasons))
    limitations, todos = _guidance(reasons)
    source = binding.provenance.source
    custody = binding.provenance.custody
    return ApprovalDecisionContext(
        status=status,
        can_submit=status == "eligible"
        and row.status == "pending"
        and not reasons
        and kind is not None,
        evaluated_at=support.utc(now) if now is not None else None,
        decision_kind=kind,
        confirmation=confirmation,
        effective_deadline=support.utc(
            min(effective_deadline(binding), runs.utc(run.deadline_at))
        ),
        deadlines=ApprovalDeadlines(
            run=support.utc(run.deadline_at),
            evidence=binding.evidence_deadline,
            approval=binding.approval_deadline,
            source=source.source_deadline if source.kind == "collected" else None,
            custody=custody.expires_at if custody else None,
        ),
        policy_status=policy_status,
        policy_passed=policy_passed,
        reasons=reasons,
        limitations=limitations,
        context_todos=todos,
    )


def _attribution(session, row):
    if row.status == "pending":
        return None, False
    expected = {
        "approved": ("decision_approve",),
        "rejected": ("decision_reject",),
    }.get(row.status, ("decision_invalidated", "decision_gate_denied"))
    event = session.scalar(
        select(InfraAutomationAudit)
        .where(
            InfraAutomationAudit.target_id == row.id,
            InfraAutomationAudit.project_id == row.project_id,
            InfraAutomationAudit.workspace_id == row.workspace_id,
            InfraAutomationAudit.event_type.in_(expected),
        )
        .order_by(InfraAutomationAudit.sequence.desc())
        .limit(1)
    )
    if event is None or event.after_digest is None:
        raise LifecycleError(503)
    actor = AuditActor(event.actor_principal_id, event.actor_type, event.actor_role)
    legacy = event.before_digest is None and event.after_digest == row.binding_digest
    if (
        not legacy
        and decisions.decision_audit_digest(row, actor=actor) != event.after_digest
    ):
        raise LifecycleError(503)
    if (
        row.status in {"approved", "rejected"}
        and event.actor_principal_id != row.reviewer_id
    ):
        raise LifecycleError(503)
    reason, limited = _safe_text(event.reason)
    return ApprovalAttribution(
        event_id=event.id,
        principal_id=event.actor_principal_id,
        principal_type=event.actor_type,
        role=event.actor_role,
        project_id=event.project_id,
        workspace_id=event.workspace_id,
        reason=reason,
        occurred_at=support.utc(event.created_at),
        before_digest=event.before_digest,
        after_digest=event.after_digest,
        state_digest_version=None if legacy else 1,
    ), limited


def get_approval(approval_id, project_id, workspace_id=None, *, decision_service=None):
    """Read exact retained facts even when current decision authority is unavailable."""
    service = (
        decisions._default_service if decision_service is None else decision_service
    )
    with authorization.authorized_session() as session:
        grant = support.scope(
            session, project_id, workspace_id, "automation.decision", mutation=False
        )
        row = repository.get_request(session, support.identifier(approval_id))
        if (
            row is None
            or row.project_id != project_id
            or (workspace_id is not None and row.workspace_id != workspace_id)
        ):
            raise authorization.TrustedAuthorizationError()
        report = authorization.guard_report(
            session, row.report_id, "report.read", mutation=False
        )
        if report is None or (report.project_id, report.workspace_id) != (
            row.project_id,
            row.workspace_id,
        ):
            raise authorization.TrustedAuthorizationError()
        try:
            run = runs.get_run(session, row.run_id)
            if run is None or (run.project_id, run.workspace_id) != (
                row.project_id,
                row.workspace_id,
            ):
                raise ValueError("Missing retained run")
            document = _document(run)
            view = decisions._view(row)
            limited = False
            if view["reason"] is not None:
                view["reason"], limited = _safe_text(view["reason"], limit=2048)
            receipt = ApprovalReceipt.model_validate_json(support.canonical(view))
            binding = receipt.binding
            payload = json.loads(row.report_bytes)
            summary = _report_summary(payload, binding)
            attribution, audit_limited = _attribution(session, row)
            context = _context(session, row, run, document, binding, payload, service)
            packet = ApprovalReviewPacket(
                receipt=receipt,
                report=summary,
                action=_action(binding),
                context=context,
                attribution=attribution,
                can_export_audit=authorization.trusted_capability_allowed(
                    grant.principal, grant.role, "automation.admin"
                ),
                screening_limited=limited or audit_limited or summary.summary_limited,
            )
            value = packet.model_dump(mode="json")
            support.screened(value)
            support.bounded_payload(value)
            return packet
        except authorization.TrustedAuthorizationError:
            raise
        except (
            LifecycleError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            OverflowError,
        ):
            raise LifecycleError(503) from None
