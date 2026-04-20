"""Jenkins parser."""

from __future__ import annotations

import re

from parsers.base import UnifiedChange, build_change_id


STAGE_PATTERN = re.compile(r"stage\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")


def parse_jenkins(name: str, raw_content: bytes | None) -> list[UnifiedChange]:
    if not raw_content:
        return []

    content = raw_content.decode("utf-8", errors="ignore")
    stages = STAGE_PATTERN.findall(content)
    if not stages:
        return [
            UnifiedChange(
                change_id=build_change_id(name, "jenkins", "pipeline", "modify", 0),
                source_file=name,
                tool="jenkins",
                resource_id="pipeline",
                action="modify",
                summary="Jenkins pipeline included in analysis set.",
            )
        ]

    return [
        UnifiedChange(
            change_id=build_change_id(
                name, "jenkins", f"stage/{stage_name}", "modify", index
            ),
            source_file=name,
            tool="jenkins",
            resource_id=f"stage/{stage_name}",
            action="modify",
            summary=f"Jenkins stage {stage_name} included in analysis set.",
        )
        for index, stage_name in enumerate(stages)
    ]
