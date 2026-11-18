"""Frozen plan-directed capabilities and deny-before-construction guard."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from types import MappingProxyType

_CATALOG = json.loads(Path(__file__).with_name("catalog.json").read_text())
ALLOWLIST = frozenset(row["iam_action"] for row in _CATALOG["operations"].values())
PERMISSIONS = MappingProxyType(
    {
        name: frozenset(
            {_CATALOG["operations"][op]["iam_action"] for op in row["operations"]}
        )
        for name, row in _CATALOG["families"].items()
    }
)


def assert_read_only(actions):
    for action in actions:
        if (
            not isinstance(action, str)
            or re.fullmatch(
                r"[a-z0-9]+:(Describe|Get|List|BatchGet|Head)[A-Z][A-Za-z0-9]*", action
            )
            is None
        ):
            raise ValueError("Non-read-only AWS action")


def authorize(action, construct):
    if not isinstance(action, str) or action not in ALLOWLIST:
        logging.getLogger("cloud.aws").warning("action_refused")
        raise PermissionError("AWS action refused")
    return construct()
