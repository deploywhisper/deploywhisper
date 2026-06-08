"""Tests for shared project/workspace switcher helpers."""

from __future__ import annotations

import unittest
from unittest.mock import patch

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
import ui.components.project_workspace_switcher as switcher_module


class _FakeElement:
    def __init__(self, *, kind: str, label: str | None = None) -> None:
        self.kind = kind
        self.label = label
        self.props_values: list[str] = []
        self.class_values: list[str] = []
        self.style_values: list[str] = []
        self.opened = False
        self.value = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def props(self, value: str):
        self.props_values.append(value)
        return self

    def classes(self, value: str):
        self.class_values.append(value)
        return self

    def style(self, value: str):
        self.style_values.append(value)
        return self

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.opened = False


class _FakeUi:
    def __init__(self) -> None:
        self.dialogs: list[_FakeElement] = []
        self.cards: list[_FakeElement] = []
        self.buttons: list[_FakeElement] = []

    def dialog(self) -> _FakeElement:
        element = _FakeElement(kind="dialog")
        self.dialogs.append(element)
        return element

    def card(self) -> _FakeElement:
        element = _FakeElement(kind="card")
        self.cards.append(element)
        return element

    def column(self) -> _FakeElement:
        return _FakeElement(kind="column")

    def row(self) -> _FakeElement:
        return _FakeElement(kind="row")

    def element(self, _tag: str) -> _FakeElement:
        return _FakeElement(kind="element")

    def input(self, label: str) -> _FakeElement:
        return _FakeElement(kind="input", label=label)

    def textarea(self, label: str) -> _FakeElement:
        return _FakeElement(kind="textarea", label=label)

    def label(self, text: str) -> _FakeElement:
        return _FakeElement(kind="label", label=text)

    def button(
        self,
        text: str,
        *,
        on_click=None,
        color: str | None = None,
    ) -> _FakeElement:
        element = _FakeElement(kind="button", label=text)
        element.on_click = on_click
        element.color = color
        self.buttons.append(element)
        return element

    def separator(self) -> _FakeElement:
        return _FakeElement(kind="separator")


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

    def test_create_project_dialog_is_persistent_with_explicit_close_controls(
        self,
    ) -> None:
        fake_ui = _FakeUi()
        lifecycle = {"opened": 0, "closed": 0}

        def decorate_modal_card(element, *, label: str) -> None:
            element.props(f'role=dialog aria-modal=true aria-label="{label}"')

        with (
            patch.object(switcher_module, "ui", fake_ui),
            patch.object(
                switcher_module,
                "decorate_modal_card",
                decorate_modal_card,
            ),
        ):
            switcher_module.open_create_project_dialog(
                on_created=lambda _project: None,
                on_open=lambda: lifecycle.update(opened=lifecycle["opened"] + 1),
                on_close=lambda: lifecycle.update(closed=lifecycle["closed"] + 1),
            )

        self.assertEqual(len(fake_ui.dialogs), 1)
        self.assertIn("persistent", fake_ui.dialogs[0].props_values)
        self.assertTrue(fake_ui.dialogs[0].opened)
        self.assertEqual(lifecycle, {"opened": 1, "closed": 0})
        self.assertIn(
            'data-dw-create-project-dialog="1"',
            fake_ui.cards[0].props_values,
        )
        self.assertIn(
            'role=dialog aria-modal=true aria-label="Create project workspace"',
            fake_ui.cards[0].props_values,
        )
        button_labels = [button.label for button in fake_ui.buttons]
        self.assertIn("Close", button_labels)
        self.assertIn("Cancel", button_labels)
        self.assertIn("Create project", button_labels)
        close_button = next(
            button for button in fake_ui.buttons if button.label == "Close"
        )
        cancel_button = next(
            button for button in fake_ui.buttons if button.label == "Cancel"
        )
        self.assertIn('data-dw-modal-close="1"', close_button.props_values)
        self.assertIn('data-dw-modal-close="1"', cancel_button.props_values)

        close_button.on_click()
        cancel_button.on_click()

        self.assertEqual(lifecycle, {"opened": 1, "closed": 1})


if __name__ == "__main__":
    unittest.main()
