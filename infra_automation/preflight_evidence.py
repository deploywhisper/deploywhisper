"""Versioned read projection of durable advisory preflight evidence facts.

Recovery prose is a fixed v1 interpretation of persisted state, not a new worker
event or authority. Reads remain possible when cleanup has invalidated the worker.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import get_args


from infra_automation.artifact_intake import screen_metadata
from infra_automation.lifecycle import LifecycleError, SnapshotDocument
from infra_automation.preflight_contracts import EvidenceStatus, PreflightEvidenceStatus
from infra_automation.state import AttemptState, RunState, TERMINAL_STATES


_RECOVERY: dict[str, tuple[EvidenceStatus, str, str]] = {
    "failed": (
        "failed",
        "Analysis did not complete successfully.",
        "Review the failed preflight and submit a new analysis.",
    ),
    "timed_out": (
        "failed",
        "Preflight execution timed out before completing analysis.",
        "Review execution limits and submit a new preflight.",
    ),
    "cancelled": (
        "interrupted",
        "Preflight was cancelled; evidence analysis may be incomplete.",
        "Submit a new preflight if analysis is still required.",
    ),
    "expired": (
        "interrupted",
        "Preflight expired before completing analysis.",
        "Submit a new preflight with current evidence.",
    ),
    "stopped_by_gate": (
        "interrupted",
        "Preflight stopped before completing its workflow.",
        "Review the stopped workflow before submitting a new preflight.",
    ),
    "rejected": (
        "interrupted",
        "Preflight was rejected before completing its workflow.",
        "Review the rejected workflow before submitting a new preflight.",
    ),
}


def build_evidence_status(
    run,
    document: SnapshotDocument,
    attempts,
    *,
    manifest_present: bool,
    links: list[dict],
    now: datetime,
) -> PreflightEvidenceStatus:
    """Project already-authorized facts without writes, credentials or risk logic.

    Evidence expiry follows the captured evidence policy, independently of a
    shorter requested execution timeout. The caller supplies facts from one read
    transaction; this function does not authenticate them or grant eligibility.
    """
    try:
        if (
            run.state not in get_args(RunState)
            or type(manifest_present) is not bool
            or type(links) is not list
            or len(links) > 50
            or type(now) is not datetime
            or now.tzinfo is None
        ):
            raise ValueError
        step_kinds = {step.id: step.kind for step in document.definition.steps}
        relevant = [
            attempt
            for attempt in attempts
            if step_kinds.get(attempt.step_id) in {"uploaded_intake", "shared_analysis"}
        ]
        if any(attempt.state not in get_args(AttemptState) for attempt in relevant):
            raise ValueError
        analysis = [
            attempt
            for attempt in relevant
            if step_kinds[attempt.step_id] == "shared_analysis"
        ]
        latest = max(
            analysis or relevant,
            key=lambda attempt: (attempt.attempt_number, attempt.id),
            default=None,
        )
        captured = datetime.strptime(
            document.captured_at, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        deadline = captured + timedelta(seconds=document.policy.evidence_ttl_seconds)
        timestamp = now.astimezone(timezone.utc)
        limitations = [
            "Repository source and immutable commit remain unverified for uploaded evidence."
        ]
        todos = ["Verify source identity before any handoff decision."]
        for link in links:
            retained = {key: link[key] for key in ("limitations", "context_todos")}
            if any(
                type(values) is not list
                or len(values) > 50
                or any(type(value) is not str for value in values)
                for values in retained.values()
            ):
                raise ValueError
            screen_metadata(retained)
            limitations.extend(retained["limitations"])
            todos.extend(retained["context_todos"])
        report_available = bool(links)
        status: EvidenceStatus = "available" if report_available else "pending"
        failure = _RECOVERY.get(run.state)
        if failure is None and latest is not None and not report_available:
            failure = _RECOVERY.get(latest.state)
        if failure is not None:
            status, limitation, todo = failure
            if report_available:
                limitation = "Preflight did not complete its workflow; its linked report remains advisory."
            limitations.append(limitation)
            todos.append(todo)
        if not report_available:
            if run.state in TERMINAL_STATES:
                if not manifest_present:
                    status = "missing"
                    limitations.append("Mandatory uploaded evidence is missing.")
                    todos.append(
                        "Resubmit the mandatory supported artifacts in a new preflight."
                    )
                elif run.state == "succeeded":
                    status = "missing"
                    limitations.append("Mandatory analysis report is missing.")
                    todos.append(
                        "Submit a new preflight to produce a linked analysis report."
                    )
            elif failure is None:
                limitations.append("Mandatory evidence analysis has not completed.")
                todos.append("Wait for mandatory evidence and analysis to complete.")
        if timestamp >= deadline:
            status = "stale"
            limitations.append("Evidence freshness has expired.")
            todos.append("Collect current evidence and submit a new preflight.")
        return PreflightEvidenceStatus(
            status=status,
            run_state=run.state,
            run_version=run.version,
            attempt_id=latest.id if latest is not None else None,
            attempt_state=latest.state if latest is not None else None,
            manifest_present=manifest_present,
            report_available=report_available,
            evaluated_at=timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            evidence_deadline=deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
            limitations=list(dict.fromkeys(limitations)),
            context_todos=list(dict.fromkeys(todos)),
        )
    except (ValueError, TypeError, AttributeError, KeyError, OverflowError):
        raise LifecycleError(503) from None
