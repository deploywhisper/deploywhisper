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
    build_meta,
)
from services.analysis_service import analyze_uploaded_files, build_advisory_summary, build_share_summary
from services.intake_service import build_pending_analysis
from services.report_service import fetch_analysis_report, fetch_filtered_analysis_history

router = APIRouter(prefix="/api/v1/analyses", tags=["analyses"], route_class=ApiRoute)


@router.get("", response_model=AnalysisListResponse)
def list_analyses(
    severity: str | None = Query(default=None),
    recommendation: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> AnalysisListResponse:
    data = fetch_filtered_analysis_history(
        severity=severity,
        recommendation=recommendation,
        search=search,
    )
    return AnalysisListResponse(
        data=[AnalysisReportData(**report) for report in data],
        meta=build_meta(count=len(data)),
    )


@router.post(
    "",
    response_model=AnalysisRunResponse,
    responses={
        400: {"model": ErrorResponse},
        405: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_analysis(
    files: list[UploadFile] | None = File(default=None, description="Supported deployment artifacts to analyze."),
    trigger_type: str | None = Header(default=None, alias="X-DeployWhisper-Trigger-Type"),
    trigger_id: str | None = Header(default=None, alias="X-DeployWhisper-Trigger-Id"),
) -> AnalysisRunResponse:
    if not files:
        raise ApiError(
            status_code=400,
            code="missing_artifacts",
            message="At least one artifact file is required.",
        )

    raw_files = [(upload.filename or "artifact.bin", await upload.read()) for upload in files]
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
        meta=build_meta(
            api_version="v1",
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
        raise ApiError(status_code=404, code="analysis_not_found", message="Analysis report not found.")
    return AnalysisDetailResponse(
        data=AnalysisReportData(**report),
        meta=build_meta(id=report_id),
    )
