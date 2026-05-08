"""Tests for project model documentation coverage."""

from __future__ import annotations

from pathlib import Path
import re

import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_MODEL_GUIDE = REPO_ROOT / "docs" / "concepts" / "project-model.md"


class ProjectModelDocumentationTests(unittest.TestCase):
    def test_project_modeling_guide_covers_common_self_hosted_mappings(self) -> None:
        self.assertTrue(PROJECT_MODEL_GUIDE.exists(), "Project model guide is missing.")
        content = PROJECT_MODEL_GUIDE.read_text(encoding="utf-8").lower()

        self.assertIn("does not require a saas control plane", content)
        self.assertIn("self-hosted install", content)

        expected_mappings = {
            "monorepo with several services owned by one platform or product group": [
                "use one project for the repository or product area",
                "use workspaces for environments, deploy targets, or service slices",
            ],
            "multi-repo product with one deployment domain": [
                "use one project for the product or service group",
                "deploywhisper_github_project_key",
                "use workspaces for environment, account, region, or deployment lane",
            ],
            "independent multi-repo services with different owners": [
                "use one project per service or bounded context",
                "repo-derived github project keys are a reasonable default",
            ],
            "terraform workspace based delivery": [
                "use a project for the terraform stack or platform domain",
                "map each terraform workspace to a deploywhisper workspace",
            ],
            "kubernetes cluster based delivery": [
                "use a project for the application group",
                "map clusters, namespaces, or gitops applications to workspaces",
            ],
            "platform team shared infrastructure": [
                "use one project per platform capability",
                "use workspaces for cloud accounts, clusters, regions, or maturity stages",
            ],
        }
        mapping_rows = self._recommended_mapping_rows(content)
        self.assertGreaterEqual(len(mapping_rows), len(expected_mappings))
        for setup, expected_phrases in expected_mappings.items():
            with self.subTest(setup=setup):
                row = mapping_rows[setup]
                for phrase in expected_phrases:
                    self.assertIn(phrase, " ".join(row.values()))

        self.assertIn("| infrastructure setup |", content)
        self.assertIn("| recommended project mapping |", content)
        self.assertIn("| recommended workspace mapping |", content)
        self.assertIn(
            "unknown, malformed, or blank project key stops github artifact loading",
            self._squash_whitespace(content),
        )

    def test_documentation_links_point_to_project_model_guide(self) -> None:
        link_expectations = {
            REPO_ROOT / "README.md": (
                {
                    "Project Model Guide": "./docs/concepts/project-model.md",
                    "Project Workspaces": "./docs/project-workspaces.md",
                },
            ),
            REPO_ROOT / "docs" / "project-workspaces.md": (
                {"Project Model Guide": "./concepts/project-model.md"},
            ),
        }

        for source, (expected_links,) in link_expectations.items():
            with self.subTest(source=source.name):
                content = source.read_text(encoding="utf-8")
                actual_links = dict(self._markdown_links(content))
                for label, expected_href in expected_links.items():
                    with self.subTest(label=label):
                        self.assertEqual(expected_href, actual_links.get(label))
                        target = (source.parent / expected_href).resolve()
                        self.assertTrue(target.exists())

                model_target = (
                    source.parent / expected_links["Project Model Guide"]
                ).resolve()
                self.assertEqual(PROJECT_MODEL_GUIDE, model_target)

    @staticmethod
    def _markdown_links(content: str) -> list[tuple[str, str]]:
        return re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)

    @staticmethod
    def _recommended_mapping_rows(content: str) -> dict[str, dict[str, str]]:
        lines = content.splitlines()
        expected_headers = [
            "infrastructure setup",
            "recommended project mapping",
            "recommended workspace mapping",
            "example keys",
        ]
        header_index = next(
            (
                index
                for index, line in enumerate(lines)
                if ProjectModelDocumentationTests._table_cells(line) == expected_headers
            ),
            None,
        )
        if header_index is None:
            raise AssertionError("Recommended mappings table header is missing.")

        headers = ProjectModelDocumentationTests._table_cells(lines[header_index])
        separator = ProjectModelDocumentationTests._table_cells(lines[header_index + 1])
        if headers != expected_headers or not all(
            ProjectModelDocumentationTests._is_separator_cell(cell)
            for cell in separator
        ):
            raise AssertionError("Recommended mappings table header is malformed.")

        rows: dict[str, dict[str, str]] = {}
        for line in lines[header_index + 2 :]:
            if not line.lstrip().startswith("|"):
                break
            cells = ProjectModelDocumentationTests._table_cells(line)
            if len(cells) != len(expected_headers):
                raise AssertionError(f"Malformed recommended mapping row: {line!r}")
            row = dict(zip(expected_headers, cells, strict=True))
            rows[row["infrastructure setup"]] = row

        return rows

    @staticmethod
    def _table_cells(line: str) -> list[str]:
        if not line.lstrip().startswith("|"):
            return []
        return [
            re.sub(r"\s+", " ", cell.strip()).lower()
            for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))
        ]

    @staticmethod
    def _is_separator_cell(cell: str) -> bool:
        return bool(re.fullmatch(r":?-{3,}:?", cell))

    @staticmethod
    def _squash_whitespace(content: str) -> str:
        return re.sub(r"\s+", " ", content).strip()


if __name__ == "__main__":
    unittest.main()
