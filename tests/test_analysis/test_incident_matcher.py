"""Tests for incident similarity matching."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.incident_service as incident_service_module
import analysis.incident_matcher as incident_matcher_module
from parsers.base import UnifiedChange


class IncidentMatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "incidents.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(incident_service_module)
        reload(incident_matcher_module)
        database_module.init_db()

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_find_incident_matches_returns_ranked_match(self) -> None:
        incident_service_module.ingest_incident_document(
            "incident.md",
            "# Database exposure\nDate: 2026-04-16\nSeverity: P1\nTerraform security group database exposure during deployment restart.",
        )
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Terraform security group database exposure during deployment restart.",
            )
        ]
        matches = incident_matcher_module.find_incident_matches(changes)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].title, "Database exposure")
        self.assertGreater(matches[0].similarity, 0.2)
        self.assertEqual(matches[0].incident_date, "2026-04-16")

    def test_find_incident_matches_returns_empty_when_no_candidates(self) -> None:
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Terraform security group database exposure during deployment restart.",
            )
        ]
        matches = incident_matcher_module.find_incident_matches(changes)
        self.assertEqual(matches, [])

    def test_find_incident_matches_avoids_generic_token_false_positive(self) -> None:
        incident_service_module.ingest_incident_document(
            "generic.md",
            "# Generic deployment note\nSeverity: low\nA deployment changed a resource and included a service update.",
        )
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Terraform changed a resource.",
            )
        ]
        matches = incident_matcher_module.find_incident_matches(changes, min_similarity=0.15)
        self.assertEqual(matches, [])

    def test_find_incident_matches_ranks_more_specific_incident_higher(self) -> None:
        incident_service_module.ingest_incident_document(
            "generic.md",
            "# Generic deployment note\nSeverity: low\nSecurity group update.",
        )
        incident_service_module.ingest_incident_document(
            "specific.md",
            "# Database exposure\nSeverity: P1\nTerraform security group database exposure during deployment restart.",
        )
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Terraform security group database exposure during deployment restart.",
            )
        ]
        matches = incident_matcher_module.find_incident_matches(changes, min_similarity=0.1)
        self.assertGreaterEqual(len(matches), 1)
        self.assertEqual(matches[0].title, "Database exposure")

    def test_find_incident_matches_prefers_higher_severity_and_recent_context(self) -> None:
        incident_service_module.ingest_incident_document(
            "older.md",
            "# Similar deploy\nDate: 2024-01-01\nSeverity: low\nDatabase exposure during deploy restart.",
        )
        incident_service_module.ingest_incident_document(
            "recent.md",
            "# Similar deploy\nDate: 2026-04-16\nSeverity: P1\nDatabase exposure during deploy restart.",
        )
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Database exposure during deploy restart.",
            )
        ]
        matches = incident_matcher_module.find_incident_matches(changes, min_similarity=0.1)
        self.assertGreaterEqual(len(matches), 2)
        self.assertEqual(matches[0].source_file, "recent.md")
