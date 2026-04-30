"""Shared UI theme helpers."""

from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from services.project_service import (
    get_active_project,
    has_active_project_selection,
    list_projects,
    ProjectRecord,
    set_active_project,
)
from ui.components.project_workspace_switcher import (
    build_project_combobox,
    open_create_project_dialog,
    project_context_heading,
    project_context_meta,
    project_context_summary,
)

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

_THEME_HEAD_HTML = r"""
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
  padding: 224px 0 36px;
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

.dw-header-stack {
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

.dw-topbar-primary {
  width: 100%;
  align-items: center;
  gap: 16px;
}

.dw-topbar-nav {
  min-width: 0;
}

.dw-topbar-utilities {
  align-items: center;
}

.dw-project-bar {
  width: min(1240px, 100%);
  margin: 12px auto 0;
  padding: 18px 20px;
  border-radius: 26px;
  border: 1px solid var(--dw-line);
  background: linear-gradient(180deg, var(--dw-surface), var(--dw-surface-strong));
  box-shadow: var(--dw-shadow);
  backdrop-filter: blur(22px);
  -webkit-backdrop-filter: blur(22px);
}

.dw-project-filter-copy {
  min-width: 220px;
  flex: 1 1 260px;
}

.dw-project-filter-kicker {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dw-muted);
}

.dw-project-filter-title {
  color: var(--dw-text);
  font-size: 17px;
  line-height: 1.2;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.dw-project-filter-meta {
  color: var(--dw-muted);
  font-size: 12px;
  line-height: 1.5;
}

.dw-project-filter-controls {
  width: min(100%, 560px);
  flex: 1 1 420px;
  align-items: stretch;
  justify-content: flex-end;
  gap: 10px;
  overflow: visible;
}

.dw-project-bar,
.dw-project-combobox {
  position: relative;
  overflow: visible;
}

.dw-project-search-input {
  min-width: 320px;
  flex: 1 1 360px;
}

.dw-project-search-input .q-field__control {
  min-height: 52px;
  border-radius: 18px;
  background: var(--dw-surface-soft);
  border-color: transparent !important;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}

.dw-project-search-input .q-field--outlined .q-field__control:before {
  border-color: var(--dw-line);
}

.dw-project-search-input .q-field--focused .q-field__control {
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--dw-accent) 14%, transparent);
}

.dw-project-search-input .q-field__native,
.dw-project-search-input .q-field__input,
.dw-project-search-input .q-field__label,
.dw-project-search-input .q-field__marginal {
  color: var(--dw-text) !important;
}

.dw-project-search-input .q-field__label {
  color: var(--dw-muted) !important;
}

.dw-project-search-input .q-field__append .q-icon,
.dw-project-search-input .q-field__prepend .q-icon {
  color: var(--dw-accent);
}

.dw-project-dropdown-anchor {
  position: absolute;
  top: calc(100% + 10px);
  left: 0;
  right: 0;
  z-index: 1300;
}

.dw-project-dropdown-panel {
  border: 1px solid var(--dw-line);
  border-radius: 20px;
  background: color-mix(in srgb, var(--dw-surface-strong) 96%, transparent);
  box-shadow: 0 22px 46px rgba(2, 7, 17, 0.24);
  overflow: hidden;
}

.dw-project-dropdown-list {
  max-height: min(360px, calc(100vh - 220px));
  overflow-y: auto;
  padding: 6px;
}

.dw-project-feedback-row {
  padding: 16px 18px;
}

.dw-project-feedback-copy,
.dw-project-empty-copy {
  color: var(--dw-muted);
  font-size: 12px;
  line-height: 1.55;
}

.dw-project-option-button {
  display: block;
  width: 100%;
  min-height: 76px;
  padding: 12px 14px;
  border-radius: 14px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background 0.16s ease, transform 0.16s ease;
  user-select: none;
}

.dw-project-option-button:hover,
.dw-project-option-active {
  background: var(--dw-pill-bg);
}

.dw-project-option-selected {
  box-shadow: inset 0 0 0 1px var(--dw-accent-line);
}

.dw-project-option-primary {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--dw-text);
  line-height: 1.35;
  white-space: normal;
}

.dw-project-option-meta {
  display: block;
  margin-top: 2px;
  color: var(--dw-muted);
  font-size: 12px;
  line-height: 1.45;
  white-space: normal;
  overflow-wrap: anywhere;
}

.dw-project-option-check {
  color: var(--dw-accent);
  margin-top: 2px;
}

.dw-project-empty-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--dw-text);
}

.dw-project-match {
  background: color-mix(in srgb, var(--dw-accent) 22%, transparent);
  color: var(--dw-text);
  border-radius: 6px;
  padding: 0 2px;
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

.dw-verdict-card {
  margin-top: 12px;
  padding: 22px 24px;
}

.dw-verdict-score-block {
  min-width: 124px;
  padding: 16px 18px;
  border-radius: 20px;
  border: 1px solid var(--dw-accent-line);
  background: linear-gradient(180deg, color-mix(in srgb, var(--dw-accent) 16%, transparent), color-mix(in srgb, var(--dw-accent) 7%, transparent));
}

.dw-verdict-score-value {
  color: var(--dw-text);
  font-size: clamp(34px, 4vw, 46px);
  line-height: 0.95;
  font-weight: 800;
  letter-spacing: -0.06em;
}

.dw-verdict-score-label {
  color: var(--dw-accent-contrast);
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.dw-verdict-top-risk {
  color: var(--dw-text);
  font-size: clamp(20px, 2vw, 26px);
  line-height: 1.25;
  font-weight: 600;
  letter-spacing: -0.04em;
  max-width: 18ch;
}

.dw-findings-row {
  border-radius: 18px;
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
  width: 84px;
}

.dw-findings-col-confidence {
  width: 150px;
}

.dw-findings-col-actions {
  width: 116px;
}

.dw-findings-grid {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr) 88px 88px 150px 116px;
  gap: 12px;
  align-items: start;
}

.dw-findings-header {
  border: 1px solid var(--dw-line);
  border-radius: 20px;
  background: color-mix(in srgb, var(--dw-surface-soft) 88%, transparent);
}

.dw-findings-header .q-btn {
  justify-content: flex-start;
}

.dw-findings-row-card {
  border: 1px solid var(--dw-line);
}

.dw-findings-row-base {
  background: color-mix(in srgb, var(--dw-surface-soft) 92%, transparent);
}

.dw-findings-row-alt {
  background: color-mix(in srgb, var(--dw-surface-soft) 74%, transparent);
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
  background: linear-gradient(90deg, var(--dw-accent), var(--dw-green));
}

.dw-report-score-block {
  min-width: 140px;
  padding: 18px 20px;
  border-radius: 22px;
  border: 1px solid var(--dw-line);
  background: color-mix(in srgb, var(--dw-surface-soft) 90%, transparent);
  text-align: center;
}

.dw-detail-list-row {
  border: 1px solid var(--dw-line);
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

.dw-topology-uploader {
  width: 100%;
}

.dw-topology-uploader .q-uploader {
  width: 100%;
  border: 1px solid var(--dw-line-strong) !important;
  box-shadow: none !important;
  overflow: hidden;
}

.dw-topology-uploader .q-uploader__header {
  padding: 12px 16px;
}

.dw-topology-uploader .q-uploader__list {
  padding: 10px;
}

.dw-topology-uploader .q-uploader__file {
  border-radius: 14px;
  background: color-mix(in srgb, var(--dw-surface) 92%, transparent);
  border: 1px solid var(--dw-line);
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
    padding-top: 262px;
  }

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
  .dw-header-stack {
    inset: 12px 0 auto;
    padding: 0 12px;
  }

  .dw-topbar-shell {
    padding: 12px 14px;
    gap: 12px;
  }

  .dw-project-bar {
    margin-top: 10px;
    padding: 16px 16px 18px;
  }

  .dw-topbar-primary {
    align-items: flex-start;
  }

  .dw-topbar-nav {
    width: 100%;
    justify-content: flex-start !important;
  }

  .dw-project-filter-controls {
    width: 100%;
    justify-content: stretch;
  }

  .dw-project-search-input {
    min-width: 0;
  }

  .dw-brand-subtitle,
  .dw-brand-tag {
    display: none;
  }

  .dw-findings-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .dw-main-content {
    padding-top: 308px;
  }

  .dw-project-filter-controls {
    flex-direction: column;
    align-items: stretch;
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
                ui.html(
                    '<span class="dw-brand-title">Deploy<span>Whisper</span></span>'
                )
                ui.html('<span class="dw-brand-tag">AI intelligence</span>')
            if not compact:
                ui.label("Advisory deployment intelligence").classes(
                    "dw-brand-subtitle"
                )


def build_navigation_shell(
    active: str,
    *,
    on_project_change: Callable[[ProjectRecord], None] | None = None,
) -> Callable[[], None]:
    """Render the shared top navigation shell."""
    nav_items = (
        ("Dashboard", "/", "dashboard"),
        ("Skills", "/skills", "skills"),
        ("History", "/history", "history"),
        ("Settings", "/settings", "settings"),
    )

    with ui.element("div").classes("dw-header-stack"):
        with ui.column().classes("dw-topbar-shell w-full"):
            with ui.row().classes("dw-topbar-primary w-full justify-between flex-wrap"):
                build_brand_lockup(compact=True)
                with ui.row().classes(
                    "dw-topbar-nav items-center gap-1 flex-wrap grow justify-center max-md:w-full"
                ):
                    for label, href, key in nav_items:
                        classes = "dw-nav-link no-underline"
                        if active == key:
                            classes += " dw-nav-link-active"
                        ui.link(label, href).classes(classes)
                with ui.row().classes(
                    "dw-topbar-utilities items-center gap-2 ml-auto max-md:w-full max-md:justify-end"
                ):
                    ui.button(
                        "Theme",
                        icon="contrast",
                        on_click=lambda: ui.run_javascript(
                            "window.dwToggleTheme && window.dwToggleTheme()"
                        ),
                    ).props("flat no-caps").classes("dw-theme-button")

        @ui.refreshable
        def render_project_bar() -> None:
            saved_selection = has_active_project_selection()
            active_project = get_active_project()
            current_project_id = (
                active_project.id if saved_selection and active_project else None
            )
            with ui.card().classes("dw-project-bar shadow-none"):
                with ui.row().classes(
                    "w-full items-end justify-between gap-4 flex-wrap"
                ):
                    with ui.column().classes("dw-project-filter-copy gap-[3px]"):
                        ui.label(project_context_heading()).classes(
                            "dw-project-filter-kicker"
                        )
                        ui.label(project_context_summary(active_project)).classes(
                            "dw-project-filter-title"
                        )
                        ui.label(
                            project_context_meta(
                                has_saved_selection=saved_selection,
                                active_project=active_project,
                            )
                        ).classes("dw-project-filter-meta")
                    with ui.row().classes("dw-project-filter-controls flex-wrap"):
                        build_project_combobox(
                            projects=list_projects(),
                            current_project_id=current_project_id,
                            on_select=lambda project: handle_project_change(project),
                        )
                        ui.button(
                            "New project",
                            on_click=lambda: open_create_project_dialog(
                                on_created=lambda created: handle_project_change(
                                    created
                                )
                            ),
                            color="primary",
                        ).props("flat no-caps").classes("dw-theme-button")

        def handle_project_change(project: ProjectRecord) -> None:
            set_active_project(project.id)
            render_project_bar.refresh()
            if on_project_change is not None:
                on_project_change(project)

        render_project_bar()
    return lambda: render_project_bar.refresh()


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
