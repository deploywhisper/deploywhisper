"""Analysis retrieval API routes."""

from __future__ import annotations

import hmac
import os
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from pydantic import ValidationError

from api.errors import ApiError, ApiRoute
from api.schemas import (
    AnalysisDetailResponse,
    AnalysisListResponse,
    AnalysisReportData,
    AnalysisRunResponse,
    AdvisorySummaryData,
    AnalysisShareConfigData,
    AnalysisShareConfigRequest,
    AnalysisShareConfigResponse,
    ErrorResponse,
    build_analysis_run_data,
    build_report_meta,
)
from config import settings
from services.analysis_service import (
    AnalysisPersistenceError,
    analyze_uploaded_files,
    build_share_summary,
    resolve_analysis_project_scope,
)
from services.intake_service import (
    MAX_TOTAL_UPLOAD_BYTES,
    build_pending_analysis,
    uniquify_artifact_names,
)
from services.report_service import REPORT_SCHEMA_VERSION
from services.report_service import build_report_advisory_payload
from services.report_service import configure_report_share
from services.report_service import fetch_analysis_report
from services.report_service import fetch_filtered_analysis_history_page
from services.report_service import normalize_report_schema_version
from services.project_service import (
    ensure_default_project,
    has_restricted_project_scope,
    require_project_permission,
)
from services.project_service import resolve_project_reference

router = APIRouter(prefix="/api/v1/analyses", tags=["analyses"], route_class=ApiRoute)
READ_CHUNK_BYTES = 1024 * 1024
_HISTORY_ANALYSIS_STATUSES = {"complete", "degraded", "fallback"}


def _list_report_schema_meta(reports: list[dict]) -> dict[str, object]:
    def schema_major(schema_version: str) -> int:
        return int(schema_version[1:]) if schema_version.startswith("v") else 0

    versions = sorted(
        {
            normalize_report_schema_version(report.get("report_schema_version"))
            for report in reports
        },
        key=schema_major,
    )
    return {
        "report_schema_version": versions[0]
        if len(versions) == 1
        else REPORT_SCHEMA_VERSION,
        "report_schema_versions": versions,
    }


def _analysis_run_advisory(result) -> AdvisorySummaryData:
    persisted_report = result.persisted_report
    try:
        fallback_payload = (
            build_report_advisory_payload(persisted_report)
            if isinstance(persisted_report, dict)
            else {}
        )
    except (TypeError, ValueError) as exc:
        raise ApiError(
            status_code=500,
            code="analysis_advisory_contract_invalid",
            message="Analysis advisory contract validation failed.",
        ) from exc
    try:
        advisory = AdvisorySummaryData.model_validate(fallback_payload)
    except ValidationError as exc:
        raise ApiError(
            status_code=500,
            code="analysis_advisory_contract_invalid",
            message="Analysis advisory contract validation failed.",
        ) from exc
    if isinstance(persisted_report, dict):
        persisted_report["advisory"] = advisory.model_dump(mode="json")
    return advisory


def _project_api_error(exc: ValueError) -> ApiError:
    code = getattr(exc, "code", "invalid_project_request")
    status_code = getattr(exc, "status_code", None) or (
        404 if code in {"project_not_found", "workspace_not_found"} else 400
    )
    return ApiError(
        status_code=status_code,
        code=code,
        message=str(exc),
    )


def _split_project_scope_header(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _authorization_context(
    project_role: Annotated[
        str | None,
        Header(alias="X-DeployWhisper-Project-Role"),
    ] = None,
    project_keys: Annotated[
        str | None,
        Header(alias="X-DeployWhisper-Project-Keys"),
    ] = None,
) -> dict[str, object]:
    return {
        "role": project_role,
        "allowed_project_keys": _split_project_scope_header(project_keys),
    }


def _raise_authorization_error(exc: PermissionError) -> ApiError:
    raise ApiError(
        status_code=403,
        code=getattr(exc, "code", "project_permission_denied"),
        message=getattr(exc, "message", str(exc)),
    ) from exc


def _project_scope_forbidden_error() -> ApiError:
    return ApiError(
        status_code=403,
        code="project_scope_forbidden",
        message="Caller is not authorized for the requested project.",
    )


def _normalize_history_bound(
    value: datetime | None, *, field_name: str
) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ApiError(
            status_code=400,
            code="invalid_history_time_bound",
            message=f"{field_name} must include a timezone offset.",
        )
    return value.astimezone(UTC)


def _normalize_history_analysis_status(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized not in _HISTORY_ANALYSIS_STATUSES:
        raise ApiError(
            status_code=400,
            code="invalid_analysis_status",
            message=("analysis_status must be one of: complete, degraded, fallback."),
        )
    return normalized


def _empty_analysis_list_response(*, page: int, page_size: int) -> AnalysisListResponse:
    return AnalysisListResponse(
        data=[],
        meta=build_report_meta(
            report_schema_version=REPORT_SCHEMA_VERSION,
            report_schema_versions=[],
            count=0,
            total_count=0,
            page=page,
            page_size=page_size,
        ),
    )


def _should_return_empty_history_for_scope_error(exc: PermissionError) -> bool:
    return getattr(exc, "code", None) == "project_scope_forbidden"


def _should_mask_project_reference_error(
    *,
    authorization: dict[str, object],
    project_id: int | None,
    exc: ValueError,
) -> bool:
    return (
        project_id is not None
        and getattr(exc, "code", None)
        in {"project_not_found", "conflicting_project_reference"}
        and has_restricted_project_scope(
            role=authorization["role"],
            allowed_project_keys=authorization["allowed_project_keys"],
        )
    )


def _should_mask_scope_reference_error(
    *,
    authorization: dict[str, object],
    exc: ValueError,
) -> bool:
    return getattr(exc, "code", None) in {
        "project_not_found",
        "conflicting_project_reference",
        "workspace_not_found",
        "conflicting_workspace_reference",
    } and has_restricted_project_scope(
        role=authorization["role"],
        allowed_project_keys=authorization["allowed_project_keys"],
    )


def _require_api_project_permission(
    *,
    authorization: dict[str, object],
    capability: str,
    project_id: int | None = None,
    project_key: str | None = None,
) -> None:
    if project_key is not None:
        require_project_permission(
            role=authorization["role"],
            capability=capability,
            project_key=project_key,
            allowed_project_keys=authorization["allowed_project_keys"],
        )
        if project_id is not None:
            try:
                resolve_project_reference(
                    project_id=project_id, project_key=project_key
                )
            except ValueError as exc:
                if _should_mask_project_reference_error(
                    authorization=authorization,
                    project_id=project_id,
                    exc=exc,
                ):
                    raise _project_scope_forbidden_error() from exc
                raise
        return
    if project_id is not None:
        require_project_permission(
            role=authorization["role"],
            capability=capability,
            allowed_project_keys=authorization["allowed_project_keys"],
        )
        try:
            project = resolve_project_reference(project_id=project_id)
        except ValueError as exc:
            if _should_mask_project_reference_error(
                authorization=authorization,
                project_id=project_id,
                exc=exc,
            ):
                raise _project_scope_forbidden_error() from exc
            raise
        require_project_permission(
            role=authorization["role"],
            capability=capability,
            project_key=project.project_key,
            allowed_project_keys=authorization["allowed_project_keys"],
        )


def _require_report_share_permission(
    *,
    authorization: dict[str, object],
    report_id: int,
) -> None:
    require_project_permission(
        role=authorization["role"],
        capability="report.share.manage",
        allowed_project_keys=authorization["allowed_project_keys"],
    )
    report = fetch_analysis_report(report_id)
    if report is None:
        if has_restricted_project_scope(
            role=authorization["role"],
            allowed_project_keys=authorization["allowed_project_keys"],
        ):
            raise _project_scope_forbidden_error()
        raise ApiError(
            status_code=404,
            code="analysis_not_found",
            message="Analysis report not found.",
        )
    project = report.get("project") or {}
    require_project_permission(
        role=authorization["role"],
        capability="report.share.manage",
        project_key=project.get("project_key"),
        allowed_project_keys=authorization["allowed_project_keys"],
    )


def _reject_unscoped_workspace_id(
    *,
    project_id: int | None,
    project_key: str | None,
    workspace_id: int | None,
) -> None:
    if workspace_id is None or project_id is not None or project_key is not None:
        return
    raise ApiError(
        status_code=400,
        code="missing_project_scope",
        message="Project scope is required when resolving workspace_id.",
    )


def require_share_management_token(
    share_token: str | None = Header(
        default=None,
        alias="X-DeployWhisper-Share-Token",
    ),
) -> None:
    """Require an explicit management token before mutating share settings."""
    configured_token = (
        os.getenv("DEPLOYWHISPER_SHARE_TOKEN")
        or os.getenv("APP_SHARE_MANAGEMENT_TOKEN")
        or settings.share_management_token
        or ""
    ).strip()
    if not configured_token:
        raise ApiError(
            status_code=405,
            code="share_configuration_disabled",
            message=(
                "Share configuration API is disabled. Set "
                "DEPLOYWHISPER_SHARE_TOKEN to enable it."
            ),
        )
    if not share_token or not hmac.compare_digest(share_token, configured_token):
        raise ApiError(
            status_code=403,
            code="share_configuration_forbidden",
            message="Share configuration requires a valid management token.",
        )


async def _read_upload_files_with_limit(
    files: list[UploadFile],
) -> list[tuple[str, bytes]]:
    remaining = MAX_TOTAL_UPLOAD_BYTES
    buffered: list[tuple[str, bytes]] = []

    for upload in files:
        file_size = getattr(upload, "size", None)
        if isinstance(file_size, int) and file_size > remaining:
            raise ApiError(
                status_code=413,
                code="upload_limit_exceeded",
                message="Total artifact payload exceeds the 50 MB analysis-session limit.",
            )

        chunks = bytearray()
        while True:
            chunk = await upload.read(min(READ_CHUNK_BYTES, remaining + 1))
            if not chunk:
                break
            if len(chunk) > remaining:
                raise ApiError(
                    status_code=413,
                    code="upload_limit_exceeded",
                    message="Total artifact payload exceeds the 50 MB analysis-session limit.",
                )
            chunks.extend(chunk)
            remaining -= len(chunk)
        buffered.append((upload.filename or "artifact.bin", bytes(chunks)))

    return uniquify_artifact_names(buffered)


@router.get(
    "",
    response_model=AnalysisListResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        405: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def list_analyses(
    project_id: int | None = Query(default=None),
    project_key: str | None = Query(default=None),
    workspace_id: int | None = Query(default=None),
    workspace_key: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    recommendation: str | None = Query(default=None),
    search: str | None = Query(default=None),
    toolchain: str | None = Query(default=None),
    analysis_status: str | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    authorization: dict[str, object] = Depends(_authorization_context),
) -> AnalysisListResponse:
    try:
        _reject_unscoped_workspace_id(
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
        )
        if (
            project_id is None
            and project_key is None
            and workspace_id is None
            and workspace_key is None
        ):
            project_id = ensure_default_project().id
        _require_api_project_permission(
            authorization=authorization,
            capability="report.read",
            project_id=project_id,
            project_key=project_key,
        )
        created_from = _normalize_history_bound(
            created_from,
            field_name="created_from",
        )
        created_to = _normalize_history_bound(
            created_to,
            field_name="created_to",
        )
        analysis_status = _normalize_history_analysis_status(analysis_status)
        page_payload = fetch_filtered_analysis_history_page(
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
            severity=severity,
            recommendation=recommendation,
            search=search,
            toolchain=toolchain,
            analysis_status=analysis_status,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
    except PermissionError as exc:
        if _should_return_empty_history_for_scope_error(exc):
            return _empty_analysis_list_response(page=page, page_size=page_size)
        _raise_authorization_error(exc)
    except ApiError as exc:
        if exc.code == "project_scope_forbidden":
            return _empty_analysis_list_response(page=page, page_size=page_size)
        raise
    except ValueError as exc:
        if _should_mask_project_reference_error(
            authorization=authorization,
            project_id=project_id,
            exc=exc,
        ) or _should_mask_scope_reference_error(
            authorization=authorization,
            exc=exc,
        ):
            return _empty_analysis_list_response(page=page, page_size=page_size)
        raise _project_api_error(exc) from exc
    reports = page_payload["items"]
    return AnalysisListResponse(
        data=[AnalysisReportData(**report) for report in reports],
        meta=build_report_meta(
            **_list_report_schema_meta(reports),
            count=len(page_payload["items"]),
            total_count=page_payload["total_count"],
            page=page_payload["page"],
            page_size=page_payload["page_size"],
        ),
    )


@router.post(
    "",
    response_model=AnalysisRunResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        405: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_analysis(
    files: list[UploadFile] | None = File(
        default=None, description="Supported deployment artifacts to analyze."
    ),
    project_id: int | None = Form(
        default=None,
        description="Required unless project_key is provided; numeric project id for the analysis.",
    ),
    project_key: str | None = Form(
        default=None,
        description="Required unless project_id is provided; project key for the analysis.",
    ),
    workspace_id: int | None = Form(
        default=None,
        description="Optional numeric workspace/environment id for the analysis.",
    ),
    workspace_key: str | None = Form(
        default=None,
        description="Optional project-local workspace/environment key for the analysis.",
    ),
    trigger_type: str | None = Header(
        default=None, alias="X-DeployWhisper-Trigger-Type"
    ),
    trigger_id: str | None = Header(default=None, alias="X-DeployWhisper-Trigger-Id"),
    actor: str | None = Header(default=None, alias="X-DeployWhisper-Actor"),
    authorization: dict[str, object] = Depends(_authorization_context),
) -> AnalysisRunResponse:
    if not files:
        raise ApiError(
            status_code=400,
            code="missing_artifacts",
            message="At least one artifact file is required.",
        )

    try:
        project_key_for_auth = project_key.strip() if project_key is not None else None
        if project_key_for_auth:
            _require_api_project_permission(
                authorization=authorization,
                capability="analysis.submit",
                project_key=project_key_for_auth,
            )
        else:
            require_project_permission(
                role=authorization["role"],
                capability="analysis.submit",
                allowed_project_keys=authorization["allowed_project_keys"],
            )
        try:
            resolved_project = resolve_analysis_project_scope(
                project_id=project_id,
                project_key=project_key,
                workspace_id=workspace_id,
                workspace_key=workspace_key,
            )
        except ValueError as exc:
            if _should_mask_project_reference_error(
                authorization=authorization,
                project_id=project_id,
                exc=exc,
            ) or _should_mask_scope_reference_error(
                authorization=authorization,
                exc=exc,
            ):
                raise _project_scope_forbidden_error() from exc
            raise
        if not project_key_for_auth:
            _require_api_project_permission(
                authorization=authorization,
                capability="analysis.submit",
                project_id=resolved_project.id,
            )
    except PermissionError as exc:
        _raise_authorization_error(exc)
    except ValueError as exc:
        if _should_mask_project_reference_error(
            authorization=authorization,
            project_id=project_id,
            exc=exc,
        ) or _should_mask_scope_reference_error(
            authorization=authorization,
            exc=exc,
        ):
            raise _project_scope_forbidden_error() from exc
        raise _project_api_error(exc) from exc

    raw_files = await _read_upload_files_with_limit(files)
    pending_analysis = build_pending_analysis(raw_files)
    if pending_analysis.ready_count == 0:
        raise ApiError(
            status_code=400,
            code="no_supported_artifacts",
            message="At least one supported artifact is required for analysis.",
            details={"items": [item.model_dump() for item in pending_analysis.items]},
        )

    try:
        result = analyze_uploaded_files(
            raw_files,
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
            audit_context={
                "source_interface": "api",
                "trigger_type": trigger_type or "api_request",
                "trigger_id": trigger_id,
                "actor": actor or "api_client",
            },
        )
    except AnalysisPersistenceError as exc:
        raise ApiError(
            status_code=500,
            code=exc.code,
            message=str(exc),
            details={"reason": exc.public_reason},
        ) from exc
    except ValueError as exc:
        raise _project_api_error(exc) from exc
    advisory = _analysis_run_advisory(result)
    share_summary = build_share_summary(result.persisted_report)
    return AnalysisRunResponse(
        data=build_analysis_run_data(
            intake=pending_analysis,
            result=result,
            advisory=advisory,
            share_summary=share_summary,
        ),
        meta=build_report_meta(
            api_version="v1",
            report_schema_version=REPORT_SCHEMA_VERSION,
            advisory_only=True,
            submitted_artifact_count=len(raw_files),
            accepted_artifact_count=pending_analysis.ready_count,
        ),
    )


@router.get(
    "/{report_id}",
    response_model=AnalysisDetailResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        405: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_analysis(
    report_id: int,
    project_id: int | None = Query(default=None),
    project_key: str | None = Query(default=None),
    workspace_id: int | None = Query(default=None),
    workspace_key: str | None = Query(default=None),
    authorization: dict[str, object] = Depends(_authorization_context),
) -> AnalysisDetailResponse:
    try:
        _reject_unscoped_workspace_id(
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
        )
        if (
            project_id is None
            and project_key is None
            and workspace_id is None
            and workspace_key is None
        ):
            project_id = ensure_default_project().id
        _require_api_project_permission(
            authorization=authorization,
            capability="report.read",
            project_id=project_id,
            project_key=project_key,
        )
        report = fetch_analysis_report(
            report_id,
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
        )
    except PermissionError as exc:
        _raise_authorization_error(exc)
    except ValueError as exc:
        if _should_mask_project_reference_error(
            authorization=authorization,
            project_id=project_id,
            exc=exc,
        ) or _should_mask_scope_reference_error(
            authorization=authorization,
            exc=exc,
        ):
            raise _project_scope_forbidden_error() from exc
        raise _project_api_error(exc) from exc
    if report is None:
        raise ApiError(
            status_code=404,
            code="analysis_not_found",
            message="Analysis report not found.",
        )
    return AnalysisDetailResponse(
        data=AnalysisReportData(**report),
        meta=build_report_meta(
            id=report_id,
            report_schema_version=normalize_report_schema_version(
                report.get("report_schema_version")
            ),
        ),
    )


@router.post(
    "/{report_id}/share",
    response_model=AnalysisShareConfigResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        405: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def configure_analysis_share(
    report_id: int,
    payload: AnalysisShareConfigRequest,
    _: None = Depends(require_share_management_token),
    authorization: dict[str, object] = Depends(_authorization_context),
) -> AnalysisShareConfigResponse:
    try:
        _require_report_share_permission(
            authorization=authorization,
            report_id=report_id,
        )
    except PermissionError as exc:
        _raise_authorization_error(exc)
    share_config = configure_report_share(
        report_id,
        password=payload.password,
        redact_filenames=payload.redact_filenames,
    )
    if share_config is None:
        raise ApiError(
            status_code=404,
            code="analysis_not_found",
            message="Analysis report not found.",
        )
    return AnalysisShareConfigResponse(
        data=AnalysisShareConfigData(**share_config),
        meta=build_report_meta(
            id=report_id,
            report_schema_version=REPORT_SCHEMA_VERSION,
        ),
    )
