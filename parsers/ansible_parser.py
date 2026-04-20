"""Ansible parser."""

from __future__ import annotations

import yaml

from parsers.base import UnifiedChange, build_change_id


def parse_ansible(name: str, raw_content: bytes | None) -> list[UnifiedChange]:
    if not raw_content:
        return []

    documents = [doc for doc in yaml.safe_load_all(raw_content.decode("utf-8")) if doc]
    changes: list[UnifiedChange] = []
    occurrence = 0
    for document in documents:
        if isinstance(document, list):
            plays = document
        else:
            plays = [document]
        for play in plays:
            tasks = play.get("tasks", []) if isinstance(play, dict) else []
            for index, task in enumerate(tasks, start=1):
                task_name = (
                    task.get("name", f"task-{index}")
                    if isinstance(task, dict)
                    else f"task-{index}"
                )
                changes.append(
                    UnifiedChange(
                        change_id=build_change_id(
                            name, "ansible", task_name, "modify", occurrence
                        ),
                        source_file=name,
                        tool="ansible",
                        resource_id=task_name,
                        action="modify",
                        summary=f"Ansible task {task_name} included in analysis set.",
                    )
                )
                occurrence += 1
    return changes
