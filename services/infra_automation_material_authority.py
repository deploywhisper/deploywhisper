"""Co-located material authority composed from retained facts and operator metadata."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from sqlalchemy import select

from infra_automation.approval_eligibility import EvidenceFacts, LiveBinding
from infra_automation.collection_contracts import CollectionProvenance
from infra_automation.decisions import (
    CollectedSource,
    Custody,
    DecisionBinding,
    DecisionProvenance,
    binding_digest,
    freeze_report_snapshot,
    instant,
)
from infra_automation.lifecycle import LifecycleError
from infra_automation.material_authority import MaterialAuthorityLedger, load_public_key
from infra_automation.material_probe import UnixMaterialCustodyProbe
from infra_automation.material_authority import MaterialAuthorityRecord
from infra_automation.targets import semantic_payload
from models.repositories import infra_automation_runs as runs
from models.repositories import infra_automation_units as unit_repository
from models.tables import (
    AnalysisReport,
    InfraAutomationArtifactManifest,
    InfraAutomationReportLink,
)
from services import infra_automation_support as support
from services.infra_automation_collection import configured_registry
from services.infra_automation_decisions import (
    DecisionMaterial,
    DecisionService,
    MaterialReadScope,
    MaterialWitness,
)
from services.infra_automation_engine_service import _document
from services.infra_automation_targets import target_for_decision


def ledger_custody_probe(record, collection, binding):
    """Trust only the operator ledger's active exact nonsecret custody receipt."""
    custody = collection.custody
    return bool(
        record.state == "active"
        and custody is not None
        and record.custody_handle == custody.handle
        and record.raw_local_digest == custody.raw_local_digest
        and record.expires_at == custody.expires_at
        and binding.provenance.custody is not None
        and binding.provenance.custody.handle == record.custody_handle
    )


class CoLocatedMaterialAuthority:
    """Resolve nonsecret authority while raw custody remains receiver-only."""

    def __init__(
        self,
        ledger_path,
        *,
        verification_key,
        recovery_status=None,
        custody_probe=None,
        clock=None,
    ):
        self.ledger = MaterialAuthorityLedger(
            ledger_path, verification_key=verification_key
        )
        self.recovery_status = recovery_status or self._configured_recovery
        self.custody_probe = custody_probe
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _configured_recovery(session):
        from infra_automation.operator_recovery import configured_store

        store = configured_store()
        if store is None:
            raise LifecycleError(503)
        try:
            return store.assert_ready(effects=True, session=session)
        except Exception:
            raise LifecycleError(503) from None

    def _now(self):
        value = self.clock()
        if type(value) is not datetime or value.tzinfo is None:
            raise LifecycleError(503)
        return value.astimezone(timezone.utc)

    def _document(self, session):
        try:
            recovery = self.recovery_status(session)
            source_id = recovery["installation_id"]
            generation = recovery["generation"]
            return self.ledger.read(source_id=source_id, recovery_generation=generation)
        except LifecycleError:
            raise
        except Exception:
            raise LifecycleError(503) from None

    @staticmethod
    def _graph(document, decision_step_id):
        nodes = {step.id: step for step in document.definition.steps}
        decision = nodes.get(decision_step_id)
        gate = nodes.get(decision.binding.step_id) if decision else None
        analysis = nodes.get(gate.report.step_id) if gate else None
        if (
            decision is None
            or decision.kind != "human_decision"
            or gate is None
            or gate.kind != "policy_evaluation"
            or analysis is None
            or analysis.kind != "shared_analysis"
        ):
            raise LifecycleError(409)
        return decision, gate, analysis

    def _derive(self, session, run, step_id, generation, previous=None):
        document = _document(run)
        _, gate, analysis = self._graph(document, step_id)
        attempts = runs.list_attempts(session, run_id=run.id)
        source_attempt = next(
            (
                item
                for item in reversed(attempts)
                if item.step_id == analysis.artifact.step_id
                and item.state == "succeeded"
            ),
            None,
        )
        analysis_attempt = next(
            (
                item
                for item in reversed(attempts)
                if item.step_id == analysis.id and item.state == "succeeded"
            ),
            None,
        )
        if source_attempt is None or analysis_attempt is None:
            raise LifecycleError(409)
        link = session.scalar(
            select(InfraAutomationReportLink).where(
                InfraAutomationReportLink.run_id == run.id,
                InfraAutomationReportLink.attempt_id == analysis_attempt.id,
                InfraAutomationReportLink.project_id == run.project_id,
                InfraAutomationReportLink.workspace_id == run.workspace_id,
            )
        )
        manifest = (
            session.get(InfraAutomationArtifactManifest, link.manifest_id)
            if link is not None
            else None
        )
        if link is None or manifest is None or manifest.collection_bytes is None:
            raise LifecycleError(409)
        try:
            collection = CollectionProvenance.model_validate_json(
                manifest.collection_bytes
            )
        except (ValueError, TypeError):
            raise LifecycleError(409) from None
        source = CollectedSource(
            repository_id=collection.repository_id,
            commit_sha=collection.commit_sha,
            collector_id=collection.scope.runner_id,
            profile_digest=collection.profile_digest,
            screened_transport_digest=manifest.digest,
            redaction_version=collection.redaction_version,
            collected_at=collection.collected_at,
            source_deadline=collection.source_deadline,
        )
        custody = Custody.model_validate(collection.custody.model_dump())
        if self._now() >= instant(custody.expires_at):
            raise LifecycleError(409)
        target = target_for_decision(session, run, document, step_id)
        if target is None:
            raise LifecycleError(409)
        report = session.get(AnalysisReport, link.report_id)
        if report is None:
            raise LifecycleError(409)
        from services.report_service import _serialize_report

        report_bytes, report_digest = freeze_report_snapshot(_serialize_report(report))
        policy_row, _ = support.policy_state(session, run.project_id)
        if policy_row is None:
            raise LifecycleError(409)
        policy_digest = support.digest(
            support.canonical(
                {
                    "automation": document.policy.model_dump(mode="json"),
                    "advisory": document.advisory_policy.model_dump(mode="json"),
                }
            )
        )
        retained_units = unit_repository.run_units(session, run.id)
        unit_digest = (
            retained_units.evidence_digest
            if retained_units is not None and retained_units.evidence_digest
            else support.digest(
                support.canonical(
                    {"version": 1, "kind": "no-declared-units", "run_id": run.id}
                )
            )
        )
        now = self._now()
        approval_deadline = (
            previous.approval_deadline
            if previous is not None
            else support.utc(
                min(
                    now + timedelta(seconds=document.policy.approval_ttl_seconds),
                    instant(source.source_deadline),
                    instant(custody.expires_at),
                )
            )
        )
        target_definition = target.definition
        values = dict(
            authorization_kind=gate.authorization_kind,
            workflow_id=run.workflow_id,
            revision_id=run.revision_id,
            workflow_revision_digest=run.definition_digest,
            input_digest=run.input_digest,
            provenance=DecisionProvenance(
                authorization_kind=gate.authorization_kind,
                source=source,
                custody=custody,
            ),
            project_id=run.project_id,
            workspace_id=run.workspace_id,
            environment=document.environment,
            canonical_target=target_definition.canonical_target,
            receiver_id=target_definition.receiver_id,
            pipeline_repository_id=target_definition.pipeline_repository_id,
            pipeline_workflow_id=target_definition.pipeline_workflow_id,
            pipeline_workflow_revision=target_definition.pipeline_workflow_revision,
            report_id=report.id,
            report_schema_version=report.report_schema_version,
            report_bytes_digest=report_digest,
            policy_version=policy_row.version,
            policy_result="passed",
            policy_digest=policy_digest,
            unit_waves_digest=unit_digest,
            screened_artifact_digests=(manifest.digest,),
            redaction_version=collection.redaction_version,
            payload_digest="sha256:" + "0" * 64,
            evidence_deadline=source.source_deadline,
            approval_deadline=approval_deadline,
            authorization_epoch=document.authority.authorization_epoch,
            restore_epoch=document.authority.restore_epoch,
        )
        provisional = DecisionBinding.model_validate_json(
            json.dumps(values, default=lambda value: value.model_dump(mode="json"))
        )
        binding = DecisionBinding.model_validate_json(
            json.dumps(
                {
                    **provisional.model_dump(mode="json"),
                    "payload_digest": support.digest(
                        semantic_payload(provisional, target)
                    ),
                }
            )
        )
        digest = binding_digest(binding)
        candidate = MaterialAuthorityRecord(
            run_id=run.id,
            step_id=step_id,
            binding_digest=digest,
            source_digest=support.digest(
                support.canonical(source.model_dump(mode="json"))
            ),
            custody_handle=custody.handle,
            raw_local_digest=custody.raw_local_digest,
            expires_at=custody.expires_at,
            generation=generation,
        )
        if self.custody_probe is None:
            raise LifecycleError(503)
        try:
            from infra_automation.receiver_protocol import (
                receiver_binding_from_decision,
            )

            receiver_binding = receiver_binding_from_decision(binding)
            if self.custody_probe(candidate, collection, receiver_binding) is not True:
                raise ValueError
        except Exception:
            raise LifecycleError(503) from None
        evidence = EvidenceFacts(
            source_kind="collected",
            source_verified=True,
            collected_at=instant(source.collected_at),
            evidence_deadline=instant(binding.evidence_deadline),
            complete=True,
            report_available=True,
            recommendation=report.recommendation,
            policy_status="advisory",
            policy_passed=True,
            artifact_step_id=analysis.artifact.step_id,
            report_step_id=analysis.id,
            evidence_ttl_seconds=document.policy.evidence_ttl_seconds,
        )
        live = LiveBinding(
            expected_tuple_digest=digest,
            current_tuple_digest=digest,
            membership_active=True,
            target_available=True,
            custody_available=True,
            approval_deadline=instant(binding.approval_deadline),
            custody_deadline=instant(custody.expires_at),
            source_deadline=instant(source.source_deadline),
            target_id=target_definition.canonical_target,
            environment=document.environment,
            authorization_kind=gate.authorization_kind,
        )
        return (
            DecisionMaterial(
                binding=binding,
                evidence=evidence,
                live=live,
                registry_contract=configured_registry(),
            ),
            candidate,
        )

    def propose_record(self, session, run, step_id, generation, previous=None):
        """Derive an exact nonsecret candidate; the operator decides publication."""
        _, record = self._derive(session, run, step_id, generation, previous)
        return record

    def material(self, session, run, step_id, previous=None):
        authority = self._document(session)
        record = next(
            (
                item
                for item in authority.records
                if item.run_id == run.id
                and item.step_id == step_id
                and item.state == "active"
            ),
            None,
        )
        if record is None:
            raise LifecycleError(503)
        material, candidate = self._derive(
            session, run, step_id, record.generation, previous
        )
        if candidate != record:
            raise LifecycleError(409)
        return material

    def witness(self, session, scope: MaterialReadScope):
        scope = MaterialReadScope.model_validate(scope)
        authority = self._document(session)
        by_step = {(item.run_id, item.step_id): item for item in authority.records}
        generations = []
        for _, step_id, digest in scope.receipts:
            record = by_step.get((scope.run_id, step_id))
            if (
                record is None
                or record.state != "active"
                or record.binding_digest != digest
            ):
                raise LifecycleError(503)
            generations.append(record.generation)
        return MaterialWitness(
            source_id=f"{authority.source_id}:g{authority.recovery_generation}",
            scope_digest=scope.digest,
            generations=tuple(generations),
        )

    def decision_service(self):
        return DecisionService(
            material_port=self.material,
            material_witness_port=self.witness,
            clock=self.clock,
        )


_configured_signature = None


def configure_colocated_defaults(
    *,
    ledger_path,
    verification_key_path,
    probe_socket_path,
    session_factory=None,
    clock=None,
):
    """Install one trusted service graph at startup; HTTP callers cannot select it."""
    global _configured_signature
    signature = (
        str(ledger_path),
        str(verification_key_path),
        str(probe_socket_path),
        id(session_factory),
        id(clock),
    )
    if _configured_signature is not None:
        if _configured_signature != signature:
            raise LifecycleError(503)
        from services import infra_automation_decisions as decisions
        from services import infra_automation_handoffs as handoffs

        return decisions._default_service, handoffs._default_service
    verification_key = load_public_key(verification_key_path)
    authority = CoLocatedMaterialAuthority(
        ledger_path,
        verification_key=verification_key,
        custody_probe=UnixMaterialCustodyProbe(probe_socket_path, verification_key),
        clock=clock,
    )
    decision_service = authority.decision_service()
    from services import infra_automation_decisions as decisions
    from services import infra_automation_handoffs as handoffs
    from services.infra_automation_receiver_composition import (
        create_github_handoff_service,
    )

    handoff_service = create_github_handoff_service(
        decision_service=decision_service,
        session_factory=session_factory,
        clock=clock,
    )
    decisions._default_service = decision_service
    handoffs._default_service = handoff_service
    _configured_signature = signature
    return decision_service, handoff_service
