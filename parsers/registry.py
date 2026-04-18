"""Parser registry and normalization flow."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

import yaml

from parsers.ansible_parser import parse_ansible
from parsers.base import ParseBatchResult, ParseIssue, ParsedFileResult, UnifiedChange
from parsers.cloudformation_parser import parse_cloudformation
from parsers.jenkins_parser import parse_jenkins
from parsers.kubernetes_parser import parse_kubernetes
from parsers.terraform_parser import parse_terraform

ParserFn = Callable[[str, bytes | None], list[UnifiedChange]]

PARSERS: dict[str, ParserFn] = {
    "terraform": parse_terraform,
    "kubernetes": parse_kubernetes,
    "ansible": parse_ansible,
    "jenkins": parse_jenkins,
    "cloudformation": parse_cloudformation,
}


def _decode_content(raw: bytes | None) -> str:
    if not raw:
        return ""
    return raw.decode("utf-8", errors="ignore")


def _load_yaml_documents(content: str) -> list[object]:
    if not content.strip():
        return []
    try:
        return [doc for doc in yaml.safe_load_all(content) if doc is not None]
    except yaml.YAMLError:
        return []


def _content_preview(content: str, *, line_limit: int = 100) -> str:
    return "\n".join(content.splitlines()[:line_limit])


def _looks_like_cloudformation_preview(content: str) -> bool:
    preview = _content_preview(content)
    top_level_keys = re.compile(
        r"(?m)^(AWSTemplateFormatVersion|Resources|Parameters|Outputs)\s*:"
    )
    intrinsic_markers = re.compile(
        r"(?m)(!Ref\b|!Sub\b|!GetAtt\b|Fn::Sub\b|Fn::Join\b|Fn::GetAtt\b|AWS::)"
    )
    return bool(top_level_keys.search(preview) or intrinsic_markers.search(preview))


def detect_tool_type(name: str, raw_content: bytes | None = None) -> str:
    lower_name = name.lower()
    path = Path(lower_name)
    content = _decode_content(raw_content)

    if lower_name == "jenkinsfile" or path.name == "jenkinsfile":
        return "jenkins"

    if path.suffix in {".tf", ".tfvars", ".hcl"}:
        return "terraform"

    if path.suffix == ".json":
        try:
            payload = json.loads(content) if content else {}
        except json.JSONDecodeError:
            payload = {}
        if "resource_changes" in payload:
            return "terraform"
        if any(
            key in payload
            for key in (
                "AWSTemplateFormatVersion",
                "Resources",
                "Parameters",
                "Outputs",
            )
        ):
            return "cloudformation"

    if path.suffix in {".yaml", ".yml"}:
        if _looks_like_cloudformation_preview(content):
            return "cloudformation"
        documents = _load_yaml_documents(content)
        for document in documents:
            if isinstance(document, dict) and {"apiVersion", "kind"} <= set(
                document.keys()
            ):
                return "kubernetes"
        for document in documents:
            if isinstance(document, dict) and (
                "AWSTemplateFormatVersion" in document
                or "Resources" in document
                or str(document.get("Transform", "")).startswith("AWS::")
            ):
                return "cloudformation"
        for document in documents:
            if isinstance(document, dict) and (
                "hosts" in document or "tasks" in document or "roles" in document
            ):
                return "ansible"

    return "unsupported"


def parse_uploaded_files(files: list[tuple[str, bytes | None]]) -> ParseBatchResult:
    results: list[ParsedFileResult] = []
    for name, raw_content in files:
        tool = detect_tool_type(name, raw_content)
        parser = PARSERS.get(tool)
        if parser is None:
            results.append(
                ParsedFileResult(
                    file_name=name,
                    tool=tool,
                    status="skipped",
                    issue=ParseIssue(
                        file_name=name,
                        tool=tool,
                        message="Unsupported or unrecognized file excluded from parsing.",
                    ),
                )
            )
            continue

        try:
            changes = parser(name, raw_content)
            if not changes:
                raise ValueError(
                    f"No normalized changes produced for supported {tool} artifact."
                )
            results.append(
                ParsedFileResult(
                    file_name=name,
                    tool=tool,
                    status="parsed",
                    changes=changes,
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                ParsedFileResult(
                    file_name=name,
                    tool=tool,
                    status="failed",
                    issue=ParseIssue(
                        file_name=name,
                        tool=tool,
                        message=str(exc),
                    ),
                )
            )

    return ParseBatchResult(files=results)
