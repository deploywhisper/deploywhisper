"""Tests for incident ingestion and retrieval."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path
from unittest.mock import patch

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.report_service as report_service_module
import services.incident_service as incident_service_module
import services.incident_import_service as incident_import_service_module
import services.project_service as project_service_module
import analysis.incident_matcher as incident_matcher_module
from analysis.risk_scorer import RiskAssessment
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult
from sqlalchemy.exc import IntegrityError


def _incident_file_content(title: str, reference: str = "INC-900") -> str:
    return (
        '{"title":"' + title + '","severity":"high",'
        '"incident_date":"2026-05-20",'
        '"root_cause":"Ingress drift.",'
        '"trigger_change":"Security group update.",'
        '"affected_services":["checkout-api"],'
        '"rollback_path":"Restore previous security group.",'
        '"prevention_notes":["Review ingress diffs."],'
        f'"source":{{"system":"manual","reference":"{reference}"}},'
        '"redaction":{"status":"redacted","contains_sensitive_data":false}}'
    )


class IncidentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "incidents.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        reload(report_service_module)
        reload(incident_service_module)
        reload(incident_import_service_module)
        reload(incident_matcher_module)
        database_module.init_db()
        self.project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_ingest_incident_document_persists_record(self) -> None:
        result = incident_service_module.ingest_incident_document(
            "incident.md",
            "# Database exposure\nDate: 2026-04-16\nSeverity: P1\nThe security group was opened too broadly.",
            project_id=self.project.id,
        )
        self.assertEqual(result["title"], "Database exposure")
        self.assertEqual(result["severity"], "critical")
        self.assertEqual(result["incident_date"], "2026-04-16")

        records = incident_service_module.get_incident_records(
            project_id=self.project.id
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source_file"], "incident.md")
        self.assertEqual(records[0]["project_id"], self.project.id)

    def test_ingest_incident_document_requires_project_scope(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            incident_service_module.ingest_incident_document(
                "incident.md",
                "# Database exposure\nSeverity: high\nRollback required.",
            )

        self.assertIn("Project scope is required", str(ctx.exception))

    def test_incident_matcher_can_load_stored_candidates(self) -> None:
        incident_service_module.ingest_incident_document(
            "incident.md",
            "# Database exposure\nSeverity: high\nThe security group was opened too broadly.",
            project_id=self.project.id,
        )
        candidates = incident_matcher_module.load_incident_candidates(
            project_id=self.project.id
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["title"], "Database exposure")

    def test_incident_candidates_do_not_cross_project_or_workspace(self) -> None:
        other_project = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        prod_workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production",
        )
        staging_workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="staging",
            display_name="Staging",
        )
        incident_service_module.ingest_incident_document(
            "payments-prod.md",
            "# Payments prod exposure\nSeverity: high\nPayment API ingress opened.",
            project_id=self.project.id,
            workspace_id=prod_workspace.id,
        )
        incident_service_module.ingest_incident_document(
            "payments-staging.md",
            "# Payments staging exposure\nSeverity: high\nPayment API ingress opened.",
            project_id=self.project.id,
            workspace_id=staging_workspace.id,
        )
        incident_service_module.ingest_incident_document(
            "platform.md",
            "# Platform exposure\nSeverity: high\nPlatform ingress opened.",
            project_id=other_project.id,
        )

        prod_candidates = incident_matcher_module.load_incident_candidates(
            project_id=self.project.id,
            workspace_id=prod_workspace.id,
        )
        project_candidates = incident_matcher_module.load_incident_candidates(
            project_id=self.project.id,
        )

        self.assertEqual(
            [item["source_file"] for item in prod_candidates], ["payments-prod.md"]
        )
        self.assertEqual(
            [item["source_file"] for item in project_candidates],
            ["payments-prod.md", "payments-staging.md"],
        )

    def test_ingest_plain_text_without_heading_or_severity_uses_fallbacks(self) -> None:
        result = incident_service_module.ingest_incident_document(
            "plain.txt",
            "Database access widened during deployment and required emergency rollback.",
            project_id=self.project.id,
        )
        self.assertEqual(
            result["title"],
            "Database access widened during deployment and required emergency rollback.",
        )
        self.assertEqual(result["severity"], "unknown")
        self.assertIsNone(result["incident_date"])

    def test_ingest_incident_document_can_reference_analysis_id(self) -> None:
        project = self.project
        report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="incident-link.tf",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=10,
                severity="low",
                recommendation="go",
                top_risk="Linked incident test report.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: linked incident test report.",
                explanation="Linked incident test report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=project.id,
            audit_context={"source_interface": "api"},
        )

        result = incident_service_module.ingest_incident_document(
            "incident.md",
            "# Linked incident\nSeverity: high\nRollback after deploy.",
            analysis_id=report["id"],
        )

        self.assertEqual(result["analysis_id"], report["id"])
        records = incident_service_module.get_incident_records(project_id=project.id)
        self.assertEqual(records[0]["analysis_id"], report["id"])
        self.assertEqual(records[0]["project_id"], project.id)

    def test_incident_ingestion_status_summarizes_indexed_records(self) -> None:
        incident_service_module.ingest_incident_document(
            "checkout-ingress.md",
            (
                "# Checkout ingress exposure\n"
                "Date: 2026-04-20\n"
                "Severity: high\n"
                "Redaction status: redacted\n"
                "Payment API ingress opened."
            ),
            project_id=self.project.id,
        )

        status = incident_service_module.get_incident_ingestion_status(
            project_id=self.project.id
        )

        self.assertEqual(status.project_id, self.project.id)
        self.assertEqual(status.indexed_count, 1)
        self.assertEqual(status.rejected_count, 0)
        self.assertEqual(status.redaction_status, "redacted")
        self.assertEqual(status.freshness_status, "current")
        self.assertIsNotNone(status.last_indexed_at)
        self.assertEqual(len(status.sources), 1)
        self.assertEqual(status.sources[0].import_source, "checkout-ingress.md")
        self.assertEqual(status.sources[0].indexed_count, 1)
        self.assertEqual(status.sources[0].failure_summaries, [])

    def test_incident_reindex_replaces_and_removes_stale_entries_by_project_scope(
        self,
    ) -> None:
        other_project = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        incident_import_service_module.reindex_incident_files(
            [
                incident_import_service_module.IncidentImportFile(
                    source_file="checkout.json",
                    content=(
                        '{"title":"Old checkout incident","severity":"low",'
                        '"incident_date":"2026-05-19",'
                        '"root_cause":"Old ingress drift.",'
                        '"trigger_change":"Security group update.",'
                        '"affected_services":["checkout-api"],'
                        '"rollback_path":"Restore previous security group.",'
                        '"prevention_notes":["Review ingress diffs."],'
                        '"source":{"system":"manual","reference":"INC-899"},'
                        '"redaction":{"status":"none","contains_sensitive_data":false}}'
                    ),
                ),
                incident_import_service_module.IncidentImportFile(
                    source_file="stale.json",
                    content=(
                        '{"title":"Stale incident","severity":"medium",'
                        '"incident_date":"2026-05-18",'
                        '"root_cause":"Legacy drift.",'
                        '"trigger_change":"Legacy update.",'
                        '"affected_services":["checkout-api"],'
                        '"rollback_path":"Restore legacy config.",'
                        '"prevention_notes":["Retire stale source."],'
                        '"source":{"system":"manual","reference":"INC-898"},'
                        '"redaction":{"status":"none","contains_sensitive_data":false}}'
                    ),
                ),
            ],
            project_id=self.project.id,
        )
        incident_service_module.ingest_incident_document(
            "stale.json",
            "# Other project stale incident\nSeverity: high\nRedaction status: none\nKeep me.",
            project_id=other_project.id,
        )

        result = incident_import_service_module.reindex_incident_files(
            [
                incident_import_service_module.IncidentImportFile(
                    source_file="checkout.json",
                    content=(
                        '{"title":"Updated checkout incident","severity":"high",'
                        '"incident_date":"2026-05-20",'
                        '"root_cause":"Ingress drift.",'
                        '"trigger_change":"Security group update.",'
                        '"affected_services":["checkout-api"],'
                        '"rollback_path":"Restore previous security group.",'
                        '"prevention_notes":["Review ingress diffs."],'
                        '"source":{"system":"manual","reference":"INC-900"},'
                        '"redaction":{"status":"redacted","contains_sensitive_data":false}}'
                    ),
                )
            ],
            project_id=self.project.id,
            remove_missing_sources=True,
        )

        records = incident_service_module.get_incident_records(
            project_id=self.project.id
        )
        other_records = incident_service_module.get_incident_records(
            project_id=other_project.id
        )

        self.assertEqual(result.indexed_count, 1)
        self.assertEqual(result.replaced_count, 1)
        self.assertEqual(result.removed_count, 1)
        self.assertEqual(result.status.indexed_count, 1)
        self.assertEqual(
            [record["source_file"] for record in records], ["checkout.json"]
        )
        self.assertEqual(records[0]["title"], "Updated checkout incident")
        self.assertEqual(
            [record["source_file"] for record in other_records], ["stale.json"]
        )
        self.assertEqual(result.status.freshness_status, "current")

    def test_reindex_invalidates_backtesting_snapshot_after_success(self) -> None:
        with patch(
            "services.incident_import_service.invalidate_backtesting_snapshot"
        ) as invalidate:
            incident_import_service_module.reindex_incident_files(
                [
                    incident_import_service_module.IncidentImportFile(
                        source_file="checkout.json",
                        content=_incident_file_content("Updated checkout incident"),
                    )
                ],
                project_id=self.project.id,
            )

        invalidate.assert_called_once_with(project_id=self.project.id)

    def test_reindex_failure_status_persists_actionable_correction_paths(self) -> None:
        with self.assertRaises(
            incident_import_service_module.IncidentImportValidationError
        ):
            incident_import_service_module.reindex_incident_files(
                [
                    incident_import_service_module.IncidentImportFile(
                        source_file="broken.json",
                        content="{}",
                    )
                ],
                project_id=self.project.id,
            )

        status = incident_service_module.get_incident_ingestion_status(
            project_id=self.project.id
        )

        self.assertEqual(status.indexed_count, 0)
        self.assertGreater(status.rejected_count, 0)
        self.assertEqual(status.sources[0].import_source, "broken.json")
        self.assertGreater(status.sources[0].rejected_count, 0)
        self.assertIn("Add", status.sources[0].failure_summaries[0].correction_path)
        self.assertTrue(status.sources[0].failure_summaries[0].message)

    def test_import_failure_status_persists_actionable_source_failures(self) -> None:
        with self.assertRaises(
            incident_import_service_module.IncidentImportValidationError
        ):
            incident_import_service_module.import_incident_files(
                [
                    incident_import_service_module.IncidentImportFile(
                        source_file="broken.json",
                        content="{}",
                    )
                ],
                project_id=self.project.id,
            )

        status = incident_service_module.get_incident_ingestion_status(
            project_id=self.project.id
        )

        self.assertEqual(status.indexed_count, 0)
        self.assertGreater(status.rejected_count, 0)
        self.assertEqual(len(status.sources), 1)
        self.assertEqual(status.sources[0].import_source, "broken.json")
        self.assertGreater(status.sources[0].rejected_count, 0)
        self.assertIn("Add", status.sources[0].failure_summaries[0].correction_path)

    def test_successful_import_clears_previous_failed_source_status(self) -> None:
        with self.assertRaises(
            incident_import_service_module.IncidentImportValidationError
        ):
            incident_import_service_module.reindex_incident_files(
                [
                    incident_import_service_module.IncidentImportFile(
                        source_file="checkout.json",
                        content="{}",
                    )
                ],
                project_id=self.project.id,
            )

        incident_import_service_module.import_incident_files(
            [
                incident_import_service_module.IncidentImportFile(
                    source_file="checkout.json",
                    content=_incident_file_content("Recovered checkout incident"),
                )
            ],
            project_id=self.project.id,
        )
        status = incident_service_module.get_incident_ingestion_status(
            project_id=self.project.id
        )

        self.assertEqual(status.indexed_count, 1)
        self.assertEqual(status.rejected_count, 0)
        self.assertEqual(len(status.sources), 1)
        self.assertEqual(status.sources[0].import_source, "checkout.json")
        self.assertEqual(status.sources[0].failure_summaries, [])

    def test_reindex_duplicate_source_files_rejected_without_changing_index(
        self,
    ) -> None:
        incident_import_service_module.reindex_incident_files(
            [
                incident_import_service_module.IncidentImportFile(
                    source_file="checkout.json",
                    content=_incident_file_content("Stable checkout incident"),
                )
            ],
            project_id=self.project.id,
        )

        with self.assertRaises(
            incident_import_service_module.IncidentImportValidationError
        ):
            incident_import_service_module.reindex_incident_files(
                [
                    incident_import_service_module.IncidentImportFile(
                        source_file="checkout.json",
                        content=_incident_file_content("Updated checkout incident"),
                    ),
                    incident_import_service_module.IncidentImportFile(
                        source_file="checkout.json",
                        content=_incident_file_content("Duplicate checkout incident"),
                    ),
                ],
                project_id=self.project.id,
            )

        records = incident_service_module.get_incident_records(
            project_id=self.project.id
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "Stable checkout incident")

    def test_reindex_rolls_back_existing_index_when_insert_fails(self) -> None:
        incident_import_service_module.reindex_incident_files(
            [
                incident_import_service_module.IncidentImportFile(
                    source_file="checkout.json",
                    content=_incident_file_content("Stable checkout incident"),
                )
            ],
            project_id=self.project.id,
        )

        with (
            patch(
                "services.incident_import_service.create_incident_record_in_session",
                side_effect=RuntimeError("forced insert failure"),
            ),
            self.assertRaises(RuntimeError),
        ):
            incident_import_service_module.reindex_incident_files(
                [
                    incident_import_service_module.IncidentImportFile(
                        source_file="checkout.json",
                        content=_incident_file_content("Updated checkout incident"),
                    )
                ],
                project_id=self.project.id,
            )

        records = incident_service_module.get_incident_records(
            project_id=self.project.id
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "Stable checkout incident")

    def test_remove_missing_sources_only_removes_managed_reindex_sources(self) -> None:
        incident_service_module.ingest_incident_document(
            "manual.json",
            "# Manual incident\nSeverity: high\nRedaction status: none\nKeep me.",
            project_id=self.project.id,
        )
        incident_import_service_module.reindex_incident_files(
            [
                incident_import_service_module.IncidentImportFile(
                    source_file="managed.json",
                    content=_incident_file_content("Managed incident"),
                )
            ],
            project_id=self.project.id,
        )

        result = incident_import_service_module.reindex_incident_files(
            [
                incident_import_service_module.IncidentImportFile(
                    source_file="replacement.json",
                    content=_incident_file_content("Replacement incident"),
                )
            ],
            project_id=self.project.id,
            remove_missing_sources=True,
        )
        records = incident_service_module.get_incident_records(
            project_id=self.project.id
        )

        self.assertEqual(result.removed_count, 1)
        self.assertEqual(
            [record["source_file"] for record in records],
            ["manual.json", "replacement.json"],
        )

    def test_remove_missing_sources_removes_managed_import_sources(self) -> None:
        incident_import_service_module.import_incident_files(
            [
                incident_import_service_module.IncidentImportFile(
                    source_file="managed-a.json",
                    content=_incident_file_content("Managed A", reference="INC-A"),
                ),
                incident_import_service_module.IncidentImportFile(
                    source_file="managed-b.json",
                    content=_incident_file_content("Managed B", reference="INC-B"),
                ),
            ],
            project_id=self.project.id,
        )

        result = incident_import_service_module.reindex_incident_files(
            [
                incident_import_service_module.IncidentImportFile(
                    source_file="managed-a.json",
                    content=_incident_file_content(
                        "Managed A updated", reference="INC-A2"
                    ),
                )
            ],
            project_id=self.project.id,
            remove_missing_sources=True,
        )
        records = incident_service_module.get_incident_records(
            project_id=self.project.id
        )

        self.assertEqual(result.removed_count, 1)
        self.assertEqual(
            [record["source_file"] for record in records],
            ["managed-a.json"],
        )
        self.assertEqual(records[0]["title"], "Managed A updated")

    def test_project_wide_authoritative_reindex_removes_workspace_managed_sources(
        self,
    ) -> None:
        workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production",
        )
        incident_import_service_module.import_incident_files(
            [
                incident_import_service_module.IncidentImportFile(
                    source_file="workspace-managed.json",
                    content=_incident_file_content(
                        "Workspace managed", reference="INC-WS"
                    ),
                )
            ],
            project_id=self.project.id,
            workspace_id=workspace.id,
        )

        result = incident_import_service_module.reindex_incident_files(
            [],
            project_id=self.project.id,
            remove_missing_sources=True,
        )
        records = incident_service_module.get_incident_records(
            project_id=self.project.id
        )
        status = incident_service_module.get_incident_ingestion_status(
            project_id=self.project.id
        )

        self.assertEqual(result.removed_count, 1)
        self.assertEqual(records, [])
        self.assertEqual(status.sources, [])

    def test_project_wide_reindex_preserves_same_named_workspace_sources(
        self,
    ) -> None:
        workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production",
        )
        incident_import_service_module.import_incident_files(
            [
                incident_import_service_module.IncidentImportFile(
                    source_file="checkout.json",
                    content=_incident_file_content(
                        "Workspace checkout", reference="INC-WS-CHECKOUT"
                    ),
                )
            ],
            project_id=self.project.id,
            workspace_id=workspace.id,
        )

        result = incident_import_service_module.reindex_incident_files(
            [
                incident_import_service_module.IncidentImportFile(
                    source_file="checkout.json",
                    content=_incident_file_content(
                        "Project checkout", reference="INC-PROJECT-CHECKOUT"
                    ),
                )
            ],
            project_id=self.project.id,
            remove_missing_sources=True,
        )
        records = incident_service_module.get_incident_records(
            project_id=self.project.id
        )

        self.assertEqual(result.indexed_count, 1)
        self.assertEqual(result.removed_count, 0)
        self.assertEqual(
            {
                (record["source_file"], record["workspace_id"], record["title"])
                for record in records
            },
            {
                ("checkout.json", None, "Project checkout"),
                ("checkout.json", workspace.id, "Workspace checkout"),
            },
        )

    def test_empty_authoritative_reindex_clears_all_managed_sources(self) -> None:
        incident_import_service_module.reindex_incident_files(
            [
                incident_import_service_module.IncidentImportFile(
                    source_file="managed.json",
                    content=_incident_file_content("Managed incident"),
                )
            ],
            project_id=self.project.id,
        )

        result = incident_import_service_module.reindex_incident_files(
            [],
            project_id=self.project.id,
            remove_missing_sources=True,
        )
        records = incident_service_module.get_incident_records(
            project_id=self.project.id
        )

        self.assertEqual(result.indexed_count, 0)
        self.assertEqual(result.removed_count, 1)
        self.assertEqual(records, [])
        self.assertEqual(result.status.indexed_count, 0)
        self.assertEqual(result.status.freshness_status, "empty")

    def test_authoritative_reindex_clears_omitted_failed_source_status(self) -> None:
        with self.assertRaises(
            incident_import_service_module.IncidentImportValidationError
        ):
            incident_import_service_module.reindex_incident_files(
                [
                    incident_import_service_module.IncidentImportFile(
                        source_file="broken.json",
                        content="{}",
                    )
                ],
                project_id=self.project.id,
            )

        result = incident_import_service_module.reindex_incident_files(
            [
                incident_import_service_module.IncidentImportFile(
                    source_file="replacement.json",
                    content=_incident_file_content("Replacement incident"),
                )
            ],
            project_id=self.project.id,
            remove_missing_sources=True,
        )

        self.assertEqual(result.removed_count, 0)
        self.assertEqual(
            [source.import_source for source in result.status.sources],
            ["replacement.json"],
        )
        self.assertEqual(result.status.rejected_count, 0)

    def test_request_level_reindex_failures_do_not_create_batch_source(self) -> None:
        with self.assertRaises(
            incident_import_service_module.IncidentImportValidationError
        ):
            incident_import_service_module.reindex_incident_files(
                [],
                project_id=self.project.id,
                remove_missing_sources=False,
            )

        status = incident_service_module.get_incident_ingestion_status(
            project_id=self.project.id
        )

        self.assertEqual(status.sources, [])
        self.assertEqual(status.rejected_count, 0)

    def test_project_scoped_source_registry_rejects_duplicate_null_workspace_key(
        self,
    ) -> None:
        with database_module.SessionLocal() as session:
            session.add(
                tables_module.IncidentIngestionSource(
                    project_id=self.project.id,
                    workspace_id=None,
                    source_file="checkout.json",
                    status="indexed",
                    indexed_count=1,
                    rejected_count=0,
                    redaction_status="redacted",
                    failure_summaries_json="[]",
                    created_at=incident_service_module.datetime.now(
                        incident_service_module.UTC
                    ),
                    updated_at=incident_service_module.datetime.now(
                        incident_service_module.UTC
                    ),
                )
            )
            session.commit()
            session.add(
                tables_module.IncidentIngestionSource(
                    project_id=self.project.id,
                    workspace_id=None,
                    source_file="checkout.json",
                    status="indexed",
                    indexed_count=1,
                    rejected_count=0,
                    redaction_status="redacted",
                    failure_summaries_json="[]",
                    created_at=incident_service_module.datetime.now(
                        incident_service_module.UTC
                    ),
                    updated_at=incident_service_module.datetime.now(
                        incident_service_module.UTC
                    ),
                )
            )
            with self.assertRaises(IntegrityError):
                session.commit()

    def test_project_status_keeps_same_source_file_separate_by_workspace(
        self,
    ) -> None:
        prod = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production",
        )
        staging = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="staging",
            display_name="Staging",
        )
        incident_service_module.ingest_incident_document(
            "checkout.json",
            "# Prod incident\nSeverity: high\nRedaction status: redacted\n",
            project_id=self.project.id,
            workspace_id=prod.id,
        )
        incident_service_module.ingest_incident_document(
            "checkout.json",
            "# Staging incident\nSeverity: medium\nRedaction status: none\n",
            project_id=self.project.id,
            workspace_id=staging.id,
        )

        status = incident_service_module.get_incident_ingestion_status(
            project_id=self.project.id
        )

        self.assertEqual(status.indexed_count, 2)
        self.assertEqual(
            {(source.import_source, source.workspace_id) for source in status.sources},
            {("checkout.json", prod.id), ("checkout.json", staging.id)},
        )
        self.assertEqual(
            {source.scope_label for source in status.sources},
            {f"Workspace #{prod.id}", f"Workspace #{staging.id}"},
        )

    def test_incident_index_snapshot_exposes_version_and_freshness(self) -> None:
        empty_snapshot = incident_service_module.get_incident_index_snapshot(
            project_id=self.project.id
        )
        incident_service_module.ingest_incident_document(
            "checkout.json",
            "# Checkout incident\nSeverity: high\nRedaction status: redacted\n",
            project_id=self.project.id,
        )
        current_snapshot = incident_service_module.get_incident_index_snapshot(
            project_id=self.project.id
        )

        self.assertEqual(empty_snapshot["incident_index_version"], "incidents:empty")
        self.assertEqual(current_snapshot["incident_index_size"], 1)
        self.assertEqual(current_snapshot["incident_index_freshness_status"], "current")
        self.assertTrue(
            str(current_snapshot["incident_index_version"]).startswith("incidents:1:")
        )
        self.assertIsNotNone(current_snapshot["incident_index_last_indexed_at"])


if __name__ == "__main__":
    unittest.main()
