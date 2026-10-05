"""Credential boundaries for current and historical artifact snapshots."""

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
import services.artifact_snapshot_service as snapshot_service
from services.content_security import BLOCKED_CONTENT


class SnapshotContentBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.snapshot_dir = self.root / "artifacts"
        self.environment = patch.dict(
            os.environ,
            {
                "DATABASE_URL": f"sqlite:///{self.root / 'reports.db'}",
                "ARTIFACT_SNAPSHOT_DIR": str(self.snapshot_dir),
            },
        )
        self.environment.start()
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(snapshot_service)
        database_module.init_db()

    def tearDown(self) -> None:
        database_module.engine.dispose()
        self.environment.stop()
        self.tempdir.cleanup()

    def test_batch_context_blocks_bare_sibling_credential_echo(self) -> None:
        secret = "synthetic-sibling-task-value"
        raw = f"hosts: all\ntasks:\n  - name: {secret}\n    debug:\n      msg: safe\n".encode()

        snapshot_service.save_report_artifacts(
            1, {"playbook.yaml": raw}, sensitive_values=(secret,)
        )

        self.assertEqual(
            snapshot_service.load_report_artifact(1, "playbook.yaml").content,
            BLOCKED_CONTENT,
        )
        for path in self.snapshot_dir.rglob("*"):
            if path.is_file():
                self.assertNotIn(secret.encode(), path.read_bytes())

    def test_raw_and_structured_credentials_block_entire_snapshot(self) -> None:
        for artifact_name, raw in (
            ("main.tf", b'password = "synthetic-raw-value"'),
            (
                "secret.yaml",
                b"kind: Secret\ndata:\n  arbitrary: c3ludGhldGljLWt1YmUtdmFsdWU=\n",
            ),
        ):
            with self.subTest(artifact_name=artifact_name):
                snapshot_service.save_report_artifacts(1, {artifact_name: raw})
                self.assertEqual(
                    snapshot_service.load_report_artifact(1, artifact_name).content,
                    BLOCKED_CONTENT,
                )

    def test_historical_sensitive_filename_blocks_content_and_scrubs_display_name(
        self,
    ) -> None:
        report_dir = self.snapshot_dir / "1"
        report_dir.mkdir(parents=True)
        name = "password=synthetic-name-value.env"
        (report_dir / "manifest.json").write_text(json.dumps({name: "old.txt"}))
        (report_dir / "old.txt").write_text("legacy unrecognized credential payload")

        snapshot = snapshot_service.load_report_artifact(1, name)

        self.assertEqual(snapshot.content, BLOCKED_CONTENT)
        self.assertNotIn("synthetic-name-value", snapshot.artifact_name)

    def test_clean_snapshot_content_is_preserved(self) -> None:
        raw = b"hosts: all\ntasks: []\n"
        snapshot_service.save_report_artifacts(1, {"playbook.yaml": raw})
        self.assertEqual(
            snapshot_service.load_report_artifact(1, "playbook.yaml").content,
            raw.decode(),
        )
