"""Synthetic credential regression tests for incident and scanner imports."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path
from unittest.mock import patch

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.incident_import_service as incident_import_module
import services.incident_service as incident_service_module
import services.project_service as project_service_module
import services.scanner_import_service as scanner_import_module


class ConnectorImportSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.modules = (
            config_module,
            tables_module,
            database_module,
            project_service_module,
            incident_service_module,
            incident_import_module,
            scanner_import_module,
        )
        self.environment = patch.dict(
            os.environ,
            {"DATABASE_URL": f"sqlite:///{Path(self.tempdir.name) / 'security.db'}"},
        )
        self.environment.start()
        # LIFO cleanups restore runtime before removing the isolated database,
        # including failures during reload, migration, or project setup.
        self.addCleanup(self._restore_runtime)
        for module in self.modules:
            reload(module)
        self.database = database_module
        self.tables = tables_module
        self.incidents = incident_import_module
        self.incident_service = incident_service_module
        self.scanners = scanner_import_module
        self.database.init_db()
        self.project = project_service_module.create_project(
            project_key="synthetic-security", display_name="Synthetic Security"
        )
        self.secret = "SYNTHETIC_IMPORT_CREDENTIAL_12_3"

    def _restore_runtime(self) -> None:
        database_module.engine.dispose()
        self.environment.stop()
        for module in self.modules:
            reload(module)

    def test_cleanup_restores_runtime_before_removing_temporary_database(self) -> None:
        temporary_url = config_module.settings.database_url
        self._restore_runtime()
        self.assertNotEqual(config_module.settings.database_url, temporary_url)
        self.assertEqual(
            str(database_module.engine.url), config_module.settings.database_url
        )
        self.assertIs(
            incident_service_module.SessionLocal, database_module.SessionLocal
        )
        self.assertIs(incident_import_module.SessionLocal, database_module.SessionLocal)
        self.assertIs(scanner_import_module.SessionLocal, database_module.SessionLocal)
        self.assertTrue(Path(self.tempdir.name).exists())

    def test_setup_failure_restores_runtime_and_environment(self) -> None:
        original_url = config_module.settings.database_url
        original_environment_url = os.environ.get("DATABASE_URL")
        for stage in ("reload", "init_db", "create_project"):
            with self.subTest(stage=stage):
                fixture = ConnectorImportSecurityTests(
                    "test_incident_import_screens_discarded_credentials_and_sibling_echoes"
                )
                target = {
                    "reload": f"{__name__}.reload",
                    "init_db": f"{__name__}.database_module.init_db",
                    "create_project": f"{__name__}.project_service_module.create_project",
                }[stage]
                original_reload = reload
                skipped_module = {
                    "init_db": database_module,
                    "create_project": project_service_module,
                }.get(stage)

                def reload_without_patched_module(module):
                    return (
                        module if module is skipped_module else original_reload(module)
                    )

                if stage == "reload":
                    with patch(
                        target, side_effect=RuntimeError("synthetic setup failure")
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError, "synthetic setup failure"
                        ):
                            fixture.setUp()
                else:
                    with (
                        patch(
                            target, side_effect=RuntimeError("synthetic setup failure")
                        ),
                        patch(
                            f"{__name__}.reload",
                            side_effect=reload_without_patched_module,
                        ),
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError, "synthetic setup failure"
                        ):
                            fixture.setUp()
                fixture.doCleanups()
                self.assertEqual(
                    os.environ.get("DATABASE_URL"), original_environment_url
                )
                self.assertEqual(config_module.settings.database_url, original_url)
                self.assertEqual(str(database_module.engine.url), original_url)
                self.assertIs(
                    incident_service_module.SessionLocal, database_module.SessionLocal
                )
                self.assertIs(
                    incident_import_module.SessionLocal, database_module.SessionLocal
                )
                self.assertIs(
                    scanner_import_module.SessionLocal, database_module.SessionLocal
                )
                self.assertFalse(Path(fixture.tempdir.name).exists())

    def _incident(self) -> dict:
        return {
            "title": f"Rotation failure {self.secret}",
            "severity": "high",
            "incident_date": "2026-01-01",
            "root_cause": "Rotation failed",
            "trigger_change": "Deployment",
            "affected_services": ["app"],
            "rollback_path": "Restore config",
            "prevention_notes": [f"Avoid echoing {self.secret}"],
            "source": {"system": "manual", "reference": "ticket-12"},
            "redaction": {"status": "none", "contains_sensitive_data": False},
            # This field is dropped by normalization; it must still protect echoes.
            "connector": {"api_key": self.secret},
        }

    def test_incident_import_screens_discarded_credentials_and_sibling_echoes(
        self,
    ) -> None:
        result = self.incidents.import_incident_files(
            [
                self.incidents.IncidentImportFile(
                    source_file="synthetic.json", content=json.dumps(self._incident())
                )
            ],
            project_id=self.project.id,
        )
        self.assertNotIn(self.secret, result.model_dump_json())
        records = self.incident_service.get_incident_records(project_id=self.project.id)
        self.assertNotIn(self.secret, json.dumps(records))
        self.assertIn("Redaction status: redacted", records[0]["content"])
        with self.database.SessionLocal() as session:
            stored = session.query(self.tables.IncidentRecord).one()
            self.assertNotIn(self.secret, stored.content)
            self.assertNotIn(self.secret, stored.title)

    def test_yaml_errors_never_persist_or_return_source_lines(self) -> None:
        for filename, content in (
            ("synthetic.yaml", f"password: [{self.secret}\n"),
            ("synthetic.md", f"---\npassword: [{self.secret}\n---\n# Example"),
        ):
            with self.assertRaises(
                self.incidents.IncidentImportValidationError
            ) as captured:
                self.incidents.reindex_incident_files(
                    [
                        self.incidents.IncidentImportFile(
                            source_file=filename, content=content
                        )
                    ],
                    project_id=self.project.id,
                )
            self.assertNotIn(self.secret, str(captured.exception))
            self.assertIn("line", captured.exception.field_errors[0].message)
        status = self.incident_service.get_incident_ingestion_status(
            project_id=self.project.id
        )
        self.assertNotIn(self.secret, status.model_dump_json())
        with self.database.SessionLocal() as session:
            for source in session.query(self.tables.IncidentIngestionSource).all():
                self.assertNotIn(self.secret, source.failure_summaries_json)

    def test_plain_incident_and_legacy_read_screen_sensitive_values(self) -> None:
        result = self.incident_service.ingest_incident_document(
            "synthetic.md",
            f"# Rotation {self.secret}\npassword: {self.secret}\nSeverity: high\n",
            project_id=self.project.id,
        )
        self.assertNotIn(self.secret, json.dumps(result))
        with self.database.SessionLocal() as session:
            record = session.query(self.tables.IncidentRecord).one()
            record.content = f"# Legacy {self.secret}\npassword: {self.secret}\n"
            record.title = f"Legacy {self.secret}"
            session.commit()
        self.assertNotIn(
            self.secret,
            json.dumps(
                self.incident_service.get_incident_records(project_id=self.project.id)
            ),
        )
        self.assertNotIn(
            self.secret,
            self.incident_service.get_incident_ingestion_status(
                project_id=self.project.id
            ).model_dump_json(),
        )

    def _sarif(self) -> dict:
        return {
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {"driver": {"name": "Synthetic"}},
                    "results": [
                        {
                            "ruleId": "R1",
                            "message": {"text": f"Rotation {self.secret}"},
                            "level": "warning",
                            "properties": {"api_key": self.secret},
                            "locations": [
                                {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": "main.py"},
                                        "region": {
                                            "startLine": 1,
                                            "snippet": {"text": f"raw {self.secret}"},
                                            "credential": self.secret,
                                        },
                                    }
                                }
                            ],
                        }
                    ],
                }
            ],
        }

    def test_sarif_collects_dropped_secrets_and_discards_raw_regions(self) -> None:
        file = self.scanners.ScannerImportFile(
            source_file="synthetic.sarif", content=json.dumps(self._sarif())
        )
        result = self.scanners.import_sarif_file(file, project_id=self.project.id)
        self.assertNotIn(self.secret, result.model_dump_json())
        self.assertEqual(result.evidence[0].region, {"startLine": 1})
        # Screening does not alter stable raw source identity.
        refreshed = self.scanners.import_sarif_file(file, project_id=self.project.id)
        self.assertEqual(result.evidence[0].id, refreshed.evidence[0].id)
        with self.database.SessionLocal() as session:
            stored = session.query(self.tables.ExternalScannerEvidence).one()
            self.assertNotIn(self.secret, stored.message)
            self.assertEqual(json.loads(stored.region_json), {"startLine": 1})
            stored.region_json = json.dumps(
                {"startLine": 1, "snippet": {"text": self.secret}}
            )
            stored.message = f"password={self.secret}"
            session.commit()
        legacy = self.scanners.list_external_scanner_evidence(
            project_id=self.project.id
        )
        self.assertNotIn(self.secret, legacy[0].model_dump_json())
        self.assertEqual(legacy[0].region, {"startLine": 1})

    def test_incident_batch_context_protects_sibling_echoes_and_scope_errors(
        self,
    ) -> None:
        first = self._incident()
        second = self._incident()
        second.pop("connector")
        files = [
            self.incidents.IncidentImportFile(
                source_file="declaration.json", content=json.dumps(first)
            ),
            self.incidents.IncidentImportFile(
                source_file="echo.json", content=json.dumps(second)
            ),
        ]
        for importer in (
            self.incidents.import_incident_files,
            self.incidents.reindex_incident_files,
        ):
            result = importer(files, project_id=self.project.id)
            self.assertNotIn(self.secret, result.model_dump_json())
            self.assertNotIn(
                self.secret,
                json.dumps(
                    self.incident_service.get_incident_records(
                        project_id=self.project.id
                    )
                ),
            )
            with self.assertRaises(ValueError) as captured:
                importer(
                    files, project_id=self.project.id, workspace_key=self.secret.lower()
                )
            self.assertNotIn(
                self.secret.lower().replace("_", "-"), str(captured.exception)
            )

    def test_incident_alias_survives_declaration_removal_and_plain_names_are_distinct(
        self,
    ) -> None:
        payload = self._incident()
        filename = f"{self.secret}.json"
        first = self.incidents.import_incident_files(
            [
                self.incidents.IncidentImportFile(
                    source_file=filename, content=json.dumps(payload)
                )
            ],
            project_id=self.project.id,
        )
        alias = first.records[0]["source_file"]
        payload.pop("connector")
        payload["title"] = "Routine incident"
        payload["prevention_notes"] = ["Verify rotation"]
        second = self.incidents.reindex_incident_files(
            [
                self.incidents.IncidentImportFile(
                    source_file=filename, content=json.dumps(payload)
                )
            ],
            project_id=self.project.id,
        )
        self.assertEqual(second.replaced_count, 1)
        records = self.incident_service.get_incident_records(project_id=self.project.id)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source_file"], alias)
        plain = [
            self.incident_service.ingest_incident_document(
                f"{self.secret}-{name}.md",
                f"# Incident\npassword: {self.secret}",
                project_id=self.project.id,
            )
            for name in ("one", "two")
        ]
        self.assertEqual(len({item["source_file"] for item in plain}), 2)
        self.assertTrue(all(self.secret not in item["source_file"] for item in plain))
        remembered = self.incident_service.ingest_incident_document(
            f"{self.secret}-one.md", "", project_id=self.project.id
        )
        self.assertEqual(remembered["source_file"], plain[0]["source_file"])
        self.assertNotIn(self.secret, json.dumps(remembered))

    def test_project_wide_reindex_reuses_workspace_alias_but_explicit_scope_isolated(
        self,
    ) -> None:
        workspace = project_service_module.create_workspace(
            project_key=self.project.project_key,
            workspace_key="production",
            display_name="Production",
        )
        other = project_service_module.create_workspace(
            project_key=self.project.project_key,
            workspace_key="staging",
            display_name="Staging",
        )
        payload = self._incident()
        filename = f"{self.secret}.json"
        original = self.incidents.import_incident_files(
            [
                self.incidents.IncidentImportFile(
                    source_file=filename, content=json.dumps(payload)
                )
            ],
            project_id=self.project.id,
            workspace_id=workspace.id,
        )
        alias = original.records[0]["source_file"]
        payload.pop("connector")
        payload["title"] = "Routine incident"
        payload["prevention_notes"] = ["Verify rotation"]
        file = self.incidents.IncidentImportFile(
            source_file=filename, content=json.dumps(payload)
        )
        isolated = self.incidents.reindex_incident_files(
            [file], project_id=self.project.id, workspace_id=other.id
        )
        self.assertEqual(isolated.status.sources[0].import_source, filename)
        wide = self.incidents.reindex_incident_files(
            [file], project_id=self.project.id, remove_missing_sources=True
        )
        self.assertEqual(
            wide.removed_count, 1
        )  # The unrelated raw staging source is missing.
        records = self.incident_service.get_incident_records(project_id=self.project.id)
        self.assertEqual({record["source_file"] for record in records}, {alias})
        self.assertEqual(
            {record["workspace_id"] for record in records}, {None, workspace.id}
        )
        self.assertTrue(
            all(
                source.import_source == alias
                for source in wide.status.sources
                if source.indexed_count
            )
        )

    def test_scanner_names_remain_distinct_and_legacy_labels_screen_encoded_values(
        self,
    ) -> None:
        from urllib.parse import quote

        results = [
            self.scanners.import_sarif_file(
                self.scanners.ScannerImportFile(
                    source_file=f"{self.secret}-{name}.sarif",
                    content=json.dumps(self._sarif()),
                ),
                project_id=self.project.id,
            )
            for name in ("one", "two")
        ]
        self.assertEqual(len({item.source_file for item in results}), 2)
        self.assertEqual(results[0].evidence[0].id, results[1].evidence[0].id)
        with self.database.SessionLocal() as session:
            record = session.query(self.tables.ExternalScannerEvidence).one()
            record.tool_name = quote("api_key=OPAQUE_ENCODED_VALUE", safe="")
            record.rule_id = quote("token=OPAQUE_ENCODED_VALUE", safe="")
            session.commit()
        legacy = self.scanners.list_external_scanner_evidence(
            project_id=self.project.id
        )[0]
        self.assertNotIn("OPAQUE_ENCODED_VALUE", legacy.model_dump_json())

    def test_sarif_preserves_all_valid_coordinates(self) -> None:
        payload = self._sarif()
        region = payload["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
            "region"
        ]
        coordinates = {"startLine": 1, "startColumn": 2, "endLine": 2, "endColumn": 3}
        region.update(coordinates)
        result = self.scanners.import_sarif_file(
            self.scanners.ScannerImportFile(
                source_file="coordinates.sarif", content=json.dumps(payload)
            ),
            project_id=self.project.id,
        )
        self.assertEqual(result.evidence[0].region, coordinates)
        self.assertEqual(
            self.scanners.list_external_scanner_evidence(project_id=self.project.id)[
                0
            ].region,
            coordinates,
        )

    def test_sensitive_incident_filename_preserves_format_dispatch(self) -> None:
        for suffix in (".json", ".yaml", ".md"):
            with self.subTest(suffix=suffix):
                content = json.dumps(self._incident())
                if suffix == ".md":
                    content = "---\n" + content + "\n---\n# Rotation"
                file = self.incidents.IncidentImportFile(
                    source_file=f"{self.secret}{suffix}", content=content
                )
                result = self.incidents.import_incident_files(
                    [file], project_id=self.project.id
                )
                self.assertEqual(result.imported, 1)
                self.assertNotIn(self.secret, result.model_dump_json())
                self.assertTrue(result.records[0]["source_file"].endswith(suffix))
                reindexed = self.incidents.reindex_incident_files(
                    [file], project_id=self.project.id
                )
                self.assertEqual(reindexed.replaced_count, 1)
                self.assertNotIn(self.secret, reindexed.model_dump_json())

    def test_unsupported_sensitive_suffix_is_not_reintroduced_in_errors(self) -> None:
        file = self.incidents.IncidentImportFile(
            source_file=f"incident.{self.secret}", content=json.dumps(self._incident())
        )
        with self.assertRaises(
            self.incidents.IncidentImportValidationError
        ) as captured:
            self.incidents.import_incident_files([file], project_id=self.project.id)
        self.assertNotIn(self.secret, str(captured.exception))
        self.assertNotIn(self.secret.lower(), str(captured.exception))

    def test_sensitive_filename_aliases_preserve_distinct_source_identity(self) -> None:
        payload = json.dumps(self._incident())
        aliases = [
            self.incidents._screen_import_file(
                self.incidents.IncidentImportFile(
                    source_file=f"{self.secret}-{number}.json", content=payload
                )
            ).source_file
            for number in (1, 2)
        ]
        self.assertNotEqual(aliases[0], aliases[1])
        self.assertEqual(
            aliases[0],
            self.incidents._screen_import_file(
                self.incidents.IncidentImportFile(
                    source_file=f"{self.secret}-1.json", content=payload
                )
            ).source_file,
        )

    def test_scanner_pre_storage_validation_screens_full_local_context(self) -> None:
        for failure in ("scope", "storage", "duplicate"):
            with self.subTest(failure=failure):
                payload = self._sarif()
                results = payload["runs"][0]["results"]
                kwargs = {"project_id": self.project.id}
                if failure == "scope":
                    kwargs = {}
                elif failure == "storage":
                    results[0]["ruleId"] = "R" * 256
                else:
                    results.append(json.loads(json.dumps(results[0])))
                with self.assertRaises(
                    self.scanners.ScannerImportValidationError
                ) as captured:
                    self.scanners.import_sarif_file(
                        self.scanners.ScannerImportFile(
                            source_file=f"{self.secret}.sarif",
                            content=json.dumps(payload),
                        ),
                        **kwargs,
                    )
                self.assertNotIn(self.secret, str(captured.exception))
                self.assertNotIn(
                    self.secret,
                    json.dumps(
                        self.scanners.scanner_import_failure_summaries(
                            captured.exception.field_errors
                        )
                    ),
                )

    def test_scanner_secret_labels_keep_distinct_stable_identity_hashes(self) -> None:
        payload = self._sarif()
        results = payload["runs"][0]["results"]
        results[0]["ruleId"] = f"{self.secret}-one"
        second = json.loads(json.dumps(results[0]))
        second["ruleId"] = f"{self.secret}-two"
        results.append(second)
        file = self.scanners.ScannerImportFile(
            source_file="synthetic.sarif", content=json.dumps(payload)
        )
        result = self.scanners.import_sarif_file(file, project_id=self.project.id)
        self.assertNotIn(self.secret, result.model_dump_json())
        self.assertEqual(len({item.source_ref for item in result.evidence}), 2)
        self.assertTrue(
            all(
                item.source_ref.startswith("sarif://finding/")
                for item in result.evidence
            )
        )
        refreshed = self.scanners.import_sarif_file(file, project_id=self.project.id)
        self.assertEqual(
            [item.id for item in result.evidence],
            [item.id for item in refreshed.evidence],
        )

    def test_scanner_validation_scrubs_echoes_in_source_and_field_paths(self) -> None:
        payload = self._sarif()
        payload["runs"][0]["results"][0]["fingerprints"] = {self.secret: 12}
        with self.assertRaises(self.scanners.ScannerImportValidationError) as captured:
            self.scanners.import_sarif_file(
                self.scanners.ScannerImportFile(
                    source_file=f"{self.secret}.sarif", content=json.dumps(payload)
                ),
                project_id=self.project.id,
            )
        self.assertNotIn(self.secret, str(captured.exception))
        self.assertNotIn(
            self.secret,
            json.dumps(
                self.scanners.scanner_import_failure_summaries(
                    captured.exception.field_errors
                )
            ),
        )

    def test_semgrep_collects_dropped_credentials_before_metadata_projection(
        self,
    ) -> None:
        payload = {
            "results": [
                {
                    "check_id": "R1",
                    "path": "main.py",
                    "start": {"line": 1, "col": 1},
                    "end": {"line": 1, "col": 2},
                    "extra": {
                        "message": f"Rotation {self.secret}",
                        "severity": "WARNING",
                        "lines": "raw source",
                        "metadata": {"api_key": self.secret, "confidence": self.secret},
                    },
                }
            ]
        }
        result = self.scanners.import_semgrep_json_file(
            self.scanners.ScannerImportFile(
                source_file="synthetic.json", content=json.dumps(payload)
            ),
            project_id=self.project.id,
        )
        self.assertNotIn(self.secret, result.model_dump_json())
        with self.database.SessionLocal() as session:
            stored = session.query(self.tables.ExternalScannerEvidence).one()
            self.assertNotIn(self.secret, stored.message + stored.properties_json)


if __name__ == "__main__":
    unittest.main()
