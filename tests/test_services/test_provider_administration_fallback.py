"""Integration regressions for degraded provider administration settings."""

from __future__ import annotations

import os
import json
import tempfile
import unittest
from importlib import reload
from pathlib import Path
from unittest.mock import Mock, patch

import config as config_module
import models.database as database_module
import models.repositories.analysis_reports as reports_repository_module
import models.repositories.settings as settings_repository_module
import models.tables as tables_module
import services.artifact_snapshot_service as snapshots_module
import services.project_service as project_service_module
import services.report_service as report_service_module
import services.settings_service as settings_service_module
from services.analysis_service import build_analysis_artifacts


class ProviderAdministrationFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_database_url = os.getenv(
            "DATABASE_URL", "sqlite:///data/deploywhisper.db"
        )
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        environment = patch.dict(
            os.environ,
            {
                "DATABASE_URL": f"sqlite:///{self.tempdir.name}/providers.db",
                "ARTIFACT_SNAPSHOT_DIR": str(Path(self.tempdir.name) / "artifacts"),
                "OPENAI_API_KEY": "",
                "LLM_API_KEY": "",
                "NARRATOR_ENABLED": "true",
            },
        )
        self.environment = environment
        self.modules = (
            config_module,
            tables_module,
            database_module,
            reports_repository_module,
            settings_repository_module,
            snapshots_module,
            project_service_module,
            settings_service_module,
            report_service_module,
        )
        environment.start()
        self.addCleanup(self._restore_runtime)
        for module in self.modules:
            reload(module)
        database_module.init_db()
        self.files = [
            (
                "main.tf",
                b'resource "aws_security_group" "public" {\n'
                b"  ingress {\n"
                b"    from_port = 22\n"
                b"    to_port = 22\n"
                b'    protocol = "tcp"\n'
                b'    cidr_blocks = ["0.0.0.0/0"]\n'
                b"  }\n"
                b"}\n",
            )
        ]

    def _restore_runtime(self) -> None:
        database_module.engine.dispose()
        self.environment.stop()
        for module in self.modules:
            reload(module)

    def test_cleanup_restores_runtime_before_temporary_database_is_removed(
        self,
    ) -> None:
        temporary_url = config_module.settings.database_url
        self.assertNotEqual(temporary_url, self.original_database_url)
        self._restore_runtime()
        self.assertEqual(
            config_module.settings.database_url, self.original_database_url
        )
        self.assertEqual(str(database_module.engine.url), self.original_database_url)
        self.assertEqual(
            settings_service_module.settings.database_url, self.original_database_url
        )

    def test_setup_failure_restores_runtime_and_environment(self) -> None:
        original_url = config_module.settings.database_url
        original_snapshot_dir = os.environ.get("ARTIFACT_SNAPSHOT_DIR")
        for failure in ("reload", "init_db"):
            with self.subTest(failure=failure):
                fixture = ProviderAdministrationFallbackTests(
                    "test_missing_environment_credential_preserves_persisted_report"
                )
                try:
                    target = (
                        f"{__name__}.reload"
                        if failure == "reload"
                        else f"{__name__}.database_module.init_db"
                    )
                    if failure == "reload":
                        with patch(
                            target, side_effect=RuntimeError("synthetic setup failure")
                        ):
                            with self.assertRaisesRegex(
                                RuntimeError, "synthetic setup"
                            ):
                                fixture.setUp()
                    else:
                        original_reload = reload

                        def reload_without_database(module):
                            return (
                                module
                                if module is database_module
                                else original_reload(module)
                            )

                        with (
                            patch(
                                target,
                                side_effect=RuntimeError("synthetic setup failure"),
                            ),
                            patch(
                                f"{__name__}.reload",
                                side_effect=reload_without_database,
                            ),
                        ):
                            with self.assertRaisesRegex(
                                RuntimeError, "synthetic setup"
                            ):
                                fixture.setUp()
                finally:
                    fixture.doCleanups()
                self.assertEqual(config_module.settings.database_url, original_url)
                self.assertEqual(str(database_module.engine.url), original_url)
                self.assertEqual(
                    os.environ.get("ARTIFACT_SNAPSHOT_DIR"), original_snapshot_dir
                )

    def _store_runtime(self, provider: str, *, local_mode: bool = False) -> None:
        # Emulate existing persisted configuration, including invalid legacy rows.
        # The administration save path should reject invalid new configurations.
        values = {
            "active_llm_provider": provider,
            f"llm_provider_config::{provider}::model": "gpt-4.1-mini",
            f"llm_provider_config::{provider}::api_base": "https://api.openai.com/v1",
            f"llm_provider_config::{provider}::local_mode": (
                "true" if local_mode else "false"
            ),
        }
        with database_module.SessionLocal() as session:
            for key, value in values.items():
                settings_repository_module.upsert_setting(session, key=key, value=value)

    def _assert_deterministic_report_survives(
        self, completion_client=None, *, secret=None
    ):
        baseline = build_analysis_artifacts(
            self.files,
            allow_llm_assistance=False,
            include_narrative=False,
            include_topology_context=False,
            include_incident_context=False,
        )
        result = build_analysis_artifacts(
            self.files,
            completion_client=completion_client,
            include_topology_context=False,
            include_incident_context=False,
        )
        self.assertTrue(result.assessment.contributors)
        self.assertTrue(result.evidence_items)
        self.assertTrue(result.findings)
        for field in ("score", "severity", "recommendation", "top_risk"):
            self.assertEqual(
                getattr(result.assessment, field), getattr(baseline.assessment, field)
            )
        self.assertEqual(result.evidence_items, baseline.evidence_items)
        self.assertEqual(result.findings, baseline.findings)
        self.assertEqual(result.blast_radius, baseline.blast_radius)
        self.assertEqual(result.rollback_plan, baseline.rollback_plan)
        self.assertTrue(result.narrative.degraded)
        self.assertFalse(result.narrative.available)
        self.assertEqual(result.narrative.source, "fallback")
        self.assertTrue(result.narrative.failure_notice)
        if secret is not None:
            self.assertNotIn(secret, result.narrative.model_dump_json())

        baseline_persisted = report_service_module.persist_analysis_report(
            baseline.parse_batch,
            baseline.assessment,
            baseline.narrative,
            findings=baseline.findings,
            evidence_items=baseline.evidence_items,
            blast_radius=baseline.blast_radius,
            rollback_plan=baseline.rollback_plan,
            submitted_artifacts=self.files,
        )
        persisted = report_service_module.persist_analysis_report(
            result.parse_batch,
            result.assessment,
            result.narrative,
            findings=result.findings,
            evidence_items=result.evidence_items,
            blast_radius=result.blast_radius,
            rollback_plan=result.rollback_plan,
            submitted_artifacts=self.files,
        )
        report = report_service_module.fetch_analysis_report(persisted["id"])
        self.assertIsNotNone(report)
        # Persistence applies the report's deterministic uncertainty calibration.
        # Compare against that same canonical path with model assistance disabled.
        self.assertEqual(report["risk_score"], baseline_persisted["risk_score"])
        self.assertEqual(report["recommendation"], baseline_persisted["recommendation"])
        self.assertEqual(len(report["findings"]), len(result.findings))
        self.assertTrue(report["narrative_degraded"])
        self.assertEqual(report["narrative_source"], "fallback")
        self.assertEqual(
            report["narrative_failure_notice"], result.narrative.failure_notice
        )
        self.assertEqual(report["narrative_provider"], result.narrative.provider)
        self.assertEqual(report["narrative_local_mode"], result.narrative.local_mode)
        self.assertIn(result.narrative.failure_notice, report["warnings"])
        return report

    def test_malformed_known_provider_runtime_preserves_deterministic_report(
        self,
    ) -> None:
        self._store_runtime("openai")
        with database_module.SessionLocal() as session:
            settings_repository_module.upsert_setting(
                session,
                key="llm_provider_config::openai::api_base",
                value="https://api.openai.com:invalid/v1",
            )
        completion_client = Mock()
        self._assert_deterministic_report_survives(completion_client)
        completion_client.assert_not_called()

    def test_legacy_model_credentials_are_screened_in_memory_and_at_rest(self) -> None:
        self._store_runtime("openai", local_mode=True)
        for key_name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_API_KEY"):
            with self.subTest(key_name=key_name):
                secret = f"synthetic-{key_name.lower()}-credential"
                metadata_value = (
                    "".join(f"%{ord(character):02X}" for character in secret).replace(
                        "%", "%2525"
                    )
                    if key_name == "LLM_API_KEY"
                    else secret
                )
                with database_module.SessionLocal() as session:
                    settings_repository_module.upsert_setting(
                        session,
                        key="llm_provider_config::openai::model",
                        value=f"legacy-model-{metadata_value}",
                    )
                completion_client = Mock()
                with patch.dict(os.environ, {key_name: secret}):
                    report = self._assert_deterministic_report_survives(
                        completion_client, secret=secret
                    )
                    self.assertNotIn(secret, json.dumps(report))
                    self.assertNotIn(metadata_value, json.dumps(report))
                    with database_module.SessionLocal() as session:
                        stored = reports_repository_module.get_analysis_report(
                            session, report["id"]
                        )
                        self.assertNotIn(secret, stored.llm_model or "")
                        self.assertNotIn(metadata_value, stored.llm_model or "")
                        # Also screen legacy reports created before credential-aware
                        # persistence, while the configured credential is available.
                        stored.llm_model = f"legacy-model-{metadata_value}"
                        session.commit()
                    legacy_report = report_service_module.fetch_analysis_report(
                        report["id"]
                    )
                    self.assertNotIn(secret, json.dumps(legacy_report))
                    self.assertNotIn(metadata_value, json.dumps(legacy_report))
                completion_client.assert_not_called()

    def test_persistence_screens_provider_credentials_from_supplied_narrative(
        self,
    ) -> None:
        result = build_analysis_artifacts(
            self.files,
            allow_llm_assistance=False,
            include_narrative=False,
            include_topology_context=False,
            include_incident_context=False,
        )
        secret = "synthetic-narrative-metadata-credential"
        encoded = "".join(f"%{ord(character):02X}" for character in secret).replace(
            "%", "%2525"
        )
        narrative = result.narrative.model_copy(
            update={"model": encoded, "warnings": [f"Legacy warning: {secret}"]}
        )
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": secret}):
            persisted = report_service_module.persist_analysis_report(
                result.parse_batch,
                result.assessment,
                narrative,
                findings=result.findings,
                evidence_items=result.evidence_items,
                submitted_artifacts=self.files,
            )
            self.assertNotIn(secret, json.dumps(persisted))
            self.assertNotIn(encoded, json.dumps(persisted))
            with database_module.SessionLocal() as session:
                stored = reports_repository_module.get_analysis_report(
                    session, persisted["id"]
                )
                self.assertNotIn(secret, stored.llm_model or "")
                self.assertNotIn(encoded, stored.llm_model or "")
                self.assertNotIn(secret, stored.warnings_json)

    def test_missing_environment_credential_preserves_persisted_report(self) -> None:
        self._store_runtime("openai")
        self.assertFalse(settings_service_module.resolve_provider_runtime()["api_key"])
        with patch("openai.OpenAI") as sdk_constructor:
            self._assert_deterministic_report_survives()
        sdk_constructor.assert_not_called()

    def test_invalid_legacy_provider_preserves_report_without_external_calls(
        self,
    ) -> None:
        self._store_runtime("unsupported-provider")
        completion_client = Mock()
        self._assert_deterministic_report_survives(completion_client)
        completion_client.assert_not_called()

    def test_external_provider_disabled_by_local_mode_preserves_report(self) -> None:
        self._store_runtime("openai", local_mode=True)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-provider-key"}):
            completion_client = Mock()
            report = self._assert_deterministic_report_survives(completion_client)
        completion_client.assert_not_called()
        self.assertTrue(report["narrative_local_mode"])
        self.assertIn("Local mode", report["narrative_failure_notice"])


if __name__ == "__main__":
    unittest.main()
