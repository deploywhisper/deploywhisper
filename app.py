"""FastAPI runtime entry point for DeployWhisper."""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from html import escape
import logging
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse, RedirectResponse

from api.errors import (
    ApiError,
    api_error_handler,
    http_error_envelope_handler,
    validation_error_handler,
)
from api.routes.analyses import router as analyses_router
from api.routes.deployments import router as deployments_router
from api.routes.github_app import router as github_app_router
from api.routes.health import router as health_router
from api.routes.incidents import router as incidents_router
from api.routes.projects import router as projects_router
from api.routes.settings import router as context_router
from api.routes.settings import settings_router
from api.routes.skills import router as skills_router
from api.routes.stats import router as stats_router
from config import settings
from logging_config import configure_logging
from models.database import init_db
from services.artifact_snapshot_service import load_report_artifact
from services.backtesting_service import run_due_weekly_backtests
from services.skill_manifest_service import build_skill_manifest_v1_schema
from services.topology_service import run_due_topology_drift_checks

configure_logging()
logger = logging.getLogger(__name__)
TOPOLOGY_DRIFT_SCHEDULER_POLL_SECONDS = 60
FRONTEND_DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist"
FRONTEND_INDEX_PATH = FRONTEND_DIST_DIR / "index.html"


class SPAStaticFiles(StaticFiles):
    """Serve built SPA assets and fall back to index.html for client routes."""

    async def get_response(self, path: str, scope: dict[str, Any]):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and FRONTEND_INDEX_PATH.is_file():
                return FileResponse(FRONTEND_INDEX_PATH)
            raise


def _fallback_spa_shell() -> HTMLResponse:
    """Return a minimal SPA shell when frontend/dist is absent in test contexts."""
    return HTMLResponse(
        content=(
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{escape(settings.app_name)}</title>"
            '</head><body><div id="root"></div></body></html>'
        )
    )


async def _topology_drift_scheduler_loop(stop_event: asyncio.Event) -> None:
    """Run topology drift checks on a lightweight polling loop."""
    while not stop_event.is_set():
        try:
            run_due_topology_drift_checks()
        except Exception:
            logger.exception("Topology drift scheduler pass failed.")
        try:
            run_due_weekly_backtests()
        except Exception:
            logger.exception("Weekly backtesting pass failed.")
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=TOPOLOGY_DRIFT_SCHEDULER_POLL_SECONDS,
            )
        except TimeoutError:
            continue


@asynccontextmanager
async def lifespan(app):
    """Initialize local storage and background maintenance for the app."""
    init_db()
    stop_event = asyncio.Event()
    drift_scheduler_task = asyncio.create_task(
        _topology_drift_scheduler_loop(stop_event)
    )
    try:
        yield
    finally:
        stop_event.set()
        drift_scheduler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await drift_scheduler_task


fastapi_app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)
fastapi_app.add_exception_handler(ApiError, api_error_handler)
fastapi_app.add_exception_handler(RequestValidationError, validation_error_handler)
fastapi_app.add_exception_handler(StarletteHTTPException, http_error_envelope_handler)
fastapi_app.include_router(health_router)
fastapi_app.include_router(analyses_router)
fastapi_app.include_router(deployments_router)
fastapi_app.include_router(github_app_router)
fastapi_app.include_router(projects_router)
fastapi_app.include_router(context_router)
fastapi_app.include_router(settings_router)
fastapi_app.include_router(skills_router)
fastapi_app.include_router(stats_router)
fastapi_app.include_router(incidents_router)


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


@fastapi_app.get("/schemas/skill-manifest-v1.json", include_in_schema=False)
def skill_manifest_schema_document() -> JSONResponse:
    """Publish the versioned skill manifest schema for author tooling."""
    return JSONResponse(
        content=build_skill_manifest_v1_schema(),
        media_type="application/schema+json",
    )


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
            "body{margin:0;background:#f4f4f5;color:#0a0a0a;font-family:'Plus Jakarta Sans',ui-sans-serif,system-ui,sans-serif;}"
            "main{max-width:1200px;margin:0 auto;padding:24px;}"
            "a{color:#ff6900;text-decoration:none;font-weight:700;}"
            "h1{font:700 20px/1.3 'Plus Jakarta Sans',ui-sans-serif,system-ui;margin:0 0 8px;}"
            "p{font:500 14px/1.5 'Plus Jakarta Sans',ui-sans-serif,system-ui;color:#71717b;margin:0 0 16px;}"
            "table{width:100%;border-collapse:collapse;border:1px solid #e4e4e7;background:#fff;border-radius:12px;overflow:hidden;}"
            ".artifact-gutter{width:72px;padding:0 12px;text-align:right;vertical-align:top;background:#f9fafb;border-right:1px solid #e4e4e7;}"
            ".artifact-gutter a{display:block;padding:10px 0;color:#71717b;}"
            ".artifact-code{padding:0;}"
            ".artifact-code pre{margin:0;padding:10px 16px;white-space:pre-wrap;word-break:break-word;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;}"
            ".artifact-line.active{background:rgba(255,105,0,0.10);}"
            ".artifact-line.active .artifact-gutter a{color:#ff6900;font-weight:700;}"
            "</style></head><body><main>"
            f"<p><a href='/history'>&larr; Back to history</a></p>"
            f"<h1>{escape(snapshot.artifact_name)}</h1>"
            f"<p>Report {report_id} artifact snapshot stored locally for review.</p>"
            f"<table><tbody>{''.join(rows)}</tbody></table>"
            "</main></body></html>"
        )
    )


def _redirect_target_with_query(path: str, request: Request) -> str:
    query = request.url.query
    return f"{path}?{query}" if query else path


@fastapi_app.api_route("/app", methods=["GET", "HEAD"], include_in_schema=False)
def legacy_app_root_redirect(request: Request) -> RedirectResponse:
    """Redirect the coexistence-era SPA mount to the cutover root route."""
    return RedirectResponse(
        url=_redirect_target_with_query("/", request),
        status_code=308,
    )


@fastapi_app.api_route(
    "/app/{path:path}", methods=["GET", "HEAD"], include_in_schema=False
)
def legacy_app_route_redirect(path: str, request: Request) -> RedirectResponse:
    """Redirect `/app/...` client routes to their Phase 7 root paths."""
    target = f"/{path.lstrip('/')}" if path else "/"
    return RedirectResponse(
        url=_redirect_target_with_query(target, request),
        status_code=308,
    )


@fastapi_app.api_route(
    "/history/{report_id}", methods=["GET", "HEAD"], include_in_schema=False
)
def legacy_history_report_redirect(report_id: int) -> RedirectResponse:
    """Redirect retired report detail links to the React report route."""
    return RedirectResponse(url=f"/reports/{report_id}", status_code=308)


@fastapi_app.api_route(
    "/history/{report_id}/compare", methods=["GET", "HEAD"], include_in_schema=False
)
def legacy_history_compare_redirect(report_id: int) -> RedirectResponse:
    """Redirect legacy comparison links to the React comparison route."""
    return RedirectResponse(
        url=f"/reports/{report_id}?compare=previous#report-comparison",
        status_code=308,
    )


if FRONTEND_DIST_DIR.is_dir():
    fastapi_app.mount(
        "/",
        SPAStaticFiles(directory=FRONTEND_DIST_DIR, html=True),
        name="frontend",
    )
else:

    @fastapi_app.api_route(
        "/{path:path}", methods=["GET", "HEAD"], include_in_schema=False
    )
    def missing_frontend_spa_fallback(path: str) -> HTMLResponse:
        """Serve client routes in tests when the built SPA has not been produced."""
        blocked_prefixes = ("api/", "schemas/")
        blocked_paths = {"api", "schemas", "openapi.json"}
        if path in blocked_paths or path.startswith(blocked_prefixes):
            raise StarletteHTTPException(status_code=404, detail="Not Found")
        if "." in path.rsplit("/", maxsplit=1)[-1]:
            raise StarletteHTTPException(status_code=404, detail="Not Found")
        return _fallback_spa_shell()


def create_app():
    """Expose the shared FastAPI runtime for tests and ASGI adapters."""
    return fastapi_app


def run() -> None:
    """Start the FastAPI application."""
    uvicorn.run(
        fastapi_app,
        host=settings.app_host,
        port=settings.app_port,
    )


if __name__ in {"__main__", "__mp_main__"}:
    run()
