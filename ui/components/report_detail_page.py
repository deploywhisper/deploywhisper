"""Full-page report detail rendering."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from nicegui import ui

from analysis.blast_radius import BlastRadiusResult
from analysis.rollback_planner import RollbackPlan
from ui.components.blast_radius_graph import render_blast_radius_panel
from ui.components.context_completeness_panel import (
    render_context_completeness_panel,
)
from ui.components.findings_table import render_findings_table
from ui.components.review_accessibility import decorate_review_section
from ui.components.rollback_plan import render_rollback_plan
from ui.formatters.datetime import format_history_timestamp
from ui.formatters.narrative import extract_llm_notice
from ui.formatters.recommendations import render_recommendation_label
from ui.formatters.risk_labels import render_risk_badge


def _detail_stat(label: str, value: str, detail: str) -> None:
    with ui.card().classes("dw-panel-soft shadow-none min-w-[180px] flex-1"):
        with ui.column().classes("gap-1 p-3"):
            ui.label(label).classes(
                "text-[11px] font-semibold uppercase tracking-[0.08em] dw-muted"
            )
            ui.label(value).classes("text-lg font-semibold dw-text")
            ui.label(detail).classes("text-xs dw-muted leading-5")


def _render_summary_and_advisory(report: dict[str, Any]) -> None:
    llm_notice = extract_llm_notice(
        report.get("warnings", []),
        report.get("narrative_failure_notice"),
    )
    with ui.card().classes("w-full dw-panel shadow-none p-5"):
        with ui.column().classes("gap-4"):
            with ui.row().classes("w-full gap-4 flex-wrap"):
                with ui.card().classes(
                    "dw-panel-soft shadow-none min-w-[280px] flex-1"
                ):
                    with ui.column().classes("gap-2 p-4"):
                        ui.label("Description").classes("text-sm font-semibold dw-text")
                        ui.label(report["top_risk"]).classes(
                            "text-base font-semibold dw-text leading-6"
                        )
                        ui.label(report["parse_summary"]).classes(
                            "text-sm dw-muted leading-6"
                        )
                with ui.card().classes(
                    "dw-panel-soft shadow-none min-w-[280px] flex-1"
                ):
                    with ui.column().classes("gap-2 p-4"):
                        ui.label("Advisory").classes("text-sm font-semibold dw-text")
                        if report.get("narrative_available", True):
                            ui.label(report["narrative_opening"]).classes(
                                "text-sm dw-text leading-6"
                            )
                        else:
                            ui.label(
                                "Narrative unavailable. Review the deterministic analysis below."
                            ).classes("text-sm dw-warning-text leading-6")
            if llm_notice:
                with ui.card().classes("dw-panel-soft shadow-none"):
                    ui.label("LLM note: " + llm_notice).classes(
                        "p-4 text-sm dw-warning-text leading-6"
                    )


def _render_resource_breakdown(report: dict[str, Any]) -> None:
    contributors = report.get("contributors", [])
    with ui.card().classes("w-full dw-panel shadow-none p-5"):
        with ui.column().classes("gap-3"):
            ui.label("Resource severity breakdown").classes(
                "text-lg font-medium dw-text"
            )
            if not contributors:
                ui.label(
                    "No resource-level severity breakdown was stored for this report."
                ).classes("text-sm dw-muted")
                return
            for contributor in contributors:
                with ui.card().classes(
                    "w-full dw-panel-soft shadow-none dw-detail-list-row"
                ):
                    with ui.row().classes(
                        "w-full items-start justify-between gap-3 p-4 flex-wrap"
                    ):
                        with ui.column().classes("min-w-0 flex-1 gap-1"):
                            ui.label(contributor["resource_id"]).classes(
                                "text-sm font-semibold dw-text"
                            )
                            ui.label(
                                f"{contributor['resource_category']} · {contributor['normalized_action']} · "
                                f"{contributor['environment']} · scope {contributor['downstream_scope']}"
                            ).classes("text-xs dw-muted")
                            ui.label(contributor["reasoning"]).classes(
                                "text-sm dw-muted leading-6"
                            )
                            for security_flag in contributor.get("security_flags", []):
                                ui.label(security_flag).classes(
                                    "text-xs dw-danger-text"
                                )
                        render_risk_badge(contributor["severity"])


def _render_audit_metadata(report: dict[str, Any]) -> None:
    audit = report.get("audit", {})
    provider_value = audit.get("llm_provider") or report.get("narrative_provider")
    trigger_value = audit.get("trigger_type") or "unknown"
    if audit.get("trigger_id"):
        trigger_value += f" · {audit['trigger_id']}"

    with ui.card().classes("w-full dw-panel shadow-none p-5"):
        with ui.column().classes("gap-4"):
            ui.label("Audit metadata").classes("text-lg font-medium dw-text")
            with ui.row().classes("w-full gap-3 flex-wrap"):
                _detail_stat(
                    "Interface",
                    str(audit.get("source_interface") or "unknown").upper(),
                    "Where the report was generated from.",
                )
                _detail_stat(
                    "Provider",
                    str(provider_value or "unknown"),
                    "LLM provider recorded in the persisted audit metadata.",
                )
                _detail_stat(
                    "Trigger",
                    trigger_value,
                    "Workflow entrypoint that created this report.",
                )
                _detail_stat(
                    "Files analyzed",
                    str(len(audit.get("files_analyzed") or [])),
                    "Artifacts included in the persisted parse batch.",
                )
            with ui.row().classes("w-full gap-3 flex-wrap"):
                _detail_stat(
                    "Risk scoring",
                    str(report.get("assessment_source") or "unknown"),
                    "Source used to score the deployment risk.",
                )
                _detail_stat(
                    "Narrative source",
                    str(report.get("narrative_source") or "unknown"),
                    "Source used to generate the advisory text.",
                )
                _detail_stat(
                    "Model",
                    str(report.get("narrative_model") or "unknown"),
                    "Model recorded for the narrative generation path.",
                )
                _detail_stat(
                    "Schema",
                    str(report.get("report_schema_version") or "unknown").upper(),
                    "Persisted report contract version.",
                )
            if report.get("skills_applied"):
                ui.label(
                    "Skills applied: " + ", ".join(report["skills_applied"])
                ).classes("text-sm dw-muted")
            files_analyzed = audit.get("files_analyzed") or []
            with ui.column().classes("gap-2"):
                ui.label("Files analyzed").classes("text-sm font-semibold dw-text")
                if files_analyzed:
                    for file_name in files_analyzed:
                        ui.link(
                            file_name,
                            f"/history/{report['id']}/artifacts?{urlencode({'name': file_name})}",
                        ).classes("text-sm dw-accent-text break-all")
                else:
                    ui.label(
                        "No analyzed files were persisted for this report."
                    ).classes("text-sm dw-muted")


def render_report_detail_page(report: dict[str, Any]) -> None:
    """Render one report as a dedicated, single-column detail page."""
    findings = report.get("findings", [])
    evidence_items = report.get("evidence_items", [])
    artifact_names = list(report.get("audit", {}).get("files_analyzed", []))
    context = report.get("context_completeness") or {}
    blast_radius = report.get("blast_radius") or {}
    rollback_plan = report.get("rollback_plan") or {}

    with ui.card().classes("w-full dw-panel shadow-none p-6") as header_card:
        decorate_review_section(header_card, section="verdict", label="Report header")
        with ui.column().classes("gap-4"):
            with ui.row().classes("w-full items-start justify-between gap-4 flex-wrap"):
                with ui.column().classes("gap-3 min-w-0 flex-1"):
                    ui.label("Analysis report").classes("dw-eyebrow")
                    with ui.row().classes("items-center gap-3 flex-wrap"):
                        render_risk_badge(report["severity"])
                        render_recommendation_label(
                            report["recommendation"], size="base"
                        )
                        ui.label(
                            format_history_timestamp(report["created_at"])
                        ).classes("text-sm dw-muted")
                    ui.label(report["top_risk"]).classes(
                        "text-2xl font-semibold dw-text leading-tight"
                    )
                    ui.label(
                        "Full advisory context for the saved deployment report, including evidence, context quality, blast radius, and rollback guidance."
                    ).classes("text-sm dw-muted leading-6")
                with ui.column().classes("dw-report-score-block shrink-0 gap-1"):
                    ui.label(str(report.get("risk_score", "—"))).classes(
                        "dw-verdict-score-value"
                    )
                    ui.label("Risk score").classes("dw-verdict-score-label")
            with ui.row().classes("w-full gap-3 flex-wrap"):
                _detail_stat(
                    "Severity",
                    str(report["severity"]).upper(),
                    "Highest persisted risk level for this report.",
                )
                _detail_stat(
                    "Recommendation",
                    str(report["recommendation"]).upper(),
                    "Advisory release recommendation captured with the report.",
                )
                _detail_stat(
                    "Created",
                    format_history_timestamp(report["created_at"]),
                    "Timestamp of the persisted report.",
                )
                _detail_stat(
                    "Schema",
                    str(report.get("report_schema_version") or "unknown").upper(),
                    "Persisted report payload contract version.",
                )

    _render_summary_and_advisory(report)
    render_findings_table(
        findings,
        evidence_items,
        title="Findings table",
        artifact_names=artifact_names,
        report_id=int(report["id"]),
    )
    render_context_completeness_panel(context)
    if (
        blast_radius.get("affected")
        or blast_radius.get("warning")
        or blast_radius.get("direct_count", 0)
        or blast_radius.get("transitive_count", 0)
    ):
        render_blast_radius_panel(
            BlastRadiusResult.model_validate(blast_radius),
            severity=str(report["severity"]),
        )
    else:
        with ui.card().classes("w-full dw-panel shadow-none p-5") as blast_card:
            decorate_review_section(
                blast_card, section="blast-radius", label="Blast radius"
            )
            ui.label("Blast radius").classes("text-lg font-medium dw-text")
            ui.label("No blast radius data was persisted for this report.").classes(
                "text-sm dw-muted"
            )
    if rollback_plan.get("steps") or rollback_plan.get("warning"):
        render_rollback_plan(RollbackPlan.model_validate(rollback_plan))
    else:
        with ui.card().classes("w-full dw-panel shadow-none p-5") as rollback_card:
            decorate_review_section(
                rollback_card, section="rollback", label="Rollback plan"
            )
            ui.label("Rollback plan").classes("text-lg font-medium dw-text")
            ui.label("No rollback plan was persisted for this report.").classes(
                "text-sm dw-muted"
            )
    _render_resource_breakdown(report)
    _render_audit_metadata(report)
