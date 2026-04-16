"""Shared UI theme helpers."""

from __future__ import annotations

from nicegui import ui

_THEME_CSS = """
<style>
:root {
  --dw-bg: #f7f8f4;
  --dw-surface: #ffffff;
  --dw-surface-2: #f1f4ef;
  --dw-border: #d8ddd4;
  --dw-text: #1d2420;
  --dw-muted: #66726b;
  --dw-accent: #d85a30;
  --dw-low: #2e9e62;
  --dw-medium: #c58a18;
  --dw-high: #d97706;
  --dw-critical: #c24141;
  --dw-uncertain: #7a6a3a;
}
body {
  background:
    radial-gradient(circle at top left, rgba(216, 90, 48, 0.08), transparent 28%),
    linear-gradient(180deg, #fafbf8 0%, var(--dw-bg) 100%);
  color: var(--dw-text);
  font-family: "DM Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.dw-shell {
  background: transparent;
}
.dw-main-content {
  margin-left: 200px;
  width: calc(100% - 200px);
  max-width: none;
  padding: 24px 16px 24px 12px;
  box-sizing: border-box;
}
.dw-sidebar {
  background: linear-gradient(180deg, #eef2eb 0%, #f7f8f4 100%);
  border-right: 1px solid var(--dw-border);
}
.dw-panel {
  border: 1px solid var(--dw-border);
  border-radius: 12px;
  background: var(--dw-surface);
  box-shadow: 0 10px 30px rgba(25, 33, 28, 0.04);
}
.dw-panel-soft {
  border: 1px solid var(--dw-border);
  border-radius: 10px;
  background: var(--dw-surface-2);
}
.dw-eyebrow {
  color: var(--dw-accent);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.dw-muted {
  color: var(--dw-muted);
}
.dw-title {
  color: var(--dw-text);
}
.dw-link {
  color: var(--dw-muted);
  text-decoration: none;
  display: block;
  border-radius: 10px;
  padding: 10px 12px;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}
.dw-link-active {
  color: var(--dw-text);
  font-weight: 600;
  background: #eef1ea;
  border-left: 3px solid var(--dw-accent);
  padding-left: 9px;
}
.dw-divider {
  background: var(--dw-border);
}
.dw-search-input .q-field__control {
  border-radius: 8px;
  background: var(--dw-surface);
}
.dw-search-input .q-field__native::placeholder {
  color: #94a099;
  opacity: 1;
}
.dw-search-input.q-field--outlined .q-field__control:before {
  border: 1px solid #e0e4dc;
}
.dw-search-input.q-field--focused .q-field__control:before,
.dw-search-input.q-field--focused .q-field__control:after {
  border-color: var(--dw-accent);
}
.dw-history-card {
  transition: box-shadow 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}
.dw-history-card:hover {
  background: #fcfcfa;
  box-shadow: 0 12px 26px rgba(25, 33, 28, 0.08);
}
.dw-history-card-selected {
  background: #fafaf7;
  border-left: 4px solid var(--dw-accent);
}
</style>
"""


def apply_theme() -> None:
    """Inject the shared visual theme for app surfaces."""
    ui.add_head_html(_THEME_CSS)
    ui.colors(primary="#D85A30")


def build_navigation_shell(active: str) -> None:
    """Render the shared left-side navigation shell."""
    with ui.left_drawer(value=True).classes("dw-sidebar w-[200px] pl-3 pr-0 py-5"):
        with ui.column().classes("gap-6"):
            with ui.column().classes("gap-1"):
                ui.label("DeployWhisper").classes("text-2xl font-medium dw-title")
                ui.label("Advisory deployment intelligence").classes("text-xs dw-muted uppercase tracking-[0.08em]")
            with ui.column().classes("gap-2"):
                ui.link("Dashboard", "/").classes("text-sm no-underline dw-link" + (" dw-link-active" if active == "dashboard" else ""))
                ui.link("History", "/history").classes("text-sm no-underline dw-link" + (" dw-link-active" if active == "history" else ""))
                ui.link("Settings", "/settings").classes("text-sm no-underline dw-link" + (" dw-link-active" if active == "settings" else ""))


def build_page_header(*, eyebrow: str, title: str, subtitle: str, back_href: str | None = None, back_label: str = "Back") -> None:
    """Render a consistent page header inside the main workspace."""
    with ui.row().classes("w-full items-start justify-between gap-4"):
        with ui.column().classes("gap-2 max-w-3xl"):
            ui.label(eyebrow).classes("dw-eyebrow")
            ui.label(title).classes("text-3xl font-medium dw-title")
            ui.label(subtitle).classes("text-sm dw-muted")
        if back_href:
            ui.button(back_label, on_click=lambda: ui.navigate.to(back_href)).props("outline no-caps").classes("text-sm")
