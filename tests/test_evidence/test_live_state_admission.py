"""Retained snapshot facts cross the existing report Evidence Law boundary atomically."""

from __future__ import annotations

import json
import unittest
from datetime import timedelta
from types import SimpleNamespace
import hashlib

from sqlalchemy import func, select, delete, update
from sqlalchemy.orm import Session
from unittest.mock import patch

from cloud.base import ResourceRead, ReadStatus, SnapshotFact
from cloud.redaction import redact_snapshot
from models.repositories.cloud_snapshots import put_snapshot
from models.cloud_snapshots import CloudContextSnapshot
from evidence.models import Finding, EvidenceItem
from models.repositories.analysis_reports import create_analysis_report
from models.tables import (
    AnalysisReport,
    AppSetting,
    ProjectWorkspace,
    EvidenceItem as StoredEvidence,
    Finding as StoredFinding,
)
from services.cloud_context_service import CloudContextError, snapshot_context
from services.confidence_ledger import evidence_law_status
from tests.test_services import test_cloud_context_service as fixtures


def publish(admission, evidence, *, project_id=1, extra_evidence=()):
    finding = Finding(
        finding_id=evidence.finding_id,
        analysis_id=0,
        title="Synthetic observation",
        description="Retained fact supports this synthetic claim",
        severity="high",
        category="compute",
        deterministic=True,
        confidence=1,
        evidence_refs=[
            evidence.evidence_id,
            *[item.evidence_id for item in extra_evidence],
        ],
    )
    return create_analysis_report(
        admission.session,
        project_id=project_id,
        risk_score=70,
        severity="high",
        recommendation="no-go",
        top_risk="Synthetic observation",
        report_schema_version="v2",
        parse_summary="Synthetic",
        narrative_opening="Synthetic",
        narrative_explanation="Synthetic",
        warnings_json="[]",
        contributors_json="[]",
        analyzed_files_json="[]",
        submission_manifest_json="{}",
        submission_manifest_fallback_json="[]",
        blast_radius_json="{}",
        rollback_plan_json="{}",
        llm_provider=None,
        llm_model=None,
        llm_local_mode=None,
        assessment_source="deterministic",
        narrative_source="fallback",
        narrative_skills_json="[]",
        source_interface="test",
        trigger_type="test",
        trigger_id=None,
        dashboard_display_duration_seconds=None,
        top_risk_contributors_json=json.dumps([evidence.evidence_id]),
        findings_payload=[finding.model_dump(mode="json")],
        evidence_payload=[
            item.model_dump(mode="json") for item in (evidence, *extra_evidence)
        ],
        commit=False,
    )


class LiveStateAdmissionTests(unittest.TestCase):
    setUp = fixtures.CloudServiceTests.setUp
    tearDown = fixtures.CloudServiceTests.tearDown
    configure = fixtures.CloudServiceTests.configure

    def collect(self):
        self.configure()
        return self.service.collect(1, (fixtures.IDENTITY,)).snapshot

    def report_count(self):
        with self.factory() as db:
            return db.scalar(select(func.count()).select_from(AnalysisReport))

    def _forged_live_evidence(self, finding_id, project_id=1):
        return EvidenceItem(
            evidence_id=hashlib.sha256(
                f"forged-{finding_id}-{project_id}".encode()
            ).hexdigest(),
            analysis_id=0,
            finding_id=finding_id,
            project_id=project_id,
            source_type="live_state",
            source_ref=f"live_state://{project_id}/{'f' * 64}#{'e' * 64}",
            summary="Synthetic forged retained fact",
            severity_hint="high",
            deterministic=True,
            confidence=1,
        )

    def test_valid_minted_claim_cannot_hide_unminted_live_row_in_same_finding(self):
        snapshot = self.collect()
        with self.assertRaises(CloudContextError) as caught:
            with self.service.admit_evidence(1, snapshot.digest) as admission:
                evidence = admission.evidence_for(
                    fixtures.IDENTITY.address,
                    "state",
                    "mixed-live",
                    severity_hint="high",
                )
                forged = self._forged_live_evidence(evidence.finding_id)
                publish(admission, evidence, extra_evidence=(forged,))
        self.assertEqual(caught.exception.code, "invalid_evidence_publication")
        self.assertEqual(self.report_count(), 0)

    def test_live_uri_cannot_be_hidden_under_an_artifact_source_label(self):
        snapshot = self.collect()
        with self.assertRaises(CloudContextError):
            with self.service.admit_evidence(1, snapshot.digest) as admission:
                evidence = admission.evidence_for(
                    fixtures.IDENTITY.address,
                    "state",
                    "mislabelled",
                    severity_hint="high",
                )
                forged = self._forged_live_evidence(evidence.finding_id)
                forged.source_type = forged.source_kind = "artifact"
                publish(admission, evidence, extra_evidence=(forged,))
        self.assertEqual(self.report_count(), 0)

    def test_empty_readonly_admission_does_not_require_a_minted_claim(self):
        snapshot = self.collect()
        with self.service.admit_evidence(1, snapshot.digest):
            pass
        self.assertEqual(self.report_count(), 0)

    def test_zero_minted_claims_cannot_publish_unminted_live_rows(self):
        snapshot = self.collect()
        with self.assertRaises(CloudContextError) as caught:
            with self.service.admit_evidence(1, snapshot.digest) as admission:
                publish(admission, self._forged_live_evidence("zero-minted"))
        self.assertEqual(caught.exception.code, "invalid_evidence_publication")
        self.assertEqual(self.report_count(), 0)

    def test_new_live_rows_in_another_project_are_not_outside_publication_check(self):
        snapshot = self.collect()
        with self.assertRaises(CloudContextError):
            with self.service.admit_evidence(1, snapshot.digest) as admission:
                evidence = admission.evidence_for(
                    fixtures.IDENTITY.address,
                    "state",
                    "project-one",
                    severity_hint="high",
                )
                publish(admission, evidence)
                publish(
                    admission,
                    self._forged_live_evidence("project-two", 2),
                    project_id=2,
                )
        self.assertEqual(self.report_count(), 0)

    def test_dangling_reference_added_after_repository_gate_is_rejected(self):
        snapshot = self.collect()
        with self.assertRaises(CloudContextError):
            with self.service.admit_evidence(1, snapshot.digest) as admission:
                evidence = admission.evidence_for(
                    fixtures.IDENTITY.address, "state", "dangling", severity_hint="high"
                )
                report = publish(admission, evidence)
                finding = report.findings[0]
                finding.evidence_refs_json = json.dumps(
                    [evidence.evidence_id, "d" * 64]
                )
        self.assertEqual(self.report_count(), 0)

    def test_existing_live_rows_in_publication_report_require_their_own_validation(
        self,
    ):
        snapshot = self.collect()
        with self.service.admit_evidence(1, snapshot.digest) as admission:
            original = admission.evidence_for(
                fixtures.IDENTITY.address,
                "state",
                "original-report",
                severity_hint="high",
            )
            report_id = publish(admission, original).id
        with self.assertRaises(CloudContextError):
            with self.service.admit_evidence(1, snapshot.digest) as admission:
                additional = admission.evidence_for(
                    fixtures.IDENTITY.address,
                    "state",
                    "additional-claim",
                    analysis_id=report_id,
                )
                admission.session.add(
                    StoredFinding(
                        finding_id=additional.finding_id,
                        analysis_id=report_id,
                        title="Synthetic",
                        description="Synthetic",
                        severity="low",
                        category="compute",
                        evidence_refs_json=json.dumps([additional.evidence_id]),
                    )
                )
                admission.session.flush()
                payload = additional.model_dump(
                    exclude={"context_source", "related_change_ids"}
                )
                admission.session.add(
                    StoredEvidence(
                        **payload,
                        context_source_json=additional.context_source.model_dump_json(),
                        related_change_ids_json=json.dumps(
                            additional.related_change_ids
                        ),
                    )
                )
        self.assertEqual(self.report_count(), 1)
        with self.factory() as db:
            self.assertIsNone(db.get(StoredEvidence, additional.evidence_id))

    def test_nonlive_artifact_evidence_may_coexist_with_minted_live_claim(self):
        snapshot = self.collect()
        with self.service.admit_evidence(1, snapshot.digest) as admission:
            evidence = admission.evidence_for(
                fixtures.IDENTITY.address,
                "state",
                "mixed-artifact",
                severity_hint="high",
            )
            artifact = EvidenceItem(
                evidence_id="a" * 64,
                analysis_id=0,
                finding_id=evidence.finding_id,
                project_id=1,
                source_type="artifact",
                source_ref="artifact://synthetic.json#record",
                summary="Synthetic artifact fact",
                severity_hint="high",
                deterministic=True,
                confidence=1,
            )
            publish(admission, evidence, extra_evidence=(artifact,))
        self.assertEqual(self.report_count(), 1)
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(StoredEvidence)), 2
            )

    def test_existing_repository_and_evidence_law_accept_retained_fact(self):
        snapshot = self.collect()
        with self.service.admit_evidence(1, snapshot.digest) as admission:
            evidence = admission.evidence_for(
                fixtures.IDENTITY.address, "state", "known-fact", severity_hint="high"
            )
            report = publish(admission, evidence)
            self.assertGreater(report.id, 0)
            serialized = {
                "severity": "high",
                "findings": [
                    {"severity": "high", "evidence_refs": [evidence.evidence_id]}
                ],
                "evidence_items": [evidence.model_dump(mode="json")],
            }
            self.assertEqual(evidence_law_status(serialized)[0], "Satisfied")
            serialized["findings"][0]["evidence_refs"] = []
            self.assertEqual(evidence_law_status(serialized)[0], "Needs review")
        self.assertEqual(self.report_count(), 1)
        with self.factory() as db:
            stored = db.get(StoredEvidence, evidence.evidence_id)
            self.assertIn(snapshot.digest, stored.source_ref)
            self.assertEqual(stored.project_id, 1)

    def test_mutating_returned_evidence_cannot_change_private_expected_claim(self):
        snapshot = self.collect()
        changes = [
            lambda e: setattr(e, "summary", "Unsupported forged claim"),
            lambda e: setattr(
                e, "source_ref", "live_state://1/" + "b" * 64 + "#" + "c" * 64
            ),
            lambda e: setattr(e.context_source, "freshness_status", "stale"),
            lambda e: setattr(e.context_source, "confidence", 0.5),
            lambda e: setattr(e, "workspace_id", 999),
            lambda e: setattr(e, "project_key", "foreign-project"),
        ]
        for mutate in changes:
            with self.subTest(mutate=mutate), self.assertRaises(CloudContextError):
                with self.service.admit_evidence(1, snapshot.digest) as admission:
                    evidence = admission.evidence_for(
                        fixtures.IDENTITY.address,
                        "state",
                        "forged",
                        severity_hint="high",
                    )
                    mutate(evidence)
                    publish(admission, evidence)
            self.assertEqual(self.report_count(), 0)

    def test_crossproject_publication_rolls_back_report_and_evidence(self):
        snapshot = self.collect()
        with self.assertRaises(CloudContextError):
            with self.service.admit_evidence(1, snapshot.digest) as admission:
                evidence = admission.evidence_for(
                    fixtures.IDENTITY.address, "state", "foreign", severity_hint="high"
                )
                publish(admission, evidence, project_id=2)
        self.assertEqual(self.report_count(), 0)

    def test_revocation_before_publication_commit_rolls_back(self):
        snapshot = self.collect()
        with self.assertRaises(CloudContextError) as caught:
            with self.service.admit_evidence(1, snapshot.digest) as admission:
                evidence = admission.evidence_for(
                    fixtures.IDENTITY.address, "state", "revoked", severity_hint="high"
                )
                publish(admission, evidence)
                self.port.allowed.remove(1)
        self.assertEqual(caught.exception.code, "authorization_denied")
        self.assertEqual(self.report_count(), 0)

    def _workspaces(self):
        with self.factory() as db:
            db.add_all(
                [
                    ProjectWorkspace(
                        id=11, project_id=1, workspace_key="own", display_name="Own"
                    ),
                    ProjectWorkspace(
                        id=22,
                        project_id=2,
                        workspace_key="foreign",
                        display_name="Foreign",
                    ),
                ]
            )
            db.commit()

    def test_report_workspace_is_checked_even_when_evidence_metadata_is_none(self):
        self._workspaces()
        snapshot = self.collect()
        with self.assertRaises(CloudContextError) as caught:
            with self.service.admit_evidence(1, snapshot.digest) as admission:
                evidence = admission.evidence_for(
                    fixtures.IDENTITY.address,
                    "state",
                    "foreign-workspace",
                    severity_hint="high",
                )
                self.assertIsNone(evidence.workspace_id)
                self.assertIsNone(evidence.workspace_key)
                report = publish(admission, evidence)
                report.workspace_id = 22
        self.assertEqual(caught.exception.code, "invalid_evidence_publication")
        self.assertEqual(self.report_count(), 0)

    def test_report_workspace_check_refreshes_after_sql_changes(self):
        self._workspaces()
        snapshot = self.collect()
        with self.assertRaises(CloudContextError):
            with self.service.admit_evidence(1, snapshot.digest) as admission:
                evidence = admission.evidence_for(
                    fixtures.IDENTITY.address,
                    "state",
                    "sql-workspace",
                    severity_hint="high",
                )
                report = publish(admission, evidence)
                self.assertIsNone(report.workspace_id)
                admission.session.execute(
                    update(AnalysisReport)
                    .where(AnalysisReport.id == report.id)
                    .values(workspace_id=22)
                    .execution_options(synchronize_session=False)
                )
        self.assertEqual(self.report_count(), 0)

    def test_missing_report_workspace_lookup_fails_closed(self):
        self._workspaces()
        snapshot = self.collect()
        original = Session.get

        def missing(session, model, identity, *args, **kwargs):
            if model is ProjectWorkspace and identity == 11:
                return None
            return original(session, model, identity, *args, **kwargs)

        with (
            patch.object(Session, "get", missing),
            self.assertRaises(CloudContextError),
        ):
            with self.service.admit_evidence(1, snapshot.digest) as admission:
                evidence = admission.evidence_for(
                    fixtures.IDENTITY.address,
                    "state",
                    "missing-workspace",
                    severity_hint="high",
                )
                report = publish(admission, evidence)
                report.workspace_id = 11
        self.assertEqual(self.report_count(), 0)

    def test_authorized_report_workspace_with_optional_metadata_succeeds(self):
        self._workspaces()
        snapshot = self.collect()
        for supplied in (False, True):
            with self.subTest(metadata=supplied):
                with self.service.admit_evidence(1, snapshot.digest) as admission:
                    evidence = admission.evidence_for(
                        fixtures.IDENTITY.address,
                        "state",
                        f"own-workspace-{supplied}",
                        severity_hint="high",
                    )
                    if supplied:
                        evidence.project_key = "one"
                        evidence.workspace_id = 11
                        evidence.workspace_key = "own"
                    report = publish(admission, evidence)
                    report.workspace_id = 11
        self.assertEqual(self.report_count(), 2)

    def test_connection_commit_cannot_persist_rejected_claim(self):
        snapshot = self.collect()
        attempts = (
            lambda connection: connection.commit(),
            lambda connection: connection.get_transaction().commit(),
            lambda connection: connection.exec_driver_sql("COMMIT"),
            lambda connection: connection.exec_driver_sql(";COMMIT"),
            lambda connection: connection.exec_driver_sql("\ufeffCOMMIT"),
            lambda connection: connection.exec_driver_sql(
                "-- comment\n /* comment */ END TRANSACTION"
            ),
        )
        for attempt in attempts:
            for swallow in (False, True):
                with (
                    self.subTest(attempt=attempt, swallow=swallow),
                    self.assertRaises(CloudContextError),
                ):
                    with self.service.admit_evidence(1, snapshot.digest) as admission:
                        evidence = admission.evidence_for(
                            fixtures.IDENTITY.address, "state", "connection-commit"
                        )
                        evidence.summary = "fabricated claim"
                        publish(admission, evidence)
                        admission.session.flush()
                        if swallow:
                            try:
                                attempt(admission.session.connection())
                            except CloudContextError:
                                pass
                        else:
                            attempt(admission.session.connection())
                self.assertEqual(self.report_count(), 0)
                with self.factory() as db:
                    self.assertIsNone(db.get(StoredEvidence, evidence.evidence_id))

    def test_existing_live_evidence_mutations_are_rolled_back(self):
        snapshot = self.collect()
        with self.service.admit_evidence(1, snapshot.digest) as admission:
            evidence = admission.evidence_for(
                fixtures.IDENTITY.address, "state", "original"
            )
            publish(admission, evidence)
        mutations = (
            lambda db: setattr(
                db.get(StoredEvidence, evidence.evidence_id), "summary", "fabricated"
            ),
            lambda db: db.execute(
                update(StoredEvidence)
                .where(StoredEvidence.evidence_id == evidence.evidence_id)
                .values(summary="fabricated")
            ),
            lambda db: db.execute(
                update(StoredEvidence)
                .where(StoredEvidence.evidence_id == evidence.evidence_id)
                .values(
                    source_type="artifact",
                    source_kind="artifact",
                    source_ref="artifact://synthetic",
                )
            ),
            lambda db: db.execute(
                delete(StoredEvidence).where(
                    StoredEvidence.evidence_id == evidence.evidence_id
                )
            ),
        )
        for mutate in mutations:
            with (
                self.subTest(mutate=mutate),
                self.assertRaises(CloudContextError) as caught,
            ):
                with self.service.admit_evidence(1, snapshot.digest) as admission:
                    mutate(admission.session)
            self.assertEqual(caught.exception.code, "invalid_evidence_publication")
            with self.factory() as db:
                stored = db.get(StoredEvidence, evidence.evidence_id)
                self.assertIsNotNone(stored)
                self.assertEqual(stored.summary, evidence.summary)
                self.assertEqual(stored.source_type, "live_state")

    def test_other_project_admission_cannot_rewrite_retained_evidence(self):
        snapshot = self.collect()
        with self.service.admit_evidence(1, snapshot.digest) as admission:
            original = admission.evidence_for(
                fixtures.IDENTITY.address, "state", "owned"
            )
            publish(admission, original)
        self.service.configure(2, enabled=True, provider="reference")
        other = self.service.collect(2, (fixtures.IDENTITY,)).snapshot
        with self.assertRaises(CloudContextError) as caught:
            with self.service.admit_evidence(2, other.digest) as admission:
                admission.session.execute(
                    update(StoredEvidence)
                    .where(StoredEvidence.evidence_id == original.evidence_id)
                    .values(summary="cross-project fabricated claim")
                )
        self.assertEqual(caught.exception.code, "invalid_evidence_publication")
        with self.factory() as db:
            self.assertEqual(
                db.get(StoredEvidence, original.evidence_id).summary, original.summary
            )

    def test_early_commit_is_rejected_before_any_publication_escapes(self):
        snapshot = self.collect()
        with self.assertRaises(CloudContextError) as caught:
            with self.service.admit_evidence(1, snapshot.digest) as admission:
                evidence = admission.evidence_for(
                    fixtures.IDENTITY.address, "state", "early", severity_hint="high"
                )
                publish(admission, evidence)
                admission.session.commit()
        self.assertEqual(caught.exception.code, "authorization_transaction_changed")
        self.assertEqual(self.report_count(), 0)

    def test_unreadable_missing_and_partial_resources_cannot_mint_claims(self):
        for state in (
            ReadStatus.UNREADABLE,
            ReadStatus.UNKNOWN,
            ReadStatus.PARTIAL,
            ReadStatus.NO_LIVE_COUNTERPART,
        ):

            def change(fields, current=state):
                fields["resources"] = (
                    ResourceRead(
                        identity=fixtures.IDENTITY,
                        status=current,
                        cause="specific_read_failure"
                        if current != ReadStatus.NO_LIVE_COUNTERPART
                        else None,
                        facts=(SnapshotFact(name="state", value="running"),)
                        if current == ReadStatus.PARTIAL
                        else (),
                    ),
                )

            self.connector = fixtures.Stub(change)
            snapshot = self.collect()
            with self.subTest(state=state), self.assertRaises(CloudContextError):
                with self.service.admit_evidence(1, snapshot.digest) as admission:
                    admission.evidence_for(
                        fixtures.IDENTITY.address, "state", "unknown"
                    )
        self.connector = fixtures.Stub()
        snapshot = self.collect()
        with self.assertRaises(CloudContextError):
            with self.service.admit_evidence(1, snapshot.digest) as admission:
                admission.evidence_for(fixtures.IDENTITY.address, "absent", "absent")

    def test_missing_snapshot_and_foreign_project_never_mint(self):
        snapshot = self.collect()
        for project, digest in ((2, snapshot.digest), (1, "f" * 64)):
            with self.subTest(project=project), self.assertRaises(CloudContextError):
                with self.service.admit_evidence(project, digest):
                    pass

    def test_existing_reference_cannot_satisfy_an_unpublished_new_admission(self):
        snapshot = self.collect()
        with self.service.admit_evidence(1, snapshot.digest) as admission:
            evidence = admission.evidence_for(
                fixtures.IDENTITY.address, "state", "existing", severity_hint="high"
            )
            publish(admission, evidence)
        with self.assertRaises(CloudContextError) as caught:
            with self.service.admit_evidence(1, snapshot.digest) as admission:
                admission.evidence_for(
                    fixtures.IDENTITY.address, "state", "existing", severity_hint="high"
                )
        self.assertEqual(caught.exception.code, "evidence_not_published")

    def test_historical_report_reference_holds_expired_payload_after_disable(self):
        def old(fields):
            fields["read_window_start"] -= timedelta(days=8)
            fields["read_window_end"] -= timedelta(days=8)

        self.connector = fixtures.Stub(old)
        configuration = self.configure()
        raw = self.connector.collect(
            (fixtures.IDENTITY,), project_id=1, scope_id=configuration.scope_id
        )
        snapshot = redact_snapshot(raw, account_identifiers=(raw.scope,))
        self.assertLess(snapshot.read_window_end + timedelta(days=7), fixtures.NOW)
        # Seed the state of an already-published historical report. This is not
        # permission to mint a new claim from an unreferenced expired payload.
        resource_hash = hashlib.sha256(fixtures.IDENTITY.address.encode()).hexdigest()
        evidence = EvidenceItem(
            evidence_id="e" * 64,
            analysis_id=0,
            finding_id="historical",
            project_id=1,
            source_type="live_state",
            source_ref=f"live_state://1/{snapshot.digest}#{resource_hash}",
            artifact=snapshot.digest,
            resource=fixtures.IDENTITY.address,
            operation="read",
            summary='state = "running"',
            severity_hint="high",
            deterministic=True,
            confidence=1,
            redaction_status=snapshot.redaction_status,
            context_source=snapshot_context(snapshot, now=fixtures.NOW),
        )
        with self.factory() as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            put_snapshot(db, snapshot, mask_accounts=True)
            report = publish(SimpleNamespace(session=db), evidence)
            report_id = report.id
            db.commit()
        self.service.configure(1, enabled=False)
        self.assertEqual(self.service.get_snapshot(1, snapshot.digest), snapshot)
        self.assertEqual(self.service.purge_expired(1), 0)
        with self.factory() as db:
            db.execute(delete(AnalysisReport).where(AnalysisReport.id == report_id))
            db.commit()
        self.assertEqual(self.service.purge_expired(1), 1)
        self.assertIsNone(self.service.get_snapshot(1, snapshot.digest))

    def test_tampered_configuration_scope_is_not_defaulted_to_disabled(self):
        self.configure()
        with self.factory() as db:
            row = db.get(AppSetting, "cloud_context:1")
            data = json.loads(row.value)
            data["project_id"] = 2
            row.value = json.dumps(data)
            db.commit()
        with self.assertRaises(CloudContextError) as caught:
            self.service.collect(1, (fixtures.IDENTITY,))
        self.assertEqual(caught.exception.code, "invalid_configuration")

    def test_redaction_corpus_is_absent_from_persisted_payload(self):
        secret = "SYNTHETIC-cloud-service-secret-canary"

        def dirty(fields):
            fields["resources"] = (
                ResourceRead(
                    identity=fixtures.IDENTITY,
                    status=ReadStatus.READ,
                    facts=(
                        SnapshotFact(name="password", value=secret),
                        SnapshotFact(name="echo", value=secret),
                        SnapshotFact(
                            name="user_data", value="SYNTHETIC-user-data-body"
                        ),
                    ),
                ),
            )

        self.connector = fixtures.Stub(dirty)
        snapshot = self.collect()
        self.assertTrue(snapshot.partial)
        with self.factory() as db:
            row = db.get(CloudContextSnapshot, (1, snapshot.digest))
            self.assertNotIn(secret, row.payload_json)
            self.assertNotIn("SYNTHETIC-user-data-body", row.payload_json)
            self.assertNotIn("123456789012", row.payload_json)
        self.assertEqual(
            snapshot_context(snapshot, now=fixtures.NOW).freshness_status, "incomplete"
        )

    def test_numeric_secret_echoes_and_tag_keys_do_not_reach_database(self):
        requested = fixtures.IDENTITY.model_copy(
            update={
                "tags": (
                    ("8675309", "numeric-key"),
                    ("12.34", "float-key"),
                    ("ordinary", "8675309"),
                )
            }
        )

        def dirty(fields):
            fields["resources"] = (
                ResourceRead(
                    identity=requested,
                    status=ReadStatus.READ,
                    facts=(
                        SnapshotFact(name="password", value=8675309),
                        SnapshotFact(name="secret_key", value=12.34),
                        SnapshotFact(name="integer_echo", value=8675309),
                        SnapshotFact(name="float_echo", value=12.34),
                    ),
                ),
            )

        self.connector = fixtures.Stub(dirty)
        self.configure()
        snapshot = self.service.collect(1, (requested,)).snapshot
        with self.factory() as db:
            row = db.get(CloudContextSnapshot, (1, snapshot.digest))
            retained = json.loads(row.payload_json)
            resource_data = json.dumps(retained["resources"])
            self.assertNotIn("8675309", resource_data)
            self.assertNotIn("12.34", resource_data)
        self.assertTrue(snapshot.partial)

    def test_separate_admissions_do_not_reuse_another_reports_evidence_identity(self):
        snapshot = self.collect()
        identities = []
        for index in range(2):
            with self.service.admit_evidence(1, snapshot.digest) as admission:
                evidence = admission.evidence_for(
                    fixtures.IDENTITY.address,
                    "state",
                    f"claim-{index}",
                    severity_hint="high",
                )
                identities.append(evidence.evidence_id)
                publish(admission, evidence)
        self.assertNotEqual(*identities)
        self.assertEqual(self.report_count(), 2)
