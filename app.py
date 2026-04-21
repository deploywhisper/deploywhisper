"""NiceGUI + FastAPI runtime entry point for DeployWhisper."""

from __future__ import annotations

from contextlib import asynccontextmanager
from html import escape

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


@fastapi_app.get("/reports/{report_id}/artifacts", include_in_schema=False)
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
