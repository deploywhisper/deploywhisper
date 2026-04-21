"""Blast radius panel rendering."""

from __future__ import annotations

from analysis.blast_radius import BlastRadiusResult
from nicegui import ui
from ui.formatters.risk_labels import risk_token


def _hex_to_rgba(color: str, alpha: float) -> str:
    stripped = color.lstrip("#")
    red = int(stripped[0:2], 16)
    green = int(stripped[2:4], 16)
    blue = int(stripped[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {alpha:.2f})"


def _empty_annotation_text(result: BlastRadiusResult) -> str:
    if result.warning:
        return result.warning
    return "No downstream dependencies found."


def _plotly_figure(result: BlastRadiusResult, *, severity: str) -> dict:
    severity_color = risk_token(severity)["color"]
    nodes = result.affected
    if not nodes:
        return {
            "data": [],
            "layout": {
                "height": 260,
                "margin": {"l": 20, "r": 20, "t": 20, "b": 20},
                "paper_bgcolor": "rgba(0,0,0,0)",
                "plot_bgcolor": "rgba(0,0,0,0)",
                "xaxis": {"visible": False},
                "yaxis": {"visible": False},
                "annotations": [
                    {
                        "text": _empty_annotation_text(result),
                        "showarrow": False,
                        "font": {"size": 14},
                    }
                ],
            },
        }

    ordered = sorted(nodes, key=lambda node: (node.depth, node.label.lower()))
    x_values = [node.depth for node in ordered]
    y_values = list(range(len(ordered), 0, -1))
    marker_colors = [
        _hex_to_rgba(severity_color, 0.92 if node.depth == 0 else 0.42)
        for node in ordered
    ]
    marker_sizes = [22 if node.depth == 0 else 18 for node in ordered]

    return {
        "data": [
            {
                "type": "scatter",
                "mode": "markers+text",
                "x": x_values,
                "y": y_values,
                "text": [node.label for node in ordered],
                "textposition": "middle right",
                "hovertemplate": [
                    f"{node.label}<br>{'Directly affected' if node.depth == 0 else 'Transitively affected'}<extra></extra>"
                    for node in ordered
                ],
                "marker": {
                    "size": marker_sizes,
                    "color": marker_colors,
                    "line": {"color": severity_color, "width": 1.5},
                },
            }
        ],
        "layout": {
            "height": max(260, 110 + len(ordered) * 38),
            "margin": {"l": 40, "r": 180, "t": 18, "b": 18},
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "showlegend": False,
            "xaxis": {
                "tickmode": "array",
                "tickvals": [0, 1],
                "ticktext": ["Direct", "Transitive"],
                "gridcolor": "rgba(148, 165, 184, 0.12)",
                "zeroline": False,
            },
            "yaxis": {"visible": False},
        },
        "config": {"displayModeBar": False, "responsive": True},
    }


def render_blast_radius_panel(result: BlastRadiusResult, *, severity: str) -> None:
    """Render a blast-radius graph plus textual equivalent."""
    direct_text = f"{result.direct_count} services directly affected, {result.transitive_count} transitively"
    with ui.card().classes("w-full dw-panel shadow-none"):
        ui.label("Blast radius").classes("text-lg font-medium dw-text")
        ui.label(direct_text).classes("text-sm dw-muted")
        ui.label(
            "Legend: depth 0 = directly affected, depth 1+ = transitively affected."
        ).classes("text-xs dw-muted")
        if result.warning:
            ui.label(result.warning).classes("text-xs dw-warning-text")

        ui.plotly(_plotly_figure(result, severity=severity)).classes("w-full")

        with ui.column().classes("w-full gap-1 mt-2"):
            ui.label("Text equivalent").classes("text-xs font-semibold dw-muted")
            ui.label(direct_text).classes("text-sm dw-text")
