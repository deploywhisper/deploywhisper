"""Context completeness panel rendering."""

from __future__ import annotations

from nicegui import ui

from services.topology_service import STALE_AFTER_DAYS
from ui.components.review_accessibility import (
    decorate_review_section,
    register_review_accessibility,
)
from ui.formatters.context_completeness import (
    context_number,
    context_score,
    render_context_completeness_badge,
)
from ui.formatters.datetime import format_history_timestamp
from ui.formatters.topology_freshness import TOPOLOGY_MANAGEMENT_LINK


DOCS_BASE_URL = "https://github.com/deploywhisper/deploywhisper/blob/develop"


def _topology_age_text(context: dict) -> str:
    freshness = context.get("topology_freshness_days")
    if freshness is None:
        return "Unknown"
    try:
        freshness_days = int(freshness)
    except (TypeError, ValueError):
        return "Unknown"
    if freshness_days == 0:
        return "Imported today"
    unit = "day" if freshness_days == 1 else "days"
    return f"{freshness_days} {unit} old"


def _last_import_text(context: dict) -> str:
    imported_at = context.get("topology_last_imported_at")
    if not imported_at:
        return "Unavailable"
    try:
        return format_history_timestamp(str(imported_at))
    except ValueError:
        return str(imported_at)


def _metric_card(label: str, value: str, detail: str | None = None) -> None:
    with ui.card().classes("dw-panel-soft shadow-none min-w-[180px] flex-1"):
        with ui.column().classes("gap-1 p-3"):
            ui.label(label).classes(
                "text-[11px] font-semibold uppercase tracking-[0.08em] dw-muted"
            )
            ui.label(value).classes("text-lg font-semibold dw-text")
            if detail:
                ui.label(detail).classes("text-xs dw-muted leading-5")


def _topology_needs_settings_fix(context: dict) -> bool:
    freshness = context.get("topology_freshness_days")
    if freshness is None:
        return True
    try:
        return int(freshness) > STALE_AFTER_DAYS
    except (TypeError, ValueError):
        return True


def _context_int(context: dict, key: str) -> int:
    try:
        return max(int(context.get(key, 0) or 0), 0)
    except (TypeError, ValueError):
        return 0


def _context_todo_items(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _context_list_items(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _owner_signal_items(value: object) -> list[dict]:
    if not isinstance(value, list | tuple):
        return []
    signals: list[dict] = []
    for item in value:
        if isinstance(item, dict):
            subject = str(item.get("subject") or "").strip()
            if subject:
                signals.append(item)
    return signals


def _context_warning_action(context: dict, link_target: str) -> tuple[str, str]:
    todos = " ".join(
        item.lower() for item in _context_todo_items(context.get("context_todos"))
    )
    if _topology_needs_settings_fix(context) or "topology" in todos:
        return "Fix in settings", link_target
    if "evidence" in todos:
        return "Review evidence", "#context-todos"
    parser_success_rate = context_number(context.get("parser_success_rate"), 1.0)
    if "parser" in todos or parser_success_rate < 1.0:
        return "Review artifacts", "#context-todos"
    if "ownership" in todos or "codeowners" in todos:
        return "Review ownership", "#ownership-context"
    incident_index_size = _context_int(context, "incident_index_size")
    if incident_index_size == 0 or "incident" in todos:
        return "Review incidents", "#context-todos"
    return "Review context TODOs", "#context-todos"


def _todo_guidance(todo: str, link_target: str) -> tuple[str, str]:
    todo_text = todo.lower()
    if "topology" in todo_text:
        return "Manage topology", link_target
    if "incident" in todo_text:
        return "Incident context guide", f"{DOCS_BASE_URL}/docs/outcome-linking.md"
    if "evidence" in todo_text:
        return "Evidence model guide", f"{DOCS_BASE_URL}/docs/evidence-model.md"
    if "parser" in todo_text or "artifact" in todo_text:
        return "Report schema guide", f"{DOCS_BASE_URL}/docs/schemas/report-v2.md"
    if "ownership" in todo_text or "codeowners" in todo_text:
        return "Ownership context guide", f"{DOCS_BASE_URL}/docs/schemas/report-v2.md"
    return "Report context guide", f"{DOCS_BASE_URL}/docs/schemas/report-v2.md"


def _render_todo_item(todo: str, link_target: str) -> None:
    guidance_label, guidance_target = _todo_guidance(todo, link_target)
    with ui.row().classes(
        "w-full items-start justify-between gap-3 flex-wrap rounded-[14px] "
        "border border-[color:var(--dw-line)] px-3 py-2"
    ):
        ui.label(todo).classes("text-xs dw-muted leading-5 min-w-0 flex-1")
        ui.link(guidance_label, guidance_target).classes(
            "text-xs font-semibold dw-accent-text"
        )


def _has_context_followups(context: dict) -> bool:
    return (
        bool(_context_todo_items(context.get("context_todos")))
        or bool(_owner_signal_items(context.get("owner_signals")))
        or bool(_context_list_items(context.get("escalation_hints")))
        or bool(_context_list_items(context.get("ownership_unmapped_subjects")))
        or bool(str(context.get("uncertainty") or "").strip())
        or bool(context.get("insufficient_context"))
        or context_score(context) < 0.7
        or _topology_needs_settings_fix(context)
        or context_number(context.get("evidence_success_rate"), 1.0) < 1.0
        or context_number(context.get("parser_success_rate"), 1.0) < 1.0
        or _context_int(context, "incident_index_size") == 0
    )


def render_context_summary_panel(
    context: dict | None,
    *,
    link_target: str = TOPOLOGY_MANAGEMENT_LINK,
) -> None:
    """Render a compact context cue near the report summary."""
    details = context or {}
    if not _has_context_followups(details):
        return
    context_todos = _context_todo_items(details.get("context_todos"))
    owner_signals = _owner_signal_items(details.get("owner_signals"))
    escalation_hints = _context_list_items(details.get("escalation_hints"))
    unmapped_subjects = _context_list_items(details.get("ownership_unmapped_subjects"))
    uncertainty = str(details.get("uncertainty") or "").strip()
    score = context_score(details)

    with ui.card().classes("w-full dw-panel shadow-none p-4"):
        with ui.column().classes("gap-3"):
            with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
                with ui.column().classes("gap-1 min-w-0 flex-1"):
                    ui.label("Summary context check").classes(
                        "text-sm font-semibold dw-text"
                    ).props("role=heading aria-level=3")
                    ui.label(
                        "Context completeness and TODOs that may change how much confidence to place in this report."
                    ).classes("text-xs dw-muted leading-5")
                render_context_completeness_badge(details)
            if uncertainty:
                ui.label(uncertainty).classes("text-sm font-semibold dw-accent-text")
            else:
                ui.label(f"Context score is {score:.2f} / 1.00.").classes(
                    "text-sm font-semibold dw-text"
                )
            if context_todos:
                ui.label("Context follow-ups").classes("text-sm font-semibold dw-text")
                with ui.column().classes("w-full gap-2"):
                    for todo in context_todos[:4]:
                        _render_todo_item(todo, link_target)
            has_ownership_summary = bool(
                owner_signals or escalation_hints or unmapped_subjects
            )
            if has_ownership_summary:
                ui.label("Ownership context").classes("text-sm font-semibold dw-text")
                with ui.column().classes("w-full gap-2"):
                    for signal in owner_signals[:3]:
                        owners = _context_list_items(signal.get("owners"))
                        owner_text = ", ".join(owners) if owners else "Unowned"
                        subject = str(signal.get("subject") or "").strip()
                        if subject:
                            ui.label(f"Owner: {subject} -> {owner_text}").classes(
                                "text-xs dw-muted leading-5"
                            )
                    for hint in escalation_hints[:3]:
                        ui.label(hint).classes("text-xs dw-muted leading-5")
                    for subject in unmapped_subjects[:3]:
                        ui.label(f"Missing owner: {subject}").classes(
                            "text-xs dw-muted leading-5"
                        )
            if not context_todos and not has_ownership_summary:
                ui.label("No context TODOs were generated.").classes("text-xs dw-muted")


def render_context_completeness_panel(
    context: dict | None,
    *,
    link_target: str = TOPOLOGY_MANAGEMENT_LINK,
) -> None:
    """Render reviewer-facing context completeness details."""
    register_review_accessibility()
    details = context or {}
    raw_parser_success_by_tool = details.get("parser_success_by_tool")
    parser_success_by_tool = (
        dict(raw_parser_success_by_tool)
        if isinstance(raw_parser_success_by_tool, dict)
        else {}
    )
    context_todos = _context_todo_items(details.get("context_todos"))
    owner_signals = _owner_signal_items(details.get("owner_signals"))
    escalation_hints = _context_list_items(details.get("escalation_hints"))
    unmapped_subjects = _context_list_items(details.get("ownership_unmapped_subjects"))
    uncertainty = str(details.get("uncertainty") or "").strip()
    score = context_score(details)
    low_context = bool(details.get("insufficient_context")) or score < 0.7
    show_context_warning = low_context or bool(uncertainty)
    stale_topology = _topology_needs_settings_fix(details)
    action_label, action_target = _context_warning_action(details, link_target)

    with ui.card().classes("w-full dw-panel shadow-none p-4") as panel:
        decorate_review_section(panel, section="context", label="Context completeness")
        with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
            with ui.column().classes("gap-2 min-w-0 flex-1"):
                ui.label("Context completeness").classes(
                    "text-lg font-medium dw-text"
                ).props("role=heading aria-level=2")
                ui.label(
                    "Review how much topology, evidence, parser, and incident context supported this report."
                ).classes("text-sm dw-muted leading-6")
            render_context_completeness_badge(details)
        with ui.card().classes("w-full dw-panel-soft shadow-none mt-3"):
            with ui.column().classes("gap-2 p-3"):
                with ui.row().classes("w-full items-center justify-between gap-3"):
                    ui.label("Context score").classes("text-sm font-semibold dw-text")
                    ui.label(f"{score:.2f} / 1.00").classes(
                        "text-sm font-semibold dw-text"
                    )
                ui.html(
                    '<div class="dw-context-progress" '
                    f'title="Context score {score:.2f}">'
                    f'<span style="width:{max(0.0, min(score, 1.0)) * 100:.0f}%"></span>'
                    "</div>"
                )
                ui.label(
                    "Higher scores indicate stronger topology freshness, evidence coverage, parser coverage, and incident context."
                ).classes("text-xs dw-muted leading-5")

        if show_context_warning:
            with ui.row().classes(
                "w-full items-center justify-between gap-3 flex-wrap mt-3 rounded-[18px] border border-[color:var(--dw-accent-line)] bg-[color:var(--dw-accent-soft)] px-4 py-3"
            ):
                ui.label(
                    uncertainty
                    or "Context warning: supporting topology, evidence, parser, or incident context may be incomplete."
                ).classes("text-sm font-semibold dw-accent-text")
                ui.link(action_label, action_target).classes(
                    "text-sm font-semibold dw-accent-text"
                )
        elif stale_topology:
            with ui.row().classes(
                "w-full items-center justify-between gap-3 flex-wrap mt-3 rounded-[18px] border border-[color:var(--dw-line)] bg-[color:var(--dw-surface-soft)] px-4 py-3"
            ):
                ui.label(
                    "Topology context is stale or missing. Refresh it in settings to keep blast radius and context details current."
                ).classes("text-sm font-semibold dw-text")
                ui.link("Fix in settings", link_target).classes(
                    "text-sm font-semibold dw-accent-text"
                )

        with ui.row().classes("w-full gap-3 flex-wrap mt-3"):
            _metric_card(
                "Topology freshness",
                _topology_age_text(details),
                "Age of the imported topology snapshot used for blast radius.",
            )
            _metric_card(
                "Last import",
                _last_import_text(details),
                "Most recent topology import timestamp recorded for this report.",
            )
            _metric_card(
                "Incident index",
                str(_context_int(details, "incident_index_size")),
                "Version {version} · freshness {freshness}".format(
                    version=details.get("incident_index_version") or "unknown",
                    freshness=details.get("incident_index_freshness_status")
                    or "unknown",
                ),
            )
            _metric_card(
                "Evidence coverage",
                f"{context_number(details.get('evidence_success_rate'), 0.0):.2f}",
                "Fraction of material changes represented by extracted evidence.",
            )
            _metric_card(
                "Parser success",
                f"{context_number(details.get('parser_success_rate'), 0.0):.2f}",
                "Overall fraction of analyzed artifacts parsed successfully.",
            )

        if uncertainty or context_todos:
            with ui.card().classes("w-full dw-panel-soft shadow-none mt-3"):
                with ui.column().classes("gap-2 p-3"):
                    ui.label("Context TODOs").props("id=context-todos").classes(
                        "text-sm font-semibold dw-text"
                    )
                    if uncertainty:
                        ui.label(uncertainty).classes("text-xs dw-muted leading-5")
                    if context_todos:
                        for todo in context_todos:
                            _render_todo_item(todo, link_target)
                    else:
                        ui.label(
                            "No context follow-up actions were generated."
                        ).classes("text-xs dw-muted")

        if owner_signals or escalation_hints or unmapped_subjects:
            with ui.card().classes("w-full dw-panel-soft shadow-none mt-3"):
                with ui.column().classes("gap-2 p-3"):
                    ui.label("Ownership context").props("id=ownership-context").classes(
                        "text-sm font-semibold dw-text"
                    )
                    if owner_signals:
                        with ui.column().classes("w-full gap-2"):
                            for signal in owner_signals:
                                owners = _context_list_items(signal.get("owners"))
                                owner_text = ", ".join(owners) if owners else "Unowned"
                                scope = str(signal.get("scope") or "ownership").title()
                                subject = str(signal.get("subject") or "").strip()
                                source = str(
                                    signal.get("source_ref")
                                    or signal.get("source")
                                    or ""
                                ).strip()
                                detail = f"{scope}: {subject} -> {owner_text}"
                                if source:
                                    detail = f"{detail} ({source})"
                                ui.label(detail).classes("text-xs dw-muted leading-5")
                    if escalation_hints:
                        ui.label("Escalation hints").classes(
                            "text-xs font-semibold dw-text"
                        )
                        for hint in escalation_hints:
                            ui.label(hint).classes("text-xs dw-muted leading-5")
                    if unmapped_subjects:
                        ui.label("Missing ownership").classes(
                            "text-xs font-semibold dw-text"
                        )
                        for subject in unmapped_subjects:
                            ui.label(f"Missing owner: {subject}").classes(
                                "text-xs dw-muted leading-5"
                            )

        with ui.card().classes("w-full dw-panel-soft shadow-none mt-3"):
            with ui.column().classes("gap-2 p-3"):
                ui.label("Parser success by tool").classes(
                    "text-sm font-semibold dw-text"
                )
                if parser_success_by_tool:
                    with ui.row().classes("w-full gap-2 flex-wrap"):
                        for tool_name, score in sorted(parser_success_by_tool.items()):
                            with ui.column().classes(
                                "min-w-[132px] flex-1 rounded-[16px] border border-[color:var(--dw-line)] px-3 py-2"
                            ):
                                ui.label(tool_name.title()).classes(
                                    "text-sm font-semibold dw-text"
                                )
                                ui.label(f"{float(score):.2f}").classes(
                                    "text-xs dw-muted"
                                )
                else:
                    ui.label(
                        "Per-tool parser coverage is unavailable for this report."
                    ).classes("text-xs dw-muted")
