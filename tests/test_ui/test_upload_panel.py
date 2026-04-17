"""Tests for upload panel state helpers."""

from __future__ import annotations

import unittest

from ui.components.upload_panel import process_uploaded_files


class UploadPanelTests(unittest.TestCase):
    def test_process_uploaded_files_marks_supported_inputs_ready(self) -> None:
        current_files: list[tuple[str, bytes]] = []

        summary = process_uploaded_files(
            current_files,
            [("etcd-pvc-new.yaml", b"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: etcd\n")],
        )

        self.assertEqual(summary.ready_count, 1)
        self.assertEqual(summary.items[0].status, "ready")
        self.assertEqual(current_files[0][0], "etcd-pvc-new.yaml")


if __name__ == "__main__":
    unittest.main()
