"""GitHub App adapter services."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
from typing import Any
from urllib import error, parse, request

from config import settings
from services.project_service import ProjectResolutionError, resolve_project_reference
from services.analysis_service import AnalysisPersistenceError, analyze_uploaded_files
from services.intake_service import (
    MAX_TOTAL_UPLOAD_BYTES,
    build_pending_analysis,
    total_upload_bytes,
    uniquify_artifact_names,
)
from services.report_service import build_share_report_link

DEFAULT_GITHUB_API_BASE_URL = "https://api.github.com"
DEFAULT_GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
DEFAULT_GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
DEFAULT_CHECK_RUN_NAME = "DeployWhisper / Risk Analysis"
PULL_REQUEST_TRIGGER_ACTIONS = {"opened", "reopened", "synchronize"}
_STATE_MAX_AGE_SECONDS = 600
_UPLOAD_LIMIT_MESSAGE = (
    "Total artifact payload exceeds the 50 MB analysis-session limit."
)
_PROJECT_SCOPE_ERROR_CODES = {
    "missing_project_scope",
    "project_not_found",
    "conflicting_project_reference",
    "invalid_project_reference",
}


class GitHubAppConfigurationError(RuntimeError):
    """Raised when required GitHub App configuration is missing."""


class GitHubAppProjectScopeError(RuntimeError):
    """Raised when GitHub analysis cannot resolve an explicit project scope."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GitHubAppRequestError(RuntimeError):
    """Raised when a GitHub API request fails."""


@dataclass(frozen=True)
class GitHubAppConfig:
    enabled: bool
    app_id: str | None
    slug: str | None
    client_id: str | None
    client_secret: str | None
    webhook_secret: str | None
    private_key_pem: str | None
    api_base_url: str
    authorize_url: str
    access_token_url: str
    app_base_url: str | None
    automatic_pr_events_enabled: bool
    checks_enabled: bool

    @property
    def install_url(self) -> str | None:
        if not self.slug:
            return None
        return f"https://github.com/apps/{self.slug}/installations/new"

    @property
    def marketplace_url(self) -> str | None:
        if not self.slug:
            return None
        return f"https://github.com/apps/{self.slug}"

    @property
    def callback_url(self) -> str | None:
        if not self.app_base_url:
            return None
        return self.app_base_url.rstrip("/") + "/api/v1/github/app/oauth/callback"


@dataclass(frozen=True)
class GitHubWebhookResult:
    event: str
    action: str | None
    handled: bool
    automatic_analysis_triggered: bool
    check_run_id: int | None
    report_id: int | None
    report_url: str | None
    note: str
    status: str = "ok"
    code: str | None = None


@dataclass(frozen=True)
class GitHubOAuthResult:
    install_url: str | None
    marketplace_url: str | None
    user_access_token: str
    token_type: str
    scope: str | None
    state_return_to: str | None


def get_github_app_config() -> GitHubAppConfig:
    inline_key = (os.getenv("DEPLOYWHISPER_GITHUB_APP_PRIVATE_KEY") or "").strip()
    private_key_path = (
        os.getenv("DEPLOYWHISPER_GITHUB_APP_PRIVATE_KEY_PATH") or ""
    ).strip()
    private_key_pem = inline_key or _load_private_key_from_path(private_key_path)
    app_base_url = (
        os.getenv("APP_BASE_URL")
        or os.getenv("PUBLIC_APP_URL")
        or settings.app_base_url
        or ""
    ).strip() or None
    return GitHubAppConfig(
        enabled=os.getenv("DEPLOYWHISPER_GITHUB_APP_ENABLED", "false").lower()
        == "true",
        app_id=(os.getenv("DEPLOYWHISPER_GITHUB_APP_ID") or "").strip() or None,
        slug=(os.getenv("DEPLOYWHISPER_GITHUB_APP_SLUG") or "").strip() or None,
        client_id=(os.getenv("DEPLOYWHISPER_GITHUB_APP_CLIENT_ID") or "").strip()
        or None,
        client_secret=(
            os.getenv("DEPLOYWHISPER_GITHUB_APP_CLIENT_SECRET") or ""
        ).strip()
        or None,
        webhook_secret=(
            os.getenv("DEPLOYWHISPER_GITHUB_APP_WEBHOOK_SECRET") or ""
        ).strip()
        or None,
        private_key_pem=private_key_pem,
        api_base_url=(
            os.getenv("DEPLOYWHISPER_GITHUB_APP_API_BASE_URL")
            or DEFAULT_GITHUB_API_BASE_URL
        ).rstrip("/"),
        authorize_url=(
            os.getenv("DEPLOYWHISPER_GITHUB_APP_AUTHORIZE_URL")
            or DEFAULT_GITHUB_AUTHORIZE_URL
        ).rstrip("/"),
        access_token_url=(
            os.getenv("DEPLOYWHISPER_GITHUB_APP_ACCESS_TOKEN_URL")
            or DEFAULT_GITHUB_ACCESS_TOKEN_URL
        ).rstrip("/"),
        app_base_url=app_base_url,
        automatic_pr_events_enabled=os.getenv(
            "DEPLOYWHISPER_GITHUB_APP_PR_EVENTS_ENABLED",
            "false",
        ).lower()
        == "true",
        checks_enabled=os.getenv(
            "DEPLOYWHISPER_GITHUB_APP_CHECKS_ENABLED",
            "true",
        ).lower()
        == "true",
    )


def _load_private_key_from_path(path_value: str) -> str | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _require_runtime_config(config: GitHubAppConfig) -> None:
    missing: list[str] = []
    if not config.enabled:
        missing.append("DEPLOYWHISPER_GITHUB_APP_ENABLED=true")
    if not config.app_id:
        missing.append("DEPLOYWHISPER_GITHUB_APP_ID")
    if not config.private_key_pem:
        missing.append(
            "DEPLOYWHISPER_GITHUB_APP_PRIVATE_KEY or DEPLOYWHISPER_GITHUB_APP_PRIVATE_KEY_PATH"
        )
    if not config.webhook_secret:
        missing.append("DEPLOYWHISPER_GITHUB_APP_WEBHOOK_SECRET")
    if missing:
        raise GitHubAppConfigurationError(
            "GitHub App runtime is not configured: " + ", ".join(missing)
        )


def _require_oauth_config(config: GitHubAppConfig) -> None:
    missing: list[str] = []
    if not config.client_id:
        missing.append("DEPLOYWHISPER_GITHUB_APP_CLIENT_ID")
    if not config.client_secret:
        missing.append("DEPLOYWHISPER_GITHUB_APP_CLIENT_SECRET")
    if not config.callback_url:
        missing.append("APP_BASE_URL or PUBLIC_APP_URL")
    if missing:
        raise GitHubAppConfigurationError(
            "GitHub App OAuth is not configured: " + ", ".join(missing)
        )


def verify_github_webhook_signature(
    payload: bytes,
    signature_header: str | None,
    *,
    config: GitHubAppConfig | None = None,
) -> bool:
    config = config or get_github_app_config()
    secret = (config.webhook_secret or "").encode("utf-8")
    if not secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header[7:], expected)


def build_github_app_oauth_url(
    *,
    return_to: str | None = None,
    config: GitHubAppConfig | None = None,
) -> str:
    config = config or get_github_app_config()
    _require_oauth_config(config)
    state = _encode_oauth_state(
        {"return_to": return_to or "", "nonce": secrets.token_urlsafe(12)},
        secret=str(config.client_secret),
    )
    query = {
        "client_id": str(config.client_id),
        "redirect_uri": str(config.callback_url),
        "state": state,
        "prompt": "select_account",
    }
    return config.authorize_url + "?" + parse.urlencode(query)


def complete_github_app_oauth(
    *,
    code: str,
    state: str,
    config: GitHubAppConfig | None = None,
) -> GitHubOAuthResult:
    config = config or get_github_app_config()
    _require_oauth_config(config)
    state_payload = _decode_oauth_state(state, secret=str(config.client_secret))
    payload = _post_form_json(
        config.access_token_url,
        {
            "client_id": str(config.client_id),
            "client_secret": str(config.client_secret),
            "code": code,
            "redirect_uri": str(config.callback_url),
        },
    )
    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise GitHubAppRequestError(
            "GitHub OAuth callback did not return an access token."
        )
    return GitHubOAuthResult(
        install_url=config.install_url,
        marketplace_url=config.marketplace_url,
        user_access_token=access_token,
        token_type=str(payload.get("token_type") or "bearer"),
        scope=(str(payload.get("scope") or "").strip() or None),
        state_return_to=(str(state_payload.get("return_to") or "").strip() or None),
    )


def handle_github_app_webhook(
    *,
    event_name: str,
    payload: dict[str, Any],
    config: GitHubAppConfig | None = None,
) -> GitHubWebhookResult:
    config = config or get_github_app_config()
    action = str(payload.get("action") or "").strip() or None
    if event_name != "pull_request":
        return GitHubWebhookResult(
            event=event_name,
            action=action,
            handled=False,
            automatic_analysis_triggered=False,
            check_run_id=None,
            report_id=None,
            report_url=None,
            note="Webhook event ignored because Story 3.6 only wires pull_request automation.",
        )
    if not config.automatic_pr_events_enabled:
        return GitHubWebhookResult(
            event=event_name,
            action=action,
            handled=True,
            automatic_analysis_triggered=False,
            check_run_id=None,
            report_id=None,
            report_url=None,
            note="GitHub App pull request automation is disabled by configuration.",
        )
    if action not in PULL_REQUEST_TRIGGER_ACTIONS:
        return GitHubWebhookResult(
            event=event_name,
            action=action,
            handled=True,
            automatic_analysis_triggered=False,
            check_run_id=None,
            report_id=None,
            report_url=None,
            note="Pull request action did not require an automatic analysis run.",
        )
    _require_runtime_config(config)
    installation_id = int(payload.get("installation", {}).get("id") or 0)
    repository = dict(payload.get("repository") or {})
    pull_request = dict(payload.get("pull_request") or {})
    sender = dict(payload.get("sender") or {})
    owner = str(repository.get("owner", {}).get("login") or "").strip()
    repo_name = str(repository.get("name") or "").strip()
    pull_number = int(pull_request.get("number") or payload.get("number") or 0)
    head_sha = str(pull_request.get("head", {}).get("sha") or "").strip()
    actor = str(sender.get("login") or "").strip()
    if (
        not installation_id
        or not owner
        or not repo_name
        or not pull_number
        or not head_sha
    ):
        raise GitHubAppRequestError(
            "GitHub pull_request webhook payload is missing installation, repository, PR number, or head SHA."
        )

    installation_token = _generate_installation_access_token(
        installation_id,
        config=config,
    )
    raw_explicit_project_key = os.getenv("DEPLOYWHISPER_GITHUB_PROJECT_KEY")
    explicit_project_key = (
        raw_explicit_project_key.strip()
        if raw_explicit_project_key is not None
        else None
    )
    project = None
    if explicit_project_key is not None:
        try:
            project = resolve_project_reference(project_key=explicit_project_key)
        except ProjectResolutionError as exc:
            return _project_scope_failure_result(
                event_name=event_name,
                action=action,
                owner=owner,
                repo_name=repo_name,
                head_sha=head_sha,
                installation_token=installation_token,
                code=exc.code,
                message=str(exc),
                config=config,
            )
        except ValueError as exc:
            return _project_scope_failure_result(
                event_name=event_name,
                action=action,
                owner=owner,
                repo_name=repo_name,
                head_sha=head_sha,
                installation_token=installation_token,
                code=getattr(exc, "code", "invalid_project_reference"),
                message=str(exc),
                config=config,
            )
        except RuntimeError as exc:
            raise GitHubAppConfigurationError(str(exc)) from exc

    raw_files = _load_pull_request_artifacts(
        owner=owner,
        repo_name=repo_name,
        pull_number=pull_number,
        head_sha=head_sha,
        installation_token=installation_token,
        api_base_url=config.api_base_url,
    )
    unique_files = uniquify_artifact_names(raw_files)
    pending = build_pending_analysis(unique_files)
    accepted_files = [
        (name, raw_content)
        for (name, raw_content), item in zip(unique_files, pending.items)
        if item.status == "ready"
    ]
    if not accepted_files:
        note = "No supported changed artifacts were available from this pull request."
        check_run_id = (
            _create_check_run(
                owner=owner,
                repo_name=repo_name,
                head_sha=head_sha,
                installation_token=installation_token,
                conclusion="neutral",
                title=DEFAULT_CHECK_RUN_NAME,
                summary=note,
                details_url=None,
                text=_check_run_text(details_url=None),
                api_base_url=config.api_base_url,
            )
            if config.checks_enabled
            else None
        )
        return GitHubWebhookResult(
            event=event_name,
            action=action,
            handled=True,
            automatic_analysis_triggered=False,
            check_run_id=check_run_id,
            report_id=None,
            report_url=None,
            note=note,
        )

    if config.checks_enabled:
        _require_check_run_report_url_config(config)

    if project is None:
        try:
            project = resolve_project_reference(
                repository_name=_repository_reference(owner, repo_name, config=config),
                allow_create=True,
            )
        except ProjectResolutionError as exc:
            return _project_scope_failure_result(
                event_name=event_name,
                action=action,
                owner=owner,
                repo_name=repo_name,
                head_sha=head_sha,
                installation_token=installation_token,
                code=exc.code,
                message=str(exc),
                config=config,
            )
        except ValueError as exc:
            return _project_scope_failure_result(
                event_name=event_name,
                action=action,
                owner=owner,
                repo_name=repo_name,
                head_sha=head_sha,
                installation_token=installation_token,
                code=getattr(exc, "code", "invalid_project_reference"),
                message=str(exc),
                config=config,
            )
        except RuntimeError as exc:
            raise GitHubAppConfigurationError(str(exc)) from exc

    try:
        result = analyze_uploaded_files(
            accepted_files,
            project_key=project.project_key,
            audit_context={
                "source_interface": "github_app",
                "trigger_type": "github_app_pull_request",
                "trigger_id": f"{owner}/{repo_name}#PR-{pull_number}",
                "actor": f"github:{actor}" if actor else "github_app",
            },
        )
    except ProjectResolutionError as exc:
        return _project_scope_failure_result(
            event_name=event_name,
            action=action,
            owner=owner,
            repo_name=repo_name,
            head_sha=head_sha,
            installation_token=installation_token,
            code=exc.code,
            message=str(exc),
            config=config,
        )
    except ValueError as exc:
        code = getattr(exc, "code", None)
        if code not in _PROJECT_SCOPE_ERROR_CODES:
            raise
        return _project_scope_failure_result(
            event_name=event_name,
            action=action,
            owner=owner,
            repo_name=repo_name,
            head_sha=head_sha,
            installation_token=installation_token,
            code=code,
            message=str(exc),
            config=config,
        )
    except AnalysisPersistenceError as exc:
        note = f"{exc} Reason: {exc.public_reason}"
        check_run_id = None
        if config.checks_enabled:
            try:
                check_run_id = _create_check_run(
                    owner=owner,
                    repo_name=repo_name,
                    head_sha=head_sha,
                    installation_token=installation_token,
                    conclusion="failure",
                    title=DEFAULT_CHECK_RUN_NAME,
                    summary=note,
                    details_url=None,
                    text=_check_run_text(details_url=None),
                    api_base_url=config.api_base_url,
                )
            except GitHubAppRequestError:
                note = f"{note} Failure check run could not be created."
        return GitHubWebhookResult(
            event=event_name,
            action=action,
            handled=True,
            automatic_analysis_triggered=False,
            check_run_id=check_run_id,
            report_id=None,
            report_url=None,
            note=note,
            status="failed",
            code=exc.code,
        )
    report_id = int(result.persisted_report["id"])
    report_url = build_share_report_link(report_id)
    check_run_id = None
    if config.checks_enabled:
        report_url = _check_run_details_url(report_id, config=config)
        check_run_id = _create_check_run(
            owner=owner,
            repo_name=repo_name,
            head_sha=head_sha,
            installation_token=installation_token,
            conclusion=_check_run_conclusion(result.assessment.recommendation),
            title=DEFAULT_CHECK_RUN_NAME,
            summary=_check_run_summary(result.persisted_report),
            details_url=report_url,
            text=_check_run_text(details_url=report_url),
            api_base_url=config.api_base_url,
        )
    return GitHubWebhookResult(
        event=event_name,
        action=action,
        handled=True,
        automatic_analysis_triggered=True,
        check_run_id=check_run_id,
        report_id=report_id,
        report_url=report_url,
        note="GitHub App webhook processed and advisory analysis completed.",
    )


def _repository_reference(
    owner: str, repo_name: str, *, config: GitHubAppConfig
) -> str:
    host = parse.urlparse(config.authorize_url).netloc.strip().lower()
    if not host:
        host = parse.urlparse(config.api_base_url).netloc.strip().lower()
    if host == "api.github.com":
        host = "github.com"
    return f"{host}/{owner}/{repo_name}" if host else f"{owner}/{repo_name}"


def _project_scope_failure_result(
    *,
    event_name: str,
    action: str | None,
    owner: str,
    repo_name: str,
    head_sha: str,
    installation_token: str,
    code: str,
    message: str,
    config: GitHubAppConfig,
) -> GitHubWebhookResult:
    note = f"{code}: {message}"
    check_run_id = (
        _create_check_run(
            owner=owner,
            repo_name=repo_name,
            head_sha=head_sha,
            installation_token=installation_token,
            conclusion="neutral",
            title=DEFAULT_CHECK_RUN_NAME,
            summary=note,
            details_url=None,
            text=_check_run_text(details_url=None),
            api_base_url=config.api_base_url,
        )
        if config.checks_enabled
        else None
    )
    return GitHubWebhookResult(
        event=event_name,
        action=action,
        handled=True,
        automatic_analysis_triggered=False,
        check_run_id=check_run_id,
        report_id=None,
        report_url=None,
        note=note,
    )


def _load_pull_request_artifacts(
    *,
    owner: str,
    repo_name: str,
    pull_number: int,
    head_sha: str,
    installation_token: str,
    api_base_url: str,
) -> list[tuple[str, bytes | None]]:
    artifacts: list[tuple[str, bytes | None]] = []
    page = 1
    while True:
        file_rows = _github_api_json(
            f"{api_base_url}/repos/{owner}/{repo_name}/pulls/{pull_number}/files?per_page=100&page={page}",
            token=installation_token,
        )
        if not isinstance(file_rows, list) or not file_rows:
            break
        for row in file_rows:
            if not isinstance(row, dict):
                continue
            status = str(row.get("status") or "")
            if status == "removed":
                continue
            filename = str(row.get("filename") or "").strip()
            if not filename:
                continue
            raw_content = _download_repo_file(
                owner=owner,
                repo_name=repo_name,
                path=filename,
                ref=head_sha,
                installation_token=installation_token,
                api_base_url=api_base_url,
            )
            artifacts.append((filename, raw_content))
            if total_upload_bytes(artifacts) > MAX_TOTAL_UPLOAD_BYTES:
                raise GitHubAppRequestError(_UPLOAD_LIMIT_MESSAGE)
        if len(file_rows) < 100:
            break
        page += 1
    return artifacts


def _download_repo_file(
    *,
    owner: str,
    repo_name: str,
    path: str,
    ref: str,
    installation_token: str,
    api_base_url: str,
) -> bytes | None:
    quoted_path = parse.quote(path, safe="/")
    payload = _github_api_json(
        f"{api_base_url}/repos/{owner}/{repo_name}/contents/{quoted_path}?ref={parse.quote(ref, safe='')}",
        token=installation_token,
    )
    if isinstance(payload, dict):
        if payload.get("encoding") == "base64" and payload.get("content"):
            return base64.b64decode(str(payload["content"]).encode("utf-8"))
        download_url = str(payload.get("download_url") or "").strip()
        if download_url:
            return _github_api_bytes(download_url, token=installation_token)
    return None


def _check_run_conclusion(recommendation: str) -> str:
    recommendation_value = str(recommendation).strip().lower()
    if recommendation_value == "go":
        return "success"
    if recommendation_value == "caution":
        return "neutral"
    return "failure"


def _check_run_summary(report: dict[str, Any]) -> str:
    headline = str(
        report.get("narrative_opening") or report.get("top_risk") or ""
    ).strip()
    if not headline:
        headline = "DeployWhisper completed an advisory review for this pull request."
    recommendation = str(report.get("recommendation") or "unknown").upper()
    severity = str(report.get("severity") or "unknown").upper()
    score = int(report.get("risk_score") or 0)
    return (
        f"{headline}\n\n"
        f"Severity: {severity}\n"
        f"Recommendation: {recommendation}\n"
        f"Risk score: {score}\n"
        "DeployWhisper remains advisory-only and never blocks merge on its own.\n"
        "Do not configure this check as a required status check."
    )


def _check_run_text(
    *,
    details_url: str | None,
) -> str:
    lines = ["DeployWhisper is advisory-only. Do not mark this check as required."]
    if details_url:
        lines.insert(0, f"[Open the full DeployWhisper report]({details_url})")
    return "\n\n".join(lines)


def _check_run_details_url(
    report_id: int,
    *,
    config: GitHubAppConfig,
) -> str:
    return f"{_require_check_run_report_url_config(config)}/reports/{report_id}"


def _require_check_run_report_url_config(config: GitHubAppConfig) -> str:
    base_url = (config.app_base_url or "").strip().rstrip("/")
    if not base_url:
        raise GitHubAppConfigurationError(
            "GitHub check runs require APP_BASE_URL or PUBLIC_APP_URL so the PR Details link opens the full DeployWhisper report."
        )
    return base_url


def _create_check_run(
    *,
    owner: str,
    repo_name: str,
    head_sha: str,
    installation_token: str,
    conclusion: str,
    title: str,
    summary: str,
    details_url: str | None,
    text: str | None,
    api_base_url: str,
) -> int | None:
    payload: dict[str, Any] = {
        "name": title,
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": conclusion,
        "completed_at": datetime.now(UTC).isoformat(),
        "output": {
            "title": title,
            "summary": summary[:65535],
        },
    }
    if text:
        payload["output"]["text"] = text[:65535]
    if details_url:
        payload["details_url"] = details_url
    response = _github_api_json(
        f"{api_base_url}/repos/{owner}/{repo_name}/check-runs",
        token=installation_token,
        method="POST",
        body=payload,
    )
    if isinstance(response, dict):
        check_run_id = response.get("id")
        if isinstance(check_run_id, int):
            return check_run_id
    return None


def _generate_installation_access_token(
    installation_id: int,
    *,
    config: GitHubAppConfig,
) -> str:
    app_jwt = _generate_app_jwt(config)
    response = _github_api_json(
        f"{config.api_base_url}/app/installations/{installation_id}/access_tokens",
        token=app_jwt,
        method="POST",
        body={},
        token_scheme="Bearer",
    )
    token = str(response.get("token") or "").strip()
    if not token:
        raise GitHubAppRequestError(
            "GitHub did not return an installation access token for the app."
        )
    return token


def _generate_app_jwt(config: GitHubAppConfig) -> str:
    if not config.app_id or not config.private_key_pem:
        raise GitHubAppConfigurationError(
            "GitHub App JWT generation requires app ID and private key."
        )
    issued_at = int(datetime.now(UTC).timestamp()) - 60
    expires_at = int((datetime.now(UTC) + timedelta(minutes=9)).timestamp())
    header = _b64url_json({"alg": "RS256", "typ": "JWT"})
    payload = _b64url_json(
        {
            "iat": issued_at,
            "exp": expires_at,
            "iss": config.app_id,
        }
    )
    signing_input = f"{header}.{payload}".encode("utf-8")
    signature = _sign_with_openssl(signing_input, config.private_key_pem)
    return f"{header}.{payload}.{_b64url(signature)}"


def _sign_with_openssl(message: bytes, private_key_pem: str) -> bytes:
    openssl_path = shutil.which("openssl")
    if openssl_path is None:
        raise GitHubAppConfigurationError(
            "OpenSSL is required to sign GitHub App JWTs in this runtime."
        )
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(private_key_pem)
        key_path = handle.name
    try:
        completed = subprocess.run(
            [openssl_path, "dgst", "-sha256", "-sign", key_path],
            input=message,
            capture_output=True,
            check=True,
        )
        return completed.stdout
    except subprocess.CalledProcessError as exc:  # noqa: PERF203
        raise GitHubAppConfigurationError(
            "GitHub App JWT signing failed. Verify the private key format."
        ) from exc
    finally:
        try:
            Path(key_path).unlink()
        except FileNotFoundError:
            pass


def _github_api_json(
    url: str,
    *,
    token: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    token_scheme: str = "Bearer",
) -> Any:
    raw = _github_api_request(
        url,
        token=token,
        method=method,
        body=body,
        token_scheme=token_scheme,
    )
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _github_api_bytes(url: str, *, token: str) -> bytes:
    return _github_api_request(url, token=token, method="GET", body=None)


def _github_api_request(
    url: str,
    *,
    token: str,
    method: str,
    body: dict[str, Any] | None,
    token_scheme: str = "Bearer",
) -> bytes:
    data = None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"{token_scheme} {token}",
        "User-Agent": "DeployWhisper-GitHub-App",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=15) as response:
            return response.read()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GitHubAppRequestError(
            f"GitHub API request failed ({exc.code}) for {url}: {detail}"
        ) from exc


def _post_form_json(url: str, form_payload: dict[str, str]) -> dict[str, Any]:
    data = parse.urlencode(form_payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "DeployWhisper-GitHub-App",
        },
    )
    try:
        with request.urlopen(req, timeout=15) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GitHubAppRequestError(
            f"GitHub OAuth token exchange failed ({exc.code}): {detail}"
        ) from exc
    return json.loads(raw)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_json(payload: dict[str, Any]) -> str:
    return _b64url(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )


def _encode_oauth_state(payload: dict[str, Any], *, secret: str) -> str:
    body = {
        **payload,
        "iat": int(datetime.now(UTC).timestamp()),
    }
    encoded_body = _b64url_json(body)
    signature = hmac.new(
        secret.encode("utf-8"),
        encoded_body.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_body}.{_b64url(signature)}"


def _decode_oauth_state(state: str, *, secret: str) -> dict[str, Any]:
    encoded_body, _, encoded_signature = state.partition(".")
    if not encoded_body or not encoded_signature:
        raise GitHubAppRequestError("GitHub App OAuth state is invalid.")
    expected_signature = _b64url(
        hmac.new(
            secret.encode("utf-8"),
            encoded_body.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    )
    if not hmac.compare_digest(expected_signature, encoded_signature):
        raise GitHubAppRequestError("GitHub App OAuth state could not be verified.")
    body = json.loads(
        base64.urlsafe_b64decode(encoded_body + "=" * (-len(encoded_body) % 4))
    )
    issued_at = int(body.get("iat") or 0)
    if (
        not issued_at
        or (datetime.now(UTC).timestamp() - issued_at) > _STATE_MAX_AGE_SECONDS
    ):
        raise GitHubAppRequestError("GitHub App OAuth state has expired.")
    return body
