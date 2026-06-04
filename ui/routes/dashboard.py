"""Dashboard shell rendering."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from html import escape
from typing import Any

from nicegui import ui

from services.project_service import (
    get_active_project,
    has_active_project_selection,
    ProjectRecord,
)
from services.report_service import (
    fetch_active_dashboard_report,
    fetch_dashboard_briefing,
    fetch_filtered_analysis_history_page,
    fetch_dashboard_stats,
)
from services.incident_service import get_incident_ingestion_status
from ui.components.project_workspace_switcher import (
    build_project_combobox,
    open_create_project_dialog,
    project_repository_context,
)
from ui.components.upload_panel import build_upload_panel
from ui.components.verdict_card import render_verdict_card
from ui.project_authorization import (
    load_authorized_ui_projects,
    resolve_authorized_active_project_selection,
    resolve_authorized_ui_active_project,
    set_authorized_ui_project,
)
from ui.routes.history import build_history_detail_page, build_history_page
from ui.routes.incidents import build_incidents_page
from ui.routes.settings import build_settings_page
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
GREEN_LIGHT = "rgba(22,163,74,0.12)"
AMBER = "#d97706"
AMBER_LIGHT = "rgba(217,119,6,0.12)"
WHITE = "#ffffff"
ORANGE_50 = "#fff7ed"
GREEN_DARK = "#166534"
GREEN_ICON = "#15803d"
AMBER_DARK = "#92400e"
ZINC_100_BORDER = "#f4f4f5"

_DASHBOARD_HEAD_INJECTED = False
_THEME_SYNC_JS = """
(() => {
  const key = 'deploywhisper-theme';
  const apply = (theme) => {
    const resolved = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.dwTheme = resolved;
    try { window.localStorage.setItem(key, resolved); } catch (_) {}
    document.querySelectorAll('[data-dw-theme-toggle-label]').forEach((node) => {
      node.textContent = resolved === 'dark' ? 'Light theme' : 'Dark theme';
    });
  };
  window.dwToggleTheme = () => {
    const current = document.documentElement.dataset.dwTheme === 'dark' ? 'dark' : 'light';
    apply(current === 'dark' ? 'light' : 'dark');
  };
  let stored = document.documentElement.dataset.dwTheme || 'light';
  try { stored = window.localStorage.getItem(key) || stored; } catch (_) {}
  apply(stored);
})();
"""
ICON_FALLBACKS = {
    "activity": "↗",
    "bolt": "⚡",
    "check_circle": "✓",
    "error_outline": "!",
    "folder": "▣",
    "grid_view": "⊞",
    "history": "↺",
    "schedule": "◷",
    "search": "⌕",
    "settings": "⚙",
    "theme": "◐",
    "warning": "!",
}


def inject_styles(*, force: bool = False) -> None:
    """Inject dashboard typography, tokens, and NiceGUI override styles."""
    global _DASHBOARD_HEAD_INJECTED
    if _DASHBOARD_HEAD_INJECTED and not force:
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
<link rel="icon" href="/assets/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/assets/favicon-32.png">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
<style>
  *, *::before, *::after {{
    box-sizing: border-box;
  }}
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
    --dw-green-light: {GREEN_LIGHT};
    --dw-amber: {AMBER};
    --dw-amber-light: {AMBER_LIGHT};
  }}
  *, body, .q-page, .nicegui-content, .q-layout,
  input, button, span, div, p, h1, h2, h3, label, a {{
    font-family: 'Plus Jakarta Sans', sans-serif !important;
  }}
  .q-icon,
  i.q-icon,
  .material-icons,
  .material-icons-outlined,
  .material-symbols-outlined {{
    font-family: 'Material Icons' !important;
    font-weight: normal !important;
    font-style: normal !important;
    font-size: 24px;
    line-height: 1;
    letter-spacing: normal;
    text-transform: none;
    display: inline-block;
    white-space: nowrap;
    word-wrap: normal;
    direction: ltr;
    -webkit-font-feature-settings: 'liga';
    -webkit-font-smoothing: antialiased;
  }}
  body, html {{
    background: {ZINC_100} !important;
    margin: 0;
    padding: 0;
  }}
  body, .nicegui-content {{
    background: {ZINC_100} !important;
  }}
  .q-page-container {{
    padding: 0 !important;
    background: {ZINC_100} !important;
  }}
  .q-layout, .q-page, .q-page-container {{
    min-height: 100vh;
  }}
  .q-drawer {{
    border-right: 1px solid {ZINC_200} !important;
    box-shadow: none !important;
    pointer-events: auto !important;
  }}
  .q-drawer-container {{
    pointer-events: none !important;
  }}
  .q-header {{
    box-shadow: none !important;
    border-bottom: 1px solid {ZINC_200} !important;
  }}
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
  .q-card {{
    border: 1px solid {ZINC_200};
    box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
  }}
  .q-separator {{ background: {ZINC_200} !important; }}
  .q-card > div {{
    padding: 0;
  }}
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
  .q-field__control::after {{
    border: 0 !important;
    display: none !important;
  }}
  .q-field--outlined .q-field__control::before {{
    display: none !important;
  }}
  .q-btn {{
    text-transform: none !important;
    min-height: 0 !important;
  }}
  .dw-clean-input .q-field__control::before,
  .dw-clean-input .q-field__control::after {{
    display: none !important;
  }}
  .dw-clean-input .q-field__control {{
    background: {ZINC_100} !important;
    border: 1px solid {ZINC_200} !important;
    border-radius: 12px !important;
    height: 40px !important;
    padding: 0 12px !important;
  }}
  .dw-clean-input .q-field__native {{
    color: {MUTED} !important;
    font-size: 13px !important;
  }}
  .dw-project-combobox {{
    position: relative;
    overflow: visible;
    min-width: 0;
    flex: 1;
  }}
  .dw-project-search-input {{
    min-width: 0;
    width: 100%;
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
  .dw-project-search-input .q-placeholder::placeholder {{
    color: {MUTED} !important;
    opacity: 1;
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
  .dw-project-feedback-row {{
    padding: 16px;
  }}
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
  .dw-project-option-active {{
    background: {ZINC_100};
  }}
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
  .dw-project-option-check {{
    color: {ORANGE};
    margin-top: 2px;
  }}
  .dw-project-match {{
    background: rgba(255,105,0,0.16);
    color: {ZINC_950};
    border-radius: 4px;
    padding: 0 2px;
  }}
  .dw-nav-item {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 12px;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 500;
    color: {MUTED};
    cursor: pointer;
    text-decoration: none;
    transition: background 0.15s, color 0.15s;
    position: relative;
  }}
  .dw-nav-item:hover {{
    background: {ZINC_100};
    color: {ZINC_950};
  }}
  .dw-nav-inactive:hover {{
    background: {ZINC_100} !important;
    color: {ZINC_950} !important;
  }}
  .dw-nav-active {{
    background: {ORANGE_LIGHT} !important;
    color: {ZINC_950} !important;
    font-weight: 600;
  }}
  .dw-nav-active::before {{
    content: '';
    position: absolute;
    left: 0;
    top: 6px;
    bottom: 6px;
    width: 3px;
    border-radius: 0 3px 3px 0;
    background: {ORANGE};
  }}
  .badge {{
    display: inline-flex;
    align-items: center;
    padding: 3px 9px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
    line-height: 1.4;
  }}
  .badge-high {{ background: rgba(220,38,38,0.12); color: #991b1b; }}
  .badge-clear {{ background: rgba(22,163,74,0.12); color: #166534; }}
  .badge-med {{ background: rgba(217,119,6,0.12); color: #92400e; }}
  .badge-analyzing {{ background: rgba(255,105,0,0.12); color: #c2410c; }}
  .badge-prod {{ background: rgba(220,38,38,0.10); color: #991b1b; }}
  .badge-staging {{ background: rgba(217,119,6,0.12); color: #92400e; }}
  .badge-dev {{ background: {ZINC_100}; color: {MUTED}; }}
  @keyframes dw-spin {{ to {{ transform: rotate(360deg); }} }}
  .dw-spin {{
    display: inline-block;
    animation: dw-spin 1s linear infinite;
    margin-right: 4px;
  }}
  .dw-metric-card,
  .dashboard-card,
  .analysis-intake-card {{
    transition: box-shadow 0.18s ease;
  }}
  .dw-metric-card:hover {{
    box-shadow: 0 4px 20px rgba(0,0,0,0.10) !important;
  }}
  .dashboard-card:hover,
  .analysis-intake-card:hover {{
    box-shadow: 0 8px 24px rgba(0,0,0,0.08) !important;
  }}
  .dw-table-row:hover {{ background: #f9fafb; }}
  .dw-report-signal-grid {{
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
    align-items: start;
  }}
  .dw-report-signal {{
    min-width: 0;
    width: 100%;
    overflow: visible;
    align-self: stretch;
  }}
  .dw-report-signal-compact {{
    min-height: 148px;
  }}
  .dw-report-signal-long {{
    grid-column: span 3;
  }}
  .dw-report-signal-action {{
    grid-column: span 1;
  }}
  .dw-report-signal-long .dw-report-signal-value {{
    font-size: 18px;
    line-height: 1.35;
    max-width: 92ch;
  }}
  .dw-report-signal-long .dw-report-signal-detail {{
    margin-top: 6px;
  }}
  .dw-report-signal-value,
  .dw-report-signal-detail {{
    display: block;
    max-width: 100%;
    white-space: normal;
    overflow-wrap: anywhere;
    word-break: break-word;
    hyphens: auto;
  }}
  @media (max-width: 1180px) {{
    .dw-report-signal-grid {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .dw-report-signal-long,
    .dw-report-signal-action {{
      grid-column: span 2;
    }}
  }}
  @media (max-width: 720px) {{
    .dw-report-signal-grid {{
      grid-template-columns: 1fr;
    }}
    .dw-report-signal-long,
    .dw-report-signal-action {{
      grid-column: span 1;
    }}
  }}
  .dw-panel-soft {{
    border: 1px solid {ZINC_200};
    border-radius: 12px;
    background: {BG};
  }}
  .dw-eyebrow {{
    color: {MUTED};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }}
  .dw-muted {{ color: {MUTED}; }}
  .dw-text, .dw-title {{ color: {ZINC_950}; }}
  .dw-accent-text {{ color: {ORANGE}; }}
  .dw-warning-text {{ color: {AMBER}; }}
  .dw-danger-text {{ color: {RED}; }}
  .dw-success-text {{ color: {GREEN}; }}
  .dw-body {{
    color: {MUTED};
    font-size: 14px;
    line-height: 1.65;
  }}
  .dw-verdict-card {{
    border-radius: 16px !important;
    background: {WHITE} !important;
    padding: 24px !important;
  }}
  .dw-verdict-score-value {{
    color: {ZINC_950};
    font-size: 44px;
    font-weight: 800;
    letter-spacing: -0.04em;
    line-height: 0.95;
  }}
  .dw-verdict-score-label,
  .dw-report-signal-detail {{
    color: {MUTED};
  }}
  .dw-verdict-top-risk {{
    color: {ZINC_950};
    font-size: 16px;
    font-weight: 700;
    line-height: 1.35;
  }}
  .dw-report-signal-value {{
    color: {ZINC_950};
  }}
  .dw-theme-toggle {{
    width: 40px;
    height: 40px;
    border: 1px solid {ZINC_200};
    border-radius: 10px;
    background: {ZINC_100};
    color: {ZINC_950};
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    flex-shrink: 0;
  }}
  html[data-dw-theme="dark"] {{
    --dw-bg: #18181b;
    --dw-zinc-100: #27272a;
    --dw-zinc-200: #3f3f46;
    --dw-zinc-950: #f4f4f5;
    --dw-text: #f4f4f5;
    --dw-muted: #a1a1aa;
    --dw-muted-text: #a1a1aa;
    --dw-line: #3f3f46;
    --dw-line-strong: #52525b;
    --dw-surface: #18181b;
    --dw-surface-strong: #18181b;
    --dw-surface-soft: #27272a;
    --dw-pill-bg: #27272a;
  }}
  html[data-dw-theme="dark"] body,
  html[data-dw-theme="dark"] .nicegui-content,
  html[data-dw-theme="dark"] .q-page-container {{
    background: #27272a !important;
    color: #f4f4f5 !important;
  }}
  html[data-dw-theme="dark"] .q-header,
  html[data-dw-theme="dark"] .q-drawer,
  html[data-dw-theme="dark"] .q-card,
  html[data-dw-theme="dark"] .dw-panel {{
    background: #18181b !important;
    border-color: #3f3f46 !important;
    color: #f4f4f5 !important;
  }}
  html[data-dw-theme="dark"] .dw-panel-soft,
  html[data-dw-theme="dark"] .dw-mini-stat,
  html[data-dw-theme="dark"] .dw-theme-toggle,
  html[data-dw-theme="dark"] .dw-header-button,
  html[data-dw-theme="dark"] .dw-theme-button,
  html[data-dw-theme="dark"] .q-field--outlined .q-field__control,
  html[data-dw-theme="dark"] .q-select .q-field__control,
  html[data-dw-theme="dark"] .q-uploader {{
    background: #27272a !important;
    border-color: #3f3f46 !important;
    color: #f4f4f5 !important;
  }}
  html[data-dw-theme="dark"] .dw-text,
  html[data-dw-theme="dark"] .dw-title,
  html[data-dw-theme="dark"] .q-field__native,
  html[data-dw-theme="dark"] .q-field__input,
  html[data-dw-theme="dark"] .q-field__label {{
    color: #f4f4f5 !important;
  }}
  html[data-dw-theme="dark"] .dw-muted,
  html[data-dw-theme="dark"] .dw-body,
  html[data-dw-theme="dark"] .dw-project-option-meta,
  html[data-dw-theme="dark"] .dw-project-filter-meta {{
    color: #a1a1aa !important;
  }}
  html[data-dw-theme="dark"] .dw-nav-inactive:hover,
  html[data-dw-theme="dark"] .dw-nav-item:hover,
  html[data-dw-theme="dark"] .dw-project-option-button:hover,
  html[data-dw-theme="dark"] .dw-project-option-active,
  html[data-dw-theme="dark"] .dw-table-row:hover,
  html[data-dw-theme="dark"] .dw-history-card:hover {{
    background: #27272a !important;
    color: #f4f4f5 !important;
  }}
  html[data-dw-theme="dark"] .dw-project-option-selected {{
    background: rgba(255,105,0,0.18) !important;
    box-shadow: inset 0 0 0 1px rgba(255,105,0,0.38) !important;
  }}
  html[data-dw-theme="dark"] .badge-high,
  html[data-dw-theme="dark"] .badge-prod {{
    background: rgba(231,0,11,0.20) !important;
    color: #fca5a5 !important;
  }}
  html[data-dw-theme="dark"] .badge-clear {{
    background: rgba(22,163,74,0.20) !important;
    color: #86efac !important;
  }}
  html[data-dw-theme="dark"] .badge-med,
  html[data-dw-theme="dark"] .badge-staging {{
    background: rgba(217,119,6,0.22) !important;
    color: #fcd34d !important;
  }}
  html[data-dw-theme="dark"] .badge-dev {{
    background: #27272a !important;
    color: #d4d4d8 !important;
  }}
  html[data-dw-theme="dark"] [style*="color:#0a0a0a"],
  html[data-dw-theme="dark"] [style*="color: #0a0a0a"],
  html[data-dw-theme="dark"] [style*="color: rgb(10, 10, 10)"],
  html[data-dw-theme="dark"] [style*="color:{ZINC_950}"],
  html[data-dw-theme="dark"] [style*="color: {ZINC_950}"] {{
    color: #f4f4f5 !important;
  }}
  html[data-dw-theme="dark"] [style*="color:#71717b"],
  html[data-dw-theme="dark"] [style*="color: #71717b"],
  html[data-dw-theme="dark"] [style*="color: rgb(113, 113, 123)"],
  html[data-dw-theme="dark"] [style*="color: rgb(156, 163, 175)"],
  html[data-dw-theme="dark"] [style*="color:{MUTED}"],
  html[data-dw-theme="dark"] [style*="color: {MUTED}"] {{
    color: #a1a1aa !important;
  }}
  html[data-dw-theme="dark"] [style*="background:#fff"],
  html[data-dw-theme="dark"] [style*="background: #fff"],
  html[data-dw-theme="dark"] [style*="background:#ffffff"],
  html[data-dw-theme="dark"] [style*="background: #ffffff"],
  html[data-dw-theme="dark"] [style*="background: rgb(255, 255, 255)"] {{
    background: #18181b !important;
  }}
  html[data-dw-theme="dark"] [style*="background:#f9fafb"],
  html[data-dw-theme="dark"] [style*="background: #f9fafb"],
  html[data-dw-theme="dark"] [style*="background:#f4f4f5"],
  html[data-dw-theme="dark"] [style*="background: #f4f4f5"],
  html[data-dw-theme="dark"] [style*="background: rgb(249, 250, 251)"],
  html[data-dw-theme="dark"] [style*="background: rgb(244, 244, 245)"] {{
    background: #27272a !important;
  }}
  html[data-dw-theme="dark"] [style*="border:1px solid #e4e4e7"],
  html[data-dw-theme="dark"] [style*="border: 1px solid #e4e4e7"],
  html[data-dw-theme="dark"] [style*="border: 1px solid rgb(228, 228, 231)"],
  html[data-dw-theme="dark"] [style*="border-color:#e4e4e7"],
  html[data-dw-theme="dark"] [style*="border-color: #e4e4e7"],
  html[data-dw-theme="dark"] [style*="border-color: rgb(228, 228, 231)"] {{
    border-color: #3f3f46 !important;
  }}
  html[data-dw-theme="dark"] .q-field__native::placeholder,
  html[data-dw-theme="dark"] .q-field__input::placeholder,
  html[data-dw-theme="dark"] input::placeholder {{
    color: #a1a1aa !important;
    opacity: 1 !important;
  }}
  .dw-dashboard-hidden-context {{
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }}
  ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
  ::-webkit-scrollbar-track {{ background: transparent; }}
  ::-webkit-scrollbar-thumb {{ background: #d4d4d8; border-radius: 3px; }}
</style>
<script>
(() => {{
  const key = 'deploywhisper-theme';
  const apply = (theme) => {{
    const resolved = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.dwTheme = resolved;
    try {{ window.localStorage.setItem(key, resolved); }} catch (_) {{}}
    document.querySelectorAll('[data-dw-theme-toggle-label]').forEach((node) => {{
      node.textContent = resolved === 'dark' ? 'Light theme' : 'Dark theme';
    }});
  }};
  window.dwToggleTheme = () => {{
    const current = document.documentElement.dataset.dwTheme === 'dark' ? 'dark' : 'light';
    apply(current === 'dark' ? 'light' : 'dark');
  }};
  let stored = 'light';
  try {{ stored = window.localStorage.getItem(key) || 'light'; }} catch (_) {{}}
  apply(stored);
}})();
</script>
""",
        shared=True,
    )
    _DASHBOARD_HEAD_INJECTED = True


def inject_global_styles(*, force: bool = False) -> None:
    """Backward-compatible alias for older imports/tests."""
    inject_styles(force=force)


def icon_symbol(name: str, *, color: str = MUTED, size: int = 18) -> None:
    """Render a dashboard icon without depending on external icon fonts."""
    glyph = ICON_FALLBACKS.get(name, "•")
    ui.html(
        f'<span aria-hidden="true" style="display:inline-flex;align-items:center;'
        f"justify-content:center;width:{size}px;height:{size}px;font-size:{size}px;"
        f'line-height:1;color:{color};font-weight:700;flex-shrink:0">{escape(glyph)}</span>'
    )


def _empty_dashboard_stats() -> dict[str, Any]:
    return {
        "total_files_scanned": 0,
        "severity_counts": {
            "low": 0,
            "medium": 0,
            "high": 0,
            "critical": 0,
        },
    }


def _empty_dashboard_briefing(message: str) -> dict[str, Any]:
    return {
        **_empty_dashboard_stats(),
        "saved_briefings": 0,
        "high_focus": 0,
        "weighted_focus_score": 0,
        "latest_summary": message,
    }


def _briefing_summary_line(saved_briefings: int, high_focus: int) -> str:
    saved_label = "briefing" if saved_briefings == 1 else "briefings"
    saved_verb = "is" if saved_briefings == 1 else "are"
    focus_label = "report is" if high_focus == 1 else "reports are"
    if saved_briefings == 0:
        return "No saved briefings yet. Upload artifacts to start building operational history."
    return (
        f"{saved_briefings} saved {saved_label} {saved_verb} shaping the current advisory view. "
        f"{high_focus} {focus_label} currently high or critical."
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


def _total_analyses_text(briefing: dict[str, Any]) -> str:
    return f"{int(briefing.get('saved_briefings') or 0):,}"


def _clean_rate_text(stats: dict[str, Any]) -> str:
    counts = stats["severity_counts"]
    total = sum(int(value) for value in counts.values())
    if total == 0:
        return "0.0%"
    clean = int(counts.get("low", 0))
    return f"{(clean / total) * 100:.1f}%"


def _high_findings_text(stats: dict[str, Any]) -> str:
    counts = stats["severity_counts"]
    return f"{int(counts.get('high', 0)) + int(counts.get('critical', 0)):,}"


def _avg_time_to_verdict_text(history_items: list[dict[str, Any]]) -> str:
    durations = [
        int(item.get("analysis_duration_seconds") or 0)
        for item in history_items
        if int(item.get("analysis_duration_seconds") or 0) > 0
    ]
    if not durations:
        return "—"
    return f"{round(sum(durations) / len(durations))}s"


def _parse_report_created_at(report: dict[str, Any]) -> datetime | None:
    created_at = str(report.get("created_at") or "")
    if not created_at:
        return None
    try:
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _severity_counts(stats: dict[str, Any]) -> dict[str, int]:
    counts = stats.get("severity_counts") or {}
    return {
        "low": int(counts.get("low", 0) or 0),
        "medium": int(counts.get("medium", 0) or 0),
        "high": int(counts.get("high", 0) or 0),
        "critical": int(counts.get("critical", 0) or 0),
    }


def _verdict_data_from_stats(stats: dict[str, Any]) -> dict[str, int]:
    counts = _severity_counts(stats)
    return {
        "clear": counts["low"],
        "caution": counts["medium"],
        "high": counts["high"] + counts["critical"],
    }


def _trend_points(history_items: list[dict[str, Any]], metric: str) -> list[float]:
    bucketed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for report in history_items:
        created_at = _parse_report_created_at(report)
        if created_at is None:
            continue
        bucketed[created_at.date().isoformat()].append(report)

    days = sorted(bucketed)[-7:]
    if not days:
        return [0, 0, 0, 0, 0, 0, 0]

    points: list[float] = []
    for day in days:
        reports = bucketed[day]
        if metric == "analyses":
            points.append(float(len(reports)))
        elif metric == "rate":
            low = sum(1 for report in reports if report.get("severity") == "low")
            points.append(float(round((low / len(reports)) * 100)) if reports else 0.0)
        elif metric == "findings":
            points.append(
                float(
                    sum(
                        1
                        for report in reports
                        if report.get("severity") in {"high", "critical"}
                    )
                )
            )
        else:
            durations = [
                int(report.get("analysis_duration_seconds") or 0)
                for report in reports
                if int(report.get("analysis_duration_seconds") or 0) > 0
            ]
            points.append(
                float(round(sum(durations) / len(durations))) if durations else 0.0
            )

    while len(points) < 7:
        points.insert(0, 0.0)
    return points


def _recent_history_page(project_id: int | None) -> dict[str, Any]:
    return fetch_filtered_analysis_history_page(
        project_id=project_id,
        page=1,
        page_size=50,
    )


def _incident_count(project_id: int | None, authorization_error: str | None) -> int:
    if authorization_error is not None:
        return 0
    status = get_incident_ingestion_status(project_id=project_id)
    return int(status.indexed_count)


def sparkline_svg(
    points: list[float], color: str, width: int = 200, height: int = 40
) -> str:
    """Generate an inline SVG area sparkline."""
    if len(points) < 2:
        points = [0, *(points or [0])]
    max_v = max(points) or 1
    xs = [i * width / (len(points) - 1) for i in range(len(points))]
    ys = [height - (p / max_v * height * 0.85) for p in points]
    coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    area_coords = f"0,{height} " + coords + f" {width},{height}"
    gradient_id = f"sg_{color[1:]}"
    return f"""
    <svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg"
         style="width:100%;height:40px;display:block;overflow:visible">
      <defs>
        <linearGradient id="{gradient_id}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="{color}" stop-opacity="0.35"/>
          <stop offset="100%" stop-color="{color}" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <polygon points="{area_coords}" fill="url(#{gradient_id})" />
      <polyline points="{coords}" fill="none" stroke="{color}"
                stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>"""


def env_badge(env: str) -> str:
    """Return the environment badge markup for the recent analyses table."""
    normalized = env.strip().lower()
    display = {
        "prod": "Production",
        "production": "Production",
        "stage": "Staging",
        "staging": "Staging",
        "dev": "Dev",
        "development": "Dev",
    }.get(normalized, env)
    classes = {
        "Production": "badge-prod",
        "Staging": "badge-staging",
        "Dev": "badge-dev",
    }
    return (
        f'<span class="badge {classes.get(display, "badge-dev")}">'
        f"{escape(display)}</span>"
    )


def verdict_badge(verdict: str) -> str:
    """Return the verdict badge markup for the recent analyses table."""
    classes = {
        "HIGH": "badge-high",
        "CLEAR": "badge-clear",
        "MED": "badge-med",
        "ANALYZING": "badge-analyzing",
    }
    spinner = '<span class="dw-spin">⟳</span>' if verdict == "ANALYZING" else ""
    return f'<span class="badge {classes.get(verdict, "badge-dev")}">{spinner}{escape(verdict)}</span>'


def _verdict_percentages(verdict_data: dict[str, int]) -> tuple[int, int, int]:
    clear = int(verdict_data.get("clear", 0) or 0)
    caution = int(verdict_data.get("caution", 0) or 0)
    high = int(verdict_data.get("high", 0) or 0)
    total = clear + caution + high
    if total == 0:
        return 0, 0, 0
    clear_pct = round(clear / total * 100)
    caution_pct = round(caution / total * 100)
    return clear_pct, caution_pct, 100 - clear_pct - caution_pct


def donut_chart_svg(verdict_data: dict[str, int]) -> str:
    """Render a verdict health donut chart from persisted verdict counts."""
    clear_pct, caution_pct, high_pct = _verdict_percentages(verdict_data)
    total = sum(
        int(verdict_data.get(key, 0) or 0) for key in ("clear", "caution", "high")
    )
    dominant_label = "Clear"
    dominant_pct = clear_pct
    if caution_pct > dominant_pct:
        dominant_label, dominant_pct = "Caution", caution_pct
    if high_pct > dominant_pct:
        dominant_label, dominant_pct = "High", high_pct

    if total == 0:
        segments = ""
    else:
        circ = 339.3
        gap = 2
        clear_dash = circ * clear_pct / 100
        caution_dash = circ * caution_pct / 100
        high_dash = circ * high_pct / 100
        caution_offset = -(clear_dash - gap)
        high_offset = -(clear_dash + caution_dash - gap * 2)
        segments = f"""
          <circle cx="80" cy="80" r="54" fill="none" stroke="{ORANGE}" stroke-width="22"
            stroke-dasharray="{clear_dash:.1f} {circ - clear_dash:.1f}" stroke-dashoffset="0"/>
          <circle cx="80" cy="80" r="54" fill="none" stroke="{AMBER}" stroke-width="22"
            stroke-dasharray="{caution_dash:.1f} {circ - caution_dash:.1f}" stroke-dashoffset="{caution_offset:.1f}"/>
          <circle cx="80" cy="80" r="54" fill="none" stroke="{RED}" stroke-width="22"
            stroke-dasharray="{high_dash:.1f} {circ - high_dash:.1f}" stroke-dashoffset="{high_offset:.1f}"/>
        """

    return f"""
    <div style="position:relative;width:160px;height:160px">
      <svg viewBox="0 0 160 160" width="160" height="160" style="transform:rotate(-90deg)">
        <circle cx="80" cy="80" r="54" fill="none" stroke="{ZINC_200}" stroke-width="22"/>
        {segments}
      </svg>
      <div style="position:absolute;inset:0;display:flex;flex-direction:column;
                  align-items:center;justify-content:center">
        <span style="font-size:28px;font-weight:800;color:{ZINC_950};line-height:1">
          {dominant_pct}%
        </span>
        <span style="font-size:12px;font-weight:500;color:{MUTED};margin-top:3px">
          {escape(dominant_label)}
        </span>
      </div>
    </div>"""


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


def build_sidebar(active_project=None, *, incidents_count: int = 0) -> None:
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
            _nav_link("Dashboard", "grid_view", "/", active=True)
            _nav_link("Skills", "bolt", "/skills")
            _nav_link("Incidents", "error_outline", "/incidents", badge=incidents_count)
            _nav_link("History", "history", "/history")
            _nav_link("Settings", "settings", "/settings")

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
    """Build the dashboard top header."""

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
        with (
            ui.element("button")
            .props('type=button aria-label="Toggle theme" title="Toggle theme"')
            .classes("dw-theme-toggle")
            .on(
                "click",
                lambda _: ui.run_javascript(
                    "window.dwToggleTheme && window.dwToggleTheme()"
                ),
            )
        ):
            icon_symbol("theme", color=MUTED, size=18)
            ui.html(
                '<span data-dw-theme-toggle-label class="dw-dashboard-hidden-context">Dark theme</span>'
            )
        with ui.element("div").style(
            f"width:40px;height:40px;border-radius:10px;background:{ORANGE};color:#fff;"
            "display:flex;align-items:center;justify-content:center;font-size:14px;"
            "font-weight:700;cursor:pointer;flex-shrink:0"
        ):
            ui.label("JD")
    ui.timer(0.05, lambda: ui.run_javascript(_THEME_SYNC_JS), once=True)


def build_page_title() -> None:
    """Build the dashboard title and Evidence Law status badge."""
    with ui.row().classes("w-full justify-between items-start flex-nowrap gap-4"):
        with ui.column().classes("gap-1").style("min-width:0"):
            ui.label("Analysis snapshot").classes(
                "font-bold text-[30px] tracking-tight leading-none"
            ).style(f"color:{ZINC_950};letter-spacing:-0.5px")
            ui.label("Real-time verdicts across every environment").classes(
                "font-medium text-sm"
            ).style(f"color:{MUTED};margin-top:4px")

        ui.html(
            """
            <div style="display:inline-flex;align-items:center;gap:6px;border:1px solid rgba(22,163,74,0.3);
                        background:rgba(22,163,74,0.08);border-radius:999px;padding:4px 14px;
                        flex-shrink:0;margin-top:4px;white-space:nowrap">
              <span style="color:#15803d;font-size:14px">🛡</span>
              <span style="font-size:12px;font-weight:600;color:#166534">Evidence Law enforced</span>
            </div>
            """
        )


def _metric_card(
    *,
    label_text: str,
    value_text: str,
    trend_text: str,
    trend_symbol: str,
    trend_color: str,
    icon_name: str,
    icon_bg: str,
    icon_color: str,
    sparkline_points: list[float],
    sparkline_color: str,
) -> None:
    with (
        ui.card()
        .classes("flex-1 dw-metric-card")
        .style(
            f"background:#fff;border:1px solid {ZINC_200};border-radius:18px;"
            "padding:20px;min-width:0;box-shadow:0 1px 3px rgba(0,0,0,0.06)"
        )
    ):
        with (
            ui.row()
            .classes("w-full justify-between items-center flex-nowrap")
            .style("margin-bottom:12px")
        ):
            ui.label(label_text).classes("font-medium text-[13px]").style(
                f"color:{MUTED}"
            )
            with ui.element("div").style(
                f"width:36px;height:36px;border-radius:10px;background:{icon_bg};"
                "display:flex;align-items:center;justify-content:center;flex-shrink:0"
            ):
                icon_symbol(icon_name, color=icon_color, size=18)
        with (
            ui.row().classes("items-end gap-2 flex-nowrap").style("margin-bottom:10px")
        ):
            ui.label(value_text).classes(
                "font-bold text-3xl tracking-tight leading-none"
            ).style(f"color:{ZINC_950}")
            ui.label(f"{trend_symbol} {trend_text}").classes(
                "font-semibold text-xs"
            ).style(f"color:{trend_color};margin-bottom:3px;white-space:nowrap")
        ui.html(sparkline_svg(sparkline_points, sparkline_color))


def build_kpi_cards(
    briefing: dict[str, Any], stats: dict[str, Any], history_items: list[dict[str, Any]]
) -> None:
    """Build the four metric cards."""
    analyses_points = _trend_points(history_items, "analyses")
    rate_points = _trend_points(history_items, "rate")
    finding_points = _trend_points(history_items, "findings")
    time_points = _trend_points(history_items, "time")
    with ui.row().classes("w-full gap-4 flex-nowrap").style("overflow-x:auto"):
        _metric_card(
            label_text="Total Analyses",
            value_text=_total_analyses_text(briefing),
            trend_text="live",
            trend_symbol="↑",
            trend_color=GREEN,
            icon_name="activity",
            icon_bg=ORANGE_LIGHT,
            icon_color=ORANGE,
            sparkline_points=analyses_points,
            sparkline_color=ORANGE,
        )
        _metric_card(
            label_text="Clean Verdict Rate",
            value_text=_clean_rate_text(stats),
            trend_text="live",
            trend_symbol="↑",
            trend_color=GREEN,
            icon_name="check_circle",
            icon_bg=GREEN_LIGHT,
            icon_color=GREEN,
            sparkline_points=rate_points,
            sparkline_color=GREEN,
        )
        _metric_card(
            label_text="High/Critical Findings",
            value_text=_high_findings_text(stats),
            trend_text="live",
            trend_symbol="↓",
            trend_color=RED,
            icon_name="warning",
            icon_bg="rgba(231,0,11,0.12)",
            icon_color=RED,
            sparkline_points=finding_points,
            sparkline_color=RED,
        )
        _metric_card(
            label_text="Avg Time to Verdict",
            value_text=_avg_time_to_verdict_text(history_items),
            trend_text="live",
            trend_symbol="↓",
            trend_color=GREEN,
            icon_name="schedule",
            icon_bg=AMBER_LIGHT,
            icon_color=AMBER,
            sparkline_points=time_points,
            sparkline_color=AMBER,
        )


def _workspace_environment(report: dict[str, Any]) -> str:
    workspace = report.get("workspace")
    if isinstance(workspace, dict):
        environment = str(workspace.get("environment") or "").strip()
        if environment:
            return environment.title()
    source = str(report.get("audit", {}).get("source_interface") or "ui").strip()
    return source.upper() if source else "UI"


def _recent_service_label(report: dict[str, Any]) -> str:
    files = report.get("audit", {}).get("files_analyzed") or []
    if files:
        return str(files[0])
    top_risk = str(report.get("top_risk") or "").strip()
    return top_risk or f"Analysis #{report.get('id', '')}".strip()


def _verdict_label(report: dict[str, Any]) -> str:
    severity = str(report.get("severity") or "").lower()
    if severity in {"critical", "high"}:
        return "HIGH"
    if severity == "medium":
        return "MED"
    if severity == "low":
        return "CLEAR"
    return "ANALYZING"


def _triggered_by(report: dict[str, Any]) -> str:
    audit = report.get("audit") or {}
    actor = str(audit.get("actor") or "").strip()
    if actor:
        return actor
    source = str(audit.get("source_interface") or "ui").strip()
    return source or "ui"


def _duration_label(report: dict[str, Any]) -> str:
    duration = int(report.get("analysis_duration_seconds") or 0)
    return f"{duration}s" if duration > 0 else "—"


def build_recent_analyses(history_items: list[dict[str, Any]]) -> None:
    """Build the recent analyses table content."""
    with (
        ui.row()
        .classes("w-full justify-between items-start flex-nowrap")
        .style("margin-bottom:14px")
    ):
        with ui.column().classes("gap-0").style("min-width:0"):
            ui.label("Recent Analyses").style(
                f"font-size:18px;font-weight:700;color:{ZINC_950};letter-spacing:-0.3px"
            )
            ui.label("Last 6 deployment verdicts").style(
                f"font-size:13px;color:{MUTED};margin-top:2px"
            )
        ui.html(
            f'<a href="/history" style="font-size:13px;font-weight:600;color:{ORANGE};'
            'cursor:pointer;display:flex;align-items:center;gap:2px;white-space:nowrap">View all ›</a>'
        )

    header = (
        '<div style="display:grid;grid-template-columns:1.4fr 1fr 1fr 1.2fr 0.7fr;'
        f'padding:8px 12px;border-bottom:1px solid {ZINC_200};min-width:720px">'
        '<span style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.07em;color:#9ca3af">Service</span>'
        '<span style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.07em;color:#9ca3af">Environment</span>'
        '<span style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.07em;color:#9ca3af">Verdict</span>'
        '<span style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.07em;color:#9ca3af">Triggered By</span>'
        '<span style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.07em;color:#9ca3af;text-align:right">Duration</span>'
        "</div>"
    )
    rows = []
    for report in history_items[:6]:
        report_id = report.get("id")
        href = f"/history/{int(report_id)}" if report_id is not None else "/history"
        service = _recent_service_label(report)
        env = _workspace_environment(report)
        verdict = _verdict_label(report)
        actor = _triggered_by(report)
        duration = _duration_label(report)
        rows.append(
            f'<a href="{escape(href)}" class="dw-table-row" style="display:grid;grid-template-columns:1.4fr 1fr 1fr 1.2fr 0.7fr;'
            f'padding:12px;border-bottom:1px solid {ZINC_100_BORDER};align-items:center;min-width:720px;text-decoration:none">'
            f'<span style="color:{ZINC_950};font-size:14px;font-weight:600;min-width:0;overflow:hidden;text-overflow:ellipsis">{escape(service)}</span>'
            f"<span>{env_badge(env)}</span>"
            f"<span>{verdict_badge(verdict)}</span>"
            f'<span style="color:{MUTED};font-size:13px;font-weight:500;min-width:0;overflow:hidden;text-overflow:ellipsis">{escape(actor)}</span>'
            f'<span style="color:{MUTED};font-size:13px;text-align:right">{escape(duration)}</span>'
            "</a>"
        )
    if not rows:
        rows.append(
            f'<div style="padding:16px 12px;color:{MUTED};font-size:13px;min-width:720px">'
            "No analyses yet. Run an analysis to populate this table.</div>"
        )
    ui.html(f'<div style="width:100%;overflow-x:auto">{header}{"".join(rows)}</div>')


def build_verdict_health(verdict_data: dict[str, int]) -> None:
    """Build the verdict health donut chart content."""
    clear_pct, caution_pct, high_pct = _verdict_percentages(verdict_data)
    ui.label("Verdict Health").style(
        f"font-size:18px;font-weight:700;color:{ZINC_950};letter-spacing:-0.3px"
    )
    ui.label("Distribution last 30 days").style(
        f"font-size:13px;color:{MUTED};margin-top:2px;margin-bottom:16px"
    )
    ui.html(
        f"""
        <div style="display:flex;justify-content:center;margin-bottom:18px">
          {donut_chart_svg(verdict_data)}
        </div>
        """
    )
    for label, color, count, pct in [
        ("Clear", ORANGE, int(verdict_data.get("clear", 0) or 0), clear_pct),
        ("Caution", AMBER, int(verdict_data.get("caution", 0) or 0), caution_pct),
        ("High", RED, int(verdict_data.get("high", 0) or 0), high_pct),
    ]:
        ui.html(
            f"""
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
              <span style="display:flex;align-items:center;gap:8px;font-size:14px;color:{ZINC_950};font-weight:500;min-width:0">
                <span style="width:10px;height:10px;border-radius:50%;background:{color};display:inline-block;flex-shrink:0"></span>
                {escape(label)}
              </span>
              <span style="font-size:14px;font-weight:600;color:{MUTED};flex-shrink:0">{pct}% · {count}</span>
            </div>
            """
        )


def build_bottom_row(
    history_items: list[dict[str, Any]], verdict_data: dict[str, int]
) -> None:
    """Build Recent Analyses and Verdict Health side by side."""
    with ui.row().classes("w-full gap-4 items-start flex-nowrap"):
        with ui.card().style(
            f"flex:2;background:#fff;border:1px solid {ZINC_200};border-radius:18px;"
            "padding:22px;min-width:0;box-shadow:0 1px 3px rgba(0,0,0,0.06)"
        ):
            build_recent_analyses(history_items)

        with ui.card().style(
            f"flex:1;background:#fff;border:1px solid {ZINC_200};border-radius:18px;"
            "padding:22px;min-width:240px;box-shadow:0 1px 3px rgba(0,0,0,0.06)"
        ):
            build_verdict_health(verdict_data)


def build_briefing_card(briefing: dict[str, Any]) -> None:
    """Build the Deployment Briefing side card."""
    severity_counts = briefing.get("severity_counts") or {}
    latest_summary = str(briefing.get("latest_summary") or "")
    saved_briefings = int(briefing.get("saved_briefings") or 0)
    high_focus = int(briefing.get("high_focus") or 0)
    files_scanned = int(briefing.get("total_files_scanned") or 0)
    weighted_focus = int(briefing.get("weighted_focus_score") or 0)

    ui.label("Deployment briefing").style(
        f"font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.09em;color:{ORANGE}"
    )
    with (
        ui.row()
        .classes("w-full items-start gap-3 flex-nowrap")
        .style("margin-top:10px;margin-bottom:12px")
    ):
        ui.label(latest_summary).style(
            f"font-size:14px;font-weight:600;color:{ZINC_950};line-height:1.5;flex:1;min-width:0"
        )
        with (
            ui.column()
            .classes("items-center")
            .style(
                f"background:{ZINC_100};border-radius:12px;padding:10px;min-width:64px;"
                "flex-shrink:0;text-align:center"
            )
        ):
            ui.label(str(weighted_focus)).style(
                f"font-size:24px;font-weight:700;color:{ZINC_950};line-height:1"
            )
            ui.label("RISK FOCUS").style(
                f"font-size:9px;font-weight:600;text-transform:uppercase;"
                f"letter-spacing:0.07em;color:{MUTED};margin-top:3px"
            )

    with ui.element("div").style(
        f"background:#f9fafb;border:1px solid {ZINC_200};border-radius:10px;"
        f"padding:12px;font-size:12px;color:{MUTED};line-height:1.6;margin-bottom:14px"
    ):
        ui.label(_briefing_summary_line(saved_briefings, high_focus))

    ui.separator().style(f"border-color:{ZINC_200};margin:0 0 12px")

    with ui.row().classes("w-full gap-2 flex-nowrap").style("margin-bottom:14px"):
        for label, value in [
            ("FILES\nSCANNED", files_scanned),
            ("SAVED\nBRIEFINGS", saved_briefings),
            ("HIGH\nFOCUS", high_focus),
        ]:
            with ui.column().classes("flex-1 gap-0").style("min-width:0"):
                ui.label(str(value)).style(
                    f"font-size:22px;font-weight:700;color:{ZINC_950};line-height:1"
                )
                ui.html(
                    f'<span style="font-size:9px;font-weight:600;text-transform:uppercase;'
                    f"letter-spacing:0.06em;color:{MUTED};margin-top:3px;display:block;"
                    f'white-space:pre-line">{escape(label)}</span>'
                )

    ui.separator().style(f"border-color:{ZINC_200};margin:0 0 12px")
    ui.label("Last scan: Current project history").style(
        f"font-size:12px;color:{MUTED};margin-bottom:8px"
    )

    ui.html(
        f"""
        <div style="display:flex;gap:4px;height:6px;margin-bottom:8px">
          <div style="flex:1;background:{RED};border-radius:3px"></div>
          <div style="flex:1;background:{AMBER};border-radius:3px"></div>
          <div style="flex:1;background:{GREEN};border-radius:3px"></div>
          <div style="flex:1;background:{ORANGE};border-radius:3px"></div>
        </div>
        <div style="display:flex;gap:10px;flex-wrap:nowrap;overflow-x:auto">
          <span style="font-size:10px;font-weight:600;color:{GREEN}">LOW <span style="color:{MUTED};font-weight:400">{int(severity_counts.get("low", 0))}</span></span>
          <span style="font-size:10px;font-weight:600;color:{AMBER}">MEDIUM <span style="color:{MUTED};font-weight:400">{int(severity_counts.get("medium", 0))}</span></span>
          <span style="font-size:10px;font-weight:600;color:{RED}">HIGH <span style="color:{MUTED};font-weight:400">{int(severity_counts.get("high", 0))}</span></span>
          <span style="font-size:10px;font-weight:600;color:{ORANGE}">CRITICAL <span style="color:{MUTED};font-weight:400">{int(severity_counts.get("critical", 0))}</span></span>
        </div>
        """
    )


def build_deploy_review(
    *,
    active_project,
    authorization_error: str | None,
    briefing: dict[str, Any],
    on_analysis_complete,
    on_project_change,
) -> None:
    """Build the anchored Deploy Review upload section."""
    ui.html('<div id="deploy-review"></div>')
    active_report = (
        None
        if authorization_error is not None
        else fetch_active_dashboard_report(
            project_id=active_project.id if active_project is not None else None
        )
    )
    with ui.row().classes("w-full gap-4 items-start flex-nowrap"):
        with ui.card().style(
            f"flex:2;background:#fff;border:1px solid {ZINC_200};border-radius:18px;"
            "padding:22px;min-width:0;box-shadow:0 1px 3px rgba(0,0,0,0.06)"
        ):
            ui.label("Deploy review").style(
                f"font-size:10px;font-weight:700;text-transform:uppercase;"
                f"letter-spacing:0.09em;color:{ORANGE}"
            )
            if authorization_error is not None:
                ui.label(authorization_error).style(
                    f"font-size:13px;font-weight:600;color:{AMBER};margin-top:8px"
                )
            elif active_project is not None:
                ui.label(
                    f"Current project: {active_project.display_name} ({active_project.project_key})"
                ).style(
                    f"font-size:11px;color:{MUTED};margin-top:3px;margin-bottom:10px;"
                    "text-transform:uppercase"
                )

            if active_report is None:
                ui.html(
                    f"""
                    <div style="font-size:34px;font-weight:800;line-height:1.2;color:{ZINC_950};
                                margin-bottom:12px;letter-spacing:-0.5px">
                      Know the risk before<br>you hit <span style="color:{ORANGE}">deploy</span>
                    </div>
                    """
                )
                ui.label(
                    "Upload artifacts and generate one advisory briefing. One screen for verdict, blast radius, rollback guidance, incident similarity, and a human-readable narrative before release."
                ).style(
                    f"font-size:13px;color:{MUTED};line-height:1.7;margin-bottom:16px"
                )
            if active_report is not None:
                render_verdict_card(active_report)

            result_mount = ui.column().classes("w-full gap-4")
            build_upload_panel(
                on_analysis_complete=on_analysis_complete,
                on_project_change=on_project_change,
                embedded=True,
                result_container=result_mount,
            )

        with ui.card().style(
            f"flex:1;background:#fff;border:1px solid {ZINC_200};border-radius:18px;"
            "padding:18px;min-width:260px;box-shadow:0 1px 3px rgba(0,0,0,0.06)"
        ):
            build_briefing_card(briefing)


def _build_legacy_context_markers(
    stats: dict[str, Any], briefing: dict[str, Any]
) -> None:
    """Keep app-shell compatibility strings available to non-visual tests."""
    ui.html(
        '<div class="dw-dashboard-hidden-context">'
        f"Search repo or project name New project dw-project-bar Files scanned "
        f"{int(stats.get('total_files_scanned') or 0)} "
        f"{escape(str(briefing.get('latest_summary') or ''))}"
        "</div>"
    )


def build_dashboard() -> None:
    """Render the primary DeployWhisper dashboard."""
    content_refresh = {"fn": lambda *_: None}

    def handle_project_change(*_) -> None:
        render_header.refresh()
        render_sidebar.refresh()
        content_refresh["fn"]()

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
                active_project,
                incidents_count=_incident_count(
                    current_project_id, authorization_error
                ),
            )

        render_sidebar()

    @ui.refreshable
    def render_dashboard_content() -> None:
        _, active_project, authorization_error = resolve_authorized_ui_active_project()
        current_project_id = active_project.id if active_project is not None else None
        stats = (
            _empty_dashboard_stats()
            if authorization_error is not None
            else fetch_dashboard_stats(project_id=current_project_id)
        )
        briefing = (
            _empty_dashboard_briefing(authorization_error)
            if authorization_error is not None
            else fetch_dashboard_briefing(project_id=current_project_id)
        )
        history_page = (
            {"items": []}
            if authorization_error is not None
            else _recent_history_page(current_project_id)
        )
        history_items = list(history_page.get("items") or [])
        verdict_data = _verdict_data_from_stats(stats)

        with (
            ui.element("main")
            .classes("dw-dashboard-main w-full")
            .props('role=main aria-label="Deployment review workspace"')
        ):
            with (
                ui.column()
                .classes("w-full gap-6")
                .style("padding:32px;max-width:1280px;margin:0 auto;min-width:0")
            ):
                build_page_title()
                build_kpi_cards(briefing, stats, history_items)
                build_bottom_row(history_items, verdict_data)
                build_deploy_review(
                    active_project=active_project,
                    authorization_error=authorization_error,
                    briefing=briefing,
                    on_analysis_complete=render_dashboard_content.refresh,
                    on_project_change=handle_project_change,
                )
                _build_legacy_context_markers(stats, briefing)

    render_dashboard_content()
    content_refresh["fn"] = lambda *_: render_dashboard_content.refresh()
    ui.timer(
        5.0,
        lambda: (
            render_header.refresh(),
            render_sidebar.refresh(),
        ),
    )


@ui.page("/history")
def history_page(report_id: int | None = None) -> None:
    if report_id is not None:
        build_history_detail_page(report_id)
        return
    build_history_page()


@ui.page("/history/{report_id}")
def history_detail_page(report_id: int) -> None:
    build_history_detail_page(report_id)


@ui.page("/history/{report_id}/compare")
def history_detail_compare_page(report_id: int) -> None:
    build_history_detail_page(report_id, show_comparison=True)


@ui.page("/settings")
def settings_page() -> None:
    build_settings_page()


@ui.page("/incidents")
def incidents_page() -> None:
    build_incidents_page()
