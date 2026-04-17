"""Shared UI theme helpers."""

from __future__ import annotations

from nicegui import ui

_BRAND_MARK_SVG = """
<svg width="26" height="26" viewBox="0 0 80 80" fill="none" aria-hidden="true">
  <path d="M16 12 L40 4 L64 12 L64 42 C64 58 52 68 40 74 C28 68 16 58 16 42Z" fill="var(--dw-accent-soft)" stroke="var(--dw-accent)" stroke-width="2.5"/>
  <path d="M28 36 C28 28 34 22 40 22" stroke="var(--dw-accent)" stroke-width="3" stroke-linecap="round"/>
  <path d="M24 40 C24 28 31 18 40 18" stroke="var(--dw-accent)" stroke-width="2.2" stroke-linecap="round" opacity=".55"/>
  <circle cx="40" cy="40" r="3.5" fill="var(--dw-accent)"/>
  <path d="M40 48 L40 56" stroke="var(--dw-accent)" stroke-width="3" stroke-linecap="round"/>
  <path d="M36 53 L40 57 L44 53" stroke="var(--dw-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

_THEME_HEAD_HTML = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Sora:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<script>
(() => {
  const STORAGE_KEY = 'deploywhisper-theme';
  const resolveTheme = () => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') {
      return stored;
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  };

  const setTheme = (theme) => {
    const root = document.documentElement;
    root.dataset.dwTheme = theme;
    window.localStorage.setItem(STORAGE_KEY, theme);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute('content', theme === 'dark' ? '#0b111c' : '#f4efe7');
    }
  };

  window.dwApplyTheme = (theme) => setTheme(theme === 'dark' ? 'dark' : 'light');
  window.dwToggleTheme = () => setTheme(resolveTheme() === 'dark' ? 'light' : 'dark');
  setTheme(resolveTheme());
})();
</script>
"""

_THEME_CSS = """
<style>
html[data-dw-theme="light"] {
  --dw-bg: #f4efe7;
  --dw-bg-soft: #efe7da;
  --dw-page-gradient: linear-gradient(180deg, #fcf8f1 0%, #f4efe7 55%, #ece5d8 100%);
  --dw-page-radial-1: rgba(217, 107, 61, 0.18);
  --dw-page-radial-2: rgba(73, 92, 132, 0.10);
  --dw-grid: rgba(30, 39, 52, 0.05);
  --dw-surface: rgba(255, 253, 249, 0.86);
  --dw-surface-strong: rgba(255, 252, 247, 0.96);
  --dw-surface-soft: rgba(255, 255, 255, 0.50);
  --dw-line: rgba(88, 74, 60, 0.12);
  --dw-line-strong: rgba(88, 74, 60, 0.18);
  --dw-text: #1f2530;
  --dw-muted: #5f6978;
  --dw-muted-soft: #788292;
  --dw-accent: #d96b3d;
  --dw-accent-strong: #c65c30;
  --dw-accent-soft: rgba(217, 107, 61, 0.14);
  --dw-accent-line: rgba(217, 107, 61, 0.24);
  --dw-accent-contrast: #8b3b1b;
  --dw-pill-bg: rgba(31, 37, 48, 0.04);
  --dw-shadow: 0 22px 55px rgba(63, 43, 24, 0.10);
  --dw-green: #2f9d6a;
  --dw-amber: #c58714;
  --dw-high: #db7c1f;
  --dw-red: #c84545;
  --dw-blue: #4768b7;
}

html[data-dw-theme="dark"] {
  --dw-bg: #070b12;
  --dw-bg-soft: #0b1220;
  --dw-page-gradient: linear-gradient(180deg, #0d1018 0%, #091018 42%, #070b12 100%);
  --dw-page-radial-1: rgba(217, 107, 61, 0.16);
  --dw-page-radial-2: rgba(73, 92, 132, 0.16);
  --dw-grid: rgba(255, 255, 255, 0.028);
  --dw-surface: rgba(15, 22, 35, 0.82);
  --dw-surface-strong: rgba(17, 26, 41, 0.94);
  --dw-surface-soft: rgba(255, 255, 255, 0.03);
  --dw-line: rgba(255, 255, 255, 0.08);
  --dw-line-strong: rgba(255, 255, 255, 0.14);
  --dw-text: #edf0f8;
  --dw-muted: #98a5bf;
  --dw-muted-soft: #71809d;
  --dw-accent: #d96b3d;
  --dw-accent-strong: #e07a4f;
  --dw-accent-soft: rgba(217, 107, 61, 0.14);
  --dw-accent-line: rgba(217, 107, 61, 0.30);
  --dw-accent-contrast: #ffd0bb;
  --dw-pill-bg: rgba(255, 255, 255, 0.04);
  --dw-shadow: 0 26px 60px rgba(3, 7, 18, 0.42);
  --dw-green: #45c48d;
  --dw-amber: #e0b35e;
  --dw-high: #f08b39;
  --dw-red: #ff7a7a;
  --dw-blue: #6ea8ff;
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

body {
  background:
    radial-gradient(circle at top, var(--dw-page-radial-1), transparent 34%),
    radial-gradient(circle at 12% 18%, var(--dw-page-radial-2), transparent 22%),
    var(--dw-page-gradient);
  color: var(--dw-text);
  font-family: "Sora", sans-serif;
  -webkit-font-smoothing: antialiased;
}

body::before {
  content: "";
  position: fixed;
  inset: 0;
  background-image:
    linear-gradient(var(--dw-grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--dw-grid) 1px, transparent 1px);
  background-size: 72px 72px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.65), transparent 92%);
  pointer-events: none;
  opacity: 0.78;
}

a {
  color: inherit;
  text-decoration: none;
}

code,
.dw-mono {
  font-family: "IBM Plex Mono", monospace;
}

.dw-main-content {
  width: min(1240px, calc(100% - 32px));
  max-width: 1240px;
  margin: 0 auto;
  padding: 122px 0 36px;
  box-sizing: border-box;
}

.dw-shell {
  position: relative;
}

.dw-panel {
  position: relative;
  border: 1px solid var(--dw-line);
  border-radius: 28px;
  background: linear-gradient(180deg, var(--dw-surface), var(--dw-surface-strong));
  box-shadow: var(--dw-shadow);
  overflow: hidden;
  backdrop-filter: blur(22px);
  -webkit-backdrop-filter: blur(22px);
}

.dw-panel::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.05), transparent 26%);
  pointer-events: none;
}

.dw-panel-soft {
  border: 1px solid var(--dw-line);
  border-radius: 20px;
  background: var(--dw-surface-soft);
}

.dw-page-header {
  padding: 28px 30px;
}

.dw-topbar {
  position: fixed;
  inset: 18px 0 auto;
  z-index: 100;
  padding: 0 16px;
}

.dw-topbar-shell {
  width: min(1240px, 100%);
  margin: 0 auto;
  padding: 14px 18px;
  border-radius: 24px;
  border: 1px solid var(--dw-line);
  background: color-mix(in srgb, var(--dw-surface-strong) 82%, transparent);
  box-shadow: 0 18px 44px rgba(2, 7, 17, 0.16);
  backdrop-filter: blur(22px);
  -webkit-backdrop-filter: blur(22px);
}

.dw-brand {
  display: inline-flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.dw-brand-mark {
  width: 46px;
  height: 46px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 16px;
  border: 1px solid var(--dw-accent-line);
  background: linear-gradient(180deg, color-mix(in srgb, var(--dw-accent) 18%, transparent), color-mix(in srgb, var(--dw-accent) 8%, transparent));
  flex-shrink: 0;
}

.dw-brand-copy {
  min-width: 0;
}

.dw-brand-title {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--dw-text);
}

.dw-brand-title span {
  color: var(--dw-accent);
}

.dw-brand-tag {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid var(--dw-line);
  background: var(--dw-pill-bg);
  color: var(--dw-muted);
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.dw-brand-subtitle {
  color: var(--dw-muted);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.dw-nav-link {
  color: var(--dw-muted);
  font-size: 13px;
  font-weight: 500;
  padding: 10px 14px;
  border-radius: 14px;
  transition: color 0.18s ease, background 0.18s ease, border-color 0.18s ease;
}

.dw-nav-link:hover,
.dw-nav-link-active {
  color: var(--dw-text);
  background: var(--dw-pill-bg);
}

.dw-theme-button,
.dw-header-button {
  border: 1px solid var(--dw-line) !important;
  border-radius: 16px !important;
  background: var(--dw-pill-bg) !important;
  color: var(--dw-text) !important;
  min-height: 44px;
}

.dw-header-button {
  padding: 0 16px;
}

.dw-theme-button .q-icon {
  color: var(--dw-accent);
}

.dw-eyebrow {
  color: var(--dw-accent);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.dw-title {
  color: var(--dw-text);
}

.dw-text {
  color: var(--dw-text);
}

.dw-muted {
  color: var(--dw-muted);
}

.dw-body {
  color: var(--dw-muted);
  font-size: 14px;
  line-height: 1.8;
}

.dw-accent-text {
  color: var(--dw-accent);
}

.dw-warning-text {
  color: var(--dw-amber);
}

.dw-danger-text {
  color: var(--dw-red);
}

.dw-success-text {
  color: var(--dw-green);
}

.dw-dashboard-hero {
  padding: 30px;
}

.dw-dashboard-headline {
  font-size: clamp(32px, 5vw, 52px);
  line-height: 1.02;
  letter-spacing: -0.05em;
  font-weight: 800;
}

.dw-dashboard-headline .dw-gradient {
  background: linear-gradient(180deg, #ffffff 0%, color-mix(in srgb, var(--dw-text) 78%, transparent) 92%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

html[data-dw-theme="light"] .dw-dashboard-headline .dw-gradient {
  background: linear-gradient(180deg, #1f2530 0%, #59606d 92%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.dw-hero-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 999px;
  border: 1px solid var(--dw-line);
  background: var(--dw-pill-bg);
  color: var(--dw-text);
  font-size: 12px;
}

.dw-preview {
  padding: 24px;
  border-radius: 28px;
  border: 1px solid var(--dw-line);
  background: linear-gradient(180deg, color-mix(in srgb, var(--dw-bg-soft) 78%, transparent), color-mix(in srgb, var(--dw-bg) 96%, transparent));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.dw-preview-kicker {
  color: var(--dw-accent);
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-weight: 600;
}

.dw-preview-title {
  color: var(--dw-text);
  font-size: 23px;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.04em;
}

.dw-preview-score {
  width: 92px;
  height: 92px;
  border-radius: 24px;
  border: 1px solid var(--dw-accent-line);
  background: linear-gradient(180deg, color-mix(in srgb, var(--dw-accent) 16%, transparent), color-mix(in srgb, var(--dw-accent) 8%, transparent));
}

.dw-preview-score-value {
  color: var(--dw-text);
  font-size: 34px;
  line-height: 1;
  font-weight: 700;
}

.dw-preview-score-label {
  color: var(--dw-accent-contrast);
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.dw-preview-body,
.dw-mini-stat {
  border: 1px solid var(--dw-line);
  background: var(--dw-surface-soft);
}

.dw-preview-body {
  padding: 16px 18px;
  border-radius: 18px;
  color: color-mix(in srgb, var(--dw-text) 86%, transparent);
  font-size: 13px;
  line-height: 1.8;
}

.dw-preview-callout {
  margin-top: 14px;
  padding: 14px 16px;
  border-left: 3px solid color-mix(in srgb, var(--dw-red) 48%, transparent);
  border-radius: 0 14px 14px 0;
  background: color-mix(in srgb, var(--dw-red) 12%, transparent);
  color: color-mix(in srgb, var(--dw-red) 84%, white);
  font-size: 13px;
}

.dw-mini-stat {
  padding: 14px;
  border-radius: 18px;
}

.dw-mini-stat strong {
  display: block;
  color: var(--dw-text);
  font-size: 18px;
  letter-spacing: -0.03em;
  margin-bottom: 4px;
}

.dw-mini-stat span {
  color: var(--dw-muted);
  font-size: 11px;
  letter-spacing: 0.10em;
  text-transform: uppercase;
}

.dw-stat-card {
  min-height: 150px;
  padding: 24px;
}

.dw-stat-value {
  color: var(--dw-text);
  font-size: 42px;
  line-height: 1;
  letter-spacing: -0.05em;
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

.dw-history-card {
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.dw-history-card:hover {
  transform: translateY(-2px);
  border-color: var(--dw-line-strong);
}

.dw-history-card-selected {
  border-color: var(--dw-accent-line);
  box-shadow: 0 0 0 1px var(--dw-accent-line), var(--dw-shadow);
}

.dw-search-input .q-field__control,
.q-field--outlined .q-field__control,
.q-select .q-field__control,
.q-uploader {
  border-radius: 18px !important;
  border-color: var(--dw-line) !important;
  background: var(--dw-surface-soft) !important;
  color: var(--dw-text) !important;
}

.dw-search-input .q-field__native,
.q-field__native,
.q-field__input,
.q-field__label,
.q-uploader__title,
.q-uploader__subtitle {
  color: var(--dw-text) !important;
}

.dw-search-input .q-field__native::placeholder,
.q-field__native::placeholder {
  color: var(--dw-muted) !important;
  opacity: 1;
}

.q-field--outlined .q-field__control:before,
.q-field--outlined .q-field__control:after {
  border-color: var(--dw-line-strong) !important;
}

.q-field--focused .q-field__control:before,
.q-field--focused .q-field__control:after {
  border-color: var(--dw-accent) !important;
}

.q-checkbox__inner,
.q-toggle__inner,
.q-radio__inner {
  color: var(--dw-accent) !important;
}

.q-linear-progress {
  border-radius: 999px;
  overflow: hidden;
}

.q-dialog__inner .dw-panel {
  max-width: min(760px, 92vw);
}

.dw-danger-button {
  color: var(--dw-red) !important;
}

@media (max-width: 960px) {
  .dw-main-content {
    width: min(100%, calc(100% - 24px));
    padding-top: 136px;
  }
}

@media (max-width: 820px) {
  .dw-topbar {
    inset: 12px 0 auto;
    padding: 0 12px;
  }

  .dw-topbar-shell {
    padding: 12px 14px;
    gap: 12px;
  }

  .dw-brand-subtitle,
  .dw-brand-tag {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    transition: none !important;
  }
}
</style>
"""


def apply_theme() -> None:
    """Inject the shared visual theme for app surfaces."""
    ui.add_head_html(_THEME_HEAD_HTML)
    ui.add_head_html(_THEME_CSS)
    ui.colors(primary="#D96B3D")


def build_brand_lockup(*, href: str = "/", compact: bool = False) -> None:
    """Render the shared DeployWhisper logo lockup."""
    with ui.element("a").props(f"href={href}").classes("dw-brand no-underline"):
        with ui.element("span").classes("dw-brand-mark"):
            ui.html(_BRAND_MARK_SVG)
        with ui.column().classes("dw-brand-copy gap-[2px]"):
            with ui.row().classes("items-center gap-3 flex-wrap"):
                ui.html('<span class="dw-brand-title">Deploy<span>Whisper</span></span>')
                ui.html('<span class="dw-brand-tag">AI intelligence</span>')
            if not compact:
                ui.label("Advisory deployment intelligence").classes("dw-brand-subtitle")


def build_navigation_shell(active: str) -> None:
    """Render the shared top navigation shell."""
    nav_items = (
        ("Dashboard", "/", "dashboard"),
        ("History", "/history", "history"),
        ("Settings", "/settings", "settings"),
    )

    with ui.element("header").classes("dw-topbar"):
        with ui.row().classes("dw-topbar-shell w-full items-center gap-4 flex-wrap justify-between"):
            build_brand_lockup(compact=True)
            with ui.row().classes("items-center gap-1 flex-wrap grow justify-center max-md:w-full"):
                for label, href, key in nav_items:
                    classes = "dw-nav-link no-underline"
                    if active == key:
                        classes += " dw-nav-link-active"
                    ui.link(label, href).classes(classes)
            with ui.row().classes("items-center gap-2 ml-auto max-md:w-full max-md:justify-end"):
                ui.button(
                    "Theme",
                    icon="contrast",
                    on_click=lambda: ui.run_javascript("window.dwToggleTheme && window.dwToggleTheme()"),
                ).props("flat no-caps").classes("dw-theme-button")


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
            ui.button(back_label, on_click=lambda: ui.navigate.to(back_href)).props("flat no-caps").classes(
                "dw-header-button"
            )
