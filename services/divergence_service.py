"""Bind offline plan comparison to an authorized retained observation."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from analysis.divergence import DivergenceAssessment, ObservationStatus, compare_plan
from cloud.base import LiveContextSnapshot
from evidence.models import EvidenceItem, Finding
from models.repositories.cloud_snapshots import CloudSnapshotStorageError
from parsers.base import ParseBatchResult
from services.cloud_context_service import (
    DEFAULT_SNAPSHOT_STALE_AFTER,
    CloudContextError,
    CloudContextService,
)
from services.content_security import sensitive_submission_values
from services.intake_service import build_parse_batch
from services.settings_service import provider_credential_values

DEFAULT_PLAN_STALENESS_SECONDS = 3600

_ERRORS = {
    "invalid_grounding_snapshot": "A retained snapshot digest is required for plan comparison.",
    "invalid_grounding_plan": "Supply exactly one qualified Terraform or OpenTofu recorded plan for comparison.",
    "invalid_plan_staleness": "The plan staleness threshold must be a positive integer.",
    "grounding_evidence_unavailable": "The retained grounding observation is unavailable for this project.",
}


class DivergenceRequestError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(_ERRORS[code])


class _ReportPublicationFailure(CloudContextError):
    """Carry an operational error through the cloud transaction rollback."""

    def __init__(self, error: Exception):
        super().__init__("grounded_report_persistence_failed")
        self.error = error


class _ReportGroundingAuthority:
    """Reuse current project permissions on the report publication transaction."""

    def __init__(self):
        self.report_written = False

    @contextmanager
    def session(self, project_id, operation):
        from services.project_service import (
            TrustedAuthorizationError,
            authorized_session,
        )

        try:
            with authorized_session() as session:
                self.check(session, project_id, operation)
                yield session
                self.check(session, project_id, operation)
        except TrustedAuthorizationError:
            raise
        except (OSError, SQLAlchemyError, CloudSnapshotStorageError) as exc:
            if self.report_written:
                raise _ReportPublicationFailure(exc) from exc
            raise

    def check(self, session, project_id, operation):
        from services.project_service import guard_project

        if operation != "admit":
            raise CloudContextError("authorization_unavailable")
        # Snapshots are project-wide. A workspace-only grant cannot read them.
        guard_project(session, project_id, capability="report.read", mutation=False)
        guard_project(session, project_id, capability="analysis.submit", mutation=True)


@contextmanager
def divergence_admission(
    project_id: int, digest: str, *, comparison: DivergenceAssessment | None = None
):
    from services.project_service import TrustedAuthorizationError

    authority = _ReportGroundingAuthority()
    service = CloudContextService(unit_of_work=authority)

    def check_finalization(snapshot):
        ensure_comparison_publishable(comparison, snapshot)

    try:
        with service.admit_evidence(
            project_id,
            digest,
            before_finalize=check_finalization if comparison is not None else None,
        ) as admission:
            try:
                yield admission
            except (
                CloudContextError,
                TrustedAuthorizationError,
                DivergenceRequestError,
            ):
                raise
            except Exception as exc:
                raise _ReportPublicationFailure(exc) from exc
            # Evidence verification and the retention recheck run after this
            # body, inside the same transaction and before its owning commit.
            authority.report_written = comparison is not None
    except _ReportPublicationFailure as exc:
        raise exc.error from None
    except CloudContextError:
        raise DivergenceRequestError("grounding_evidence_unavailable") from None


def _observation_status(snapshot: LiveContextSnapshot) -> ObservationStatus:
    # Evaluate observation age independently of resource-level completeness.
    age = datetime.now(timezone.utc) - snapshot.read_window_end
    if age < timedelta(0):
        return "unknown"
    return "stale" if age > DEFAULT_SNAPSHOT_STALE_AFTER else "current"


def ensure_comparison_publishable(
    comparison: DivergenceAssessment, snapshot: LiveContextSnapshot
) -> None:
    """An observation that ceased to be current can no longer support the result."""
    if (
        comparison.observation_status == "current"
        and _observation_status(snapshot) != "current"
    ):
        raise DivergenceRequestError("grounding_evidence_unavailable")


def compare_retained_plan(
    files: list[tuple[str, bytes | None]],
    *,
    project_id: int,
    snapshot_digest: str,
    stale_after_seconds: int | None,
    parse_batch: ParseBatchResult | None = None,
) -> DivergenceAssessment:
    if not isinstance(snapshot_digest, str) or not re.fullmatch(
        r"[0-9a-f]{64}", snapshot_digest
    ):
        raise DivergenceRequestError("invalid_grounding_snapshot")
    if stale_after_seconds is None:
        stale_after_seconds = DEFAULT_PLAN_STALENESS_SECONDS
    if type(stale_after_seconds) is not int or stale_after_seconds <= 0:
        raise DivergenceRequestError("invalid_plan_staleness")
    if parse_batch is None:
        parse_batch = build_parse_batch(files)
    # Count every admitted Terraform JSON plan before checking its format.
    plans = [
        item
        for item in parse_batch.files
        if item.tool == "terraform" and Path(item.file_name.lower()).suffix == ".json"
    ]
    if len(plans) != 1 or plans[0].status != "parsed":
        raise DivergenceRequestError("invalid_grounding_plan")
    sources = [content for name, content in files if name == plans[0].file_name]
    if len(sources) != 1 or sources[0] is None or len(sources[0]) > 50 * 1024 * 1024:
        raise DivergenceRequestError("invalid_grounding_plan")
    try:
        plan = json.loads(sources[0])
    except (ValueError, RecursionError):
        raise DivergenceRequestError("invalid_grounding_plan") from None
    if (
        not isinstance(plan, dict)
        or plan.get("format_version") != "1.2"
        or not isinstance(plan.get("resource_changes"), list)
    ):
        raise DivergenceRequestError("invalid_grounding_plan")
    with divergence_admission(project_id, snapshot_digest) as admission:
        snapshot = admission.snapshot
    sensitive_values = sensitive_submission_values(files) + provider_credential_values()
    try:
        return compare_plan(
            plan,
            snapshot,
            stale_after_seconds=stale_after_seconds,
            sensitive_values=sensitive_values,
            observation_status=_observation_status(snapshot),
        )
    except (ValueError, TypeError, RecursionError):
        raise DivergenceRequestError("invalid_grounding_plan") from None


def divergence_findings(
    comparison: DivergenceAssessment, admission
) -> tuple[list[Finding], list[EvidenceItem]]:
    findings, evidence_items = [], []
    for resource in comparison.resources:
        if resource.status != "diverged":
            continue
        finding_id = f"divergence-{uuid4().hex}"
        severity = (
            "medium" if any(d.requires_caution for d in resource.differences) else "low"
        )
        evidence = [
            admission.evidence_for(
                resource.address, name, finding_id, severity_hint=severity
            )
            for name in dict.fromkeys(
                name
                for difference in resource.differences
                for name in (difference.fact_name, *difference.supporting_fact_names)
            )
        ]
        triples = []
        for change in resource.differences:
            planned = json.dumps(change.planned) if change.planned_known else "unknown"
            triples.append(
                f"{change.attribute}: recorded {json.dumps(change.recorded)}, "
                f"live {json.dumps(change.live)}, planned {planned}."
            )
        findings.append(
            Finding(
                finding_id=finding_id,
                analysis_id=0,
                title="Plan differs from observed reality",
                category="plan_reality_divergence",
                description=f"{resource.address}. " + " ".join(triples),
                severity=severity,
                deterministic=True,
                confidence=1.0,
                evidence_refs=[item.evidence_id for item in evidence],
                guidance=["Regenerate the plan against the current environment."],
            )
        )
        evidence_items.extend(evidence)
    return findings, evidence_items


def _verified_timing(comparison: DivergenceAssessment) -> bool:
    return (
        comparison.observation_status == "current"
        and comparison.freshness.status != "unknown"
    )


def divergence_has_gaps(comparison: DivergenceAssessment) -> bool:
    return not _verified_timing(comparison) or any(
        row.status in {"unknown", "unreadable"}
        or row.reason == "comparable_facts_incomplete"
        for row in comparison.resources
    )


def divergence_gate_exit_code(comparison: DivergenceAssessment | None) -> int:
    """A confirmed current divergence wins over unrelated unresolved resources."""
    if comparison is None:
        return 2
    if comparison.diverged and _verified_timing(comparison):
        return 3
    return 2 if divergence_has_gaps(comparison) else 0
