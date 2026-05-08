"""Static contract tests for local container deployment artifacts."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class ContainerContractTests(unittest.TestCase):
    def test_migration_history_includes_evidence_foundation_upgrade(self) -> None:
        versions_dir = Path("migrations/versions")
        migrations = sorted(
            path for path in versions_dir.glob("*.py") if path.name != "__init__.py"
        )
        self.assertEqual(
            [path.name for path in migrations],
            [
                "0001_create_analysis_reports.py",
                "005_add_evidence_model.py",
                "006_add_report_schema_version.py",
                "007_add_blast_radius_payload.py",
                "008_add_rollback_plan_payload.py",
                "009_add_report_share_settings.py",
                "010_add_project_workspaces.py",
                "011_add_deployment_outcome_fields.py",
                "012_add_feedback_event_fields.py",
                "013_add_incident_analysis_reference.py",
                "014_add_project_workspace_records.py",
                "015_add_report_workspace_scope.py",
                "016_scope_learning_context_records.py",
                "017_add_submission_manifest_payload.py",
            ],
        )
        baseline_content = migrations[0].read_text(encoding="utf-8")
        evidence_content = migrations[1].read_text(encoding="utf-8")
        schema_content = migrations[2].read_text(encoding="utf-8")
        blast_radius_content = migrations[3].read_text(encoding="utf-8")
        rollback_content = migrations[4].read_text(encoding="utf-8")
        share_content = migrations[5].read_text(encoding="utf-8")
        project_content = migrations[6].read_text(encoding="utf-8")
        deployment_outcomes_content = migrations[7].read_text(encoding="utf-8")
        feedback_content = migrations[8].read_text(encoding="utf-8")
        incident_link_content = migrations[9].read_text(encoding="utf-8")
        workspace_content = migrations[10].read_text(encoding="utf-8")
        report_workspace_content = migrations[11].read_text(encoding="utf-8")
        learning_context_scope_content = migrations[12].read_text(encoding="utf-8")
        submission_manifest_content = migrations[13].read_text(encoding="utf-8")
        self.assertIn("down_revision = None", baseline_content)
        self.assertIn('"app_settings"', baseline_content)
        self.assertIn(
            'down_revision = "0001_create_analysis_reports"', evidence_content
        )
        self.assertIn('"evidence_items"', evidence_content)
        self.assertIn('down_revision = "005_add_evidence_model"', schema_content)
        self.assertIn('"report_schema_version"', schema_content)
        self.assertIn(
            'down_revision = "006_add_report_schema_version"', blast_radius_content
        )
        self.assertIn('"blast_radius_json"', blast_radius_content)
        self.assertIn(
            'down_revision = "007_add_blast_radius_payload"', rollback_content
        )
        self.assertIn('"rollback_plan_json"', rollback_content)
        self.assertIn('down_revision = "008_add_rollback_plan_payload"', share_content)
        self.assertIn('"share_redact_filenames"', share_content)
        self.assertIn(
            'down_revision = "009_add_report_share_settings"', project_content
        )
        self.assertIn('"projects"', project_content)
        self.assertIn('"project_id"', project_content)
        self.assertIn(
            'down_revision = "010_add_project_workspaces"',
            deployment_outcomes_content,
        )
        self.assertIn('"deployed_at"', deployment_outcomes_content)
        self.assertIn('"linked_incident_id"', deployment_outcomes_content)
        self.assertIn(
            'down_revision = "011_add_deployment_outcome_fields"',
            feedback_content,
        )
        self.assertIn('"finding_id"', feedback_content)
        self.assertIn('"false_positive_reason"', feedback_content)
        self.assertIn(
            'down_revision = "012_add_feedback_event_fields"',
            incident_link_content,
        )
        self.assertIn('"analysis_id"', incident_link_content)
        self.assertIn(
            'down_revision = "013_add_incident_analysis_reference"',
            workspace_content,
        )
        self.assertIn('"project_workspaces"', workspace_content)
        self.assertIn('"workspace_key"', workspace_content)
        self.assertIn(
            'down_revision = "014_add_project_workspace_records"',
            report_workspace_content,
        )
        self.assertIn('"workspace_id"', report_workspace_content)
        self.assertIn(
            'down_revision = "015_add_report_workspace_scope"',
            learning_context_scope_content,
        )
        self.assertIn('"incident_records"', learning_context_scope_content)
        self.assertIn('"project_id"', learning_context_scope_content)
        self.assertIn('"workspace_id"', learning_context_scope_content)
        self.assertIn(
            'down_revision = "016_scope_learning_context_records"',
            submission_manifest_content,
        )
        self.assertIn('"submission_manifest_json"', submission_manifest_content)
        self.assertIn(
            '"submission_manifest_fallback_json"', submission_manifest_content
        )

    def test_dockerfile_exists(self) -> None:
        self.assertTrue(Path("Dockerfile").exists())

    def test_dockerfile_uses_multistage_non_root_runtime(self) -> None:
        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
        self.assertIn("FROM python:3.11-slim AS builder", dockerfile)
        self.assertIn("FROM python:3.11-slim AS runtime", dockerfile)
        self.assertIn("COPY --from=builder /opt/venv /opt/venv", dockerfile)
        self.assertIn(
            "COPY --chown=appuser:appuser integrations ./integrations", dockerfile
        )
        self.assertNotIn("tests/skill-tests", dockerfile)
        self.assertIn("USER appuser", dockerfile)
        self.assertIn("HEALTHCHECK", dockerfile)
        self.assertIn('CMD ["python", "app.py"]', dockerfile)

    def test_dockerignore_excludes_heavy_local_artifacts(self) -> None:
        dockerignore = Path(".dockerignore")
        self.assertTrue(dockerignore.exists())
        content = dockerignore.read_text(encoding="utf-8")
        self.assertIn(".venv", content)
        self.assertIn("tests/", content)
        self.assertNotIn("!tests/skill-tests/**", content)
        self.assertIn("_bmad-output/", content)

    def test_compose_uses_single_app_service_and_unique_port(self) -> None:
        compose_path = Path("docker-compose.yml")
        self.assertTrue(compose_path.exists())
        payload = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
        services = payload.get("services", {})
        self.assertIn("deploywhisper", services)
        self.assertEqual(len(services), 1)
        build = services["deploywhisper"].get("build", {})
        self.assertEqual(build["target"], "runtime")
        ports = services["deploywhisper"].get("ports", [])
        self.assertIn("8080:8080", ports)
        environment = services["deploywhisper"].get("environment", {})
        self.assertEqual(environment["APP_PORT"], 8080)
        self.assertIn("APP_BASE_URL", environment)
        self.assertIn("DEPLOYWHISPER_SHARE_TOKEN", environment)
        self.assertIn("LLM_API_BASE", environment)
        self.assertEqual(services["deploywhisper"]["restart"], "unless-stopped")
        self.assertIn(
            "deploywhisper-data:/app/data", services["deploywhisper"]["volumes"]
        )
        self.assertIn("deploywhisper-data", payload.get("volumes", {}))
