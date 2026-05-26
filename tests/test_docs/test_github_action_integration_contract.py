"""Tests for the external GitHub Action integration contract."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess  # nosec
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
ACTION_GUIDE = REPO_ROOT / "docs" / "github-action.md"
README = REPO_ROOT / "README.md"


class GitHubActionIntegrationContractTests(unittest.TestCase):
    def test_github_action_guide_points_to_external_action_and_v2_schema(self) -> None:
        self.assertTrue(ACTION_GUIDE.exists(), "GitHub Action guide is missing.")
        content = ACTION_GUIDE.read_text(encoding="utf-8")

        for expected in (
            "deploywhisper/analyze-action@v1",
            "https://github.com/deploywhisper/analyze-action",
            "POST /api/v1/analyses",
            "project-key",
            "workspace-key",
            "project_key",
            "report_schema_version",
            "share_summary.json_payload",
            "docs/schemas/report-v2.md",
            "JSON-encoded string",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

    def test_github_action_guide_maps_outputs_to_canonical_schema_fields(self) -> None:
        content = ACTION_GUIDE.read_text(encoding="utf-8")
        mapping = self._table_mapping(
            content,
            header=["Action output", "Canonical source"],
        )

        self.assertEqual(
            {
                "report-id": "data.persisted_report.id",
                "report-link": "data.share_summary.json_payload.report_link",
                "severity": "data.advisory.severity, falling back to data.share_summary.severity when advisory is blank",
                "recommendation": "data.advisory.recommendation, falling back to data.share_summary.recommendation when advisory is blank",
                "share-summary-json": "JSON-encoded data.share_summary.json_payload",
                "share-summary-markdown": "data.share_summary.markdown",
            },
            mapping,
        )

    def test_github_action_guide_separates_action_owned_github_metadata(self) -> None:
        content = ACTION_GUIDE.read_text(encoding="utf-8")
        metadata_mapping = self._table_mapping(
            content,
            header=["Action output", "Action-owned source"],
        )

        self.assertEqual(
            {
                "comment-id": "GitHub PR comment identifier returned by the external action",
                "comment-url": "GitHub PR comment URL returned by the external action",
                "comment-updated": "GitHub PR comment create/update state returned by the external action",
            },
            metadata_mapping,
        )

    def test_github_action_guide_locks_advisory_local_first_boundaries(self) -> None:
        content = self._normalized_prose(ACTION_GUIDE.read_text(encoding="utf-8"))

        expected_clauses = (
            "Consumers should use `data.advisory.requires_attention` to decide whether to notify reviewers or add manual checks.",
            "Advisory-first boundary: the action surfaces evidence and recommendations for review, but does not enforce deployment blocking by itself.",
            "Local-first boundary: raw IaC, scanner artifacts, incident exports, and sensitive context stay in the user's infrastructure by default.",
            "External model calls should receive structured summaries, not raw uploads.",
            "Secret-storage prohibition: the action contract must not persist API tokens, provider credentials, raw infrastructure state, or deployment secrets.",
            "The `report-link` output is publicly shareable only when the DeployWhisper server is configured with a public base URL such as `APP_BASE_URL` or `PUBLIC_APP_URL`.",
            "Without that public URL prerequisite, self-hosted app instances may emit a local or private fallback link such as `http://127.0.0.1:8080/reports/{id}`, so GitHub Action consumers should treat `report-link` and `share-summary-json.report_link` as optional for external review workflows.",
        )
        for expected in expected_clauses:
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

    def test_app_repo_does_not_host_marketplace_action_runtime(self) -> None:
        tracked_files = subprocess.check_output(  # nosec
            ["git", "ls-files", "--cached"],
            cwd=REPO_ROOT,
            text=True,
        ).splitlines()
        forbidden_files = [
            path
            for path in tracked_files
            if self._is_forbidden_action_runtime_path(path)
            or self._contains_standalone_action_runtime_markers(REPO_ROOT / path)
        ]

        self.assertEqual([], forbidden_files)

    def test_github_action_guide_names_external_smoke_consumer_owner(self) -> None:
        content = self._normalized_prose(ACTION_GUIDE.read_text(encoding="utf-8"))

        expected_clauses = (
            "Action repo: `deploywhisper/analyze-action`",
            "Owns packaged action runtime code and Marketplace release metadata.",
            "Smoke consumer repo: `deploywhisper/action-smoke-consumer`",
            "Owns live GitHub Actions smoke workflows for immutable release tags and the moving `v1` compatibility tag.",
            "Owns same-repository PR smoke validation for published action behavior.",
        )
        for expected in expected_clauses:
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

    def test_documentation_links_resolve_to_contract_guides(self) -> None:
        link_expectations = {
            README: {"docs/github-action.md": "./docs/github-action.md"},
            ACTION_GUIDE: {"Report Schema v2": "./schemas/report-v2.md"},
        }

        for source, expected_links in link_expectations.items():
            with self.subTest(source=source.name):
                content = source.read_text(encoding="utf-8")
                actual_links = {
                    self._strip_code(label): href
                    for label, href in self._markdown_links(content)
                }
                for label, expected_href in expected_links.items():
                    with self.subTest(label=label):
                        self.assertEqual(expected_href, actual_links.get(label))
                        self.assertTrue(
                            (source.parent / expected_href).resolve().exists()
                        )

    def test_readme_links_to_github_action_contract(self) -> None:
        content = README.read_text(encoding="utf-8")
        self.assertIn("docs/github-action.md", content)
        self.assertIn("deploywhisper/analyze-action@v1", content)
        self.assertIn("project-key", content)
        self.assertIn("publicly shareable only", content)
        self.assertIn("local/private", content)
        self.assertIn("APP_BASE_URL", content)
        self.assertIn("PUBLIC_APP_URL", content)

    @staticmethod
    def _table_mapping(content: str, *, header: list[str]) -> dict[str, str]:
        lines = content.splitlines()
        header_index = next(
            (
                index
                for index, line in enumerate(lines)
                if GitHubActionIntegrationContractTests._table_cells(line) == header
            ),
            None,
        )
        if header_index is None:
            raise AssertionError(f"Expected table is missing: {header!r}.")

        rows: dict[str, str] = {}
        for line in lines[header_index + 2 :]:
            if not line.lstrip().startswith("|"):
                break
            cells = GitHubActionIntegrationContractTests._table_cells(line)
            if len(cells) != 2:
                raise AssertionError(f"Malformed mapping row: {line!r}")
            output, source = cells
            clean_output = GitHubActionIntegrationContractTests._strip_code(output)
            clean_source = GitHubActionIntegrationContractTests._strip_code(source)
            if clean_output in rows:
                raise AssertionError(f"Duplicate action output: {clean_output}")
            rows[clean_output] = clean_source
        return rows

    @staticmethod
    def _is_forbidden_action_runtime_path(path: str) -> bool:
        normalized = path.replace("\\", "/")
        name = Path(normalized).name
        if name in {
            "action.yml",
            "action.yaml",
            "action_runtime.py",
            "run_action.py",
            "PUBLISHING.md",
        }:
            return True
        return normalized.startswith(".github/actions/")

    @staticmethod
    def _contains_standalone_action_runtime_markers(path: Path) -> bool:
        if path == Path(__file__).resolve():
            return False
        if path.suffix not in {".py", ".yml", ".yaml"}:
            return False
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return False
        action_runtime_markers = (
            'COMMENT_MARKER = "<!-- deploywhisper:pr-comment -->"',
            'SCAN_META_MARKER = "deploywhisper:scan-meta"',
            "def run_action(args:",
            "write_github_output(",
        )
        composite_action_markers = (
            "github.action_path",
            "run_action.py",
            "deploywhisper.outputs.",
        )
        return any(marker in content for marker in action_runtime_markers) or all(
            marker in content for marker in composite_action_markers
        )

    @staticmethod
    def _markdown_links(content: str) -> list[tuple[str, str]]:
        return re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)

    @staticmethod
    def _strip_code(value: str) -> str:
        return value.replace("`", "").strip()

    @staticmethod
    def _normalized_prose(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _table_cells(line: str) -> list[str]:
        if not line.lstrip().startswith("|"):
            return []
        return [cell.strip() for cell in line.strip().strip("|").split("|")]


if __name__ == "__main__":
    unittest.main()
