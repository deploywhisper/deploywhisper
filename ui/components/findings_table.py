"""Findings table with evidence drill-down."""

from __future__ import annotations

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
    if source_type == "artifact" and report_id is not None and resolved_artifact_name:
        artifact_href = _artifact_view_href(
            report_id, resolved_artifact_name, line_number
        )
    return {
        "source_type": source_type,
        "source_icon": meta["icon"],
        "source_label": meta["label"],
        "display_source_ref": display_source_ref,
        "artifact_href": artifact_href,
        "source_system": _source_system(source_type, parsed),
    }


def _evidence_for_finding(
    finding: dict[str, Any], evidence_items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    refs = set(finding.get("evidence_refs", []))
    return [
        evidence_item
        for evidence_item in evidence_items
        if evidence_item.get("evidence_id") in refs
    ]


def _tool_from_evidence(
    finding: dict[str, Any], evidence_items: list[dict[str, Any]]
) -> str:
    matched = _evidence_for_finding(finding, evidence_items)
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
) -> None:
    """Render the findings table with sortable headers and evidence drill-down."""
    register_review_accessibility()
    sort_state = {"key": "severity"}
    expanded_ids: set[str] = set(expanded_finding_ids or ())
    table_mount = None
    artifact_name_set = set(artifact_names or [])

    def toggle_expanded(finding_id: str) -> None:
        if finding_id in expanded_ids:
            expanded_ids.remove(finding_id)
        else:
            expanded_ids.add(finding_id)
        render_rows()

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
                finding_id = str(finding["finding_id"])
                matched_evidence = _evidence_for_finding(finding, evidence_items)
                tool = _tool_from_evidence(finding, evidence_items)
                evidence_panel_id = f"evidence-inspector-{finding_id}"
                row_classes = "w-full dw-findings-row shadow-none dw-findings-row-card"
                row_classes += (
                    " dw-findings-row-alt" if index % 2 else " dw-findings-row-base"
                )
                with ui.card().classes(row_classes) as row_card:
                    row_card.props(
                        "tabindex=0 "
                        'data-dw-finding-row="1" '
                        f"aria-expanded={'true' if finding_id in expanded_ids else 'false'} "
                        f'aria-controls={evidence_panel_id} aria-label="Finding {finding["title"]}"'
                    )
                    row_card.classes("dw-finding-row")
                    row_card.on(
                        "click",
                        lambda _=None, fid=finding_id: toggle_expanded(fid),
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
                            if finding.get("uncertainty_note"):
                                ui.label(finding["uncertainty_note"]).classes(
                                    "text-xs dw-warning-text"
                                )
                        ui.label(tool).classes(
                            "dw-findings-col dw-findings-col-tool text-xs uppercase dw-muted"
                        )
                        ui.label(str(len(matched_evidence))).classes(
                            "dw-findings-col dw-findings-col-evidence text-sm font-semibold dw-text"
                        )
                        with ui.column().classes(
                            "dw-findings-col dw-findings-col-confidence items-start gap-1"
                        ):
                            render_confidence_badge(float(finding["confidence"]))
                        with ui.column().classes(
                            "dw-findings-col dw-findings-col-actions items-end gap-2"
                        ):
                            button_label = (
                                "Hide evidence"
                                if finding_id in expanded_ids
                                else "View evidence"
                            )
                            ui.button(
                                button_label,
                                on_click=lambda fid=finding_id: toggle_expanded(fid),
                            ).props(
                                "outline dense no-caps "
                                f"aria-controls={evidence_panel_id} "
                                f"aria-expanded={'true' if finding_id in expanded_ids else 'false'}"
                            ).on("click.stop", lambda *_: None)
                    if finding_id in expanded_ids:
                        with ui.column().classes(
                            "w-full gap-2 px-3 pb-3 pt-0 border-t border-[color:var(--dw-line)]"
                        ) as evidence_panel:
                            evidence_panel.props(
                                f'id={evidence_panel_id} data-dw-evidence-inspector="1"'
                            )
                            decorate_review_section(
                                evidence_panel,
                                section="evidence",
                                label="Evidence inspector",
                            )
                            ui.label("Evidence inspector").classes(
                                "text-sm font-semibold dw-text mt-2"
                            )
                            if not matched_evidence:
                                ui.label(
                                    "No evidence items are linked to this finding."
                                ).classes("text-xs dw-muted")
                            for evidence_item in matched_evidence:
                                descriptor = describe_evidence_item(
                                    evidence_item,
                                    artifact_names=artifact_name_set,
                                    report_id=report_id,
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
