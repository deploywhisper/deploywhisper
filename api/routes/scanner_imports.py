"""External scanner import API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field, StrictInt
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.errors import ApiError, ApiRoute, api_error_handler
from api.schemas import ErrorResponse, ListMetaPayload, build_meta
from services import scanner_import_service as scanner_import_service_module
from services.project_service import (
    has_restricted_project_scope,
    require_project_permission,
    resolve_project_reference,
)
from services.scanner_import_service import (
    ScannerImportFile,
    ScannerImportPayloadTooLarge,
    ScannerImportResult,
    ScannerImportValidationError,
    import_sarif_file,
    scanner_import_failure_summaries,
)


class ScannerImportRoute(ApiRoute):
    """API route that bounds scanner import request bodies during parsing."""

    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def scanner_import_route_handler(request: Request):
            content_length = request.headers.get("content-length")
            if (
                content_length is not None
                and content_length.isdigit()
                and int(content_length)
                > scanner_import_service_module.SARIF_IMPORT_MAX_REQUEST_BYTES
            ):
                return await api_error_handler(
                    request,
                    _payload_too_large_error(
                        limit_bytes=scanner_import_service_module.SARIF_IMPORT_MAX_REQUEST_BYTES,
                        scope="request envelope",
                    ),
                )

            received_bytes = 0
            original_receive = request._receive

            async def receive_with_limit():
                nonlocal received_bytes
                message = await original_receive()
                if message.get("type") == "http.request":
                    received_bytes += len(message.get("body", b""))
                    if (
                        received_bytes
                        > scanner_import_service_module.SARIF_IMPORT_MAX_REQUEST_BYTES
                    ):
                        raise StarletteHTTPException(
                            status_code=413,
                            detail=_payload_too_large_detail(
                                limit_bytes=scanner_import_service_module.SARIF_IMPORT_MAX_REQUEST_BYTES,
                                scope="request envelope",
                            ),
                        )
                return message

            request._receive = receive_with_limit
            return await original_handler(request)

        return scanner_import_route_handler


router = APIRouter(
    prefix="/api/v1/scanner-imports",
    tags=["scanner-imports"],
    route_class=ScannerImportRoute,
)


class SarifImportRequest(BaseModel):
    """SARIF import API request."""

    source_file: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    project_id: StrictInt | None = Field(default=None, ge=1)
    project_key: str | None = Field(default=None, min_length=1)
    workspace_id: StrictInt | None = Field(default=None, ge=1)
    workspace_key: str | None = Field(default=None, min_length=1)


class ScannerImportResponse(BaseModel):
    """SARIF import API response."""

    data: ScannerImportResult
    meta: ListMetaPayload


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


def _project_api_error(exc: ValueError) -> ApiError:
    code = getattr(exc, "code", "invalid_project_request")
    status_code = getattr(exc, "status_code", None) or (
        404 if code in {"project_not_found", "workspace_not_found"} else 400
    )
    return ApiError(
        status_code=status_code,
        code=code,
        message=getattr(exc, "message", str(exc)),
    )


def _project_scope_forbidden_error() -> ApiError:
    return ApiError(
        status_code=403,
        code="project_scope_forbidden",
        message="Caller is not authorized for the requested project.",
    )


def _should_mask_scope_reference_error(
    *,
    authorization: dict[str, object],
    project_id: int | None,
    exc: ValueError,
) -> bool:
    code = getattr(exc, "code", None)
    return code in {
        "project_not_found",
        "conflicting_project_reference",
        "workspace_not_found",
        "conflicting_workspace_reference",
    } and has_restricted_project_scope(
        role=authorization["role"],
        allowed_project_keys=authorization["allowed_project_keys"],
    )


def _require_scanner_permission(
    *,
    authorization: dict[str, object],
    project_id: int | None,
    project_key: str | None,
) -> None:
    if project_key is not None:
        require_project_permission(
            role=authorization["role"],
            capability="scanner.manage",
            project_key=project_key,
            allowed_project_keys=authorization["allowed_project_keys"],
        )
        if project_id is not None:
            resolve_project_reference(project_id=project_id, project_key=project_key)
        return
    if project_id is not None:
        project = resolve_project_reference(project_id=project_id)
        require_project_permission(
            role=authorization["role"],
            capability="scanner.manage",
            project_key=project.project_key,
            allowed_project_keys=authorization["allowed_project_keys"],
        )


def _raise_project_error(
    exc: ValueError,
    *,
    authorization: dict[str, object],
    project_id: int | None,
) -> None:
    if _should_mask_scope_reference_error(
        authorization=authorization,
        project_id=project_id,
        exc=exc,
    ):
        raise _project_scope_forbidden_error() from exc
    raise _project_api_error(exc) from exc


def _validation_error(exc: ScannerImportValidationError) -> ApiError:
    return ApiError(
        status_code=422,
        code="sarif_import_validation_failed",
        message="SARIF import validation failed.",
        details={"failures": scanner_import_failure_summaries(exc.field_errors)},
    )


def _payload_too_large_error(
    *,
    limit_bytes: int | None = None,
    scope: str = "SARIF content",
) -> ApiError:
    return ApiError(
        status_code=413,
        **_payload_too_large_detail(limit_bytes=limit_bytes, scope=scope),
    )


def _payload_too_large_detail(
    *,
    limit_bytes: int | None = None,
    scope: str = "SARIF content",
) -> dict:
    effective_limit = (
        limit_bytes
        if limit_bytes is not None
        else scanner_import_service_module.SARIF_IMPORT_MAX_CONTENT_BYTES
    )
    return {
        "code": "scanner_import_limit_exceeded",
        "message": str(
            ScannerImportPayloadTooLarge(
                limit_bytes=effective_limit,
                scope=scope,
            )
        ),
        "details": {},
    }


@router.post(
    "/sarif",
    response_model=ScannerImportResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        404: {"model": ErrorResponse, "description": "Not Found"},
        413: {"model": ErrorResponse, "description": "Content Too Large"},
        422: {"model": ErrorResponse, "description": "Unprocessable Content"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"},
    },
)
def import_sarif(
    request: SarifImportRequest,
    project_role: Annotated[
        str | None,
        Header(alias="X-DeployWhisper-Project-Role"),
    ] = None,
    project_keys: Annotated[
        str | None,
        Header(alias="X-DeployWhisper-Project-Keys"),
    ] = None,
) -> dict:
    """Import SARIF scanner findings as external evidence."""
    auth_context = _authorization_context(project_role, project_keys)
    try:
        _require_scanner_permission(
            authorization=auth_context,
            project_id=request.project_id,
            project_key=request.project_key,
        )
        result = import_sarif_file(
            ScannerImportFile(
                source_file=request.source_file,
                content=request.content,
            ),
            project_id=request.project_id,
            project_key=request.project_key,
            workspace_id=request.workspace_id,
            workspace_key=request.workspace_key,
        )
    except PermissionError as exc:
        raise ApiError(
            status_code=403,
            code=getattr(exc, "code", "project_permission_denied"),
            message=getattr(exc, "message", str(exc)),
        ) from exc
    except ScannerImportPayloadTooLarge as exc:
        raise _payload_too_large_error() from exc
    except ScannerImportValidationError as exc:
        raise _validation_error(exc) from exc
    except ValueError as exc:
        _raise_project_error(
            exc,
            authorization=auth_context,
            project_id=request.project_id,
        )
    return {
        "data": result.model_dump(mode="json"),
        "meta": build_meta(count=result.imported_count),
    }
