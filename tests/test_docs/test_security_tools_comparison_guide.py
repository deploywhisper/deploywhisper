"""Documentation checks for security tools comparison guidance."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPARISON_GUIDE = (
    REPO_ROOT / "docs" / "comparisons" / "deploywhisper-alongside-security-tools.md"
)
SCANNER_IMPORTS_DOC = REPO_ROOT / "docs" / "scanner-imports.md"
README = REPO_ROOT / "README.md"


class SecurityToolsComparisonGuideTests(unittest.TestCase):
    def test_comparison_guide_documents_complementary_tool_roles(self) -> None:
        content = self._normalized_prose(COMPARISON_GUIDE.read_text(encoding="utf-8"))

        self.assert_section_exists(content, "Responsibility Split")
        self.assert_section_exists(content, "Team Usage")
        expected_clauses = (
            "DeployWhisper does not replace scanners",
            "SAST, SCA, container, secrets, CSPM, policy-as-code, and IaC scanners",
            "External scanner evidence is review context",
            "scanner severity alone must not become a high or critical DeployWhisper finding",
            "Use scanner gates for known vulnerability, policy, and secret classes",
            "Use DeployWhisper for deployment-specific risk briefing",
        )
        for expected in expected_clauses:
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

    def test_comparison_guide_documents_ingestion_and_conflict_handling(self) -> None:
        content = self._normalized_prose(COMPARISON_GUIDE.read_text(encoding="utf-8"))

        self.assert_section_exists(content, "Ingestion Setup")
        self.assert_section_exists(content, "Conflict Handling")
        expected_clauses = (
            "POST /api/v1/scanner-imports/sarif",
            "POST /api/v1/scanner-imports/semgrep",
            "`project_key`",
            "`workspace_key`",
            "`share_summary.json_payload.scanner_conflicts`",
            "recommended verification",
            "freshness",
            "Do not silently choose one source",
        )
        for expected in expected_clauses:
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

    def test_comparison_guide_links_to_supporting_docs(self) -> None:
        content = COMPARISON_GUIDE.read_text(encoding="utf-8")
        actual_links = self._markdown_links_by_label(content)

        expected_links = {
            "Scanner Imports": "../scanner-imports.md",
            "CI Advisory Consumption": "../ci-advisory-consumption.md",
        }
        for label, expected_href in expected_links.items():
            with self.subTest(label=label):
                self.assertEqual(expected_href, actual_links.get(label))
                self.assertTrue((COMPARISON_GUIDE.parent / expected_href).exists())

    def test_comparison_guide_includes_team_usage_examples(self) -> None:
        content = self._normalized_prose(COMPARISON_GUIDE.read_text(encoding="utf-8"))

        self.assert_section_exists(content, "Examples")
        expected_clauses = (
            "AppSec",
            "Platform",
            "SRE",
            "Scanner reports critical public ingress",
            "Scanner reports no issue, but DeployWhisper flags high rollback risk",
            "Scanner output is stale",
        )
        for expected in expected_clauses:
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

    def test_primary_docs_link_to_comparison_guide(self) -> None:
        guide_relative = "docs/comparisons/deploywhisper-alongside-security-tools.md"
        readme_content = README.read_text(encoding="utf-8")
        scanner_doc_content = SCANNER_IMPORTS_DOC.read_text(encoding="utf-8")
        readme_links = self._markdown_links_by_label(readme_content)
        scanner_links = self._markdown_links_by_label(scanner_doc_content)

        self.assertRegex(
            self._normalized_prose(readme_content),
            r"\*\*Scanner imports\*\*:.*docs/comparisons/deploywhisper-alongside-security-tools\.md",
        )
        self.assertEqual(
            f"./{guide_relative}",
            readme_links.get("DeployWhisper Alongside Security Tools"),
        )
        self.assertEqual(
            "./comparisons/deploywhisper-alongside-security-tools.md",
            scanner_links.get("security tools comparison guide"),
        )

        for href, source in (
            (readme_links["DeployWhisper Alongside Security Tools"], README),
            (scanner_links["security tools comparison guide"], SCANNER_IMPORTS_DOC),
        ):
            with self.subTest(source=source.name, href=href):
                self.assertTrue((source.parent / href).resolve().exists())

    def assert_section_exists(self, content: str, heading: str) -> None:
        self.assertIn(f"## {heading}", content)

    @staticmethod
    def _markdown_links(content: str) -> list[tuple[str, str]]:
        return re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)

    @staticmethod
    def _markdown_links_by_label(content: str) -> dict[str, str]:
        return {
            label.replace("`", "").strip(): href.strip()
            for label, href in SecurityToolsComparisonGuideTests._markdown_links(
                content
            )
        }

    @staticmethod
    def _normalized_prose(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()


if __name__ == "__main__":
    unittest.main()
