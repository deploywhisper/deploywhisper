"""Shared UI theme tokens and lightweight compatibility helpers."""

from __future__ import annotations

from nicegui import ui

BRAND_MARK_IMAGE_PATH = "/assets/favicon-512.png"
PLUS_JAKARTA_400_PATH = "/assets/fonts/plus-jakarta-sans-400.ttf"
PLUS_JAKARTA_500_PATH = "/assets/fonts/plus-jakarta-sans-500.ttf"
PLUS_JAKARTA_600_PATH = "/assets/fonts/plus-jakarta-sans-600.ttf"
PLUS_JAKARTA_700_PATH = "/assets/fonts/plus-jakarta-sans-700.ttf"
PLUS_JAKARTA_800_PATH = "/assets/fonts/plus-jakarta-sans-800.ttf"
MATERIAL_ICONS_PATH = "/assets/fonts/material-icons-regular.ttf"

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

LOCAL_FONT_ASSET_CSS = f"""
@font-face {{
  font-family: 'Plus Jakarta Sans';
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url('{PLUS_JAKARTA_400_PATH}') format('truetype');
}}
@font-face {{
  font-family: 'Plus Jakarta Sans';
  font-style: normal;
  font-weight: 500;
  font-display: swap;
  src: url('{PLUS_JAKARTA_500_PATH}') format('truetype');
}}
@font-face {{
  font-family: 'Plus Jakarta Sans';
  font-style: normal;
  font-weight: 600;
  font-display: swap;
  src: url('{PLUS_JAKARTA_600_PATH}') format('truetype');
}}
@font-face {{
  font-family: 'Plus Jakarta Sans';
  font-style: normal;
  font-weight: 700;
  font-display: swap;
  src: url('{PLUS_JAKARTA_700_PATH}') format('truetype');
}}
@font-face {{
  font-family: 'Plus Jakarta Sans';
  font-style: normal;
  font-weight: 800;
  font-display: swap;
  src: url('{PLUS_JAKARTA_800_PATH}') format('truetype');
}}
@font-face {{
  font-family: 'Material Icons';
  font-style: normal;
  font-weight: 400;
  font-display: block;
  src: url('{MATERIAL_ICONS_PATH}') format('truetype');
}}
"""

LOCAL_MATERIAL_ICON_CSS = """
.q-icon,
i.q-icon,
.material-icons,
.material-icons-outlined,
.material-symbols-outlined {
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
  font-feature-settings: 'liga';
}
"""

LOCAL_DESIGN_ASSET_CSS = LOCAL_FONT_ASSET_CSS + LOCAL_MATERIAL_ICON_CSS
LOCAL_DESIGN_ASSET_HEAD_HTML = f"<style>{LOCAL_DESIGN_ASSET_CSS}</style>"

_THEME_HEAD_HTML = (
    """
<link rel="icon" href="/assets/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/assets/favicon-32.png">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
"""
    + LOCAL_DESIGN_ASSET_HEAD_HTML
)

_THEME_CSS = f"""
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

  html, body, .q-layout, .q-page, .q-page-container, .nicegui-content {{
    margin: 0;
    padding: 0 !important;
    background: {ZINC_100} !important;
    color: {ZINC_950};
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    -webkit-font-smoothing: antialiased;
  }}

  .q-page, .nicegui-content, input, button, span, div, p, h1, h2, h3, label, a {{
    font-family: 'Plus Jakarta Sans', sans-serif !important;
  }}

  a {{
    color: inherit;
    text-decoration: none;
  }}

  .q-header,
  .q-drawer {{
    box-shadow: none !important;
  }}

  .q-card {{
    border: 1px solid {ZINC_200};
    box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
  }}

  .q-separator {{
    background: {ZINC_200} !important;
  }}

  .q-btn {{
    min-height: 0 !important;
    text-transform: none !important;
  }}

  .bg-primary,
  .q-btn.bg-primary,
  .q-btn.dw-orange-button,
  .dw-orange-button {{
    background: {ORANGE} !important;
    color: #fff !important;
    border-radius: 12px !important;
    font-weight: 700 !important;
  }}

  .text-primary,
  .q-btn.text-primary,
  .q-btn.dw-orange-text-button,
  .dw-orange-text-button,
  .dw-link,
  .dw-accent-text {{
    color: {ORANGE} !important;
  }}

  .q-field__control,
  .q-field__native,
  .q-field__input {{
    background: transparent !important;
    color: {ZINC_950} !important;
    min-height: 0 !important;
  }}

  .q-field__control::before,
  .q-field__control::after,
  .q-field--outlined .q-field__control::before {{
    border-color: {ZINC_200} !important;
  }}

  .q-field--focused .q-field__control::before,
  .q-field--focused .q-field__control::after {{
    border-color: {ORANGE} !important;
  }}

  .q-uploader,
  .q-select .q-field__control,
  .q-field--outlined .q-field__control {{
    border-color: {ZINC_200} !important;
    border-radius: 12px !important;
    background: #fff !important;
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

  .dw-main-content {{
    width: 100%;
    max-width: 1280px;
    margin: 0 auto;
    padding: 32px;
  }}

  .dw-panel {{
    position: relative;
    overflow: hidden;
    border: 1px solid {ZINC_200} !important;
    border-radius: 18px !important;
    background: #fff !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
    padding: 22px !important;
  }}

  .dw-page-header {{
    padding: 24px !important;
  }}

  .dw-panel-soft {{
    border: 1px solid {ZINC_200} !important;
    border-radius: 12px !important;
    background: {BG} !important;
  }}

  .dw-eyebrow {{
    color: {MUTED};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }}

  .dw-title,
  .dw-text {{
    color: {ZINC_950};
  }}

  .dw-muted {{
    color: {MUTED};
  }}

  .dw-body {{
    color: {MUTED};
    font-size: 14px;
    line-height: 1.65;
  }}

  .dw-warning-text {{
    color: {AMBER};
  }}

  .dw-danger-text {{
    color: {RED};
  }}

  .dw-success-text {{
    color: {GREEN};
  }}

  .dw-header-button,
  .dw-theme-button {{
    min-height: 40px !important;
    padding: 0 14px !important;
    border: 1px solid {ZINC_200} !important;
    border-radius: 12px !important;
    background: {ZINC_100} !important;
    color: {ZINC_950} !important;
    font-weight: 700 !important;
  }}

  .dw-mini-stat {{
    border: 1px solid {ZINC_200};
    border-radius: 14px;
    background: {BG};
    padding: 14px;
  }}

  .dw-nav-inactive:hover,
  .dw-history-card:hover {{
    background: {ZINC_100} !important;
    color: {ZINC_950} !important;
  }}

  .dw-history-card {{
    transition: box-shadow 0.18s ease, border-color 0.18s ease;
  }}

  .dw-history-card-selected {{
    border-color: rgba(255,105,0,0.28) !important;
    box-shadow: 0 0 0 1px rgba(255,105,0,0.28), 0 1px 3px rgba(0,0,0,0.06) !important;
  }}

  .dw-danger-button {{
    color: {RED} !important;
  }}

  ::-webkit-scrollbar {{
    width: 6px;
    height: 6px;
  }}

  ::-webkit-scrollbar-track {{
    background: transparent;
  }}

  ::-webkit-scrollbar-thumb {{
    background: #d4d4d8;
    border-radius: 3px;
  }}
</style>
"""

_REPORT_LAYOUT_CSS = """
<style>
.dw-report-signal-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  align-items: start;
}

.dw-report-signal {
  min-width: 0;
  width: 100%;
  overflow: visible;
  align-self: stretch;
}

.dw-report-signal-compact {
  min-height: 148px;
}

.dw-report-signal-long {
  grid-column: span 3;
}

.dw-report-signal-action {
  grid-column: span 1;
}

.dw-report-signal-long .dw-report-signal-value {
  font-size: 18px;
  line-height: 1.35;
  max-width: 92ch;
}

.dw-report-signal-long .dw-report-signal-detail {
  margin-top: 6px;
}

.dw-report-signal-value,
.dw-report-signal-detail {
  display: block;
  max-width: 100%;
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
  hyphens: auto;
}

@media (max-width: 1180px) {
  .dw-report-signal-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .dw-report-signal-long,
  .dw-report-signal-action {
    grid-column: span 2;
  }
}

@media (max-width: 720px) {
  .dw-report-signal-grid {
    grid-template-columns: 1fr;
  }

  .dw-report-signal-long,
  .dw-report-signal-action {
    grid-column: span 1;
  }
}

.dw-verdict-card {
  margin-top: 12px;
  padding: 22px 24px !important;
}

.dw-verdict-score-block {
  min-width: 124px;
  padding: 16px 18px;
  border-radius: 14px;
  border: 1px solid var(--dw-accent-line);
  background: var(--dw-accent-soft);
}

.dw-verdict-score-value {
  color: var(--dw-text);
  font-size: 44px;
  line-height: 0.95;
  font-weight: 800;
}

.dw-verdict-score-label {
  color: var(--dw-accent-contrast);
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.dw-verdict-top-risk {
  color: var(--dw-text);
  font-size: 18px;
  line-height: 1.3;
  font-weight: 700;
  max-width: min(58ch, 100%);
  overflow-wrap: anywhere;
  word-break: break-word;
  hyphens: auto;
}

.dw-findings-row {
  border-radius: 14px;
}

.dw-findings-col {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 600;
}

.dw-findings-col-severity {
  width: 120px;
}

.dw-findings-col-title {
  min-width: min(360px, 100%);
}

.dw-findings-col-tool {
  width: 84px;
}

.dw-findings-col-evidence {
  width: min(240px, 100%);
}

.dw-findings-col-confidence {
  width: 150px;
}

.dw-findings-col-actions {
  width: 116px;
}

.dw-findings-grid {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr) 88px minmax(220px, 0.7fr) 150px 116px;
  gap: 12px;
  align-items: start;
}

.dw-findings-header {
  border: 1px solid var(--dw-line);
  border-radius: 14px;
  background: var(--dw-surface-soft);
}

.dw-findings-header .q-btn {
  justify-content: flex-start;
}

.dw-findings-row-card {
  border: 1px solid var(--dw-line);
}

.dw-findings-row-base,
.dw-findings-row-alt {
  background: #fff;
}

.dw-context-progress {
  position: relative;
  width: 100%;
  height: 12px;
  border-radius: 999px;
  background: var(--dw-pill-bg);
  border: 1px solid var(--dw-line);
  overflow: hidden;
}

.dw-context-progress span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--dw-accent);
}

.dw-detail-list-row {
  border: 1px solid var(--dw-line);
}

.dw-stat-card {
  min-height: 150px;
  padding: 24px !important;
}

.dw-stat-value {
  color: var(--dw-text);
  font-size: 42px;
  line-height: 1;
  font-weight: 700;
}

.dw-stat-label {
  margin-top: 10px;
  color: var(--dw-text);
  font-size: 14px;
  font-weight: 600;
}

.dw-stat-detail {
  color: var(--dw-muted);
  font-size: 12px;
  line-height: 1.7;
}

@media (max-width: 960px) {
  .dw-findings-grid {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .dw-findings-col {
    width: auto !important;
  }

  .dw-findings-col-actions,
  .dw-findings-col-confidence {
    justify-self: start;
  }
}

@media (max-width: 820px) {
  .dw-findings-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
"""


def apply_theme() -> None:
    """Inject the shared compatibility theme for app surfaces."""
    ui.colors(primary=ORANGE)
    ui.add_head_html(_THEME_HEAD_HTML)
    ui.add_head_html(_THEME_CSS)
    ui.add_head_html(_REPORT_LAYOUT_CSS)


def build_page_header(
    *,
    eyebrow: str,
    title: str,
    subtitle: str,
    back_href: str | None = None,
    back_label: str = "Back",
) -> None:
    """Render a consistent page header inside the main workspace."""
    with ui.row().classes("w-full items-start justify-between gap-4 flex-wrap"):
        with ui.column().classes("gap-3 max-w-3xl"):
            ui.label(eyebrow).classes("dw-eyebrow")
            ui.label(title).classes("text-3xl font-semibold dw-title leading-tight")
            ui.label(subtitle).classes("dw-body")
        if back_href:
            ui.button(back_label, on_click=lambda: ui.navigate.to(back_href)).props(
                "flat no-caps"
            ).classes("dw-header-button")
