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
            "project-id",
            "workspace-key",
            "workspace-id",
            "project_key",
            "project_id",
            "workspace_key",
            "workspace_id",
            "report_schema_version",
            "share_summary.json_payload",
            "docs/schemas/report-v2.md",
            "JSON-encoded string",
            "local-first upload boundary",
            "data.advisory.requires_attention",
            "public `APP_BASE_URL` or `PUBLIC_APP_URL`",
            "endpoint derives project scope",
            "`changed-files`",
            "`working-directory`",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

    def test_github_action_guide_maps_outputs_to_canonical_schema_fields(self) -> None:
        content = ACTION_GUIDE.read_text(encoding="utf-8")
        mapping = self._canonical_schema_mapping(content)

        self.assertEqual(
            {
                "report-id": "data.persisted_report.id",
                "report-link": "data.share_summary.json_payload.report_link",
                "severity": "data.advisory.severity",
                "recommendation": "data.advisory.recommendation",
                "share-summary-json": "JSON-encoded data.share_summary.json_payload",
                "share-summary-markdown": "data.share_summary.markdown",
                "comment-id": "GitHub PR comment identifier returned by the external action",
                "comment-url": "GitHub PR comment URL returned by the external action",
                "comment-updated": "GitHub PR comment create/update state returned by the external action",
            },
            mapping,
        )

    def test_app_repo_does_not_host_marketplace_action_runtime(self) -> None:
        tracked_or_unignored = self._repository_owned_paths()
        forbidden_files = [
            path
            for path in tracked_or_unignored
            if Path(path).name in {"action.yml", "action.yaml"}
        ]

        self.assertEqual([], forbidden_files)

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
        self.assertIn("project-id", content)
        self.assertIn("workspace-key", content)
        self.assertIn("workspace-id", content)
        self.assertIn("APP_BASE_URL", content)
        self.assertIn("PUBLIC_APP_URL", content)

    @staticmethod
    def _canonical_schema_mapping(content: str) -> dict[str, str]:
        lines = content.splitlines()
        header_index = next(
            (
                index
                for index, line in enumerate(lines)
                if GitHubActionIntegrationContractTests._table_cells(line)
                == ["Action output", "Canonical source"]
            ),
            None,
        )
        if header_index is None:
            raise AssertionError("Canonical schema mapping table is missing.")

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
    def _markdown_links(content: str) -> list[tuple[str, str]]:
        return re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)

    @staticmethod
    def _strip_code(value: str) -> str:
        return value.replace("`", "").strip()

    @staticmethod
    def _table_cells(line: str) -> list[str]:
        if not line.lstrip().startswith("|"):
            return []
        return [cell.strip() for cell in line.strip().strip("|").split("|")]

    @staticmethod
    def _repository_owned_paths() -> list[str]:
        if (REPO_ROOT / ".git").exists():
            return subprocess.check_output(  # nosec
                ["git", "ls-files", "--cached"],
                cwd=REPO_ROOT,
                text=True,
            ).splitlines()
        ignored_roots = {".git", ".venv", "node_modules", "__pycache__"}
        return [
            str(path.relative_to(REPO_ROOT))
            for path in REPO_ROOT.rglob("*")
            if path.is_file()
            and not any(
                part in ignored_roots for part in path.relative_to(REPO_ROOT).parts
            )
        ]


if __name__ == "__main__":
    unittest.main()
