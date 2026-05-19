"""Findings table with evidence drill-down."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from nicegui import ui

from ui.components.review_accessibility import (
    decorate_review_section,
    register_review_accessibility,
)
from ui.formatters.confidence import render_confidence_badge
from ui.formatters.determinism import render_determinism_badge
from ui.formatters.risk_labels import render_risk_badge

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
SOURCE_TYPE_META = {
    "artifact": {"icon": "description", "label": "Artifact"},
    "topology": {"icon": "hub", "label": "Topology"},
    "incident": {"icon": "history", "label": "Incident"},
    "history": {"icon": "schedule", "label": "History"},
    "heuristic": {"icon": "rule", "label": "Heuristic"},
    "skill": {"icon": "psychology", "label": "Skill"},
    "external_scanner": {"icon": "policy", "label": "External scanner"},
    "user_context": {"icon": "person_search", "label": "User context"},
}
EXTERNAL_SOURCE_TYPES = {
    "topology",
    "incident",
    "history",
    "scanner",
    "external",
    "external_scanner",
}
USER_CONTEXT_SOURCE_TYPES = {"user_context"}
SEVERE_LEVELS = {"high", "critical"}
REDACTION_EXPLANATIONS = {
    "none": "No redaction was applied to this evidence item.",
    "redacted": (
        "Sensitive portions were redacted before display; safe metadata remains "
        "available for review."
    ),
    "sensitive_blocked": (
        "Sensitive-file handling blocked raw evidence content; safe metadata "
        "remains available for review."
    ),
}


def _parse_fragment(fragment: str) -> tuple[str, dict[str, list[str]]]:
    if not fragment:
        return "", {}
    locator, separator, query_string = fragment.partition("?")
    if separator:
        return locator, parse_qs(query_string)
    return fragment, {}


def _line_from_locator(locator: str, params: dict[str, list[str]]) -> str | None:
    for candidate in params.get("line", []):
        if candidate.isdigit():
            return candidate
    normalized = locator.strip()
    if normalized.lower().startswith("line="):
        candidate = normalized.split("=", 1)[1]
        if candidate.isdigit():
            return candidate
    if normalized.lower().startswith("l") and normalized[1:].isdigit():
        return normalized[1:]
    return None


def _source_path(parsed) -> str:
    pieces = [parsed.netloc, parsed.path.lstrip("/")]
    return "/".join(piece for piece in pieces if piece)


def _source_system(source_type: str, parsed) -> str | None:
    if source_type not in {"topology", "incident"}:
        return None
    candidates = [
        parsed.netloc,
        parsed.path.strip("/").split("/", 1)[0] if parsed.path.strip("/") else "",
    ]
    for candidate in candidates:
        value = unquote(candidate).strip()
        if value:
            return value
    return None


def _clean_text(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _title_label(value: str) -> str:
    normalized = value.replace("_", " ").replace("-", " ").strip()
    if not normalized:
        return "Unknown"
    return normalized[0].upper() + normalized[1:]


def _scope_label(
    scope_name: str,
    scope_key: str | None,
    scope_id: int | None,
) -> str:
    identifier = str(scope_key or "").strip()
    if identifier and scope_id is not None:
        return f"{scope_name} {identifier} (#{scope_id})"
    if identifier:
        return f"{scope_name} {identifier}"
    if scope_id is not None:
        return f"{scope_name} #{scope_id}"
    return f"{scope_name} not recorded"


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _redaction_status(value: Any) -> str:
    if value is None:
        return "unknown"
    status = str(value).strip().lower()
    if not status:
        return "unknown"
    if status in REDACTION_EXPLANATIONS:
        return status
    return "unknown"


def _effective_redaction_status(
    evidence_item: dict[str, Any],
    *,
    legacy_missing_redaction_is_none: bool = False,
) -> str:
    if legacy_missing_redaction_is_none and "redaction_status" not in evidence_item:
        return "none"
    return _redaction_status(evidence_item.get("redaction_status"))


def _redaction_label(status: str) -> str:
    if status == "unknown":
        return "Unknown"
    return _title_label(status)


def _redaction_explanation(status: str) -> str:
    if status in REDACTION_EXPLANATIONS:
        return REDACTION_EXPLANATIONS[status]
    return (
        "Evidence content availability is unknown; safe metadata remains available "
        "for review."
    )


def _can_render_evidence_summary(redaction_status: str) -> bool:
    return redaction_status == "none"


def _safe_prop_value(value: Any) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or ""))
    normalized = re.sub(r" {2,}", " ", text).strip()
    return normalized.replace("\\", "\\\\").replace('"', '\\"')


def _safe_dom_id(*parts: Any) -> str:
    raw = "-".join(str(part or "") for part in parts)
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", raw).strip("-")
    if safe == raw and safe:
        return safe
    digest = sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"{safe or 'unknown'}-{digest}"


def _finding_row_key(finding: dict[str, Any], index: int) -> str:
    return _safe_dom_id(
        "finding-row",
        index,
        finding.get("finding_id"),
        finding.get("title"),
    )


def _is_legacy_report_schema(report_schema_version: str | None) -> bool:
    version = str(report_schema_version or "").strip().lower()
    return version == "v1"


def _resolve_artifact_name(
    source_path: str,
    artifact_names: set[str] | None,
) -> str | None:
    if not artifact_names:
        return None
    if source_path in artifact_names:
        return source_path
    source_basename = Path(source_path).name
    if not source_basename:
        return None
    basename_matches = [
        artifact_name
        for artifact_name in artifact_names
        if Path(artifact_name).name == source_basename
    ]
    if len(basename_matches) == 1:
        return basename_matches[0]
    return None


def _artifact_view_href(
    report_id: int,
    artifact_name: str,
    line_number: str | None,
) -> str:
    query = {"name": artifact_name}
    if line_number is not None:
        query["line"] = line_number
    href = f"/history/{report_id}/artifacts?{urlencode(query)}"
    if line_number is not None:
        href += f"#L{line_number}"
    return href


def describe_evidence_item(
    evidence_item: dict[str, Any],
    *,
    artifact_names: set[str] | None = None,
    report_id: int | None = None,
    legacy_missing_redaction_is_none: bool = False,
) -> dict[str, Any]:
    """Build the UI-facing evidence metadata for one inspector card."""
    source_type = str(evidence_item.get("source_type", "heuristic")).lower()
    source_ref = str(evidence_item.get("source_ref", ""))
    meta = SOURCE_TYPE_META.get(source_type, SOURCE_TYPE_META["heuristic"])
    parsed = urlparse(source_ref)
    source_path = unquote(_source_path(parsed))
    locator, locator_params = _parse_fragment(parsed.fragment)
    locator = unquote(locator)
    line_number = _line_from_locator(locator, locator_params)
    display_bits = [source_path or unquote(source_ref)]
    if line_number is not None:
        display_bits.append(f"line {line_number}")
    elif locator and not locator.lower().startswith("line="):
        display_bits.append(locator)
    display_source_ref = " \u00b7 ".join(bit for bit in display_bits if bit)
    artifact_href = None
    resolved_artifact_name = _resolve_artifact_name(source_path, artifact_names)
    artifact_label = _clean_text(
        evidence_item.get("artifact"), source_path or "unknown artifact"
    )
    resource_label = _clean_text(evidence_item.get("resource"), "resource not recorded")
    operation_label = _clean_text(
        evidence_item.get("operation"), "operation not recorded"
    )
    source_kind = str(evidence_item.get("source_kind") or source_type).lower()
    source_kind_meta = SOURCE_TYPE_META.get(source_kind, meta)
    project_id = _optional_int(evidence_item.get("project_id"))
    workspace_id = _optional_int(evidence_item.get("workspace_id"))
    redaction_status = _effective_redaction_status(
        evidence_item,
        legacy_missing_redaction_is_none=legacy_missing_redaction_is_none,
    )
    metadata_blocked = redaction_status in {"sensitive_blocked", "unknown"}
    if (
        source_type == "artifact"
        and report_id is not None
        and resolved_artifact_name
        and redaction_status == "none"
    ):
        artifact_href = _artifact_view_href(
            report_id, resolved_artifact_name, line_number
        )
    reference_label = (
        "Proof reference"
        if metadata_blocked
        else ("Artifact reference" if source_type == "artifact" else "Proof reference")
    )
    if metadata_blocked:
        display_source_ref = (
            "Sensitive evidence reference blocked"
            if redaction_status == "sensitive_blocked"
            else "Evidence reference unavailable"
        )
        artifact_label = (
            "sensitive evidence blocked"
            if redaction_status == "sensitive_blocked"
            else "evidence metadata unavailable"
        )
        resource_label = "resource withheld"
        operation_label = "operation withheld"
    return {
        "source_type": source_type,
        "source_icon": meta["icon"],
        "source_label": meta["label"],
        "display_source_ref": display_source_ref,
        "artifact_href": artifact_href,
        "source_system": None
        if metadata_blocked
        else _source_system(source_type, parsed),
        "reference_label": reference_label,
        "artifact_label": artifact_label,
        "resource_label": resource_label,
        "operation_label": operation_label,
        "context_source_label": "unavailable"
        if metadata_blocked
        else source_kind_meta["label"],
        "project_scope_label": "Project withheld"
        if metadata_blocked
        else _scope_label(
            "Project",
            evidence_item.get("project_key"),
            project_id,
        ),
        "workspace_scope_label": "Workspace withheld"
        if metadata_blocked
        else _scope_label(
            "Workspace",
            evidence_item.get("workspace_key"),
            workspace_id,
        ),
        "determinism_label": _clean_text(
            evidence_item.get("determinism_level"),
            "determinism not recorded",
        ),
        "redaction_status": redaction_status,
        "redaction_label": _redaction_label(redaction_status),
        "redaction_explanation": _redaction_explanation(redaction_status),
    }


def _evidence_refs(finding: dict[str, Any]) -> list[str]:
    raw_refs = finding.get("evidence_refs", [])
    if raw_refs is None:
        return []
    if isinstance(raw_refs, str):
        values = _parse_evidence_refs_string(raw_refs)
    elif isinstance(raw_refs, Mapping):
        return []
    else:
        try:
            values = list(raw_refs)
        except TypeError:
            values = [raw_refs]
    refs: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            refs.append(text)
            seen.add(text)
    return refs


def _parse_evidence_refs_string(raw_refs: str) -> list[Any]:
    unparsed = object()
    stripped = raw_refs.strip()
    if not stripped:
        return []
    if stripped[0] in {"[", "{", '"'}:
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = unparsed
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, str):
            return [parsed]
        if isinstance(parsed, Mapping) or parsed is None:
            return []
        if parsed is not unparsed:
            return [parsed]
    if "," in stripped:
        return stripped.split(",")
    return [stripped]


def _evidence_id(evidence_item: dict[str, Any]) -> str:
    evidence_id = evidence_item.get("evidence_id")
    if evidence_id is None:
        return ""
    return str(evidence_id).strip()


def _finding_id(finding: dict[str, Any] | None) -> str:
    if not finding:
        return ""
    finding_id = finding.get("finding_id")
    if finding_id is None:
        return ""
    return str(finding_id).strip()


def _unique_finding_ids(findings: list[dict[str, Any]]) -> set[str]:
    id_counts: dict[str, int] = {}
    for finding in findings:
        finding_id = _finding_id(finding)
        if finding_id:
            id_counts[finding_id] = id_counts.get(finding_id, 0) + 1
    return {finding_id for finding_id, count in id_counts.items() if count == 1}


def _evidence_for_finding(
    finding: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    *,
    fallback_finding_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    refs = set(_evidence_refs(finding))
    matched_by_ref = [
        evidence_item
        for evidence_item in evidence_items
        if _evidence_id(evidence_item) in refs
    ]
    if matched_by_ref:
        return matched_by_ref
    finding_id = _finding_id(finding)
    if not finding_id:
        return []
    if fallback_finding_ids is not None and finding_id not in fallback_finding_ids:
        return []
    return [
        evidence_item
        for evidence_item in evidence_items
        if _finding_id(evidence_item) == finding_id
    ]


def _missing_evidence_refs(
    finding: dict[str, Any],
    matched_evidence: list[dict[str, Any]],
) -> list[str]:
    matched_refs = {_evidence_id(item) for item in matched_evidence}
    return [ref for ref in _evidence_refs(finding) if ref not in matched_refs]


def _is_deterministic_evidence(evidence_item: dict[str, Any]) -> bool:
    determinism_level = str(
        evidence_item.get("determinism_level") or "deterministic"
    ).lower()
    return (
        evidence_item.get("deterministic") is True
        and determinism_level == "deterministic"
    )


def _source_type(evidence_item: dict[str, Any]) -> str:
    return str(evidence_item.get("source_type") or "heuristic").lower()


def _evidence_count_label(count: int, unavailable_count: int = 0) -> str:
    noun = "item" if count == 1 else "items"
    label = f"{count} evidence {noun}"
    if unavailable_count:
        label += f", {_unavailable_evidence_label(unavailable_count)}"
    return label


def _unavailable_evidence_label(count: int) -> str:
    return f"{count} unavailable"


def _evidence_badges(
    finding: dict[str, Any],
    matched_evidence: list[dict[str, Any]],
    missing_evidence_refs: list[str] | None = None,
) -> list[str]:
    badges: list[str] = []
    if any(_is_deterministic_evidence(item) for item in matched_evidence) or (
        not matched_evidence and finding.get("deterministic") is True
    ):
        badges.append("Deterministic")
    if (
        finding.get("deterministic") is not True
        or any(not _is_deterministic_evidence(item) for item in matched_evidence)
        or any(
            _source_type(item) in {"heuristic", "skill"} for item in matched_evidence
        )
    ):
        badges.append("Derived")
    if any(_source_type(item) in EXTERNAL_SOURCE_TYPES for item in matched_evidence):
        badges.append("External")
    if any(
        _source_type(item) in USER_CONTEXT_SOURCE_TYPES for item in matched_evidence
    ):
        badges.append("User context")
    if missing_evidence_refs:
        badges.append(_unavailable_evidence_label(len(missing_evidence_refs)))
    return badges or ["Derived"]


def _evidence_law_label(
    finding: dict[str, Any],
    matched_evidence: list[dict[str, Any]],
) -> str:
    if str(finding.get("severity") or "").lower() not in SEVERE_LEVELS:
        return "Evidence Law not required"
    if any(_is_deterministic_evidence(item) for item in matched_evidence):
        return "Evidence Law satisfied"
    return "Evidence Law needs evidence"


def finding_row_signals(
    finding: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    *,
    fallback_finding_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Build compact row signals for scanning findings before expanding evidence."""
    matched_evidence = _evidence_for_finding(
        finding,
        evidence_items,
        fallback_finding_ids=fallback_finding_ids,
    )
    missing_evidence_refs = _missing_evidence_refs(finding, matched_evidence)
    linked_evidence_count = len(matched_evidence) + len(missing_evidence_refs)
    category = str(finding.get("category") or "").strip() or "uncategorized"
    return {
        "category": category,
        "evidence_count": linked_evidence_count,
        "matched_evidence_count": len(matched_evidence),
        "missing_evidence_count": len(missing_evidence_refs),
        "evidence_count_label": _evidence_count_label(
            len(matched_evidence), len(missing_evidence_refs)
        ),
        "evidence_badges": _evidence_badges(
            finding, matched_evidence, missing_evidence_refs
        ),
        "evidence_law_label": _evidence_law_label(finding, matched_evidence),
    }


def _render_row_signal_badge(label: str) -> None:
    styles = {
        "Deterministic": (
            "rgba(83, 194, 107, 0.12)",
            "#53c26b",
            "rgba(83, 194, 107, 0.35)",
        ),
        "External": (
            "var(--dw-accent-soft)",
            "var(--dw-accent)",
            "var(--dw-accent-line)",
        ),
        "Evidence Law satisfied": (
            "rgba(83, 194, 107, 0.12)",
            "#53c26b",
            "rgba(83, 194, 107, 0.35)",
        ),
        "Evidence Law needs evidence": (
            "rgba(207, 63, 63, 0.12)",
            "#cf3f3f",
            "rgba(207, 63, 63, 0.35)",
        ),
    }
    background, color, border = styles.get(
        label,
        ("rgba(216, 164, 50, 0.12)", "#d8a432", "rgba(216, 164, 50, 0.35)"),
    )
    ui.label(label).classes("text-[11px] font-semibold").style(
        f"background:{background};"
        f"color:{color};"
        f"border:1px solid {border};"
        "border-radius:12px;"
        "padding:4px 10px;"
        "line-height:1.1;"
    )


def _render_inspector_fact(label: str, value: str) -> None:
    ui.label(f"{label} {value}").classes("text-xs dw-muted break-all")


def _render_missing_evidence_notice(missing_refs: list[str]) -> None:
    if not missing_refs:
        return
    ui.label("Evidence unavailable").classes("text-sm font-semibold dw-warning-text")
    ui.label(
        "Linked evidence was not persisted or is unavailable due to sensitive-file "
        "handling. The finding remains tied to safe reference metadata only."
    ).classes("text-xs dw-muted leading-5")
    ref_label = "reference" if len(missing_refs) == 1 else "references"
    ui.label(
        f"Missing evidence refs: {len(missing_refs)} unavailable {ref_label}"
    ).classes("text-xs dw-muted break-all")
    if len(missing_refs) > 3:
        ui.label(
            f"{len(missing_refs)} missing evidence refs summarized without raw "
            "reference values."
        ).classes("text-xs dw-muted")
        _render_inspector_fact("Resource", "resource not recorded")
        _render_inspector_fact("Operation", "operation not recorded")
        _render_inspector_fact("Context source", "unavailable")
        _render_inspector_fact("Project", "not recorded")
        _render_inspector_fact("Workspace", "not recorded")
        _render_inspector_fact("Determinism", "determinism not recorded")
        _render_inspector_fact("Redaction", "Unknown")
        return
    for index, _ in enumerate(missing_refs, start=1):
        _render_inspector_fact("Proof reference", f"unavailable reference {index}")
        _render_inspector_fact("Resource", "resource not recorded")
        _render_inspector_fact("Operation", "operation not recorded")
        _render_inspector_fact("Context source", "unavailable")
        _render_inspector_fact("Project", "not recorded")
        _render_inspector_fact("Workspace", "not recorded")
        _render_inspector_fact("Determinism", "determinism not recorded")
        _render_inspector_fact("Redaction", "Unknown")


def _tool_from_evidence(
    finding: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    *,
    fallback_finding_ids: set[str] | None = None,
) -> str:
    matched = _evidence_for_finding(
        finding,
        evidence_items,
        fallback_finding_ids=fallback_finding_ids,
    )
    if not matched:
        return "unknown"
    source_ref = matched[0].get("source_ref", "")
    return source_ref.split("://", 1)[0] or "unknown"


def _sorted_findings(
    findings: list[dict[str, Any]],
    evidence_items: list[dict[str, Any]],
    *,
    sort_key: str,
) -> list[dict[str, Any]]:
    if sort_key == "confidence":
        return sorted(
            findings,
            key=lambda finding: float(finding.get("confidence", 0.0)),
            reverse=True,
        )
    return sorted(
        findings,
        key=lambda finding: (
            SEVERITY_ORDER.get(str(finding.get("severity", "")).lower(), 99),
            -float(finding.get("confidence", 0.0)),
            str(finding.get("title", "")).lower(),
        ),
    )


def render_findings_table(
    findings: list[dict[str, Any]],
    evidence_items: list[dict[str, Any]],
    *,
    title: str = "Findings",
    artifact_names: list[str] | None = None,
    report_id: int | None = None,
    expanded_finding_ids: set[str] | None = None,
    report_schema_version: str | None = None,
) -> None:
    """Render the findings table with sortable headers and evidence drill-down."""
    register_review_accessibility()
    sort_state = {"key": "severity"}
    requested_expanded_ids: set[str] = set(expanded_finding_ids or ())
    finding_row_keys = {
        id(finding): _finding_row_key(finding, index)
        for index, finding in enumerate(findings)
    }
    fallback_finding_ids = _unique_finding_ids(findings)
    expanded_ids: set[str] = {
        finding_row_keys[id(finding)]
        for finding in findings
        if finding_row_keys[id(finding)] in requested_expanded_ids
        or str(finding.get("finding_id") or "") in requested_expanded_ids
    }
    table_mount = None
    artifact_name_set = set(artifact_names or [])
    legacy_missing_redaction_is_none = _is_legacy_report_schema(report_schema_version)

    def restore_row_focus(evidence_panel_id: str) -> None:
        panel_id_json = json.dumps(evidence_panel_id)
        ui.run_javascript(
            f"""
            const focusRequestId = (window.dwEvidenceFocusRequestId || 0) + 1;
            window.dwEvidenceFocusRequestId = focusRequestId;
            const panelId = {panel_id_json};
            const selector = `[data-dw-finding-row="1"][aria-controls="${{panelId}}"]`;
            if (window.dwRestoreFocusWhenReady) {{
              window.dwRestoreFocusWhenReady({{
                focusRequestId,
                initialActiveElement: document.body,
                selector,
              }});
            }} else {{
              const row = document.querySelector(selector);
              if (row) {{
                row.focus();
              }}
            }}
            """
        )

    def restore_button_focus(evidence_panel_id: str) -> None:
        panel_id_json = json.dumps(evidence_panel_id)
        ui.run_javascript(
            f"""
            const focusRequestId = (window.dwEvidenceFocusRequestId || 0) + 1;
            window.dwEvidenceFocusRequestId = focusRequestId;
            const panelId = {panel_id_json};
            const selector = `[data-dw-evidence-toggle="1"][aria-controls="${{panelId}}"]`;
            if (window.dwRestoreFocusWhenReady) {{
              window.dwRestoreFocusWhenReady({{
                focusRequestId,
                initialActiveElement: document.body,
                selector,
              }});
            }} else {{
              const button = document.querySelector(selector);
              if (button) {{
                button.focus();
              }}
            }}
            """
        )

    def toggle_expanded(
        finding_id: str, evidence_panel_id: str, focus_target: str | None = None
    ) -> None:
        was_expanded = finding_id in expanded_ids
        expanded_ids.clear()
        if not was_expanded:
            expanded_ids.add(finding_id)
        render_rows()
        if focus_target == "row":
            restore_row_focus(evidence_panel_id)
        elif focus_target == "button":
            restore_button_focus(evidence_panel_id)

    def set_sort(sort_key: str) -> None:
        sort_state["key"] = sort_key
        render_rows()

    def render_rows() -> None:
        assert table_mount is not None
        table_mount.clear()
        ordered = _sorted_findings(
            findings,
            evidence_items,
            sort_key=sort_state["key"],
        )
        if len(expanded_ids) > 1:
            ordered_expanded_ids = [
                finding_row_keys[id(finding)]
                for finding in ordered
                if finding_row_keys[id(finding)] in expanded_ids
            ]
            expanded_ids.clear()
            if ordered_expanded_ids:
                expanded_ids.add(ordered_expanded_ids[0])
        with table_mount:
            with ui.element("div").classes(
                "w-full dw-findings-grid dw-findings-header px-3 py-3"
            ):
                ui.label("Severity").classes("dw-findings-col dw-findings-col-severity")
                ui.label("Title").classes("dw-findings-col dw-findings-col-title")
                ui.label("Tool").classes("dw-findings-col dw-findings-col-tool")
                ui.label("Evidence").classes("dw-findings-col dw-findings-col-evidence")
                sort_confidence = (
                    "Confidence ↓"
                    if sort_state["key"] == "confidence"
                    else "Confidence"
                )
                ui.button(
                    sort_confidence,
                    on_click=lambda: set_sort("confidence"),
                ).props("flat dense no-caps").classes(
                    "dw-findings-col dw-findings-col-confidence px-0 text-xs dw-muted"
                )
                sort_severity = (
                    "Severity ↓" if sort_state["key"] == "severity" else "Sort severity"
                )
                ui.button(
                    sort_severity,
                    on_click=lambda: set_sort("severity"),
                ).props("flat dense no-caps").classes(
                    "dw-findings-col dw-findings-col-actions px-0 text-xs dw-muted"
                )
            if not ordered:
                with ui.card().classes("w-full dw-panel-soft shadow-none"):
                    ui.label("No findings were persisted for this report.").classes(
                        "p-4 text-sm dw-muted"
                    )
                return

            for index, finding in enumerate(ordered):
                row_key = finding_row_keys[id(finding)]
                matched_evidence = _evidence_for_finding(
                    finding,
                    evidence_items,
                    fallback_finding_ids=fallback_finding_ids,
                )
                missing_evidence_refs = _missing_evidence_refs(
                    finding, matched_evidence
                )
                row_signals = finding_row_signals(
                    finding,
                    evidence_items,
                    fallback_finding_ids=fallback_finding_ids,
                )
                tool = _tool_from_evidence(
                    finding,
                    evidence_items,
                    fallback_finding_ids=fallback_finding_ids,
                )
                evidence_panel_id = _safe_dom_id("evidence-inspector", row_key)
                safe_finding_title = _safe_prop_value(finding["title"])
                safe_evidence_panel_id = _safe_prop_value(evidence_panel_id)
                row_classes = "w-full dw-findings-row shadow-none dw-findings-row-card"
                row_classes += (
                    " dw-findings-row-alt" if index % 2 else " dw-findings-row-base"
                )
                with ui.card().classes(row_classes) as row_card:
                    row_card.props(
                        "tabindex=0 "
                        'data-dw-finding-row="1" '
                        f"aria-expanded={'true' if row_key in expanded_ids else 'false'} "
                        f'aria-controls={safe_evidence_panel_id} aria-label="Finding {safe_finding_title}"'
                    )
                    row_card.classes("dw-finding-row")
                    row_card.on(
                        "click",
                        lambda _=None, fid=row_key, panel_id=evidence_panel_id: (
                            toggle_expanded(fid, panel_id)
                        ),
                    )
                    row_card.on(
                        "dw-key-toggle",
                        lambda _=None, fid=row_key, panel_id=evidence_panel_id: (
                            toggle_expanded(fid, panel_id, "row")
                        ),
                    )
                    with ui.element("div").classes(
                        "w-full dw-findings-grid dw-findings-row-layout p-3"
                    ):
                        with ui.column().classes(
                            "dw-findings-col dw-findings-col-severity gap-2"
                        ):
                            render_risk_badge(finding["severity"])
                            render_determinism_badge(bool(finding.get("deterministic")))
                        with ui.column().classes(
                            "dw-findings-col dw-findings-col-title min-w-0 flex-1 gap-1"
                        ):
                            ui.label(finding["title"]).classes(
                                "text-sm font-medium dw-text"
                            )
                            ui.label(finding["description"]).classes(
                                "text-xs dw-muted leading-5"
                            )
                            ui.label(row_signals["category"]).classes(
                                "text-xs dw-muted"
                            )
                            if finding.get("uncertainty_note"):
                                ui.label(finding["uncertainty_note"]).classes(
                                    "text-xs dw-warning-text"
                                )
                        ui.label(tool).classes(
                            "dw-findings-col dw-findings-col-tool text-xs uppercase dw-muted"
                        )
                        with ui.column().classes(
                            "dw-findings-col dw-findings-col-evidence items-start gap-1"
                        ):
                            ui.label(row_signals["evidence_count_label"]).classes(
                                "text-sm font-semibold dw-text normal-case"
                            )
                            with ui.row().classes("gap-1 flex-wrap"):
                                for badge in row_signals["evidence_badges"]:
                                    _render_row_signal_badge(badge)
                            _render_row_signal_badge(row_signals["evidence_law_label"])
                        with ui.column().classes(
                            "dw-findings-col dw-findings-col-confidence items-start gap-1"
                        ):
                            render_confidence_badge(float(finding["confidence"]))
                        with ui.column().classes(
                            "dw-findings-col dw-findings-col-actions items-end gap-2"
                        ):
                            button_label = (
                                "Hide evidence"
                                if row_key in expanded_ids
                                else "View evidence"
                            )
                            ui.button(
                                button_label,
                                on_click=lambda fid=row_key, panel_id=evidence_panel_id: (
                                    toggle_expanded(fid, panel_id, "button")
                                ),
                            ).props(
                                "outline dense no-caps "
                                'data-dw-evidence-toggle="1" '
                                f"aria-controls={safe_evidence_panel_id} "
                                f"aria-expanded={'true' if row_key in expanded_ids else 'false'}"
                            ).on("click.stop", lambda *_: None)
                    if row_key in expanded_ids:
                        with ui.column().classes(
                            "w-full gap-2 px-3 pb-3 pt-0 border-t border-[color:var(--dw-line)]"
                        ) as evidence_panel:
                            evidence_panel.props(
                                f'id={safe_evidence_panel_id} data-dw-evidence-inspector="1"'
                            )
                            evidence_panel.on("click.stop", lambda *_: None)
                            decorate_review_section(
                                evidence_panel,
                                section="evidence",
                                label=f"Evidence inspector for {finding['title']}",
                            )
                            ui.label("Evidence inspector").classes(
                                "text-sm font-semibold dw-text mt-2"
                            )
                            _render_missing_evidence_notice(missing_evidence_refs)
                            if not matched_evidence and not missing_evidence_refs:
                                ui.label(
                                    "No evidence items are linked to this finding."
                                ).classes("text-xs dw-muted")
                            for evidence_item in matched_evidence:
                                descriptor = describe_evidence_item(
                                    evidence_item,
                                    artifact_names=artifact_name_set,
                                    report_id=report_id,
                                    legacy_missing_redaction_is_none=legacy_missing_redaction_is_none,
                                )
                                with ui.card().classes(
                                    "w-full dw-panel-soft shadow-none"
                                ):
                                    with ui.column().classes("gap-2 p-3"):
                                        with ui.row().classes(
                                            "items-center gap-2 flex-wrap"
                                        ):
                                            ui.icon(descriptor["source_icon"]).classes(
                                                "text-base dw-muted"
                                            )
                                            ui.label(
                                                descriptor["source_label"]
                                            ).classes(
                                                "text-xs font-semibold uppercase tracking-[0.08em] dw-muted"
                                            )
                                            render_risk_badge(
                                                evidence_item["severity_hint"],
                                                f"{str(evidence_item['severity_hint']).upper()} HINT",
                                            )
                                            render_determinism_badge(
                                                bool(evidence_item["deterministic"])
                                            )
                                            if descriptor["source_system"]:
                                                ui.label(
                                                    f"SYSTEM: {descriptor['source_system']}"
                                                ).classes(
                                                    "text-[11px] font-semibold uppercase tracking-[0.08em] dw-accent-text"
                                                ).style(
                                                    "background:var(--dw-accent-soft);"
                                                    "border:1px solid var(--dw-accent-line);"
                                                    "border-radius:12px;"
                                                    "padding:4px 10px;"
                                                )
                                        if not _can_render_evidence_summary(
                                            descriptor["redaction_status"]
                                        ):
                                            ui.label(
                                                "Evidence content unavailable"
                                            ).classes("text-sm font-medium dw-text")
                                        else:
                                            ui.label(evidence_item["summary"]).classes(
                                                "text-sm font-medium dw-text"
                                            )
                                        if descriptor["artifact_href"]:
                                            ui.link(
                                                descriptor["display_source_ref"],
                                                descriptor["artifact_href"],
                                            ).classes(
                                                "text-xs dw-accent-text break-all"
                                            )
                                        else:
                                            ui.label(
                                                descriptor["display_source_ref"]
                                            ).classes("text-xs dw-muted break-all")
                                        _render_inspector_fact(
                                            descriptor["reference_label"],
                                            descriptor["artifact_label"],
                                        )
                                        _render_inspector_fact(
                                            "Resource",
                                            descriptor["resource_label"],
                                        )
                                        _render_inspector_fact(
                                            "Operation",
                                            descriptor["operation_label"],
                                        )
                                        _render_inspector_fact(
                                            "Context source",
                                            descriptor["context_source_label"],
                                        )
                                        _render_inspector_fact(
                                            "Project",
                                            descriptor[
                                                "project_scope_label"
                                            ].removeprefix("Project "),
                                        )
                                        _render_inspector_fact(
                                            "Workspace",
                                            descriptor[
                                                "workspace_scope_label"
                                            ].removeprefix("Workspace "),
                                        )
                                        _render_inspector_fact(
                                            "Determinism",
                                            descriptor["determinism_label"],
                                        )
                                        _render_inspector_fact(
                                            "Redaction",
                                            descriptor["redaction_label"],
                                        )
                                        if descriptor["redaction_status"] != "none":
                                            ui.label(
                                                descriptor["redaction_explanation"]
                                            ).classes(
                                                "text-xs dw-warning-text leading-5"
                                            )
                                        ui.label(
                                            f"{descriptor['source_label']} · confidence {float(evidence_item['confidence']):.2f}"
                                        ).classes("text-xs dw-muted")

    with ui.card().classes("w-full dw-panel shadow-none p-4") as findings_card:
        findings_card.props('data-dw-findings-table="1"')
        decorate_review_section(findings_card, section="findings", label=title)
        with ui.row().classes("w-full items-center justify-between gap-3 flex-wrap"):
            ui.label(title).classes("text-lg font-medium dw-text")
            ui.label(
                "Severity, evidence count, confidence, and deterministic status stay visible while evidence expands inline."
            ).classes("text-xs dw-muted")
        table_mount = ui.column().classes("w-full gap-2")
        table_mount.props('data-dw-findings-table="1"')
        render_rows()
