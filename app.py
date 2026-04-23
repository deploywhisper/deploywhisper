"""NiceGUI + FastAPI runtime entry point for DeployWhisper."""

from __future__ import annotations

from contextlib import asynccontextmanager
from html import escape
import hashlib
import hmac

from fastapi import Form, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from nicegui import app as fastapi_app
from nicegui import ui
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import RedirectResponse

from api.errors import (
    ApiError,
    api_error_handler,
    http_error_envelope_handler,
    validation_error_handler,
)
from api.routes.analyses import router as analyses_router
from api.routes.health import router as health_router
from config import settings
from logging_config import configure_logging
from models.database import init_db
from services.artifact_snapshot_service import load_report_artifact
from services.report_service import fetch_analysis_report, fetch_shared_analysis_report
from ui.routes.dashboard import build_dashboard

configure_logging()


def _ensure_nicegui_config_defaults() -> None:
    """Populate runtime defaults needed before ui.run initializes NiceGUI config."""
    defaults = {
        "binding_refresh_interval": 0.1,
        "cache_control_directives": "no-cache",
        "prod_js": False,
        "title": settings.app_name,
        "viewport": "width=device-width, initial-scale=1",
        "favicon": None,
        "dark": False,
        "language": "en-US",
        "endpoint_documentation": "none",
        "message_history_length": 1000,
        "quasar_config": {},
        "reconnect_timeout": 5.0,
        "reload": False,
        "show_welcome_message": False,
        "socket_io_js_extra_headers": {},
        "socket_io_js_query_params": {},
        "socket_io_js_transports": None,
        "tailwind": True,
        "unocss": False,
        "vue_config_script": None,
    }
    for name, value in defaults.items():
        if not hasattr(fastapi_app.config, name):
            setattr(fastapi_app.config, name, value)


_ensure_nicegui_config_defaults()
fastapi_app.add_exception_handler(ApiError, api_error_handler)
fastapi_app.add_exception_handler(RequestValidationError, validation_error_handler)
fastapi_app.add_exception_handler(StarletteHTTPException, http_error_envelope_handler)
fastapi_app.include_router(health_router)
fastapi_app.include_router(analyses_router)


_original_lifespan = fastapi_app.router.lifespan_context


@asynccontextmanager
async def lifespan(app):
    """Compose NiceGUI startup/shutdown with DeployWhisper app initialization."""
    async with _original_lifespan(app):
        init_db()
        yield


fastapi_app.router.lifespan_context = lifespan


@fastapi_app.get("/api/v1", include_in_schema=False)
def versioned_api_docs_redirect() -> RedirectResponse:
    """Redirect the version root to the Swagger UI entrypoint."""
    return RedirectResponse(url="/api/v1/docs")


@fastapi_app.get("/api/v1/openapi.json", include_in_schema=False)
def versioned_openapi_document() -> JSONResponse:
    """Expose the generated OpenAPI document under the versioned API namespace."""
    return JSONResponse(content=fastapi_app.openapi())


@fastapi_app.get("/api/v1/docs", include_in_schema=False)
def versioned_swagger_ui() -> HTMLResponse:
    """Expose Swagger UI for the versioned API surface."""
    return get_swagger_ui_html(
        openapi_url="/api/v1/openapi.json",
        title=f"{settings.app_name} API Docs",
    )


@fastapi_app.get("/api/v1/redoc", include_in_schema=False)
def versioned_redoc_ui() -> HTMLResponse:
    """Expose ReDoc for the versioned API surface."""
    return get_redoc_html(
        openapi_url="/api/v1/openapi.json",
        title=f"{settings.app_name} API ReDoc",
    )


@fastapi_app.get("/openapi.json", include_in_schema=False)
def openapi_document() -> JSONResponse:
    """Expose the generated OpenAPI document for compatibility consumers."""
    return JSONResponse(content=fastapi_app.openapi())


def _shared_report_prompt_html(report_id: int, *, invalid_password: bool) -> str:
    message = (
        "Incorrect password. Try again."
        if invalid_password
        else "This shared report requires a password."
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>Shared DeployWhisper report {report_id}</title>"
        "<style>"
        "body{margin:0;background:#f4efe7;color:#18202b;font-family:ui-sans-serif,system-ui,sans-serif;}"
        "main{max-width:560px;margin:72px auto;padding:32px;background:#fff;border-radius:20px;"
        "box-shadow:0 18px 48px rgba(24,32,43,0.08);}"
        "h1{margin:0 0 12px;font-size:28px;line-height:1.2;}"
        "p{margin:0 0 18px;color:#5e697b;line-height:1.6;}"
        "label{display:block;font-weight:600;margin-bottom:8px;}"
        "input{width:100%;padding:12px 14px;border:1px solid #d6deeb;border-radius:12px;font-size:16px;}"
        "button{margin-top:16px;padding:12px 16px;border:none;border-radius:12px;background:#d96b3d;color:#fff;font-weight:700;cursor:pointer;}"
        ".error{color:#a03636;font-weight:600;}"
        "</style></head><body><main>"
        "<h1>Shared DeployWhisper report</h1>"
        f"<p class='{'error' if invalid_password else ''}'>{escape(message)}</p>"
        f"<form method='post' action='/reports/{report_id}/unlock'>"
        "<label for='password'>Password required</label>"
        "<input id='password' name='password' type='password' autocomplete='current-password' />"
        "<button type='submit'>Open shared report</button>"
        "</form></main></body></html>"
    )


def _share_cookie_name(report_id: int) -> str:
    return f"dw_share_{report_id}"


def _share_cookie_value(report: dict) -> str:
    return hashlib.sha256(
        (
            f"{report['id']}|{report.get('share_password_hash') or ''}|"
            f"{report.get('share_password_salt') or ''}"
        ).encode("utf-8")
    ).hexdigest()


def _has_valid_share_cookie(report: dict, request: Request) -> bool:
    if not report.get("share_password_hash"):
        return True
    cookie_value = request.cookies.get(_share_cookie_name(int(report["id"])))
    expected = _share_cookie_value(report)
    return bool(cookie_value) and hmac.compare_digest(cookie_value, expected)


def _share_cookie_secure(report: dict) -> bool:
    share_url = str((report.get("share") or {}).get("share_url") or "")
    return share_url.startswith("https://")


def _shared_report_html(report: dict) -> str:
    findings = report.get("findings") or []
    files_analyzed = report.get("audit", {}).get("files_analyzed") or []
    findings_html = (
        "".join(
            "<li><strong>{severity}</strong>: {title}<br><span>{description}</span></li>".format(
                severity=escape(str(finding.get("severity", "")).upper()),
                title=escape(str(finding.get("title", ""))),
                description=escape(str(finding.get("description", ""))),
            )
            for finding in findings[:5]
        )
        or "<li>No findings were persisted for this report.</li>"
    )
    files_html = (
        "".join(f"<li>{escape(str(file_name))}</li>" for file_name in files_analyzed)
        or "<li>No file metadata was persisted for this report.</li>"
    )
    share = report.get("share") or {}
    redaction_note = (
        "<p class='note'>File names are redacted for this shared view.</p>"
        if share.get("redact_filenames")
        else ""
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>Shared DeployWhisper report #{int(report['id'])}</title>"
        "<style>"
        "body{margin:0;background:#f4efe7;color:#18202b;font-family:ui-sans-serif,system-ui,sans-serif;}"
        "main{max-width:980px;margin:0 auto;padding:40px 24px 64px;}"
        ".hero,.panel{background:#fff;border-radius:20px;box-shadow:0 18px 48px rgba(24,32,43,0.08);padding:24px;margin-bottom:20px;}"
        ".eyebrow{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#7b8596;font-weight:700;}"
        "h1{margin:8px 0 12px;font-size:32px;line-height:1.15;}"
        "p,li{line-height:1.6;color:#455163;}"
        ".badge{display:inline-block;padding:6px 10px;border-radius:999px;background:#eff4fb;margin-right:8px;font-weight:700;}"
        ".score{font-size:42px;font-weight:800;color:#d96b3d;}"
        "ul{padding-left:20px;}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;}"
        ".note{margin-top:8px;color:#8b5a2b;font-weight:600;}"
        "a{color:#d96b3d;text-decoration:none;}"
        "</style></head><body><main>"
        "<section class='hero'>"
        "<div class='eyebrow'>Shared DeployWhisper report</div>"
        "<p>Analysis report</p>"
        f"<h1>{escape(str(report.get('top_risk') or 'Analysis report'))}</h1>"
        f"<span class='badge'>{escape(str(report.get('severity', '')).upper())}</span>"
        f"<span class='badge'>{escape(str(report.get('recommendation', '')).upper())}</span>"
        f"<p class='score'>{int(report.get('risk_score') or 0)}</p>"
        f"<p>{escape(str(report.get('narrative_opening') or report.get('parse_summary') or ''))}</p>"
        "</section>"
        "<section class='panel'><div class='grid'>"
        f"<div><strong>Created</strong><p>{escape(str(report.get('created_at') or ''))}</p></div>"
        f"<div><strong>Share URL</strong><p><a href='{escape(str(share.get('share_url') or ''))}'>{escape(str(share.get('share_url') or ''))}</a></p></div>"
        f"<div><strong>Blast radius</strong><p>{escape(str(report.get('blast_radius', {}).get('direct_count', 0)))} direct / {escape(str(report.get('blast_radius', {}).get('transitive_count', 0)))} transitive</p></div>"
        f"<div id='rollback'><strong>Rollback</strong><p>{escape(str(report.get('rollback_plan', {}).get('complexity', 'low')).upper())} · {escape(str(report.get('rollback_plan', {}).get('complexity_score', 1)))} / 5</p></div>"
        "</div></section>"
        "<section class='panel'><h2>Findings</h2><ul>"
        f"{findings_html}"
        "</ul></section>"
        "<section class='panel'><h2>Files analyzed</h2>"
        f"{redaction_note}<ul>{files_html}</ul></section>"
        "</main></body></html>"
    )


@fastapi_app.get("/reports/{report_id}", include_in_schema=False)
def shared_report_view(
    request: Request,
    report_id: int,
) -> HTMLResponse:
    """Render one report via a read-only public sharing route."""
    report = fetch_analysis_report(report_id)
    if report is None:
        raise StarletteHTTPException(status_code=404, detail="Report not found")
    password_required = bool(report.get("share_password_hash"))
    if password_required and not _has_valid_share_cookie(report, request):
        return HTMLResponse(
            content=_shared_report_prompt_html(
                report_id,
                invalid_password=False,
            )
        )
    shared_report = fetch_shared_analysis_report(
        report_id,
        bypass_password=password_required,
    )
    if shared_report is None:
        raise StarletteHTTPException(status_code=404, detail="Report not found")
    return HTMLResponse(content=_shared_report_html(shared_report))


@fastapi_app.post("/reports/{report_id}/unlock", include_in_schema=False)
def unlock_shared_report(report_id: int, password: str = Form(...)) -> RedirectResponse:
    """Validate a shared-report password and issue an HttpOnly access cookie."""
    shared_report = fetch_shared_analysis_report(report_id, password=password)
    if shared_report is None:
        return HTMLResponse(
            content=_shared_report_prompt_html(report_id, invalid_password=True),
            status_code=401,
        )
    report = fetch_analysis_report(report_id)
    if report is None:
        raise StarletteHTTPException(status_code=404, detail="Report not found")
    response = RedirectResponse(url=f"/reports/{report_id}", status_code=303)
    response.set_cookie(
        _share_cookie_name(report_id),
        _share_cookie_value(report),
        httponly=True,
        path=f"/reports/{report_id}",
        secure=_share_cookie_secure(shared_report),
        samesite="lax",
    )
    return response


@fastapi_app.get("/reports/{report_id}/artifacts", include_in_schema=False)
def shared_report_artifact_view(report_id: int, name: str) -> HTMLResponse:
    """Public share URLs never expose raw artifact snapshots."""
    raise StarletteHTTPException(status_code=404, detail="Artifact not found")


@fastapi_app.get("/history/{report_id}/artifacts", include_in_schema=False)
def report_artifact_view(
    report_id: int, name: str, line: int | None = None
) -> HTMLResponse:
    """Render one uploaded artifact for report-local evidence drill-down."""
    snapshot = load_report_artifact(report_id, name)
    if snapshot is None:
        raise StarletteHTTPException(status_code=404, detail="Artifact not found")
    highlighted_line = str(line) if line is not None and line > 0 else None
    rows: list[str] = []
    content_lines = snapshot.content.splitlines() or [""]
    for line_number, raw_line in enumerate(content_lines, start=1):
        active_class = " active" if highlighted_line == str(line_number) else ""
        rows.append(
            '<tr id="L{line_number}" class="artifact-line{active_class}">'
            '<td class="artifact-gutter"><a href="#L{line_number}">{line_number}</a></td>'
            '<td class="artifact-code"><pre>{raw_line}</pre></td>'
            "</tr>".format(
                line_number=line_number,
                active_class=active_class,
                raw_line=escape(raw_line),
            )
        )
    return HTMLResponse(
        content=(
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{escape(snapshot.artifact_name)} · DeployWhisper</title>"
            "<style>"
            "body{margin:0;background:#0b111c;color:#edf0f8;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;}"
            "main{max-width:1200px;margin:0 auto;padding:24px;}"
            "a{color:#f08b39;text-decoration:none;}"
            "h1{font:600 20px/1.3 Sora,ui-sans-serif,system-ui;margin:0 0 8px;}"
            "p{font:400 14px/1.5 Sora,ui-sans-serif,system-ui;color:#98a5bf;margin:0 0 16px;}"
            "table{width:100%;border-collapse:collapse;border:1px solid rgba(255,255,255,0.08);}"
            ".artifact-gutter{width:72px;padding:0 12px;text-align:right;vertical-align:top;background:#091018;border-right:1px solid rgba(255,255,255,0.06);}"
            ".artifact-gutter a{display:block;padding:10px 0;color:#71809d;}"
            ".artifact-code{padding:0;}"
            ".artifact-code pre{margin:0;padding:10px 16px;white-space:pre-wrap;word-break:break-word;}"
            ".artifact-line.active{background:rgba(217,107,61,0.12);}"
            ".artifact-line.active .artifact-gutter a{color:#ffd0bb;font-weight:700;}"
            "</style></head><body><main>"
            f"<p><a href='/history'>&larr; Back to history</a></p>"
            f"<h1>{escape(snapshot.artifact_name)}</h1>"
            f"<p>Report {report_id} artifact snapshot stored locally for review.</p>"
            f"<table><tbody>{''.join(rows)}</tbody></table>"
            "</main></body></html>"
        )
    )


@ui.page("/")
def index() -> None:
    """Render the dashboard shell placeholder."""
    build_dashboard()


def create_app():
    """Expose the shared FastAPI runtime for tests and ASGI adapters."""
    return fastapi_app


def run() -> None:
    """Start the NiceGUI application."""
    ui.run(
        host=settings.app_host,
        port=settings.app_port,
        title=settings.app_name,
        dark=False,
        reload=False,
        show=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    run()
