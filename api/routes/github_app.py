"""GitHub App adapter routes."""

from __future__ import annotations

from html import escape

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from api.errors import ApiError, ApiRoute
from config import settings
from integrations.github.app_service import (
    GitHubAppConfigurationError,
    GitHubAppProjectScopeError,
    GitHubAppRequestError,
    build_github_app_oauth_url,
    complete_github_app_oauth,
    get_github_app_config,
    handle_github_app_webhook,
    verify_github_webhook_signature,
)

router = APIRouter(
    prefix="/api/v1/github/app",
    tags=["github-app"],
    route_class=ApiRoute,
)


@router.get("/oauth/start", include_in_schema=False)
def github_app_oauth_start(
    return_to: str | None = Query(default=None),
) -> RedirectResponse:
    try:
        authorize_url = build_github_app_oauth_url(return_to=return_to)
    except GitHubAppConfigurationError as exc:
        raise ApiError(
            status_code=405,
            code="github_app_oauth_disabled",
            message=str(exc),
        ) from exc
    return RedirectResponse(url=authorize_url, status_code=302)


@router.get("/oauth/callback", include_in_schema=False)
def github_app_oauth_callback(
    code: str,
    state: str,
) -> HTMLResponse:
    try:
        result = complete_github_app_oauth(code=code, state=state)
    except (GitHubAppConfigurationError, GitHubAppRequestError) as exc:
        raise ApiError(
            status_code=400,
            code="github_app_oauth_failed",
            message=str(exc),
        ) from exc
    install_url = result.install_url or result.marketplace_url or "#"
    return_to = result.state_return_to or "/"
    return HTMLResponse(
        content=(
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>DeployWhisper GitHub App authorization</title>"
            "<style>"
            "body{margin:0;background:#f4efe7;color:#18202b;font-family:ui-sans-serif,system-ui,sans-serif;}"
            "main{max-width:720px;margin:72px auto;padding:32px;background:#fff;border-radius:20px;box-shadow:0 18px 48px rgba(24,32,43,0.08);}"
            "h1{margin:0 0 12px;font-size:30px;line-height:1.2;}"
            "p{margin:0 0 16px;color:#5e697b;line-height:1.7;}"
            "a.button{display:inline-flex;align-items:center;justify-content:center;padding:12px 16px;border-radius:12px;background:#d96b3d;color:#fff;font-weight:700;text-decoration:none;margin-right:12px;}"
            "a.secondary{background:#fff;color:#d96b3d;border:1px solid rgba(24,32,43,0.12);}"
            "</style></head><body><main>"
            "<h1>GitHub App authorization complete</h1>"
            "<p>Your DeployWhisper GitHub App authorization succeeded. Continue to the installation step to connect the app to your team or organization.</p>"
            f"<p>Token type: {escape(result.token_type)}"
            + (f" · Scope: {escape(result.scope)}" if result.scope else "")
            + "</p>"
            f"<a class='button' href='{escape(install_url)}'>Continue to GitHub App installation</a>"
            f"<a class='button secondary' href='{escape(return_to)}'>Return to DeployWhisper</a>"
            "</main></body></html>"
        )
    )


@router.post("/webhook")
async def github_app_webhook(request: Request) -> dict[str, object]:
    config = get_github_app_config()
    payload_bytes = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_github_webhook_signature(payload_bytes, signature, config=config):
        raise ApiError(
            status_code=403,
            code="github_app_webhook_forbidden",
            message="GitHub App webhook signature verification failed.",
        )
    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise ApiError(
            status_code=400,
            code="github_app_webhook_invalid_json",
            message="GitHub App webhook payload must be valid JSON.",
        ) from exc
    event_name = request.headers.get("X-GitHub-Event", "").strip() or "unknown"
    try:
        result = handle_github_app_webhook(
            event_name=event_name,
            payload=payload,
            config=config,
        )
    except GitHubAppProjectScopeError as exc:
        code = getattr(exc, "code", "invalid_project_reference")
        return {
            "data": {
                "event": event_name,
                "action": str(payload.get("action") or "").strip() or None,
                "handled": True,
                "automatic_analysis_triggered": False,
                "check_run_id": None,
                "report_id": None,
                "report_url": None,
                "marketplace_url": config.marketplace_url,
                "install_url": config.install_url,
                "advisory_only": True,
                "note": f"{code}: {exc}",
            },
            "meta": {
                "api_version": "v1",
                "app_name": settings.app_name,
            },
        }
    except GitHubAppConfigurationError as exc:
        raise ApiError(
            status_code=405,
            code="github_app_unconfigured",
            message=str(exc),
        ) from exc
    except GitHubAppRequestError as exc:
        raise ApiError(
            status_code=502,
            code="github_app_upstream_failed",
            message=str(exc),
        ) from exc

    return {
        "data": {
            "event": result.event,
            "action": result.action,
            "handled": result.handled,
            "automatic_analysis_triggered": result.automatic_analysis_triggered,
            "check_run_id": result.check_run_id,
            "report_id": result.report_id,
            "report_url": result.report_url,
            "marketplace_url": config.marketplace_url,
            "install_url": config.install_url,
            "advisory_only": True,
            "note": result.note,
        },
        "meta": {
            "api_version": "v1",
            "app_name": settings.app_name,
        },
    }
