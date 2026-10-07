"""Keep snapshot side effects inside the database fixture's temporary directory."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import services.artifact_snapshot_service as snapshot_service


def isolate_artifact_snapshots(case: TestCase, directory: str) -> None:
    settings = SimpleNamespace(artifact_snapshot_dir=str(Path(directory) / "snapshots"))
    override = patch.object(snapshot_service, "settings", settings)
    override.start()
    case.addCleanup(override.stop)
