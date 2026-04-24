"""Public skills browser pages."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode

from fastapi import Request
from nicegui import ui
from starlette.exceptions import HTTPException as StarletteHTTPException

from services.skill_registry_service import (
    SkillRegistryEntry,
    SkillRegistrySort,
    fetch_skill_registry_entry,
    fetch_skill_registry_page,
    fetch_skill_registry_versions,
)
from ui.theme import apply_theme, build_navigation_shell, build_page_header

_BROWSER_CSS = """
<style>
.dw-skills-shell {
  display: grid;
  gap: 22px;
}

.dw-skills-hero {
  padding: 34px;
  display: grid;
  gap: 22px;
  background:
    radial-gradient(circle at 85% 18%, rgba(217, 107, 61, 0.18), transparent 30%),
    linear-gradient(140deg, color-mix(in srgb, var(--dw-surface-strong) 92%, transparent), color-mix(in srgb, var(--dw-surface) 88%, transparent));
}

.dw-skills-hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(280px, 0.9fr);
  gap: 24px;
  align-items: end;
}

.dw-skills-display {
  font-size: clamp(2.7rem, 6vw, 4.8rem);
  line-height: 0.94;
  font-weight: 800;
  letter-spacing: -0.06em;
  color: var(--dw-text);
  max-width: 8ch;
}

.dw-skills-display span {
  color: var(--dw-accent);
}

.dw-skills-body {
  color: var(--dw-muted);
  font-size: 15px;
  line-height: 1.8;
  max-width: 52ch;
}

.dw-skills-hero-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.dw-skills-stat {
  border: 1px solid var(--dw-line);
  border-radius: 18px;
  padding: 16px;
  background: color-mix(in srgb, var(--dw-surface-soft) 88%, transparent);
}

.dw-skills-stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--dw-text);
}

.dw-skills-stat-label {
  margin-top: 4px;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dw-muted);
}

.dw-skills-controls {
  display: grid;
  grid-template-columns: minmax(0, 2fr) repeat(3, minmax(180px, 1fr));
  gap: 14px;
  align-items: end;
}

.dw-skills-catalog {
  display: grid;
  gap: 14px;
}

.dw-skill-row {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(0, 0.85fr) auto;
  gap: 20px;
  align-items: center;
  padding: 20px 24px;
  border: 1px solid var(--dw-line);
  border-radius: 22px;
  background: linear-gradient(180deg, var(--dw-surface), var(--dw-surface-strong));
  box-shadow: var(--dw-shadow);
  transition: transform 180ms ease, border-color 180ms ease;
}

.dw-skill-row:hover {
  transform: translateY(-2px);
  border-color: var(--dw-accent-line);
}

.dw-skill-row-title {
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.04em;
  color: var(--dw-text);
}

.dw-skill-row-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 10px;
  color: var(--dw-muted);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.dw-skill-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.dw-skill-tag {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--dw-line);
  border-radius: 999px;
  padding: 5px 9px;
  font-size: 11px;
  color: var(--dw-muted);
  background: var(--dw-pill-bg);
}

.dw-skill-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.dw-skill-metric-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--dw-text);
}

.dw-skill-metric-label {
  margin-top: 2px;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dw-muted);
}

.dw-skill-command {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--dw-line);
  border-radius: 16px;
  padding: 12px 14px;
  background: var(--dw-pill-bg);
  color: var(--dw-text);
  font-family: "IBM Plex Mono", monospace;
  font-size: 13px;
}

.dw-skill-detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.9fr);
  gap: 22px;
}

.dw-skill-detail-stack {
  display: grid;
  gap: 18px;
}

.dw-skill-section {
  padding: 24px;
}

.dw-skill-version-list {
  display: grid;
  gap: 10px;
}

.dw-skill-version-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--dw-line);
  padding-bottom: 10px;
}

.dw-skill-version-row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.dw-skill-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border-radius: 999px;
  padding: 6px 12px;
  background: var(--dw-accent-soft);
  color: var(--dw-accent-contrast);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.dw-empty-note {
  padding: 24px;
  border: 1px dashed var(--dw-line-strong);
  border-radius: 22px;
  color: var(--dw-muted);
  background: var(--dw-surface-soft);
}

@media (max-width: 900px) {
  .dw-skills-hero-grid,
  .dw-skills-controls,
  .dw-skill-row,
  .dw-skill-detail-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .dw-skills-hero,
  .dw-skill-section,
  .dw-skill-row {
    padding: 20px;
  }

  .dw-skill-metrics,
  .dw-skills-hero-stats {
    grid-template-columns: 1fr;
  }
}
</style>
"""


def _format_updated_at(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.strftime("%b %d, %Y")


def _query_value(request: Request, key: str) -> str | None:
    value = str(request.query_params.get(key) or "").strip()
    return value or None


def _fetch_catalog(
    *,
    search: str | None = None,
    tool: str | None = None,
    author: str | None = None,
    sort: SkillRegistrySort = "popularity",
) -> list[SkillRegistryEntry]:
    items: list[SkillRegistryEntry] = []
    page_number = 1
    page_size = 100
    total_count = 0

    while True:
        page = fetch_skill_registry_page(
            search=search,
            tool=tool,
            author=author,
            sort=sort,
            page=page_number,
            page_size=page_size,
        )
        if page_number == 1:
            total_count = page.total_count
        items.extend(page.items)
        if len(items) >= total_count or not page.items:
            return items
        page_number += 1


def _browser_options() -> tuple[list[str], list[str]]:
    catalog = _fetch_catalog(sort="popularity")
    tools = sorted({item.tool for item in catalog})
    authors = sorted({item.author for item in catalog})
    return tools, authors


def _navigate_with_filters(
    *,
    search: str,
    tool: str,
    author: str,
    sort: str,
) -> None:
    params: list[tuple[str, str]] = []
    if search.strip():
        params.append(("search", search.strip()))
    if tool.strip():
        params.append(("tool", tool.strip()))
    if author.strip():
        params.append(("author", author.strip()))
    if sort.strip():
        params.append(("sort", sort.strip()))
    query = f"?{urlencode(params)}" if params else ""
    ui.navigate.to(f"/skills{query}")


def _render_skill_row(skill: SkillRegistryEntry) -> None:
    with ui.element("a").props(f"href=/skills/{skill.id}").classes("no-underline"):
        with ui.element("article").classes("dw-skill-row"):
            with ui.column().classes("gap-0 min-w-0"):
                ui.label(skill.name).classes("dw-skill-row-title")
                ui.label(skill.description).classes("dw-skills-body")
                with ui.element("div").classes("dw-skill-row-meta"):
                    ui.label(skill.tool)
                    ui.label(skill.author)
                    ui.label(f"Updated {_format_updated_at(skill.updated_at)}")
                    ui.label(
                        f"{skill.available_versions} version{'s' if skill.available_versions != 1 else ''}"
                    )
                with ui.element("div").classes("dw-skill-tags"):
                    for tag in skill.tags[:4]:
                        ui.label(tag).classes("dw-skill-tag")
            with ui.element("div").classes("dw-skill-metrics"):
                for value, label in (
                    (str(skill.install_count), "Installs"),
                    (
                        (
                            f"{round(skill.test_results.pass_rate * 100):.0f}%"
                            if skill.test_results
                            else "n/a"
                        ),
                        "Pass rate",
                    ),
                    (str(skill.active_issue_count), "Active issues"),
                ):
                    with ui.column().classes("gap-0"):
                        ui.label(value).classes("dw-skill-metric-value")
                        ui.label(label).classes("dw-skill-metric-label")
            with ui.column().classes("items-start gap-3"):
                ui.label("Install ready").classes("dw-skill-chip")
                ui.label(skill.install_command).classes("dw-skill-command")


@ui.page("/skills")
def skills_browser_page(request: Request) -> None:
    apply_theme()
    ui.add_head_html(_BROWSER_CSS)
    build_navigation_shell("skills")

    tools, authors = _browser_options()
    search = _query_value(request, "search") or ""
    tool = _query_value(request, "tool") or ""
    author = _query_value(request, "author") or ""
    sort = (_query_value(request, "sort") or "popularity").lower()
    sort_value: SkillRegistrySort = "recency" if sort == "recency" else "popularity"

    catalog = _fetch_catalog(
        search=search or None,
        tool=tool or None,
        author=author or None,
        sort=sort_value,
    )

    with ui.column().classes("dw-main-content dw-shell dw-skills-shell"):
        with ui.card().classes("dw-panel shadow-none dw-skills-hero"):
            with ui.element("div").classes("dw-skills-hero-grid"):
                with ui.column().classes("gap-5"):
                    ui.label("Marketplace").classes("dw-eyebrow")
                    ui.html(
                        '<div class="dw-skills-display">DeployWhisper <span>skills atlas</span></div>'
                    )
                    ui.label(
                        "Browse the registry before you install anything. Search by domain, filter by owner, and compare readiness signals from the same catalog the CLI consumes."
                    ).classes("dw-skills-body")
                with ui.element("div").classes("dw-skills-hero-stats"):
                    for value, label in (
                        (str(len(catalog)), "Visible skills"),
                        (
                            str(sum(item.install_count for item in catalog)),
                            "Catalog installs",
                        ),
                        (
                            str(sum(item.active_issue_count for item in catalog)),
                            "Open issues",
                        ),
                        (
                            str(
                                sum(
                                    1
                                    for item in catalog
                                    if item.test_results
                                    and item.test_results.status == "passing"
                                )
                            ),
                            "Passing harnesses",
                        ),
                    ):
                        with ui.element("div").classes("dw-skills-stat"):
                            ui.label(value).classes("dw-skills-stat-value")
                            ui.label(label).classes("dw-skills-stat-label")

            with ui.element("div").classes("dw-skills-controls"):
                search_input = (
                    ui.input(
                        value=search, placeholder="Search skills, tags, or triggers"
                    )
                    .props("outlined dense clearable")
                    .classes("w-full")
                )
                tool_select = (
                    ui.select(["", *tools], value=tool, label="Tool")
                    .props("outlined dense")
                    .classes("w-full")
                )
                author_select = (
                    ui.select(["", *authors], value=author, label="Author")
                    .props("outlined dense")
                    .classes("w-full")
                )
                sort_select = (
                    ui.select(
                        {"popularity": "Popularity", "recency": "Recency"},
                        value=sort,
                        label="Sort",
                    )
                    .props("outlined dense")
                    .classes("w-full")
                )

                def apply_filters() -> None:
                    _navigate_with_filters(
                        search=str(search_input.value or ""),
                        tool=str(tool_select.value or ""),
                        author=str(author_select.value or ""),
                        sort=str(sort_select.value or "popularity"),
                    )

                search_input.on("keydown.enter", lambda _: apply_filters())
                tool_select.on_value_change(lambda _: apply_filters())
                author_select.on_value_change(lambda _: apply_filters())
                sort_select.on_value_change(lambda _: apply_filters())

        with ui.card().classes("dw-panel shadow-none dw-page-header"):
            build_page_header(
                eyebrow="Catalog",
                title="Search the current skills registry",
                subtitle=(
                    "Shared registry analytics are refreshed daily and exposed through "
                    "the same metadata contract the browser and CLI consume."
                ),
            )

        with ui.column().classes("dw-skills-catalog"):
            if not catalog:
                ui.label(
                    "No skills match the current search and filter combination."
                ).classes("dw-empty-note")
            for item in catalog:
                _render_skill_row(item)


@ui.page("/skills/{skill_id}")
def skill_detail_page(skill_id: str) -> None:
    skill = fetch_skill_registry_entry(skill_id)
    if skill is None:
        raise StarletteHTTPException(status_code=404, detail="Skill not found")

    versions = fetch_skill_registry_versions(skill_id)

    apply_theme()
    ui.add_head_html(_BROWSER_CSS)
    build_navigation_shell("skills")

    with ui.column().classes("dw-main-content dw-shell dw-skills-shell"):
        with ui.card().classes("dw-panel shadow-none dw-skills-hero"):
            build_page_header(
                eyebrow=skill.tool,
                title=skill.name,
                subtitle=skill.description,
                back_href="/skills",
                back_label="Back to skills",
            )
            with ui.element("div").classes("dw-skill-detail-grid"):
                with ui.column().classes("dw-skill-detail-stack"):
                    ui.label(skill.install_command).classes("dw-skill-command")
                    with ui.element("div").classes("dw-skills-hero-stats"):
                        for value, label in (
                            (str(skill.install_count), "Installs"),
                            (str(skill.active_issue_count), "Active issues"),
                            (_format_updated_at(skill.updated_at), "Last updated"),
                            (
                                (
                                    f"{round(skill.test_results.pass_rate * 100):.0f}%"
                                    if skill.test_results
                                    else "n/a"
                                ),
                                "Pass rate",
                            ),
                        ):
                            with ui.element("div").classes("dw-skills-stat"):
                                ui.label(value).classes("dw-skills-stat-value")
                                ui.label(label).classes("dw-skills-stat-label")

                with ui.element("div").classes("dw-skills-hero-stats"):
                    with ui.element("div").classes("dw-skills-stat"):
                        ui.label(skill.author).classes("dw-skills-stat-value text-lg")
                        ui.label("Author").classes("dw-skills-stat-label")
                    with ui.element("div").classes("dw-skills-stat"):
                        ui.label(str(skill.available_versions)).classes(
                            "dw-skills-stat-value text-lg"
                        )
                        ui.label("Tracked versions").classes("dw-skills-stat-label")
                    with ui.element("div").classes("dw-skills-stat"):
                        ui.label(
                            _format_updated_at(skill.analytics_updated_at)
                        ).classes("dw-skills-stat-value text-lg")
                        ui.label("Analytics refreshed").classes("dw-skills-stat-label")

        with ui.element("div").classes("dw-skill-detail-grid"):
            with ui.column().classes("dw-skill-detail-stack"):
                with ui.card().classes("dw-panel shadow-none dw-skill-section"):
                    ui.label("Contributors").classes("dw-eyebrow")
                    for contributor in skill.contributors:
                        ui.label(contributor).classes("dw-skills-body")

                with ui.card().classes("dw-panel shadow-none dw-skill-section"):
                    ui.label("Version history").classes("dw-eyebrow")
                    with ui.element("div").classes("dw-skill-version-list"):
                        for version in versions:
                            with ui.element("div").classes("dw-skill-version-row"):
                                with ui.column().classes("gap-1"):
                                    ui.label(version.version).classes(
                                        "text-lg font-semibold dw-text"
                                    )
                                    ui.label(
                                        f"{version.author} · {_format_updated_at(version.updated_at)}"
                                    ).classes("dw-muted text-sm")
                                ui.label(
                                    "Current" if version.is_current else "Archived"
                                ).classes("dw-skill-chip")

            with ui.column().classes("dw-skill-detail-stack"):
                with ui.card().classes("dw-panel shadow-none dw-skill-section"):
                    ui.label("Ready to install").classes("dw-eyebrow")
                    ui.label(
                        "Use the shared CLI installer to pull the exact registry artifact shown here."
                    ).classes("dw-skills-body")
                    ui.label(skill.install_command).classes("dw-skill-command")
                    with ui.element("div").classes("dw-skill-tags"):
                        for tag in skill.tags:
                            ui.label(tag).classes("dw-skill-tag")

                with ui.card().classes("dw-panel shadow-none dw-skill-section"):
                    ui.label("Registry snapshot").classes("dw-eyebrow")
                    ui.label(
                        "This page reflects the same source-of-truth metadata, daily analytics snapshot, and version history used by the shared registry and installer surfaces."
                    ).classes("dw-skills-body")
