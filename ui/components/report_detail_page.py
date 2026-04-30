"""Full-page report detail rendering."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from nicegui import ui

from analysis.blast_radius import BlastRadiusResult
from analysis.rollback_planner import RollbackPlan
from services.feedback_service import (
    FeedbackError,
    fetch_report_feedback_state,
    record_false_negative_feedback,
    record_finding_feedback,
)
from ui.components.blast_radius_graph import render_blast_radius_panel
from ui.components.context_completeness_panel import (
    render_context_completeness_panel,
)
from ui.components.findings_table import render_findings_table
from ui.components.review_accessibility import decorate_review_section
from ui.components.rollback_plan import render_rollback_plan
from ui.components.topology_freshness_banner import render_topology_freshness_banner
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


def _primary_contributor(report: dict[str, Any]) -> dict[str, Any] | None:
    contributors = [
        contributor
        for contributor in report.get("contributors", [])
        if isinstance(contributor, dict)
    ]
    if not contributors:
        return None
    return max(
        contributors,
        key=lambda contributor: (
            int(contributor.get("contribution") or 0),
            str(contributor.get("resource_id") or ""),
        ),
    )


def _primary_finding(report: dict[str, Any]) -> dict[str, Any] | None:
    findings = [
        finding for finding in report.get("findings", []) if isinstance(finding, dict)
    ]
    if not findings:
        return None
    severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    return max(
        findings,
        key=lambda finding: (
            severity_order.get(str(finding.get("severity") or "").lower(), 0),
            float(finding.get("confidence") or 0.0),
            str(finding.get("title") or ""),
        ),
    )


def _evidence_for_finding(
    report: dict[str, Any], finding: dict[str, Any] | None
) -> dict[str, Any] | None:
    evidence_items = [
        item for item in report.get("evidence_items", []) if isinstance(item, dict)
    ]
    if not evidence_items:
        return None
    evidence_refs = set(finding.get("evidence_refs") or []) if finding else set()
    if evidence_refs:
        for item in evidence_items:
            if item.get("evidence_id") in evidence_refs:
                return item
    return evidence_items[0]


def _tool_label(value: object) -> str:
    text = str(value or "deployment artifact").strip()
    return text.upper() if len(text) <= 4 else text.title()


def _operational_narrative_items(report: dict[str, Any]) -> list[tuple[str, str]]:
    contributor = _primary_contributor(report)
    finding = _primary_finding(report)
    evidence = _evidence_for_finding(report, finding)
    rollback_plan = report.get("rollback_plan") or {}
    rollback_steps = [
        step for step in rollback_plan.get("steps", []) if isinstance(step, dict)
    ]
    critical_step = next(
        (step for step in rollback_steps if step.get("critical")),
        rollback_steps[0] if rollback_steps else None,
    )

    if contributor:
        resource_id = str(contributor.get("resource_id") or "unknown resource")
        source_file = str(contributor.get("source_file") or "unknown file")
        action = str(
            contributor.get("normalized_action")
            or contributor.get("action")
            or "change"
        )
        what_changed = (
            f"{_tool_label(contributor.get('tool'))} {action} on {resource_id} "
            f"from {source_file}: {contributor.get('summary') or report['top_risk']}"
        )
        exact_resource = (
            f"Resource {resource_id} in {source_file}; category "
            f"{contributor.get('resource_category') or 'unknown'}."
        )
        if evidence and evidence.get("source_ref"):
            exact_resource += f" Evidence reference: {evidence['source_ref']}."
    else:
        what_changed = str(report.get("parse_summary") or report.get("top_risk") or "")
        exact_resource = "Review the findings table for the exact parsed resource and artifact references."

    why_risky = (
        str(report.get("narrative_explanation") or "").strip()
        or str(contributor.get("reasoning") if contributor else "").strip()
        or str(finding.get("description") if finding else "").strip()
        or str(report.get("top_risk") or "")
    )

    security_flags = (
        list(contributor.get("security_flags") or []) if contributor else []
    )
    if security_flags:
        verify_before_deploy = "Verify before deploy: " + "; ".join(
            str(flag) for flag in security_flags[:2]
        )
    elif evidence:
        verify_before_deploy = (
            f"Verify before deploy: confirm {evidence.get('summary') or 'the top evidence item'} "
            "is expected and approved."
        )
    elif finding:
        verify_before_deploy = (
            f"Verify before deploy: review {finding.get('title') or 'the top finding'} "
            "with the owning engineer."
        )
    else:
        verify_before_deploy = "Verify before deploy: confirm the parsed change list matches the intended release."

    if rollback_plan.get("warning"):
        rollback_concern = str(rollback_plan["warning"])
    elif critical_step:
        rollback_concern = (
            f"{rollback_plan.get('complexity_score', 1)}/5 "
            f"{str(rollback_plan.get('complexity', 'low')).upper()} rollback. "
            f"First concern: {critical_step.get('title') or 'rollback step'} - "
            f"{critical_step.get('detail') or 'verify the prior stable state can be restored.'}"
        )
    else:
        rollback_concern = "No rollback concern was generated for this report."

    return [
        ("What changed?", what_changed),
        ("Why is it risky?", why_risky),
        ("Exact resource/file", exact_resource),
        ("Verify before deploying", verify_before_deploy),
        ("Rollback concern", rollback_concern),
    ]


def _render_operational_narrative(report: dict[str, Any]) -> None:
    with ui.card().classes("w-full dw-panel shadow-none p-5"):
        with ui.column().classes("gap-4"):
            with ui.column().classes("gap-1"):
                ui.label("Operational narrative").classes("text-lg font-medium dw-text")
                ui.label(
                    "A release-review view of the LLM briefing, grounded in the parsed evidence and rollback plan."
                ).classes("text-sm dw-muted leading-6")
            for label, value in _operational_narrative_items(report):
                with ui.element("div").classes(
                    "w-full border-t border-[color:var(--dw-border)] pt-3"
                ):
                    ui.label(label).classes(
                        "text-[11px] font-semibold uppercase tracking-[0.08em] dw-muted"
                    )
                    ui.label(value).classes("mt-1 text-sm dw-text leading-6")


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


def render_reviewer_feedback_panel(
    report: dict[str, Any],
    *,
    on_feedback_change=None,
) -> None:
    feedback_state = fetch_report_feedback_state(int(report["id"]))
    latest_finding_feedback = feedback_state["finding_feedback"]
    latest_false_negative = (
        feedback_state["false_negative_notes"][0]
        if feedback_state["false_negative_notes"]
        else None
    )

    def submit_finding_feedback(
        *,
        finding_id: str,
        useful: bool,
        false_positive_flag: bool = False,
        reason_input=None,
    ) -> None:
        try:
            record_finding_feedback(
                analysis_id=int(report["id"]),
                finding_id=finding_id,
                useful=useful,
                false_positive_flag=false_positive_flag,
                false_positive_reason=(
                    reason_input.value if reason_input is not None else None
                ),
            )
        except FeedbackError as exc:
            ui.notify(str(exc), color="warning")
            return
        ui.notify("Reviewer feedback saved.", color="positive")
        if on_feedback_change is not None:
            on_feedback_change()

    def submit_false_negative(note_input) -> None:
        try:
            record_false_negative_feedback(
                analysis_id=int(report["id"]),
                note=note_input.value,
            )
        except FeedbackError as exc:
            ui.notify(str(exc), color="warning")
            return
        ui.notify("Missed-finding note saved.", color="positive")
        if on_feedback_change is not None:
            on_feedback_change()

    with ui.card().classes("w-full dw-panel shadow-none p-5") as feedback_card:
        decorate_review_section(
            feedback_card,
            section="feedback",
            label="Reviewer feedback",
        )
        with ui.column().classes("gap-4"):
            with ui.column().classes("gap-1"):
                ui.label("Reviewer feedback").classes("text-lg font-medium dw-text")
                ui.label(
                    "Capture whether each finding was useful, flag false positives with a reason, and record anything the report missed."
                ).classes("text-sm dw-muted leading-6")
            for finding in report.get("findings", []):
                finding_id = str(finding["finding_id"])
                current_feedback = latest_finding_feedback.get(finding_id)
                with ui.card().classes("w-full dw-panel-soft shadow-none"):
                    with ui.column().classes("gap-3 p-4"):
                        ui.label(finding["title"]).classes(
                            "text-sm font-semibold dw-text"
                        )
                        if current_feedback is not None:
                            status_bits = []
                            if current_feedback.get("useful") is True:
                                status_bits.append("Latest vote: useful")
                            elif current_feedback.get("useful") is False:
                                status_bits.append("Latest vote: not useful")
                            if current_feedback.get("false_positive_flag"):
                                status_bits.append("Marked false positive")
                            ui.label(" · ".join(status_bits)).classes(
                                "text-xs dw-muted"
                            )
                        with ui.row().classes("w-full gap-3 flex-wrap"):
                            ui.button(
                                "Thumbs up",
                                on_click=lambda fid=finding_id: submit_finding_feedback(
                                    finding_id=fid,
                                    useful=True,
                                ),
                            ).props("outline no-caps").classes("dw-theme-button")
                            ui.button(
                                "Thumbs down",
                                on_click=lambda fid=finding_id: submit_finding_feedback(
                                    finding_id=fid,
                                    useful=False,
                                ),
                            ).props("outline no-caps").classes("dw-theme-button")
                        false_positive_reason = (
                            ui.textarea(
                                label="False positive reason",
                                value=(
                                    current_feedback.get("false_positive_reason")
                                    if current_feedback is not None
                                    else ""
                                ),
                            )
                            .props("outlined autogrow")
                            .classes("w-full")
                        )
                        ui.button(
                            "Mark false positive",
                            on_click=lambda fid=finding_id, reason_input=false_positive_reason: (
                                submit_finding_feedback(
                                    finding_id=fid,
                                    useful=False,
                                    false_positive_flag=True,
                                    reason_input=reason_input,
                                )
                            ),
                        ).props("outline no-caps").classes("dw-danger-button")
            with ui.card().classes("w-full dw-panel-soft shadow-none"):
                with ui.column().classes("gap-3 p-4"):
                    ui.label("Missed finding note").classes(
                        "text-sm font-semibold dw-text"
                    )
                    if latest_false_negative is not None:
                        ui.label(
                            "Latest note: "
                            + str(latest_false_negative["false_negative_note"])
                        ).classes("text-xs dw-muted")
                    missed_note = (
                        ui.textarea(
                            label="Missed finding note",
                            value=(
                                latest_false_negative.get("false_negative_note")
                                if latest_false_negative is not None
                                else ""
                            ),
                        )
                        .props("outlined autogrow")
                        .classes("w-full")
                    )
                    ui.button(
                        "Save missed finding note",
                        on_click=lambda note_input=missed_note: submit_false_negative(
                            note_input
                        ),
                    ).props("outline no-caps").classes("dw-theme-button")


def render_report_detail_page(
    report: dict[str, Any],
    *,
    on_feedback_change=None,
) -> None:
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
                    render_topology_freshness_banner(context)
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
    _render_operational_narrative(report)
    render_findings_table(
        findings,
        evidence_items,
        title="Findings table",
        artifact_names=artifact_names,
        report_id=int(report["id"]),
    )
    render_reviewer_feedback_panel(report, on_feedback_change=on_feedback_change)
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
