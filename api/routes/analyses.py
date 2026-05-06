"""Analysis retrieval API routes."""

from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile

from api.errors import ApiError, ApiRoute
from api.schemas import (
    AnalysisDetailResponse,
    AnalysisListResponse,
    AnalysisReportData,
    AnalysisRunResponse,
    AnalysisShareConfigData,
    AnalysisShareConfigRequest,
    AnalysisShareConfigResponse,
    ErrorResponse,
    build_analysis_run_data,
    build_report_meta,
)
from config import settings
from services.analysis_service import (
    analyze_uploaded_files,
    build_advisory_summary,
    build_share_summary,
    resolve_analysis_project_scope,
)
from services.intake_service import (
    MAX_TOTAL_UPLOAD_BYTES,
    build_pending_analysis,
    uniquify_artifact_names,
)
from services.report_service import fetch_analysis_report
from services.report_service import fetch_filtered_analysis_history_page
from services.report_service import configure_report_share
from services.report_service import REPORT_SCHEMA_VERSION
from services.project_service import ensure_default_project

router = APIRouter(prefix="/api/v1/analyses", tags=["analyses"], route_class=ApiRoute)
READ_CHUNK_BYTES = 1024 * 1024


def _project_api_error(exc: ValueError) -> ApiError:
    code = getattr(exc, "code", "invalid_project_request")
    status_code = 404 if code == "project_not_found" else 400
    return ApiError(
        status_code=status_code,
        code=code,
        message=str(exc),
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


@router.get("", response_model=AnalysisListResponse)
def list_analyses(
    project_id: int | None = Query(default=None),
    project_key: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    recommendation: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> AnalysisListResponse:
    try:
        if project_id is None and project_key is None:
            project_id = ensure_default_project().id
        page_payload = fetch_filtered_analysis_history_page(
            project_id=project_id,
            project_key=project_key,
            severity=severity,
            recommendation=recommendation,
            search=search,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise _project_api_error(exc) from exc
    return AnalysisListResponse(
        data=[AnalysisReportData(**report) for report in page_payload["items"]],
        meta=build_report_meta(
            report_schema_version=REPORT_SCHEMA_VERSION,
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
    trigger_type: str | None = Header(
        default=None, alias="X-DeployWhisper-Trigger-Type"
    ),
    trigger_id: str | None = Header(default=None, alias="X-DeployWhisper-Trigger-Id"),
) -> AnalysisRunResponse:
    if not files:
        raise ApiError(
            status_code=400,
            code="missing_artifacts",
            message="At least one artifact file is required.",
        )

    try:
        resolve_analysis_project_scope(project_id=project_id, project_key=project_key)
    except ValueError as exc:
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
            audit_context={
                "source_interface": "api",
                "trigger_type": trigger_type or "api_request",
                "trigger_id": trigger_id,
            },
        )
    except ValueError as exc:
        raise _project_api_error(exc) from exc
    advisory = build_advisory_summary(result.assessment, result.narrative)
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
) -> AnalysisDetailResponse:
    try:
        if project_id is None and project_key is None:
            project_id = ensure_default_project().id
        report = fetch_analysis_report(
            report_id,
            project_id=project_id,
            project_key=project_key,
        )
    except ValueError as exc:
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
            id=report_id, report_schema_version=REPORT_SCHEMA_VERSION
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
) -> AnalysisShareConfigResponse:
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
