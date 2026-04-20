"""Analysis retrieval API routes."""

from __future__ import annotations

from fastapi import APIRouter, File, Header, Query, UploadFile

from api.errors import ApiError, ApiRoute
from api.schemas import (
    AnalysisDetailResponse,
    AnalysisListResponse,
    AnalysisReportData,
    AnalysisRunResponse,
    ErrorResponse,
    build_analysis_run_data,
    build_report_meta,
)
from services.analysis_service import (
    analyze_uploaded_files,
    build_advisory_summary,
    build_share_summary,
)
from services.intake_service import (
    MAX_TOTAL_UPLOAD_BYTES,
    build_pending_analysis,
    uniquify_artifact_names,
)
from services.report_service import fetch_analysis_report
from services.report_service import fetch_filtered_analysis_history_page
from services.report_service import REPORT_SCHEMA_VERSION

router = APIRouter(prefix="/api/v1/analyses", tags=["analyses"], route_class=ApiRoute)
READ_CHUNK_BYTES = 1024 * 1024


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
    severity: str | None = Query(default=None),
    recommendation: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> AnalysisListResponse:
    page_payload = fetch_filtered_analysis_history_page(
        severity=severity,
        recommendation=recommendation,
        search=search,
        page=page,
        page_size=page_size,
    )
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

    raw_files = await _read_upload_files_with_limit(files)
    pending_analysis = build_pending_analysis(raw_files)
    if pending_analysis.ready_count == 0:
        raise ApiError(
            status_code=400,
            code="no_supported_artifacts",
            message="At least one supported artifact is required for analysis.",
            details={"items": [item.model_dump() for item in pending_analysis.items]},
        )

    result = analyze_uploaded_files(
        raw_files,
        audit_context={
            "source_interface": "api",
            "trigger_type": trigger_type or "api_request",
            "trigger_id": trigger_id,
        },
    )
    advisory = build_advisory_summary(result.assessment, result.narrative)
    share_summary = build_share_summary(
        advisory=advisory,
        narrative=result.narrative,
        blast_radius=result.blast_radius,
        rollback_plan=result.rollback_plan,
    )
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
def get_analysis(report_id: int) -> AnalysisDetailResponse:
    report = fetch_analysis_report(report_id)
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
