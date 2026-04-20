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
            ],
        )
        baseline_content = migrations[0].read_text(encoding="utf-8")
        evidence_content = migrations[1].read_text(encoding="utf-8")
        schema_content = migrations[2].read_text(encoding="utf-8")
        self.assertIn("down_revision = None", baseline_content)
        self.assertIn('"app_settings"', baseline_content)
        self.assertIn(
            'down_revision = "0001_create_analysis_reports"', evidence_content
        )
        self.assertIn('"evidence_items"', evidence_content)
        self.assertIn('down_revision = "005_add_evidence_model"', schema_content)
        self.assertIn('"report_schema_version"', schema_content)

    def test_dockerfile_exists(self) -> None:
        self.assertTrue(Path("Dockerfile").exists())

    def test_dockerfile_uses_multistage_non_root_runtime(self) -> None:
        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
        self.assertIn("FROM python:3.11-slim AS builder", dockerfile)
        self.assertIn("FROM python:3.11-slim AS runtime", dockerfile)
        self.assertIn("COPY --from=builder /opt/venv /opt/venv", dockerfile)
        self.assertIn("USER appuser", dockerfile)
        self.assertIn("HEALTHCHECK", dockerfile)
        self.assertIn('CMD ["python", "app.py"]', dockerfile)

    def test_dockerignore_excludes_heavy_local_artifacts(self) -> None:
        dockerignore = Path(".dockerignore")
        self.assertTrue(dockerignore.exists())
        content = dockerignore.read_text(encoding="utf-8")
        self.assertIn(".venv", content)
        self.assertIn("tests/", content)
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
        self.assertIn("LLM_API_BASE", environment)
        self.assertEqual(services["deploywhisper"]["restart"], "unless-stopped")
        self.assertIn(
            "deploywhisper-data:/app/data", services["deploywhisper"]["volumes"]
        )
        self.assertIn("deploywhisper-data", payload.get("volumes", {}))
