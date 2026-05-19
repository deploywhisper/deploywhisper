"""Full-page report detail rendering."""

from __future__ import annotations

from collections.abc import Mapping
import math
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
from ui.components.change_table import format_change_metadata_lines
from ui.components.confidence_ledger import render_confidence_ledger
from ui.components.context_completeness_panel import (
    render_context_completeness_panel,
)
from ui.components.findings_table import (
    _evidence_refs,
    _is_legacy_report_schema,
    describe_evidence_item,
    render_findings_table,
)
from ui.components.review_accessibility import decorate_review_section
from ui.components.rollback_plan import render_rollback_plan
from ui.components.topology_freshness_banner import render_topology_freshness_banner
from ui.formatters.confidence import (
    coerce_confidence,
    render_confidence_badge,
)
from ui.formatters.datetime import format_history_timestamp
from ui.formatters.narrative import (
    extract_llm_notice,
    extract_submission_manifest_notice,
)
from ui.formatters.report_header import (
    evidence_law_status,
    next_action_text,
    report_confidence_text,
    report_verdict_text,
)
from ui.formatters.recommendations import render_recommendation_label
from ui.formatters.risk_labels import render_risk_badge


def format_submission_manifest_summary(manifest: dict[str, Any]) -> str:
    parts = [
        f"{manifest.get('accepted_artifact_count', 0)} accepted",
        f"{manifest.get('analyzed_artifact_count', 0)} analyzed",
        f"{manifest.get('excluded_artifact_count', 0)} excluded",
        f"{manifest.get('failed_artifact_count', 0)} failed",
        f"{manifest.get('sensitive_artifact_count', 0)} sensitive",
    ]
    if manifest.get("partial_analysis"):
        parts.append(f"{manifest.get('partial_artifact_count', 0)} partial")
    return "Submission manifest: " + ", ".join(parts)


def format_submission_manifest_partial_notice(manifest: dict[str, Any]) -> str | None:
    if not manifest.get("partial_analysis"):
        return None
    partial_count = int(manifest.get("partial_artifact_count") or 0)
    artifact_label = "artifact" if partial_count == 1 else "artifacts"
    return (
        f"Partial analysis: {partial_count} submitted {artifact_label} "
        "reduced analysis coverage."
    )


def format_submission_manifest_fallback_summary(
    fallback_items: list[dict[str, Any]],
) -> str | None:
    if not fallback_items:
        return None
    artifact_summaries = [
        f"{item.get('name', 'artifact')} ({item.get('status', 'unknown')})"
        for item in fallback_items
    ]
    return "Fallback submission artifacts: " + ", ".join(artifact_summaries)


def _detail_stat(label: str, value: str, detail: str) -> None:
    with ui.card().classes("dw-panel-soft shadow-none min-w-[180px] flex-1"):
        with ui.column().classes("gap-1 p-3"):
            ui.label(label).classes(
                "text-[11px] font-semibold uppercase tracking-[0.08em] dw-muted"
            )
            ui.label(value).classes("text-lg font-semibold dw-text")
            ui.label(detail).classes("text-xs dw-muted leading-5")


def _header_signal(label: str, value: str, detail: str) -> None:
    with ui.element("div").classes("dw-panel-soft min-w-[180px] flex-1 p-3"):
        with ui.column().classes("gap-1"):
            ui.label(label).classes(
                "text-[11px] font-semibold uppercase tracking-[0.08em] dw-muted"
            )
            ui.label(value).classes("text-base font-semibold dw-text leading-5")
            ui.label(detail).classes("text-xs dw-muted leading-5")


def _render_summary_and_advisory(report: dict[str, Any]) -> None:
    llm_notice = extract_llm_notice(
        report.get("warnings", []),
        report.get("narrative_failure_notice"),
    )
    manifest_notice = extract_submission_manifest_notice(report.get("warnings", []))
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
            if manifest_notice:
                with ui.card().classes("dw-panel-soft shadow-none"):
                    ui.label("Report warning: " + manifest_notice).classes(
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
            _numeric_sort_value(contributor.get("contribution")),
            str(contributor.get("resource_id") or ""),
        ),
    )


def _numeric_sort_value(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float("-inf")
    if not math.isfinite(number):
        return float("-inf")
    return number


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
            coerce_confidence(finding.get("confidence")) or 0.0,
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
    evidence_refs = set(_evidence_refs(finding)) if finding else set()
    if evidence_refs:
        matched_evidence = [
            item
            for item in evidence_items
            if str(item.get("evidence_id") or "").strip() in evidence_refs
        ]
        if matched_evidence:
            return min(
                matched_evidence,
                key=lambda item: _evidence_reference_rank(item, report),
            )
    matched_by_finding = _same_finding_evidence_items(
        finding,
        evidence_items,
        _unique_finding_ids(report),
    )
    if matched_by_finding:
        return min(
            matched_by_finding,
            key=lambda item: _evidence_reference_rank(item, report),
        )
    if evidence_refs:
        return None
    if _has_unresolved_evidence_ref_payload(finding):
        return None
    if _can_use_report_level_evidence_fallback(report, evidence_items):
        return evidence_items[0]
    return None


def _can_use_report_level_evidence_fallback(
    report: dict[str, Any], evidence_items: list[dict[str, Any]]
) -> bool:
    findings = [item for item in report.get("findings", []) if isinstance(item, dict)]
    return len(findings) <= 1 and len(evidence_items) == 1


def _unique_finding_ids(report: dict[str, Any]) -> set[str]:
    id_counts: dict[str, int] = {}
    for finding in report.get("findings", []):
        if not isinstance(finding, dict):
            continue
        finding_id = str(finding.get("finding_id") or "").strip()
        if finding_id:
            id_counts[finding_id] = id_counts.get(finding_id, 0) + 1
    return {finding_id for finding_id, count in id_counts.items() if count == 1}


def _same_finding_evidence_items(
    finding: dict[str, Any] | None,
    evidence_items: list[dict[str, Any]],
    fallback_finding_ids: set[str],
) -> list[dict[str, Any]]:
    finding_id = str((finding or {}).get("finding_id") or "").strip()
    if not finding_id:
        return []
    if finding_id not in fallback_finding_ids:
        return []
    return [
        item
        for item in evidence_items
        if str(item.get("finding_id") or "").strip() == finding_id
    ]


def _has_unresolved_evidence_ref_payload(finding: dict[str, Any] | None) -> bool:
    if not finding or "evidence_refs" not in finding:
        return False
    raw_refs = finding.get("evidence_refs")
    if raw_refs is None:
        return False
    if isinstance(raw_refs, str):
        return bool(raw_refs.strip())
    if isinstance(raw_refs, Mapping):
        return True
    try:
        values = list(raw_refs)
    except TypeError:
        return True
    return any(str(value).strip() for value in values)


def _evidence_reference_rank(evidence: dict[str, Any], report: dict[str, Any]) -> int:
    descriptor = describe_evidence_item(
        evidence,
        legacy_missing_redaction_is_none=_is_legacy_report_schema(
            str(report.get("report_schema_version") or "")
        ),
    )
    redaction_status = str(descriptor["redaction_status"])
    if redaction_status == "none":
        return 0
    if redaction_status == "redacted":
        return 1
    if redaction_status == "sensitive_blocked":
        return 2
    return 3


def _safe_evidence_reference(evidence: dict[str, Any], report: dict[str, Any]) -> str:
    descriptor = describe_evidence_item(
        evidence,
        legacy_missing_redaction_is_none=_is_legacy_report_schema(
            str(report.get("report_schema_version") or "")
        ),
    )
    if descriptor["redaction_status"] == "none":
        return str(descriptor["display_source_ref"])
    if descriptor["redaction_status"] in {"sensitive_blocked", "unknown"}:
        return str(descriptor["display_source_ref"])
    return "Evidence reference redacted"


def _safe_evidence_summary(evidence: dict[str, Any], report: dict[str, Any]) -> str:
    descriptor = describe_evidence_item(
        evidence,
        legacy_missing_redaction_is_none=_is_legacy_report_schema(
            str(report.get("report_schema_version") or "")
        ),
    )
    if descriptor["redaction_status"] == "none":
        return str(evidence.get("summary") or "the top evidence item")
    return "the linked evidence metadata"


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
            exact_resource += (
                f" Evidence reference: {_safe_evidence_reference(evidence, report)}."
            )
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
            f"Verify before deploy: confirm {_safe_evidence_summary(evidence, report)} "
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
                            ui.label(
                                str(
                                    contributor.get("resource_id") or "unknown resource"
                                )
                            ).classes("text-sm font-semibold dw-text")
                            ui.label(
                                f"{contributor.get('resource_category') or 'unknown category'} · "
                                f"{contributor.get('normalized_action') or contributor.get('action') or 'unknown action'} · "
                                f"{contributor.get('environment') or 'unknown environment'} · "
                                f"scope {contributor.get('downstream_scope') or 'unknown'}"
                            ).classes("text-xs dw-muted")
                            ui.label(
                                str(
                                    contributor.get("reasoning")
                                    or contributor.get("summary")
                                    or "No contributor reasoning was recorded."
                                )
                            ).classes("text-sm dw-muted leading-6")
                            for metadata_line in format_change_metadata_lines(
                                contributor.get("metadata") or {}
                            ):
                                ui.label(metadata_line).classes(
                                    "text-xs dw-muted leading-5"
                                )
                            for security_flag in contributor.get("security_flags", []):
                                ui.label(security_flag).classes(
                                    "text-xs dw-danger-text"
                                )
                        render_risk_badge(str(contributor.get("severity") or "unknown"))


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
            manifest = report.get("submission_manifest") or {}
            if manifest.get("items"):
                with ui.column().classes("gap-2"):
                    ui.label("Submission manifest").classes(
                        "text-sm font-semibold dw-text"
                    )
                    ui.label(format_submission_manifest_summary(manifest)).classes(
                        "text-sm dw-muted"
                    )
                    partial_notice = format_submission_manifest_partial_notice(manifest)
                    if partial_notice:
                        ui.label(partial_notice).classes(
                            "text-sm dw-warning-text leading-5"
                        )
                    for item in manifest["items"]:
                        partial_marker = " · PARTIAL" if item.get("partial") else ""
                        ui.label(
                            f"{item.get('name', 'artifact')} · "
                            f"{str(item.get('status', 'unknown')).upper()} · "
                            f"{item.get('redaction_status', 'none')}"
                            f"{partial_marker}"
                        ).classes("text-xs dw-muted break-all")
            fallback_summary = format_submission_manifest_fallback_summary(
                report.get("submission_manifest_fallback") or []
            )
            if fallback_summary and not manifest.get("items"):
                ui.label(fallback_summary).classes(
                    "text-sm dw-warning-text leading-5 break-all"
                )


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
    evidence_status, evidence_detail = evidence_law_status(report)

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
                        confidence = coerce_confidence(report.get("confidence"))
                        if confidence is not None:
                            render_confidence_badge(confidence)
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
                _header_signal(
                    "Verdict",
                    report_verdict_text(report),
                    "Advisory deployment-risk orientation, not an approval or block.",
                )
                _header_signal(
                    "Advisory posture",
                    "Advisory only",
                    "Human release review remains responsible for the decision.",
                )
                _header_signal(
                    "Evidence Law",
                    evidence_status,
                    evidence_detail,
                )
                _header_signal(
                    "Confidence",
                    report_confidence_text(report),
                    "Overall report confidence captured with the verdict.",
                )
                _header_signal(
                    "Top risk",
                    str(report.get("top_risk") or "No top risk recorded."),
                    "Primary risk to inspect before drilling into evidence.",
                )
                _header_signal(
                    "Next action",
                    next_action_text(report, evidence_status),
                    "Suggested human review step before release action.",
                )

    _render_summary_and_advisory(report)
    _render_operational_narrative(report)
    render_confidence_ledger(report)
    render_findings_table(
        findings,
        evidence_items,
        title="Findings table",
        artifact_names=artifact_names,
        report_id=int(report["id"]),
        report_schema_version=str(report.get("report_schema_version") or ""),
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
