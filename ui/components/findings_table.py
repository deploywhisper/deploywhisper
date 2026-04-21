"""Findings table with evidence drill-down."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from ui.formatters.confidence import render_confidence_badge
from ui.formatters.determinism import render_determinism_badge
from ui.formatters.risk_labels import render_risk_badge

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


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
) -> None:
    """Render the findings table with sortable headers and evidence drill-down."""
    sort_state = {"key": "severity"}
    expanded_ids: set[str] = set()
    table_mount = ui.column().classes("w-full gap-2")

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
        table_mount.clear()
        ordered = _sorted_findings(
            findings,
            evidence_items,
            sort_key=sort_state["key"],
        )
        with table_mount:
            with ui.row().classes(
                "w-full items-center gap-3 flex-wrap px-3 py-2 border-b border-[color:var(--dw-line)]"
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

            for finding in ordered:
                finding_id = str(finding["finding_id"])
                matched_evidence = _evidence_for_finding(finding, evidence_items)
                tool = _tool_from_evidence(finding, evidence_items)
                with ui.card().classes(
                    "w-full dw-panel-soft dw-findings-row shadow-none"
                ) as row_card:
                    row_card.on(
                        "click",
                        lambda _=None, fid=finding_id: toggle_expanded(fid),
                    )
                    with ui.row().classes("w-full items-start gap-3 p-3 flex-wrap"):
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
                            ).props("outline dense no-caps").on(
                                "click.stop", lambda *_: None
                            )
                    if finding_id in expanded_ids:
                        with ui.column().classes(
                            "w-full gap-2 px-3 pb-3 pt-0 border-t border-[color:var(--dw-line)]"
                        ):
                            ui.label("Evidence inspector").classes(
                                "text-sm font-semibold dw-text mt-2"
                            )
                            if not matched_evidence:
                                ui.label(
                                    "No evidence items are linked to this finding."
                                ).classes("text-xs dw-muted")
                            for evidence_item in matched_evidence:
                                with ui.card().classes(
                                    "w-full dw-panel-soft shadow-none"
                                ):
                                    with ui.column().classes("gap-1 p-3"):
                                        ui.label(evidence_item["summary"]).classes(
                                            "text-sm font-medium dw-text"
                                        )
                                        ui.label(evidence_item["source_ref"]).classes(
                                            "text-xs dw-muted break-all"
                                        )
                                        ui.label(
                                            f"{evidence_item['source_type']} · {evidence_item['severity_hint']} · confidence {float(evidence_item['confidence']):.2f}"
                                        ).classes("text-xs dw-muted")

    with ui.card().classes("w-full dw-panel shadow-none p-4"):
        with ui.row().classes("w-full items-center justify-between gap-3 flex-wrap"):
            ui.label(title).classes("text-lg font-medium dw-text")
            ui.label(
                "Severity, evidence count, confidence, and deterministic status stay visible while evidence expands inline."
            ).classes("text-xs dw-muted")
        render_rows()
