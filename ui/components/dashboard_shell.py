"""Shared dashboard shell for NiceGUI workspace pages."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from html import escape

from nicegui import ui

from services.incident_service import get_incident_ingestion_status
from services.project_service import (
    get_active_project,
    has_active_project_selection,
    ProjectRecord,
)
from ui.components.project_workspace_switcher import (
    build_project_combobox,
    open_create_project_dialog,
    project_repository_context,
)
from ui.project_authorization import (
    load_authorized_ui_projects,
    resolve_authorized_active_project_selection,
    resolve_authorized_ui_active_project,
    set_authorized_ui_project,
)
from ui.theme import BRAND_MARK_IMAGE_PATH

ORANGE = "#ff6900"
ORANGE_LIGHT = "rgba(255,105,0,0.10)"
RED = "#e7000b"
MUTED = "#71717b"
ZINC_950 = "#0a0a0a"
ZINC_200 = "#e4e4e7"
ZINC_100 = "#f4f4f5"
BG = "#f9fafb"
GREEN = "#16a34a"
AMBER = "#d97706"

ICON_FALLBACKS = {
    "bolt": "⚡",
    "error_outline": "!",
    "folder": "▣",
    "grid_view": "⊞",
    "history": "↺",
    "notifications": "🔔",
    "search": "⌕",
    "settings": "⚙",
}

_SHELL_HEAD_INJECTED = False


def inject_shell_styles(*, force: bool = False) -> None:
    """Inject the shared dashboard shell style layer."""
    global _SHELL_HEAD_INJECTED
    if _SHELL_HEAD_INJECTED and not force:
        return
    ui.colors(primary=ORANGE)
    ui.add_css(
        f"""
        button.q-btn.bg-primary,
        .q-btn.q-btn--unelevated.bg-primary,
        .q-btn.dw-orange-button,
        .dw-orange-button {{
          background: {ORANGE} !important;
          color: #fff !important;
          border-radius: 12px !important;
          font-weight: 700 !important;
        }}
        .q-btn.dw-orange-text-button,
        .dw-orange-text-button,
        button.q-btn.text-primary {{
          color: {ORANGE} !important;
          border-radius: 12px !important;
          font-weight: 700 !important;
        }}
        .q-uploader .q-uploader__header,
        .q-uploader__header {{
          background: {ORANGE} !important;
          color: #fff !important;
        }}
        .q-uploader__header .q-btn,
        .q-uploader__header .q-icon,
        .q-uploader__title,
        .q-uploader__subtitle {{
          color: #fff !important;
        }}
        .q-linear-progress__model--determinate,
        .q-linear-progress__model--indeterminate {{
          background: {ORANGE} !important;
        }}
        """,
        shared=True,
    )
    ui.add_head_html(
        f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  :root {{
    --dw-orange: {ORANGE};
    --dw-orange-light: {ORANGE_LIGHT};
    --dw-red: {RED};
    --dw-muted: {MUTED};
    --dw-zinc-950: {ZINC_950};
    --dw-zinc-200: {ZINC_200};
    --dw-zinc-100: {ZINC_100};
    --dw-bg: {BG};
    --dw-green: {GREEN};
    --dw-amber: {AMBER};
    --dw-text: {ZINC_950};
    --dw-muted-text: {MUTED};
    --dw-accent: {ORANGE};
    --dw-accent-soft: {ORANGE_LIGHT};
    --dw-accent-line: rgba(255,105,0,0.28);
    --dw-accent-contrast: #c2410c;
    --dw-line: {ZINC_200};
    --dw-line-strong: #d4d4d8;
    --dw-surface: #ffffff;
    --dw-surface-strong: #ffffff;
    --dw-surface-soft: {BG};
    --dw-pill-bg: {ZINC_100};
    --dw-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }}
  *, body, .q-page, .nicegui-content, .q-layout,
  input, button, span, div, p, h1, h2, h3, label, a {{
    font-family: 'Plus Jakarta Sans', sans-serif !important;
  }}
  body, html, .nicegui-content, .q-page-container {{
    background: {ZINC_100} !important;
    margin: 0;
    padding: 0 !important;
  }}
  .q-layout, .q-page, .q-page-container {{ min-height: 100vh; }}
  .q-header {{
    box-shadow: none !important;
    border-bottom: 1px solid {ZINC_200} !important;
  }}
  .q-drawer {{
    border-right: 1px solid {ZINC_200} !important;
    box-shadow: none !important;
    pointer-events: auto !important;
  }}
  .q-drawer-container {{ pointer-events: none !important; }}
  .dw-dashboard-header {{
    left: 240px !important;
    width: calc(100% - 240px) !important;
  }}
  .dw-dashboard-main {{
    margin-left: 240px;
    margin-top: 68px;
    width: calc(100% - 240px);
    min-width: 0;
  }}
  .dw-workspace-content {{
    width: 100%;
    max-width: 1280px;
    margin: 0 auto;
    padding: 32px;
    min-width: 0;
  }}
  .q-card {{
    border: 1px solid {ZINC_200};
    box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
  }}
  .q-card > div {{ padding: 0; }}
  .q-separator {{ background: {ZINC_200} !important; }}
  .bg-primary,
  .q-btn.bg-primary {{
    background: {ORANGE} !important;
  }}
  .text-primary,
  .q-btn.text-primary {{
    color: {ORANGE} !important;
  }}
  .q-btn.bg-primary {{
    color: #fff !important;
    border-radius: 12px !important;
    font-weight: 700 !important;
  }}
  .q-btn.dw-orange-button,
  .dw-orange-button {{
    background: {ORANGE} !important;
    color: #fff !important;
    border-radius: 12px !important;
    font-weight: 700 !important;
  }}
  .q-btn.dw-orange-text-button,
  .dw-orange-text-button {{
    color: {ORANGE} !important;
    border-radius: 12px !important;
    font-weight: 700 !important;
  }}
  .q-uploader__header {{
    background: {ORANGE} !important;
    color: #fff !important;
  }}
  .q-uploader .q-uploader__header {{
    background: {ORANGE} !important;
  }}
  .q-uploader__header .q-btn,
  .q-uploader__header .q-icon,
  .q-uploader__title,
  .q-uploader__subtitle {{
    color: #fff !important;
  }}
  .q-linear-progress__model--determinate,
  .q-linear-progress__model--indeterminate {{
    background: {ORANGE} !important;
  }}
  .q-field__control,
  .q-field__native,
  .q-field__input {{
    background: transparent !important;
    min-height: 0 !important;
    color: {ZINC_950} !important;
  }}
  .q-field__control::before,
  .q-field__control::after,
  .q-field--outlined .q-field__control::before {{
    border: 0 !important;
    display: none !important;
  }}
  .q-btn {{
    text-transform: none !important;
    min-height: 0 !important;
  }}
  .dw-panel {{
    background: #fff !important;
    border: 1px solid {ZINC_200} !important;
    border-radius: 18px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
    padding: 22px !important;
  }}
  .dw-page-header {{
    padding: 24px !important;
  }}
  .dw-panel-soft {{
    border: 1px solid {ZINC_200};
    border-radius: 12px;
    background: {BG};
  }}
  .dw-header-button,
  .dw-theme-button {{
    border: 1px solid {ZINC_200} !important;
    border-radius: 12px !important;
    background: {ZINC_100} !important;
    color: {ZINC_950} !important;
    min-height: 40px !important;
    font-weight: 700 !important;
    padding: 0 14px !important;
  }}
  .dw-theme-button .q-icon {{ color: {ORANGE}; }}
  .dw-eyebrow {{
    color: {MUTED};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }}
  .dw-text, .dw-title {{ color: {ZINC_950}; }}
  .dw-muted {{ color: {MUTED}; }}
  .dw-link {{ color: {ORANGE}; font-weight: 700; text-decoration: none; }}
  .dw-accent-text {{ color: {ORANGE}; }}
  .dw-warning-text {{ color: {AMBER}; }}
  .dw-danger-text {{ color: {RED}; }}
  .dw-success-text {{ color: {GREEN}; }}
  .dw-body {{ color: {MUTED}; font-size: 14px; line-height: 1.65; }}
  .dw-mini-stat {{
    border: 1px solid {ZINC_200};
    border-radius: 14px;
    background: {BG};
    padding: 14px;
  }}
  .dw-history-card {{
    transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
  }}
  .dw-history-card:hover {{
    transform: translateY(-2px);
    border-color: #d4d4d8;
  }}
  .dw-history-card-selected {{
    border-color: rgba(255,105,0,0.28) !important;
    box-shadow: 0 0 0 1px rgba(255,105,0,0.28), 0 1px 3px rgba(0,0,0,0.06) !important;
  }}
  .dw-history-project-filter-field {{
    min-height: 40px;
    padding: 6px 12px 7px;
    border: 1px solid #d4d4d8;
    border-radius: 10px;
    background: #fff;
    justify-content: center;
    min-width: 0;
  }}
  .dw-history-filter-control {{ min-width: 0; width: 100%; }}
  .dw-nav-inactive:hover {{
    background: {ZINC_100} !important;
    color: {ZINC_950} !important;
  }}
  .dw-search-input .q-field__control,
  .q-field--outlined .q-field__control,
  .q-select .q-field__control,
  .q-uploader {{
    border-radius: 12px !important;
    border-color: {ZINC_200} !important;
    background: #fff !important;
    color: {ZINC_950} !important;
  }}
  .dw-search-input .q-field__native,
  .q-field__native,
  .q-field__input,
  .q-field__label,
  .q-uploader__title,
  .q-uploader__subtitle {{
    color: {ZINC_950} !important;
  }}
  .dw-search-input .q-field__native::placeholder,
  .q-field__native::placeholder {{
    color: {MUTED} !important;
    opacity: 1;
  }}
  .q-field--outlined .q-field__control::before,
  .q-field--outlined .q-field__control::after {{
    border-color: {ZINC_200} !important;
  }}
  .q-field--focused .q-field__control::before,
  .q-field--focused .q-field__control::after {{
    border-color: {ORANGE} !important;
  }}
  .dw-project-combobox {{
    position: relative;
    overflow: visible;
    min-width: 0;
    flex: 1;
  }}
  .dw-project-search-input .q-field__control {{
    min-height: 38px !important;
    height: 38px !important;
    background: transparent !important;
    padding: 0 !important;
  }}
  .dw-project-search-input .q-field__native,
  .dw-project-search-input .q-field__input {{
    color: {ZINC_950} !important;
    font-size: 12px !important;
    font-weight: 500 !important;
  }}
  .dw-project-dropdown-anchor {{
    position: absolute;
    top: calc(100% + 8px);
    left: -10px;
    right: -10px;
    z-index: 3000;
  }}
  .dw-project-dropdown-panel {{
    border: 1px solid {ZINC_200} !important;
    border-radius: 14px !important;
    background: #fff !important;
    box-shadow: 0 18px 42px rgba(0,0,0,0.16) !important;
    overflow: hidden;
  }}
  .dw-project-dropdown-list {{
    max-height: min(320px, calc(100vh - 120px));
    overflow-y: auto;
    padding: 6px;
  }}
  .dw-project-feedback-row {{ padding: 16px; }}
  .dw-project-empty-title {{
    font-size: 14px;
    font-weight: 700;
    color: {ZINC_950};
  }}
  .dw-project-empty-copy {{
    color: {MUTED};
    font-size: 12px;
    line-height: 1.5;
  }}
  .dw-project-option-button {{
    display: block;
    width: 100%;
    min-height: 64px;
    padding: 10px 12px;
    border-radius: 10px;
    background: transparent;
    text-align: left;
    cursor: pointer;
    user-select: none;
    transition: background 0.15s ease;
  }}
  .dw-project-option-button:hover,
  .dw-project-option-active {{ background: {ZINC_100}; }}
  .dw-project-option-selected {{
    box-shadow: inset 0 0 0 1px rgba(255,105,0,0.28);
    background: {ORANGE_LIGHT};
  }}
  .dw-project-option-primary {{
    display: block;
    color: {ZINC_950};
    font-size: 13px;
    font-weight: 700;
    line-height: 1.35;
  }}
  .dw-project-option-meta,
  .dw-project-filter-meta {{
    display: block;
    color: {MUTED};
    font-size: 11px;
    line-height: 1.45;
    overflow-wrap: anywhere;
  }}
  .dw-project-option-check {{ color: {ORANGE}; margin-top: 2px; }}
  .dw-project-match {{
    background: rgba(255,105,0,0.16);
    color: {ZINC_950};
    border-radius: 4px;
    padding: 0 2px;
  }}
  .dw-dashboard-hidden-context {{
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }}
  .dw-history-filter-row {{
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    width: 100%;
  }}
  .dw-danger-button {{ color: {RED} !important; }}
  ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
  ::-webkit-scrollbar-track {{ background: transparent; }}
  ::-webkit-scrollbar-thumb {{ background: #d4d4d8; border-radius: 3px; }}
</style>
""",
        shared=True,
    )
    _SHELL_HEAD_INJECTED = True


def icon_symbol(name: str, *, color: str = MUTED, size: int = 18) -> None:
    """Render a shell icon without relying on external icon fonts."""
    glyph = ICON_FALLBACKS.get(name, "•")
    ui.html(
        f'<span aria-hidden="true" style="display:inline-flex;align-items:center;'
        f"justify-content:center;width:{size}px;height:{size}px;font-size:{size}px;"
        f'line-height:1;color:{color};font-weight:700;flex-shrink:0">{escape(glyph)}</span>'
    )


def _current_project_labels(active_project) -> tuple[str, str]:
    if active_project is None:
        return "Unassigned", "Default workspace"
    if active_project.project_key == "unassigned":
        return active_project.display_name, "Default workspace"
    return active_project.display_name, f"Key {active_project.project_key}"


def _current_project_repository(active_project) -> str | None:
    if active_project is None:
        return None
    return project_repository_context(active_project)


def _incident_count(project_id: int | None, authorization_error: str | None) -> int:
    if authorization_error is not None or project_id is None:
        return 0
    status = get_incident_ingestion_status(project_id=project_id)
    return int(status.indexed_count)


def _nav_link(
    label: str,
    icon: str,
    href: str,
    *,
    active: bool = False,
    badge: int | None = None,
) -> None:
    style = (
        "display:flex;align-items:center;gap:12px;padding:10px 12px;"
        "border-radius:12px;font-size:14px;cursor:pointer;text-decoration:none;"
        "position:relative;"
    )
    if active:
        style += f"background:{ORANGE_LIGHT};font-weight:600;color:{ZINC_950};"
    else:
        style += f"font-weight:500;color:{MUTED};transition:background 0.15s;"
    if badge is not None:
        style += "justify-content:space-between;"

    with ui.link(target=href).classes("" if active else "dw-nav-inactive").style(style):
        if active:
            ui.element("span").style(
                f"position:absolute;left:0;top:8px;bottom:8px;width:3px;"
                f"border-radius:0 3px 3px 0;background:{ORANGE}"
            )
        with ui.element("span").style(
            "display:flex;align-items:center;gap:12px;min-width:0"
        ):
            icon_symbol(icon, color=ORANGE if active else MUTED, size=18)
            ui.label(label).style(
                f"font-size:14px;font-weight:{'600' if active else '500'};"
                f"color:{ZINC_950 if active else MUTED};min-width:0"
            )
        if badge is not None:
            ui.label(str(badge)).style(
                "min-width:20px;height:20px;background:#dc2626;color:#fff;"
                "font-size:11px;font-weight:700;border-radius:10px;display:flex;"
                "align-items:center;justify-content:center;padding:0 5px;flex-shrink:0"
            )


def build_sidebar(
    active_route: str,
    active_project=None,
    *,
    incidents_count: int = 0,
) -> None:
    """Build the fixed dashboard sidebar."""
    project_name, project_key = _current_project_labels(active_project)
    project_repository = _current_project_repository(active_project)
    with ui.element("div").style(
        "height:100%;width:100%;display:flex;flex-direction:column;gap:0"
    ):
        with ui.element("div").style(
            "height:68px;padding:0 24px;display:flex;align-items:center;gap:10px;"
            f"border-bottom:1px solid {ZINC_200};flex-shrink:0"
        ):
            ui.html(
                f'<img src="{BRAND_MARK_IMAGE_PATH}" alt="" aria-hidden="true" '
                'style="width:36px;height:36px;border-radius:10px;object-fit:contain;display:block;flex-shrink:0">'
            )
            with ui.element("div").style(
                "display:flex;flex-direction:column;gap:1px;line-height:1.2;min-width:0"
            ):
                ui.html(
                    f'<span style="font-size:15px;font-weight:700;color:{ZINC_950};letter-spacing:-0.2px">'
                    f'Deploy<span style="color:{ORANGE}">Whisper</span></span>'
                )
                ui.label("Evidence engine").style(
                    f"font-size:11px;font-weight:500;color:{MUTED}"
                )

        with (
            ui.element("nav")
            .style(
                "padding:16px 12px;flex:1;display:flex;flex-direction:column;gap:2px"
            )
            .props('role=navigation aria-label="Primary navigation"')
        ):
            _nav_link("Dashboard", "grid_view", "/", active=active_route == "dashboard")
            _nav_link("Skills", "bolt", "/skills", active=active_route == "skills")
            _nav_link(
                "Incidents",
                "error_outline",
                "/incidents",
                active=active_route == "incidents",
                badge=incidents_count,
            )
            _nav_link(
                "History", "history", "/history", active=active_route == "history"
            )
            _nav_link(
                "Settings",
                "settings",
                "/settings",
                active=active_route == "settings",
            )

        with ui.element("div").style("padding:12px;flex-shrink:0"):
            with ui.element("div").style(
                f"background:{ZINC_100};border:1px solid {ZINC_200};border-radius:16px;padding:14px"
            ):
                with (
                    ui.row()
                    .classes("items-center gap-2 flex-nowrap")
                    .style("margin-bottom:8px")
                ):
                    with ui.element("div").style(
                        f"width:30px;height:30px;border-radius:8px;background:{ORANGE_LIGHT};"
                        "display:flex;align-items:center;justify-content:center;flex-shrink:0"
                    ):
                        icon_symbol("folder", color=ORANGE, size=16)
                    ui.label("ACTIVE PROJECT").style(
                        f"font-size:10px;font-weight:600;text-transform:uppercase;"
                        f"letter-spacing:0.08em;color:{MUTED}"
                    )
                ui.label(project_name).classes("font-bold text-sm").style(
                    f"color:{ZINC_950}"
                )
                ui.label(project_key).classes("text-xs").style(f"color:{MUTED}")
                if project_repository:
                    ui.label(project_repository).classes("dw-project-filter-meta")
                ui.html(
                    '<span class="dw-dashboard-hidden-context">Active Project</span>'
                )


def _resolve_header_project_state() -> tuple[
    list[ProjectRecord], int | None, str | None
]:
    projects, authorization_error = load_authorized_ui_projects()
    saved_selection = has_active_project_selection()
    active_project = get_active_project()
    saved_selection, active_project = resolve_authorized_active_project_selection(
        has_saved_selection=saved_selection,
        active_project=active_project,
        projects=projects,
        authorization_error=authorization_error,
    )
    current_project_id = (
        active_project.id if saved_selection and active_project else None
    )
    return projects, current_project_id, authorization_error


def _build_header_project_selector(on_project_change=None) -> None:
    projects, current_project_id, authorization_error = _resolve_header_project_state()

    def select_project(
        project: ProjectRecord, available_projects: list[ProjectRecord] | None = None
    ) -> None:
        try:
            selected = set_authorized_ui_project(
                project.id, available_projects or projects
            )
        except PermissionError as exc:
            ui.notify(str(exc), color="warning")
            return
        if on_project_change is not None:
            on_project_change(selected)

    with ui.element("div").style(
        f"width:390px;max-width:34vw;height:40px;border:1px solid {ZINC_200};"
        f"border-radius:12px;background:{ZINC_100};display:flex;align-items:center;"
        "gap:8px;padding:0 10px;min-width:220px;position:relative;overflow:visible"
    ):
        build_project_combobox(
            projects=projects,
            current_project_id=current_project_id,
            on_select=select_project,
        )
        ui.button(
            "New project",
            on_click=lambda: open_create_project_dialog(
                on_created=lambda created: select_project(created, [*projects, created])
            ),
        ).props("flat dense no-caps").style(
            f"color:{ORANGE};font-size:12px;font-weight:700;padding:0 2px;"
            "min-height:0;white-space:nowrap;flex-shrink:0"
        )
    if authorization_error is not None:
        ui.html(
            f'<span class="dw-dashboard-hidden-context">{escape(authorization_error)}</span>'
        )


def build_header(on_project_change=None) -> None:
    """Build the shared top header."""

    def open_deploy_review() -> None:
        ui.run_javascript(
            """
            const target = document.getElementById('deploy-review');
            if (target) {
              target.scrollIntoView({behavior: 'smooth'});
            } else {
              window.location.href = '/#deploy-review';
            }
            """
        )

    with ui.element("div").style(
        "width:100%;height:100%;display:flex;align-items:center;padding:0 32px;gap:16px"
    ):
        with ui.element("div").style(
            f"flex:1;max-width:480px;display:flex;align-items:center;gap:8px;"
            f"background:{ZINC_100};border:1px solid {ZINC_200};border-radius:12px;"
            "height:40px;padding:0 14px;min-width:160px"
        ):
            icon_symbol("search", color=MUTED, size=16)
            ui.input(placeholder="Search analyses, services...").props(
                "borderless dense"
            ).style(
                "flex:1;background:transparent;border:none;outline:none;"
                f"font-size:13px;color:{ZINC_950};min-width:0"
            )
        _build_header_project_selector(on_project_change=on_project_change)
        ui.element("div").style("flex:1")
        with (
            ui.element("button")
            .props("type=button")
            .classes("dw-orange-button")
            .style(
                f"background:{ORANGE};color:#fff;border:none;border-radius:12px;height:40px;"
                "padding:0 14px;font-size:14px;font-weight:700;cursor:pointer;"
                "white-space:nowrap;flex-shrink:0;display:flex;align-items:center;gap:8px"
            )
            .on("click", lambda _: open_deploy_review())
        ):
            ui.html("<span>▶ Run Analysis</span>")
        with ui.element("div").style(
            f"position:relative;width:40px;height:40px;border-radius:10px;background:{ZINC_100};"
            "display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0"
        ):
            icon_symbol("notifications", color=MUTED, size=18)
            ui.element("span").style(
                "position:absolute;top:8px;right:8px;width:8px;height:8px;"
                "background:#dc2626;border-radius:50%;border:2px solid #fff"
            )
        with ui.element("div").style(
            f"width:40px;height:40px;border-radius:10px;background:{ORANGE};color:#fff;"
            "display:flex;align-items:center;justify-content:center;font-size:14px;"
            "font-weight:700;cursor:pointer;flex-shrink:0"
        ):
            ui.label("JD")


def build_app_shell(
    active_route: str,
    *,
    on_project_change: Callable[..., None] | None = None,
) -> None:
    """Build the fixed header/sidebar shell for a workspace page."""
    inject_shell_styles()

    def handle_project_change(*args) -> None:
        render_header.refresh()
        render_sidebar.refresh()
        if on_project_change is not None:
            on_project_change(*args)

    with (
        ui.header(elevated=False)
        .classes("dw-dashboard-header")
        .style(
            f"background:#ffffff;height:68px;padding:0;border-bottom:1px solid {ZINC_200}"
        )
    ):

        @ui.refreshable
        def render_header() -> None:
            build_header(on_project_change=handle_project_change)

        render_header()

    with (
        ui.left_drawer(fixed=True, bordered=False, top_corner=True)
        .props("show-if-above breakpoint=0 width=240")
        .style(
            f"width:240px;background:#ffffff;border-right:1px solid {ZINC_200};"
            "display:flex;flex-direction:column;padding:0;overflow:hidden"
        )
    ):

        @ui.refreshable
        def render_sidebar() -> None:
            _, active_project, authorization_error = (
                resolve_authorized_ui_active_project()
            )
            current_project_id = (
                active_project.id if active_project is not None else None
            )
            build_sidebar(
                active_route,
                active_project,
                incidents_count=_incident_count(
                    current_project_id, authorization_error
                ),
            )

        render_sidebar()

    ui.timer(5.0, lambda: (render_header.refresh(), render_sidebar.refresh()))


@contextmanager
def workspace_content(*, aria_label: str) -> Iterator[None]:
    """Open the shared main content container."""
    with (
        ui.element("main")
        .classes("dw-dashboard-main w-full")
        .props(f'role=main aria-label="{escape(aria_label)}"')
    ):
        with ui.column().classes("dw-workspace-content gap-6"):
            yield
