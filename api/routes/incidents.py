"""Incident ingestion management API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel, Field

from api.errors import ApiError, ApiRoute
from api.schemas import build_meta
from services.incident_import_service import (
    IncidentImportFile,
    IncidentImportValidationError,
    incident_import_failure_summaries,
    reindex_incident_files,
)
from services.incident_service import get_incident_ingestion_status
from services.project_service import (
    has_restricted_project_scope,
    require_project_permission,
    resolve_project_reference,
)

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"], route_class=ApiRoute)


class IncidentReindexRequest(BaseModel):
    """Incident reindex API request."""

    files: list[IncidentImportFile] = Field(default_factory=list)
    project_id: int | None = Field(default=None, ge=1)
    project_key: str | None = Field(default=None, min_length=1)
    workspace_id: int | None = Field(default=None, ge=1)
    workspace_key: str | None = Field(default=None, min_length=1)
    remove_missing_sources: bool = Field(default=False)


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
    if code in {"workspace_not_found", "conflicting_workspace_reference"}:
        return has_restricted_project_scope(
            role=authorization["role"],
            allowed_project_keys=authorization["allowed_project_keys"],
        )
    return (
        project_id is not None
        and code in {"project_not_found", "conflicting_project_reference"}
        and has_restricted_project_scope(
            role=authorization["role"],
            allowed_project_keys=authorization["allowed_project_keys"],
        )
    )


def _require_incident_permission(
    *,
    authorization: dict[str, object],
    project_id: int | None,
    project_key: str | None,
) -> None:
    if project_key is not None:
        require_project_permission(
            role=authorization["role"],
            capability="incident.manage",
            project_key=project_key,
            allowed_project_keys=authorization["allowed_project_keys"],
        )
        if project_id is not None:
            resolve_project_reference(project_id=project_id, project_key=project_key)
        return
    if project_id is not None:
        require_project_permission(
            role=authorization["role"],
            capability="incident.manage",
            allowed_project_keys=authorization["allowed_project_keys"],
        )
        project = resolve_project_reference(project_id=project_id)
        require_project_permission(
            role=authorization["role"],
            capability="incident.manage",
            project_key=project.project_key,
            allowed_project_keys=authorization["allowed_project_keys"],
        )


def _raise_project_error(
    exc: ValueError, *, authorization: dict[str, object], project_id: int | None
) -> None:
    if _should_mask_scope_reference_error(
        authorization=authorization,
        project_id=project_id,
        exc=exc,
    ):
        raise _project_scope_forbidden_error() from exc
    raise _project_api_error(exc) from exc


def _validation_error(exc: IncidentImportValidationError, *, code: str) -> ApiError:
    failures = incident_import_failure_summaries(exc.field_errors)
    return ApiError(
        status_code=422,
        code=code,
        message="Incident reindex validation failed.",
        details={
            "failures": [failure.model_dump(mode="json") for failure in failures],
        },
    )


@router.get("/ingestion")
def incident_ingestion_status(
    project_id: int | None = Query(default=None, ge=1),
    project_key: str | None = Query(default=None, min_length=1),
    workspace_id: int | None = Query(default=None, ge=1),
    workspace_key: str | None = Query(default=None, min_length=1),
    project_role: Annotated[
        str | None,
        Header(alias="X-DeployWhisper-Project-Role"),
    ] = None,
    project_keys: Annotated[
        str | None,
        Header(alias="X-DeployWhisper-Project-Keys"),
    ] = None,
) -> dict:
    """Return incident import/index status for admins."""
    auth_context = _authorization_context(project_role, project_keys)
    try:
        _require_incident_permission(
            authorization=auth_context,
            project_id=project_id,
            project_key=project_key,
        )
        status = get_incident_ingestion_status(
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
        )
    except PermissionError as exc:
        raise ApiError(
            status_code=403,
            code=getattr(exc, "code", "project_permission_denied"),
            message=getattr(exc, "message", str(exc)),
        ) from exc
    except ValueError as exc:
        _raise_project_error(exc, authorization=auth_context, project_id=project_id)
    return {
        "data": status.model_dump(mode="json"),
        "meta": build_meta(count=len(status.sources)),
    }


@router.post("/reindex")
def incident_reindex(
    request: IncidentReindexRequest,
    project_role: Annotated[
        str | None,
        Header(alias="X-DeployWhisper-Project-Role"),
    ] = None,
    project_keys: Annotated[
        str | None,
        Header(alias="X-DeployWhisper-Project-Keys"),
    ] = None,
) -> dict:
    """Replace or remove stale incident index entries for one project scope."""
    auth_context = _authorization_context(project_role, project_keys)
    try:
        _require_incident_permission(
            authorization=auth_context,
            project_id=request.project_id,
            project_key=request.project_key,
        )
        result = reindex_incident_files(
            request.files,
            project_id=request.project_id,
            project_key=request.project_key,
            workspace_id=request.workspace_id,
            workspace_key=request.workspace_key,
            remove_missing_sources=request.remove_missing_sources,
        )
    except PermissionError as exc:
        raise ApiError(
            status_code=403,
            code=getattr(exc, "code", "project_permission_denied"),
            message=getattr(exc, "message", str(exc)),
        ) from exc
    except IncidentImportValidationError as exc:
        raise _validation_error(
            exc,
            code="incident_reindex_validation_failed",
        ) from exc
    except ValueError as exc:
        _raise_project_error(
            exc, authorization=auth_context, project_id=request.project_id
        )
    return {
        "data": result.model_dump(mode="json"),
        "meta": build_meta(count=len(result.status.sources)),
    }
