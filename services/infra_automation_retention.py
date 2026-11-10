"""Conservative admin-only removal of expired screened manifest payloads."""

from __future__ import annotations

from datetime import datetime, timezone
import json

from sqlalchemy import select, update

from infra_automation.contracts import SAFE_INTEGER
from infra_automation.lifecycle import LifecycleError, SnapshotDocument
from infra_automation.retention import PurgeManifestRequest, RetentionReceipt
from infra_automation.state import TERMINAL_STATES
from models.repositories import infra_automation_reports as reports
from models.repositories import infra_automation_runs as runs
from models.tables import (
    InfraAutomationArtifactManifest,
    InfraAutomationDecision,
    InfraAutomationHandoff,
    InfraAutomationRetentionTombstone,
    InfraAutomationRun,
    InfraAutomationTargetLock,
)
from services import infra_automation_support as support
from services import project_service as authorization


def _now():
    return datetime.now(timezone.utc)


def purge_manifest(request: PurgeManifestRequest) -> dict:
    """One transaction removes bytes, retains identity/receipt, accounts and audits.

    All decisions still pending/approved and every external handoff are protected.
    This deliberately does not erase report snapshots or operator-local custody.
    """
    request = support.revalidate(request, PurgeManifestRequest)
    with authorization.authorized_session() as session:
        manifest = session.get(InfraAutomationArtifactManifest, request.manifest_id)
        if manifest is None:
            raise authorization.TrustedAuthorizationError()
        grant = support.scope(
            session,
            manifest.project_id,
            manifest.workspace_id,
            "automation.admin",
            mutation=True,
        )
        support.screened_label(request.reason)
        run = runs.get_run(session, manifest.run_id)
        if run is None:
            raise LifecycleError(503)
        document = SnapshotDocument.model_validate_json(run.snapshot_bytes)
        if (
            support.digest(run.snapshot_bytes) != run.snapshot_digest
            or (
                document.project_id,
                document.workspace_id,
                document.authority.principal_id,
            )
            != (manifest.project_id, manifest.workspace_id, manifest.requested_by)
            or (run.project_id, run.workspace_id, run.requested_by)
            != (manifest.project_id, manifest.workspace_id, manifest.requested_by)
        ):
            raise LifecycleError(503)
        request_digest = support.digest(
            support.canonical(
                {
                    **request.model_dump(mode="json"),
                    "actor_id": grant.principal.principal_id,
                }
            )
        )
        previous = session.get(InfraAutomationRetentionTombstone, manifest.id)
        if previous is not None:
            if previous.request_digest != request_digest:
                raise LifecycleError(409)
            reports.payload_removed(manifest)
            return support.bounded_payload(json.loads(previous.receipt_bytes))
        timestamp = _now()
        if type(timestamp) is not datetime or timestamp.tzinfo is None:
            raise LifecycleError(503)
        timestamp = timestamp.astimezone(timezone.utc)
        if timestamp < runs.utc(run.last_observed_at):
            raise LifecycleError(409)
        _, settings = support.policy_state(session, run.project_id)
        if (
            run.version != request.expected_run_version
            or run.state not in TERMINAL_STATES
            or run.external_possible
            or (timestamp - runs.utc(manifest.created_at)).total_seconds()
            < max(
                settings.retention_seconds,
                settings.evidence_ttl_seconds,
                document.policy.evidence_ttl_seconds,
            )
        ):
            raise LifecycleError(409)
        if (
            session.scalar(
                select(InfraAutomationDecision.id)
                .where(
                    InfraAutomationDecision.run_id == run.id,
                    InfraAutomationDecision.status.in_(("pending", "approved")),
                )
                .limit(1)
            )
            or session.scalar(
                select(InfraAutomationHandoff.id)
                .where(InfraAutomationHandoff.run_id == run.id)
                .limit(1)
            )
            or session.scalar(
                select(InfraAutomationTargetLock.id)
                .where(
                    InfraAutomationTargetLock.run_id == run.id,
                    InfraAutomationTargetLock.status != "resolved",
                )
                .limit(1)
            )
        ):
            raise LifecycleError(409)
        reports.manifest_files(manifest)
        original_size = len(manifest.artifacts_bytes)
        receipt = dict(
            version=1,
            manifest_id=manifest.id,
            run_id=run.id,
            project_id=run.project_id,
            workspace_id=run.workspace_id,
            original_digest=manifest.digest,
            original_size=original_size,
            actor_id=grant.principal.principal_id,
            deleted_at=support.utc(timestamp),
            reason=request.reason,
            content_status="removed",
        )
        receipt = RetentionReceipt.model_validate(receipt).model_dump(mode="json")
        receipt_bytes = support.canonical(receipt)
        receipt_digest = support.digest(receipt_bytes)
        # Charge both the raw receipt and every duplicated scalar representation.
        # Audit has its own copy of the bounded reason/identities. Fixed overhead
        # covers row/index bookkeeping, not SQLite physical-file measurements.
        scalar_record = {
            **receipt,
            "expected_run_version": request.expected_run_version,
            "request_digest": request_digest,
            "receipt_digest": receipt_digest,
            # Reserve the maximum decimal width before computing this self-bound debit.
            "reclaimed_bytes": SAFE_INTEGER,
        }
        audit_record = dict(
            project_id=run.project_id,
            workspace_id=run.workspace_id,
            actor_principal_id=grant.principal.principal_id,
            actor_type=grant.principal.principal_type,
            actor_role=grant.role,
            event_type="automation_manifest_content_removed",
            target_id=manifest.id,
            reason=request.reason,
            before_digest=manifest.digest,
            after_digest=receipt_digest,
            created_at=support.utc(timestamp),
        )
        retained_size = (
            len(receipt_bytes)
            + len(support.canonical(scalar_record))
            + len(support.canonical(audit_record))
            + 512
            + 2
        )
        delta = retained_size - original_size
        if delta >= 0:
            # Small content cannot reclaim capacity; preserve it instead of adding
            # storage during cleanup or pretending it freed bytes.
            raise LifecycleError(409)
        if (
            type(run.retained_bytes) is not int
            or not len(run.snapshot_bytes) <= run.retained_bytes + delta <= SAFE_INTEGER
            or not 1 <= run.version < SAFE_INTEGER
        ):
            raise LifecycleError(503)
        session.add(
            InfraAutomationRetentionTombstone(
                manifest_id=manifest.id,
                run_id=run.id,
                project_id=run.project_id,
                workspace_id=run.workspace_id,
                original_digest=manifest.digest,
                original_size=original_size,
                reclaimed_bytes=-delta,
                actor_id=grant.principal.principal_id,
                reason=request.reason,
                deleted_at=timestamp,
                expected_run_version=request.expected_run_version,
                request_digest=request_digest,
                receipt_bytes=receipt_bytes,
                receipt_digest=receipt_digest,
            )
        )
        session.flush()
        manifest.artifacts_bytes = b"[]"
        session.flush()
        changed = session.execute(
            update(InfraAutomationRun)
            .where(
                InfraAutomationRun.id == run.id,
                InfraAutomationRun.version == request.expected_run_version,
            )
            .values(
                retained_bytes=run.retained_bytes + delta,
                version=run.version + 1,
                last_observed_at=timestamp,
                updated_at=timestamp,
            )
        )
        if changed.rowcount != 1:
            raise LifecycleError(409)
        support.append_audit(
            session,
            grant,
            workspace_id=run.workspace_id,
            event_type="automation_manifest_content_removed",
            target_id=manifest.id,
            reason=request.reason,
            before_digest=manifest.digest,
            after_digest=receipt_digest,
        )
        return support.bounded_payload(receipt)
