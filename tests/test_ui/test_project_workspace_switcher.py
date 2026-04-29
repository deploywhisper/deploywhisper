"""Tests for shared project/workspace switcher helpers."""

from __future__ import annotations

import unittest

from services.project_service import ProjectRecord
from ui.components.project_workspace_switcher import (
    build_project_options,
    filter_project_records,
    highlight_project_match,
    split_project_option_label,
    project_context_meta,
    project_context_summary,
    project_option_label,
    project_repository_context,
)


class ProjectWorkspaceSwitcherTests(unittest.TestCase):
    def _project(
        self,
        *,
        project_key: str,
        display_name: str,
        repository_url: str | None = None,
    ) -> ProjectRecord:
        return ProjectRecord(
            id=1,
            project_key=project_key,
            display_name=display_name,
            description=None,
            repository_url=repository_url,
            default_branch=None,
            is_default=False,
            created_at="2026-04-28T00:00:00",
            updated_at="2026-04-28T00:00:00",
        )

    def test_project_option_label_includes_repo_context_when_available(self) -> None:
        project = self._project(
            project_key="payments",
            display_name="Payments",
            repository_url="https://github.com/acme/payments-api.git",
        )

        self.assertEqual(project_repository_context(project), "acme/payments-api")
        self.assertEqual(
            project_option_label(project),
            "Payments · acme/payments-api · payments",
        )

    def test_build_project_options_uses_searchable_project_labels(self) -> None:
        project = self._project(project_key="payments", display_name="Payments")

        options = build_project_options([project])

        self.assertEqual(options, {1: "Payments · payments"})

    def test_filter_project_records_matches_name_repo_and_key_case_insensitively(
        self,
    ) -> None:
        projects = [
            self._project(
                project_key="payments",
                display_name="Payments",
                repository_url="https://github.com/acme/payments-api.git",
            ),
            self._project(
                project_key="platform",
                display_name="Platform Control",
                repository_url="https://github.com/acme/platform-hub.git",
            ),
        ]

        self.assertEqual(
            [
                project.project_key
                for project in filter_project_records(projects, "pay")
            ],
            ["payments"],
        )
        self.assertEqual(
            [
                project.project_key
                for project in filter_project_records(projects, "PLATFORM-HUB")
            ],
            ["platform"],
        )
        self.assertEqual(
            [
                project.project_key
                for project in filter_project_records(projects, "payments")
            ],
            ["payments"],
        )

    def test_highlight_project_match_wraps_matching_query_in_mark(self) -> None:
        highlighted = highlight_project_match("Payments API", "pay")

        self.assertIn("<mark", highlighted)
        self.assertIn("Pay", highlighted)

    def test_split_project_option_label_breaks_primary_and_secondary_lines(
        self,
    ) -> None:
        primary, secondary = split_project_option_label(
            "Payments · acme/payments-api · payments"
        )

        self.assertEqual(primary, "Payments")
        self.assertEqual(secondary, "acme/payments-api · payments")

    def test_project_context_helpers_distinguish_default_and_active_contexts(
        self,
    ) -> None:
        project = ProjectRecord(
            id=1,
            project_key="unassigned",
            display_name="Unassigned",
            description=None,
            repository_url=None,
            default_branch=None,
            is_default=True,
            created_at="2026-04-28T00:00:00",
            updated_at="2026-04-28T00:00:00",
        )

        self.assertEqual(
            project_context_summary(project),
            "Unassigned",
        )
        self.assertEqual(
            project_context_meta(
                has_saved_selection=False,
                active_project=project,
            ),
            "Default workspace · Key unassigned",
        )
        self.assertEqual(
            project_context_meta(
                has_saved_selection=True,
                active_project=project,
            ),
            "Key unassigned",
        )


if __name__ == "__main__":
    unittest.main()
