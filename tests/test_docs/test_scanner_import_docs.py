"""Tests for scanner import documentation coverage."""

from __future__ import annotations

from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER_IMPORTS_DOC = REPO_ROOT / "docs" / "scanner-imports.md"


class ScannerImportDocumentationTests(unittest.TestCase):
    def test_semgrep_endpoint_documents_optional_workspace_scope_fields(self) -> None:
        content = SCANNER_IMPORTS_DOC.read_text(encoding="utf-8")
        semgrep_section = content.split("## Semgrep JSON Endpoint", maxsplit=1)[1]
        semgrep_section = semgrep_section.split("## Validation", maxsplit=1)[0]

        self.assertIn("Optional scope fields:", semgrep_section)
        self.assertIn("`project_id`", semgrep_section)
        self.assertIn("`workspace_id`", semgrep_section)
        self.assertIn("`workspace_key`", semgrep_section)

    def test_semgrep_validation_example_uses_semgrep_error_code(self) -> None:
        content = SCANNER_IMPORTS_DOC.read_text(encoding="utf-8")
        validation_section = content.split("## Validation", maxsplit=1)[1]
        local_first_section = validation_section.split(
            "## Local-First Boundary",
            maxsplit=1,
        )[0]

        self.assertIn("Semgrep validation example", local_first_section)
        self.assertIn("semgrep_import_validation_failed", local_first_section)
        self.assertIn("Semgrep JSON import validation failed.", local_first_section)

    def test_semgrep_endpoint_documents_top_level_fingerprint_fallback(self) -> None:
        content = SCANNER_IMPORTS_DOC.read_text(encoding="utf-8")
        semgrep_section = content.split("## Semgrep JSON Endpoint", maxsplit=1)[1]
        semgrep_section = semgrep_section.split("## Validation", maxsplit=1)[0]

        self.assertIn("`extra.fingerprint`", semgrep_section)
        self.assertIn("top-level `fingerprint`", semgrep_section)
        self.assertIn("compatibility fallback", semgrep_section)
