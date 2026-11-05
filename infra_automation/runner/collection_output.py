"""Host-only screening of bounded private saved-plan frames before local custody."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import json

from infra_automation.artifact_intake import (
    screen_artifacts,
    screen_decoded_credentials,
)
from infra_automation.runner.collector import MAX_FRAME, canonical, command_digests
from services.content_security import redact_text, redact_value


@dataclass(frozen=True)
class CollectedOutput:
    raw_plan: bytes = field(repr=False)
    screened_json: bytes = field(repr=False)
    exit_code: int
    tool: str
    tool_version: str
    command_digest: str
    argv_digest: str


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate collector field.")
        result[key] = value
    return result


def reject_nonfinite(value):
    raise ValueError("Nonfinite collector value.")


def _sensitive(value, depth=0):
    if depth > 32:
        raise ValueError("Collector nesting limit.")
    if type(value) is dict:
        for key, child in value.items():
            if key in (
                "sensitive",
                "before_sensitive",
                "after_sensitive",
                "sensitive_values",
            ) and _has_true(child):
                return True
            if _sensitive(child, depth + 1):
                return True
    elif type(value) is list:
        return any(_sensitive(child, depth + 1) for child in value)
    return False


def _has_true(value):
    if value is True:
        return True
    if type(value) is dict:
        return any(_has_true(child) for child in value.values())
    if type(value) is list:
        return any(_has_true(child) for child in value)
    return False


def parse_collection_output(raw, *, tool, version, sensitive_values=()):
    try:
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_FRAME:
            raise ValueError
        value = json.loads(
            raw, object_pairs_hook=_unique, parse_constant=reject_nonfinite
        )
        if (
            type(value) is not dict
            or set(value)
            != {"version", "tool", "tool_version", "exit_code", "plan", "json"}
            or type(value["version"]) is not int
            or value["version"] != 1
            or value["tool"] != tool
            or value["tool_version"] != version
            or type(value["exit_code"]) is not int
            or value["exit_code"] not in (0, 2)
        ):
            raise ValueError
        plan = base64.b64decode(value["plan"], validate=True)
        if (
            not plan
            or base64.b64encode(plan).decode("ascii") != value["plan"]
            or type(value["json"]) is not str
        ):
            raise ValueError
        text = value["json"]
        document = json.loads(
            text, object_pairs_hook=_unique, parse_constant=reject_nonfinite
        )
        if (
            type(document) is not dict
            or "format_version" not in document
            or document.get("errored") is True
            or document.get("complete") is False
            or document.get("incomplete") is True
            or _sensitive(document)
            or redact_text(text, sensitive_values=sensitive_values) != text
            or redact_value(document, sensitive_values=sensitive_values) != document
        ):
            raise ValueError
        screen_decoded_credentials(document, sensitive_values=sensitive_values)
        # The tool omits this optional array for an empty no-change plan. The
        # shared detector requires it; an empty array adds no evidence/change.
        if value["exit_code"] == 0 and "resource_changes" not in document:
            if (
                document.get("terraform_version") != version
                or "planned_values" not in document
            ):
                raise ValueError
            document["resource_changes"] = []
            text = canonical(document).decode("utf-8")
        screened = screen_artifacts([("plan.json", text.encode("utf-8"))])[0][1]
        command_digest, argv_digest = command_digests(tool)
        return CollectedOutput(
            plan,
            screened,
            value["exit_code"],
            tool,
            version,
            command_digest,
            argv_digest,
        )
    except Exception:
        raise ValueError("Collected evidence unavailable.") from None
