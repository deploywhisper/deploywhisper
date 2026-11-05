"""Human-declared unit revisions and atomic advisory preflight admission.

Declared paths never become runner commands. Collected association currently
admits only the qualified repository root; source declarations confer no trust.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import secrets

from sqlalchemy import select, inspect, func
from infra_automation import claims
from infra_automation.decisions import freeze_report_snapshot, instant
from infra_automation.lifecycle import LifecycleError
from infra_automation.run_resolution import runtime_workflow
from infra_automation.unit_contracts import (
    SaveUnitsRequest,
    ValidateUnitsRequest,
    UnitRunRequest,
    UnitRevisionView,
    UnitRevisionSummary,
    UnitRevisionPage,
    UnitValidation,
    UnitRunView,
)
from infra_automation.unit_map import UnitMapError, UnitPlan, plan_unit_map
from models.repositories import infra_automation_units as repo
from models.repositories import infra_automation_runs as runs
from models.repositories import infra_automation_reports as reports
from models.repositories import infra_automation_targets as targets
from models.tables import (
    InfraAutomationRunUnits,
    InfraAutomationUnitRevision,
    InfraAutomationArtifactManifest,
    InfraAutomationReportLink,
    AnalysisReport,
    InfraAutomationRun,
)
from services import infra_automation_support as support
from services import infra_automation_engine_service as engine
from services import project_service as auth

MAX_INVENTORIES = 25
MAX_REVISIONS = 32
MAX_PROJECT_BYTES = 8 * 1024 * 1024


def _human_scope(session, project_id, workspace_id, capability, *, mutation=False):
    grant = support.scope(
        session, project_id, workspace_id, capability, mutation=mutation
    )
    if (
        grant.principal.principal_type != "human"
        or grant.principal.credential_audience != "human"
    ):
        raise auth.TrustedAuthorizationError()
    return grant


def _plan(value):
    try:
        result = plan_unit_map(value)
        support.screened(result.model_dump(mode="json"))
        return result
    except UnitMapError:
        raise LifecycleError(422) from None


def _revision_view(row):
    if support.digest(row.plan_bytes) != row.plan_digest:
        raise LifecycleError(503)
    try:
        saved = UnitPlan.model_validate_json(row.plan_bytes)
        plan = _plan(saved.inventory)
        if support.canonical(plan.model_dump(mode="json")) != row.plan_bytes:
            raise LifecycleError(503)
        return UnitRevisionView(
            inventory_id=row.inventory_id,
            revision_id=row.id,
            version=row.revision_number,
            project_id=row.project_id,
            workspace_id=row.workspace_id,
            map_digest=plan.map_digest,
            waves_digest=plan.waves_digest,
            created_by=row.created_by,
            created_at=support.utc(row.created_at),
            plan=plan,
        ).model_dump(mode="json")
    except (ValueError, TypeError):
        raise LifecycleError(503) from None


def validate_units(request: ValidateUnitsRequest):
    request = support.revalidate(request, ValidateUnitsRequest)
    with auth.authorized_session() as session:
        _human_scope(
            session, request.project_id, request.workspace_id, "automation.read"
        )
        try:
            plan = plan_unit_map(request.map)
            support.screened(plan.model_dump(mode="json"))
            value = UnitValidation(valid=True, plan=plan, errors=[])
        except UnitMapError as exc:
            value = UnitValidation(valid=False, plan=None, errors=list(exc.errors))
        return support.bounded_payload(value.model_dump(mode="json"))


def save_units(request: SaveUnitsRequest):
    request = support.revalidate(request, SaveUnitsRequest)
    plan = _plan(request.map)
    raw = support.canonical(plan.model_dump(mode="json"))
    if len(raw) > 131072:
        raise LifecycleError(429)
    with auth.authorized_session() as session:
        grant = _human_scope(
            session,
            request.project_id,
            request.workspace_id,
            "automation.draft",
            mutation=True,
        )
        support.screened_label(request.reason)
        previous = (
            repo.latest(session, request.inventory_id) if request.inventory_id else None
        )
        if request.inventory_id and (
            previous is None
            or (previous.project_id, previous.workspace_id)
            != (request.project_id, request.workspace_id)
        ):
            raise auth.TrustedAuthorizationError()
        if request.expected_version != (previous.revision_number if previous else 0):
            raise LifecycleError(409)
        existing = repo.revisions(session, request.project_id)
        if (
            (
                previous is None
                and len({row.inventory_id for row in existing}) >= MAX_INVENTORIES
            )
            or request.expected_version >= MAX_REVISIONS
            or sum(len(row.plan_bytes) + 1024 for row in existing) + len(raw) + 1024
            > MAX_PROJECT_BYTES
        ):
            raise LifecycleError(429)
        from infra_automation.storage import ensure_capacity

        import config

        bounds = config.engine_bounds()
        project_run_bytes = (
            session.scalar(
                select(func.sum(InfraAutomationRun.retained_bytes)).where(
                    InfraAutomationRun.project_id == request.project_id
                )
            )
            or 0
        )
        global_run_bytes = (
            session.scalar(select(func.sum(InfraAutomationRun.retained_bytes))) or 0
        )
        if (
            project_run_bytes
            + repo.retained_bytes(session, request.project_id)
            + len(raw)
            + 1024
            > bounds.project_bytes
            or global_run_bytes + repo.retained_bytes(session) + len(raw) + 1024
            > bounds.global_bytes
        ):
            raise LifecycleError(429)
        ensure_capacity(session, additional_bytes=len(raw) + 1024)
        row = repo.add(
            session,
            InfraAutomationUnitRevision(
                id=secrets.token_hex(24),
                inventory_id=request.inventory_id or secrets.token_hex(24),
                project_id=request.project_id,
                workspace_id=request.workspace_id,
                revision_number=request.expected_version + 1,
                plan_bytes=raw,
                plan_digest=support.digest(raw),
                created_by=grant.principal.principal_id,
                created_at=datetime.now(timezone.utc),
            ),
        )
        support.append_audit(
            session,
            grant,
            workspace_id=request.workspace_id,
            event_type="unit_inventory_revision_created",
            target_id=row.id,
            reason=request.reason,
            before_digest=previous.plan_digest if previous else None,
            after_digest=row.plan_digest,
        )
        _human_scope(
            session,
            request.project_id,
            request.workspace_id,
            "automation.draft",
            mutation=True,
        )
        return support.bounded_payload(_revision_view(row))


def list_units(project_id: int, workspace_id: int):
    with auth.authorized_session() as session:
        _human_scope(session, project_id, workspace_id, "automation.read")
        latest: dict[str, InfraAutomationUnitRevision] = {}
        for row in repo.revisions(session, project_id, workspace_id):
            latest.setdefault(row.inventory_id, row)
        if len(latest) > MAX_INVENTORIES:
            raise LifecycleError(503)
        items = [
            UnitRevisionSummary.model_validate(
                {k: v for k, v in _revision_view(row).items() if k != "plan"}
            )
            for _, row in sorted(latest.items())
        ]
        return support.bounded_payload(
            UnitRevisionPage(items=items).model_dump(mode="json")
        )


def get_revision(inventory_id, revision_id, *, project_id, workspace_id):
    with auth.authorized_session() as session:
        _human_scope(session, project_id, workspace_id, "automation.read")
        row = repo.revision(session, support.identifier(revision_id))
        if row is None or (row.inventory_id, row.project_id, row.workspace_id) != (
            support.identifier(inventory_id),
            project_id,
            workspace_id,
        ):
            raise auth.TrustedAuthorizationError()
        return support.bounded_payload(_revision_view(row))


def _ancestors(steps, step_id):
    result, pending = set(), list(steps[step_id].depends_on)
    while pending:
        current = pending.pop()
        if current not in result:
            result.add(current)
            pending.extend(steps[current].depends_on)
    return result


def _bind_steps(session, run, document, plan, bindings):
    workflow = runtime_workflow(document)
    steps = {step.id: step for step in workflow.steps}
    units = {unit.id: unit for unit in plan.inventory.units}
    by_unit = {item.unit_id: item for item in bindings}
    intakes = {
        step.id
        for step in workflow.steps
        if step.kind in {"uploaded_intake", "admitted_collection"}
    }
    analyses = {step.id for step in workflow.steps if step.kind == "shared_analysis"}
    if (
        len(by_unit) != len(bindings)
        or set(by_unit) != set(units)
        or {b.intake_step_id for b in bindings} != intakes
        or {b.analysis_step_id for b in bindings} != analyses
        or len(intakes) != len(bindings)
        or len(analyses) != len(bindings)
    ):
        raise LifecycleError(422)
    sources = {source.step_id: source for source in document.sources}
    handoffs = [s for s in workflow.steps if s.kind == "registered_github_handoff"]
    result = []
    for unit_id, unit in units.items():
        binding = by_unit[unit_id]
        intake, analysis = (
            steps[binding.intake_step_id],
            steps[binding.analysis_step_id],
        )
        if (
            unit.environment != document.environment
            or analysis.artifact.step_id != intake.id
        ):
            raise LifecycleError(422)
        source = sources.get(intake.id)
        if unit.source.kind == "uploaded":
            if source is None or source.kind != "uploaded" or not binding.artifacts:
                raise LifecycleError(422)
        elif (
            source is None
            or source.kind != "collected"
            or binding.artifacts
            or unit.source.path != "."
            or (unit.source.repository_id, unit.source.commit_sha)
            != (source.repository_id, source.commit_sha)
        ):
            raise LifecycleError(422)
        declared, pending = set(), list(unit.prerequisites)
        while pending:
            current = pending.pop()
            if current not in declared:
                declared.add(current)
                pending.extend(units[current].prerequisites)
        actual = {
            other
            for other, item in by_unit.items()
            if item.analysis_step_id in _ancestors(steps, intake.id)
        }
        intake_ancestors = _ancestors(steps, intake.id)
        if any(
            steps[ancestor].kind == "registered_github_handoff"
            for ancestor in intake_ancestors
        ):
            raise LifecycleError(422)
        intake_units = {
            other
            for other, item in by_unit.items()
            if item.intake_step_id in intake_ancestors
        }
        if actual != declared or intake_units != declared:
            raise LifecycleError(422)
        review_ancestors = _ancestors(steps, analysis.id)
        review_intakes = {
            other
            for other, item in by_unit.items()
            if other != unit_id and item.intake_step_id in review_ancestors
        }
        review_analyses = {
            other
            for other, item in by_unit.items()
            if other != unit_id and item.analysis_step_id in review_ancestors
        }
        if (
            review_intakes != declared
            or review_analyses != declared
            or any(
                steps[ancestor].kind == "registered_github_handoff"
                for ancestor in review_ancestors
            )
        ):
            raise LifecycleError(422)
        lock = dict(
            unit_id=unit_id, canonical_target=unit.target, target_id=None, lock_id=None
        )
        matched = []
        for handoff in handoffs:
            gate = steps[handoff.binding.step_id]
            if gate.report.step_id == analysis.id:
                capture = targets.get_run_target(session, run.id, handoff.id)
                if capture is None:
                    raise LifecycleError(409)
                target = targets.resolve_alias(session, unit.target.lower())
                if target is None or target.id != capture.target_id:
                    raise LifecycleError(422)
                matched.append(capture)
        if handoffs and not matched:
            raise LifecycleError(422)
        if matched:
            if len({item.target_id for item in matched}) != 1:
                raise LifecycleError(422)
            lock.update(
                canonical_target=matched[0].target_id,
                target_id=matched[0].target_id,
                lock_id=matched[0].lock_id,
            )
        result.append(lock)
    return sorted(result, key=lambda item: item["unit_id"])


def request_unit_run(
    request: UnitRunRequest, *, registry=None, registry_contract=None, now=None
):
    request = support.revalidate(request, UnitRunRequest)
    support.screened_label(request.run.reason)
    if (
        sum(
            len(item.content)
            for binding in request.bindings
            for item in binding.artifacts
        )
        > 131072
    ):
        raise LifecycleError(429)
    # The normal engine admission remains the owner of live authority, leases,
    # target locks and request idempotency. This outer transaction adds the map.
    with auth.authorized_session() as session:
        workflow, _ = support.workflow(
            session, request.run.workflow_id, "automation.request", mutation=True
        )
        grant = _human_scope(
            session,
            workflow.project_id,
            request.run.workspace_id,
            "automation.request",
            mutation=True,
        )
        revision = repo.revision(session, request.revision_id)
        if revision is None or (revision.project_id, revision.workspace_id) != (
            workflow.project_id,
            request.run.workspace_id,
        ):
            raise auth.TrustedAuthorizationError()
        view = _revision_view(revision)
        if (
            repo.latest(session, revision.inventory_id).id != revision.id
            or view["map_digest"] != request.confirmed_map_digest
        ):
            raise LifecycleError(409)
        payload = request.model_dump(mode="json")
        payload["bindings"] = sorted(
            payload["bindings"], key=lambda item: item["unit_id"]
        )
        request_bytes = support.canonical(payload)
        if len(request_bytes) > 131072:
            raise LifecycleError(429)
        request_digest = support.digest(request_bytes)
        prior = runs.get_request(
            session,
            project_id=workflow.project_id,
            workspace_id=request.run.workspace_id,
            requested_by=grant.principal.principal_id,
            key_digest=support.digest(request.run.idempotency_key.encode()),
        )
        if prior is not None:
            retained = repo.run_units(session, prior.run_id)
            if retained is None or retained.request_digest != request_digest:
                raise LifecycleError(409)
            _snapshot(session, retained)
            return engine.request_run(
                request.run,
                registry=registry,
                registry_contract=registry_contract,
                now=now,
            )
        run_view = engine.request_run(
            request.run, registry=registry, registry_contract=registry_contract, now=now
        )
        run = runs.get_run(session, run_view["id"])
        if run is None:
            raise LifecycleError(503)
        document = engine._document(run)
        plan = plan_unit_map(view["plan"]["inventory"])
        lock_bindings = _bind_steps(session, run, document, plan, request.bindings)
        payload = {
            "revision": view,
            "bindings": sorted(
                [item.model_dump(exclude={"artifacts"}) for item in request.bindings],
                key=lambda item: item["unit_id"],
            ),
            "targets": lock_bindings,
        }
        raw = support.canonical(payload)
        if len(raw) > 131072:
            raise LifecycleError(429)
        timestamp = now or datetime.now(timezone.utc)
        claims._charge(session, run, len(raw) + 1024, timestamp)
        repo.add(
            session,
            InfraAutomationRunUnits(
                run_id=run.id,
                revision_id=revision.id,
                project_id=run.project_id,
                workspace_id=run.workspace_id,
                snapshot_bytes=raw,
                snapshot_digest=support.digest(raw),
                request_digest=request_digest,
            ),
        )
        for binding in request.bindings:
            if binding.artifacts:
                auth.guard_project(
                    session,
                    run.project_id,
                    run.workspace_id,
                    "analysis.submit",
                    mutation=True,
                )
                reports.create_manifest(
                    session,
                    run,
                    binding.intake_step_id,
                    [
                        (item.name, item.content.encode("utf-8"))
                        for item in binding.artifacts
                    ],
                    now=timestamp,
                )
        support.append_audit(
            session,
            grant,
            workspace_id=run.workspace_id,
            event_type="unit_inventory_confirmed",
            target_id=run.id,
            reason=request.run.reason,
            after_digest=support.digest(raw),
        )
        _human_scope(
            session,
            run.project_id,
            run.workspace_id,
            "automation.request",
            mutation=True,
        )
        return engine._view(run)


def _snapshot(session, retained):
    if support.digest(retained.snapshot_bytes) != retained.snapshot_digest:
        raise LifecycleError(503)
    try:
        payload = json.loads(retained.snapshot_bytes)
        revision = repo.revision(session, retained.revision_id)
        if (
            revision is None
            or (revision.project_id, revision.workspace_id)
            != (retained.project_id, retained.workspace_id)
            or payload["revision"] != _revision_view(revision)
        ):
            raise LifecycleError(503)
        # Revalidate persisted values through the closed public snapshot shape.
        from infra_automation.unit_contracts import UnitRunSnapshot

        UnitRunSnapshot.model_validate(
            {
                "revision": payload["revision"],
                "bindings": payload["bindings"],
                "snapshot_digest": retained.snapshot_digest,
            }
        )
        return payload
    except (ValueError, TypeError, KeyError):
        raise LifecycleError(503) from None


def _evidence(session, run, retained, snapshot, *, now=None):
    from services.report_service import _serialize_report
    from infra_automation.collection_contracts import CollectionProvenance

    timestamp = now or datetime.now(timezone.utc)
    document = engine._document(run)
    deadline = min(
        runs.utc(run.deadline_at),
        datetime.strptime(document.captured_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        + timedelta(seconds=document.policy.evidence_ttl_seconds),
    )
    if timestamp >= deadline:
        raise LifecycleError(409)
    entries, proof = [], []
    attempts = runs.list_attempts(session, run_id=run.id)
    for binding in snapshot["bindings"]:
        latest = sorted(
            [a for a in attempts if a.step_id == binding["analysis_step_id"]],
            key=lambda a: a.attempt_number,
        )
        source_attempts = sorted(
            [a for a in attempts if a.step_id == binding["intake_step_id"]],
            key=lambda a: a.attempt_number,
        )
        if (
            not latest
            or latest[-1].state != "succeeded"
            or not source_attempts
            or source_attempts[-1].state != "succeeded"
        ):
            return None
        analysis, intake = latest[-1], source_attempts[-1]
        link = session.scalar(
            select(InfraAutomationReportLink).where(
                InfraAutomationReportLink.run_id == run.id,
                InfraAutomationReportLink.project_id == run.project_id,
                InfraAutomationReportLink.workspace_id == run.workspace_id,
                InfraAutomationReportLink.attempt_id == analysis.id,
            )
        )
        if link is None:
            return None
        manifest = session.get(InfraAutomationArtifactManifest, link.manifest_id)
        if (
            manifest is None
            or (
                manifest.run_id,
                manifest.step_id,
                manifest.project_id,
                manifest.workspace_id,
            )
            != (run.id, binding["intake_step_id"], run.project_id, run.workspace_id)
            or support.digest(manifest.artifacts_bytes) != manifest.digest
            or support.digest(link.provenance_bytes) != link.digest
            or link.attempt_id != analysis.id
            or json.loads(analysis.output_json or "null")
            != {"kind": "report", "reference": link.id, "digest": link.digest}
            or json.loads(intake.output_json or "null")
            != {
                "kind": "screened_artifacts",
                "reference": manifest.id,
                "digest": manifest.digest,
            }
        ):
            raise LifecycleError(409)
        report = session.get(AnalysisReport, link.report_id)
        if report is None or (report.project_id, report.workspace_id) != (
            run.project_id,
            run.workspace_id,
        ):
            raise LifecycleError(409)
        unit = next(
            u
            for u in snapshot["revision"]["plan"]["inventory"]["units"]
            if u["id"] == binding["unit_id"]
        )
        if unit["source"]["kind"] == "declared_repository":
            if (
                manifest.collection_bytes is None
                or support.digest(manifest.collection_bytes)
                != manifest.collection_digest
            ):
                raise LifecycleError(409)
            try:
                collection = CollectionProvenance.model_validate_json(
                    manifest.collection_bytes
                )
            except (ValueError, TypeError):
                raise LifecycleError(409) from None
            source = next(
                (s for s in document.sources if s.step_id == binding["intake_step_id"]),
                None,
            )
            link_view = reports.link_view(link)
            if (
                source is None
                or source.kind != "collected"
                or collection.profile_digest != source.profile_digest
                or collection.sanitized_digest != manifest.digest
                or link_view["provenance"] != collection.model_dump(mode="json")
                or (
                    collection.scope.project_id,
                    collection.scope.workspace_id,
                    collection.scope.attempt,
                    collection.scope.coordinator_generation,
                    collection.scope.authorization_epoch,
                    collection.scope.restore_epoch,
                )
                != (
                    str(run.project_id),
                    str(run.workspace_id),
                    intake.attempt_number,
                    intake.coordinator_generation,
                    document.authority.authorization_epoch,
                    document.authority.restore_epoch,
                )
            ):
                raise LifecycleError(409)
            collected_at = instant(collection.collected_at)
            deadline = min(
                deadline,
                instant(collection.source_deadline),
                instant(collection.custody.expires_at),
                collected_at + timedelta(seconds=document.policy.evidence_ttl_seconds),
            )
            if timestamp < collected_at or timestamp >= deadline:
                raise LifecycleError(409)
            if (
                collection.repository_id,
                collection.commit_sha,
                collection.scope.run_id,
                collection.scope.step_id,
                collection.scope.fence,
            ) != (
                unit["source"]["repository_id"],
                unit["source"]["commit_sha"],
                run.id,
                binding["intake_step_id"],
                intake.fence,
            ):
                raise LifecycleError(409)
        _, report_digest = freeze_report_snapshot(_serialize_report(report))
        source_digest = manifest.collection_digest or link.digest
        entries.append(
            dict(
                unit_id=binding["unit_id"],
                manifest_digest=manifest.digest,
                report_id=link.report_id,
                report_digest=report_digest,
                source_digest=source_digest,
            )
        )
        proof.append(
            dict(
                unit_id=binding["unit_id"],
                intake_attempt_id=intake.id,
                intake_fence=intake.fence,
                analysis_attempt_id=analysis.id,
                analysis_fence=analysis.fence,
                manifest_id=manifest.id,
                link_id=link.id,
            )
        )
    raw = support.canonical(
        {
            "version": 1,
            "kind": "unit_combined_evidence",
            "snapshot_digest": retained.snapshot_digest,
            "run_snapshot_digest": run.snapshot_digest,
            "evidence_deadline": support.utc(deadline),
            "items": entries,
            "lineage": proof,
        }
    )
    return raw, entries, deadline


def finalize_run_evidence(session, run, *, now=None):
    """Called after shared analysis commits output, inside its owning transaction."""
    # Older supported migration fixtures may intentionally lack this additive table.
    if not inspect(session.connection()).has_table("infra_automation_run_units"):
        return
    retained = repo.run_units(session, run.id)
    if retained is None or retained.evidence_bytes is not None:
        return
    evidence = _evidence(session, run, retained, _snapshot(session, retained), now=now)
    if evidence is None:
        return
    raw = evidence[0]
    if len(raw) > 131072:
        raise LifecycleError(429)
    claims._charge(session, run, len(raw) + 128, now or datetime.now(timezone.utc))
    retained.evidence_bytes, retained.evidence_digest = raw, support.digest(raw)
    session.flush()


def assert_unit_binding(session, run, binding, *, now=None):
    """An associated plan must use its server-derived, current complete bundle."""
    if not inspect(session.connection()).has_table("infra_automation_run_units"):
        return
    retained = repo.run_units(session, run.id)
    if retained is None:
        return
    snapshot = _snapshot(session, retained)
    if any(
        unit["source"]["kind"] != "declared_repository"
        for unit in snapshot["revision"]["plan"]["inventory"]["units"]
    ):
        # Uploaded prerequisites may inform review but cannot establish the
        # verified source of a combined action authorization.
        raise LifecycleError(409)
    revision = repo.revision(session, retained.revision_id)
    if repo.latest(session, revision.inventory_id).id != revision.id:
        raise LifecycleError(409)
    from services.infra_automation_targets import check_run_targets

    check_run_targets(session, run, engine._document(run))
    evidence = _evidence(session, run, retained, snapshot, now=now)
    if (
        evidence is None
        or retained.evidence_bytes is None
        or evidence[0] != retained.evidence_bytes
        or support.digest(retained.evidence_bytes) != retained.evidence_digest
        or binding.unit_waves_digest != retained.evidence_digest
        or instant(binding.evidence_deadline) > evidence[2]
    ):
        raise LifecycleError(409)


def get_run_units(run_id, *, project_id, workspace_id):
    with auth.authorized_session() as session:
        _human_scope(session, project_id, workspace_id, "automation.read")
        run, _ = engine._authorized_run(session, run_id)
        if (run.project_id, run.workspace_id) != (project_id, workspace_id):
            raise auth.TrustedAuthorizationError()
        retained = repo.run_units(session, run.id)
        value = dict(
            run_id=run.id,
            project_id=project_id,
            workspace_id=workspace_id,
            run_version=run.version,
            available=retained is not None,
            snapshot=None,
            evidence=None,
            locks=[],
        )
        if retained is not None:
            snapshot = _snapshot(session, retained)
            value["snapshot"] = {
                "revision": snapshot["revision"],
                "bindings": snapshot["bindings"],
                "snapshot_digest": retained.snapshot_digest,
            }
            revision = repo.revision(session, retained.revision_id)
            changed = repo.latest(session, revision.inventory_id).id != revision.id
            for link in reports.list_links(session, run.id):
                if auth.guard_report(session, link.report_id, "report.read") is None:
                    raise auth.TrustedAuthorizationError()
            try:
                evidence = _evidence(session, run, retained, snapshot)
            except LifecycleError:
                changed, evidence = True, None
            if evidence is not None and retained.evidence_bytes is not None:
                changed = (
                    changed
                    or evidence[0] != retained.evidence_bytes
                    or support.digest(retained.evidence_bytes)
                    != retained.evidence_digest
                )
            status = (
                "changed"
                if changed
                else "available"
                if evidence and retained.evidence_bytes
                else "pending"
            )
            value["evidence"] = dict(
                status=status,
                combined_digest=retained.evidence_digest
                if status == "available"
                else None,
                items=evidence[1] if evidence else [],
            )
            for item in snapshot["targets"]:
                lock = (
                    targets.get_lock(session, item["lock_id"])
                    if item["lock_id"]
                    else None
                )
                if item["lock_id"] and (
                    lock is None
                    or lock.run_id != run.id
                    or lock.target_id != item["target_id"]
                ):
                    raise LifecycleError(503)
                if lock is not None and lock.status != "held":
                    value["evidence"]["status"] = "changed"
                    value["evidence"]["combined_digest"] = None
                value["locks"].append(
                    dict(
                        unit_id=item["unit_id"],
                        canonical_target=item["canonical_target"],
                        status=lock.status if lock else "not_requested",
                    )
                )
        return support.bounded_payload(
            UnitRunView.model_validate(value).model_dump(mode="json")
        )
