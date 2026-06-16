"""Project-scoped context API routes."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from api.errors import ApiError, ApiRoute
from api.schemas import (
    CustomSkillListResponse,
    CustomSkillStatusData,
    CustomSkillUploadData,
    CustomSkillUploadRequest,
    CustomSkillUploadResponse,
    FeedbackSummaryData,
    ProviderCapabilityData,
    ProviderOptionData,
    ProviderSettingsData,
    ProviderSettingsRequest,
    ProviderSettingsResponse,
    ProviderSettingsSaveData,
    ProviderValidationData,
    ProjectData,
    SettingsSummaryData,
    SettingsSummaryResponse,
    TopologyDriftCadenceData,
    TopologyDriftCadenceRequest,
    TopologyDriftCadenceResponse,
    TopologyContextData,
    TopologyContextRequest,
    TopologyContextResponse,
    TopologyStatusData,
    TopologyUploadRequest,
    TopologyValidationData,
    TopologyValidationResponse,
    build_meta,
)
from llm.skill_context import get_custom_skill_statuses, save_custom_skill
from services.feedback_service import fetch_feedback_summary
from services.project_service import (
    has_restricted_project_scope,
    require_project_permission,
    resolve_project_reference,
)
from services.settings_service import (
    TOPOLOGY_DRIFT_CHECK_INTERVAL_OPTIONS,
    activate_local_mode,
    get_provider_settings,
    get_topology_drift_check_interval_hours,
    provider_defaults,
    provider_select_options,
    save_provider_settings,
    save_topology_drift_check_interval_hours,
    validate_provider_settings,
)
from services.topology_service import (
    get_topology_status,
    save_topology_definition,
    validate_topology_definition,
)

router = APIRouter(prefix="/api/v1/context", tags=["context"], route_class=ApiRoute)
settings_router = APIRouter(
    prefix="/api/v1/settings", tags=["settings"], route_class=ApiRoute
)


def _project_api_error(exc: ValueError) -> ApiError:
    code = getattr(exc, "code", "invalid_project_request")
    status_code = 404 if code == "project_not_found" else 400
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


def _capability_data(capabilities) -> ProviderCapabilityData:
    return ProviderCapabilityData(
        supports_structured_output=capabilities.supports_structured_output,
        supports_remote_mcp=capabilities.supports_remote_mcp,
        supports_local_mcp=capabilities.supports_local_mcp,
        supports_tool_approval=capabilities.supports_tool_approval,
        supports_local_only_mode=capabilities.supports_local_only_mode,
    )


def _masked_key_preview(api_key: str | None) -> str | None:
    if not api_key:
        return None
    if len(api_key) <= 8:
        return "****"
    return f"{api_key[:3]}****{api_key[-4:]}"


def _provider_settings_data(provider_settings) -> ProviderSettingsData:
    return ProviderSettingsData(
        provider=provider_settings.provider,
        model=provider_settings.model,
        api_base=provider_settings.api_base,
        local_mode=provider_settings.local_mode,
        request_timeout_seconds=provider_settings.request_timeout_seconds,
        source=provider_settings.source,
        api_key_present=bool(provider_settings.api_key),
        api_key_preview=_masked_key_preview(provider_settings.api_key),
        capabilities=_capability_data(provider_settings.capabilities),
    )


def _provider_option_data(provider: str, label: str) -> ProviderOptionData:
    defaults = provider_defaults(provider)
    provider_settings = get_provider_settings(provider)
    return ProviderOptionData(
        provider=provider,
        label=label,
        model=str(defaults["model"]),
        api_base=str(defaults["api_base"]),
        local_mode=bool(defaults["local_mode"]),
        requires_api_key=bool(defaults.get("requires_api_key", False)),
        capabilities=_capability_data(provider_settings.capabilities),
    )


def _provider_options_data() -> list[ProviderOptionData]:
    return [
        _provider_option_data(provider, label)
        for provider, label in provider_select_options().items()
    ]


def _topology_status_data(status) -> TopologyStatusData:
    return TopologyStatusData(**status.model_dump(exclude={"payload"}))


def _drift_cadence_data() -> TopologyDriftCadenceData:
    return TopologyDriftCadenceData(
        interval_hours=get_topology_drift_check_interval_hours(),
        options=list(TOPOLOGY_DRIFT_CHECK_INTERVAL_OPTIONS),
    )


def _custom_skill_status_data(status) -> CustomSkillStatusData:
    return CustomSkillStatusData(**status.model_dump())


def _custom_skill_statuses_data() -> list[CustomSkillStatusData]:
    return [
        _custom_skill_status_data(status) for status in get_custom_skill_statuses()
    ]


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


def _resolve_authorized_topology_project(
    *,
    authorization: dict[str, object],
    capability: str,
    project_id: int | None = None,
    project_key: str | None = None,
):
    if project_key is not None:
        require_project_permission(
            role=authorization["role"],
            capability=capability,
            project_key=project_key,
            allowed_project_keys=authorization["allowed_project_keys"],
        )
    if project_id is not None and project_key is None:
        require_project_permission(
            role=authorization["role"],
            capability=capability,
            allowed_project_keys=authorization["allowed_project_keys"],
        )
    try:
        project = resolve_project_reference(
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
    if project_key is None:
        require_project_permission(
            role=authorization["role"],
            capability=capability,
            project_key=project.project_key,
            allowed_project_keys=authorization["allowed_project_keys"],
        )
    return project


def _build_topology_context_response(
    *,
    authorization: dict[str, object],
    capability: str = "topology.read",
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> TopologyContextResponse:
    _reject_unscoped_workspace_id(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
    )
    try:
        project = _resolve_authorized_topology_project(
            authorization=authorization,
            capability=capability,
            project_id=project_id,
            project_key=project_key,
        )
    except PermissionError as exc:
        _raise_authorization_error(exc)
    except ValueError as exc:
        if _should_mask_scope_reference_error(
            authorization=authorization,
            exc=exc,
        ):
            raise _project_scope_forbidden_error() from exc
        raise _project_api_error(exc) from exc
    try:
        status = get_topology_status(
            project_id=project.id,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
        )
    except ValueError as exc:
        if _should_mask_scope_reference_error(
            authorization=authorization,
            exc=exc,
        ):
            raise _project_scope_forbidden_error() from exc
        raise _project_api_error(exc) from exc
    return TopologyContextResponse(
        data=TopologyContextData(
            project=ProjectData(**project.model_dump()),
            topology=TopologyStatusData(**status.model_dump(exclude={"payload"})),
        ),
        meta=build_meta(),
    )


def _build_settings_summary_response(
    *,
    authorization: dict[str, object],
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> SettingsSummaryResponse:
    topology_context = _build_topology_context_response(
        authorization=authorization,
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    feedback_payload = fetch_feedback_summary(
        project_id=topology_context.data.project.id,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    return SettingsSummaryResponse(
        data=SettingsSummaryData(
            provider=_provider_settings_data(get_provider_settings()),
            provider_options=_provider_options_data(),
            topology=topology_context.data.topology,
            drift_cadence=_drift_cadence_data(),
            feedback=FeedbackSummaryData(**feedback_payload),
            custom_skills=_custom_skill_statuses_data(),
        ),
        meta=build_meta(),
    )


@settings_router.get("", response_model=SettingsSummaryResponse)
def get_settings_summary(
    project_id: int | None = Query(default=None),
    project_key: str | None = Query(default=None),
    workspace_id: int | None = Query(default=None),
    workspace_key: str | None = Query(default=None),
    authorization: dict[str, object] = Depends(_authorization_context),
) -> SettingsSummaryResponse:
    """Return settings data needed by the React settings screen."""
    return _build_settings_summary_response(
        authorization=authorization,
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )


@settings_router.put("/provider", response_model=ProviderSettingsResponse)
def update_provider_settings(
    payload: ProviderSettingsRequest,
) -> ProviderSettingsResponse:
    """Persist active narrative provider settings and return validation state."""
    local_mode = bool(payload.local_mode) if payload.provider == "ollama" else False
    if local_mode:
        saved = activate_local_mode(
            model=payload.model.strip(),
            api_base=payload.api_base.strip(),
        )
    else:
        saved = save_provider_settings(
            provider=payload.provider.strip(),
            model=payload.model.strip(),
            api_base=payload.api_base.strip(),
            api_key=payload.api_key.strip() if payload.api_key else None,
            local_mode=local_mode,
            activate=True,
        )
    validation = validate_provider_settings(saved)
    return ProviderSettingsResponse(
        data=ProviderSettingsSaveData(
            settings=_provider_settings_data(saved),
            validation=ProviderValidationData(**validation),
        ),
        meta=build_meta(),
    )


@settings_router.post(
    "/topology/preview", response_model=TopologyValidationResponse
)
def preview_settings_topology(
    payload: TopologyUploadRequest,
    authorization: dict[str, object] = Depends(_authorization_context),
) -> TopologyValidationResponse:
    """Validate topology JSON without saving it."""
    try:
        project = _resolve_authorized_topology_project(
            authorization=authorization,
            capability="topology.manage",
            project_id=payload.project_id,
            project_key=payload.project_key,
        )
        status = validate_topology_definition(
            json.dumps(payload.topology),
            project_id=project.id,
            workspace_id=payload.workspace_id,
            workspace_key=payload.workspace_key,
        )
    except PermissionError as exc:
        _raise_authorization_error(exc)
    except ValueError as exc:
        raise _project_api_error(exc) from exc
    error_message = None
    success_message = "Topology validation passed."
    if status.blocking_errors:
        error_message = "Topology validation failed: " + "; ".join(
            status.blocking_errors
        )
        success_message = None
    return TopologyValidationResponse(
        data=TopologyValidationData(
            topology=_topology_status_data(status),
            success_message=success_message,
            error_message=error_message,
        ),
        meta=build_meta(),
    )


@settings_router.put("/topology", response_model=TopologyValidationResponse)
def update_settings_topology(
    payload: TopologyUploadRequest,
    authorization: dict[str, object] = Depends(_authorization_context),
) -> TopologyValidationResponse:
    """Save topology JSON for the active project scope."""
    try:
        project = _resolve_authorized_topology_project(
            authorization=authorization,
            capability="topology.manage",
            project_id=payload.project_id,
            project_key=payload.project_key,
        )
        status = save_topology_definition(
            json.dumps(payload.topology),
            project_id=project.id,
            workspace_id=payload.workspace_id,
            workspace_key=payload.workspace_key,
        )
    except PermissionError as exc:
        _raise_authorization_error(exc)
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            code="invalid_topology_definition",
            message=str(exc),
        ) from exc
    return TopologyValidationResponse(
        data=TopologyValidationData(
            topology=_topology_status_data(status),
            success_message="Topology context saved.",
            error_message=None,
        ),
        meta=build_meta(),
    )


@settings_router.put(
    "/topology/drift-cadence", response_model=TopologyDriftCadenceResponse
)
def update_topology_drift_cadence(
    payload: TopologyDriftCadenceRequest,
) -> TopologyDriftCadenceResponse:
    """Persist the topology drift check cadence."""
    try:
        interval = save_topology_drift_check_interval_hours(payload.interval_hours)
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            code="invalid_topology_drift_cadence",
            message=str(exc),
        ) from exc
    return TopologyDriftCadenceResponse(
        data=TopologyDriftCadenceData(
            interval_hours=interval,
            options=list(TOPOLOGY_DRIFT_CHECK_INTERVAL_OPTIONS),
        ),
        meta=build_meta(),
    )


@settings_router.get("/custom-skills", response_model=CustomSkillListResponse)
def list_custom_skills() -> CustomSkillListResponse:
    """Return custom skill override status."""
    statuses = _custom_skill_statuses_data()
    return CustomSkillListResponse(data=statuses, meta=build_meta(count=len(statuses)))


@settings_router.post("/custom-skills", response_model=CustomSkillUploadResponse)
def upload_custom_skill(
    payload: CustomSkillUploadRequest,
) -> CustomSkillUploadResponse:
    """Persist a custom markdown skill and return the updated status list."""
    try:
        saved = save_custom_skill(payload.filename, payload.content)
        saved_data = _custom_skill_status_data(saved)
        return CustomSkillUploadResponse(
            data=CustomSkillUploadData(
                statuses=_custom_skill_statuses_data(),
                saved=saved_data,
                success_message=f"Saved custom skill: {saved_data.name}.",
                error_message=None,
            ),
            meta=build_meta(),
        )
    except ValueError as exc:
        return CustomSkillUploadResponse(
            data=CustomSkillUploadData(
                statuses=_custom_skill_statuses_data(),
                saved=None,
                success_message=None,
                error_message=str(exc),
            ),
            meta=build_meta(),
        )


@router.get("/topology", response_model=TopologyContextResponse)
def get_project_topology(
    project_id: int | None = Query(default=None),
    project_key: str | None = Query(default=None),
    workspace_id: int | None = Query(default=None),
    workspace_key: str | None = Query(default=None),
    authorization: dict[str, object] = Depends(_authorization_context),
) -> TopologyContextResponse:
    return _build_topology_context_response(
        authorization=authorization,
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )


@router.post("/topology", response_model=TopologyContextResponse)
def save_project_topology(
    payload: TopologyContextRequest,
    authorization: dict[str, object] = Depends(_authorization_context),
) -> TopologyContextResponse:
    _reject_unscoped_workspace_id(
        project_id=payload.project_id,
        project_key=payload.project_key,
        workspace_id=payload.workspace_id,
    )
    try:
        project = _resolve_authorized_topology_project(
            authorization=authorization,
            capability="topology.manage",
            project_id=payload.project_id,
            project_key=payload.project_key,
        )
    except PermissionError as exc:
        _raise_authorization_error(exc)
    except ValueError as exc:
        if _should_mask_scope_reference_error(
            authorization=authorization,
            exc=exc,
        ):
            raise _project_scope_forbidden_error() from exc
        raise _project_api_error(exc) from exc

    try:
        save_topology_definition(
            json.dumps(payload.topology),
            project_id=project.id,
            workspace_id=payload.workspace_id,
            workspace_key=payload.workspace_key,
        )
    except ValueError as exc:
        if _should_mask_scope_reference_error(
            authorization=authorization,
            exc=exc,
        ):
            raise _project_scope_forbidden_error() from exc
        raise ApiError(
            status_code=400,
            code="invalid_topology_definition",
            message=str(exc),
        ) from exc

    return _build_topology_context_response(
        authorization=authorization,
        capability="topology.read",
        project_id=project.id,
        workspace_id=payload.workspace_id,
        workspace_key=payload.workspace_key,
    )
