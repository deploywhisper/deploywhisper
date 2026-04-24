"""Skills registry API routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from api.errors import ApiError, ApiRoute
from api.schemas import (
    ErrorResponse,
    SkillRegistryContentData,
    SkillRegistryContentResponse,
    SkillRegistryData,
    SkillRegistryDetailResponse,
    SkillRegistryListMetaPayload,
    SkillRegistryListResponse,
    SkillRegistryResourceMetaPayload,
    SkillRegistryTestResultsResponse,
    SkillRegistryVersionData,
    SkillRegistryVersionsResponse,
    SkillTestResultsData,
)
from config import settings
from services.skill_registry_service import (
    fetch_skill_registry_content,
    fetch_skill_registry_entry,
    fetch_skill_registry_page,
    fetch_skill_registry_versions,
)
from services.skill_test_harness_service import run_skill_test_suite

router = APIRouter(prefix="/api/v1/skills", tags=["skills"], route_class=ApiRoute)


@router.get(
    "",
    response_model=SkillRegistryListResponse,
    responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
def list_skills(
    tool: str | None = Query(
        default=None,
        description="Filter by primary tool family, such as terraform or kubernetes.",
    ),
    tag: str | None = Query(
        default=None,
        description="Filter by a single tag from the skill metadata.",
    ),
    author: str | None = Query(
        default=None,
        description="Filter by author or owner label.",
    ),
    search: str | None = Query(
        default=None,
        description="Case-insensitive keyword search across name, description, tags, and triggers.",
    ),
    page: int = Query(default=1, ge=1, description="1-based results page."),
    page_size: int = Query(
        default=50,
        ge=1,
        le=100,
        description="Maximum number of results to return per page.",
    ),
) -> SkillRegistryListResponse:
    page_payload = fetch_skill_registry_page(
        tool=tool,
        tag=tag,
        author=author,
        search=search,
        page=page,
        page_size=page_size,
    )
    filters = {
        key: value
        for key, value in {
            "tool": tool,
            "tag": tag,
            "author": author,
            "search": search,
        }.items()
        if value
    }
    return SkillRegistryListResponse(
        data=[SkillRegistryData(**item.model_dump()) for item in page_payload.items],
        meta=SkillRegistryListMetaPayload(
            app=settings.app_name,
            version=settings.app_version,
            count=len(page_payload.items),
            total_count=page_payload.total_count,
            page=page_payload.page,
            page_size=page_payload.page_size,
            filters=filters,
        ),
    )


@router.get(
    "/{skill_id}",
    response_model=SkillRegistryDetailResponse,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_skill(skill_id: str) -> SkillRegistryDetailResponse:
    skill = fetch_skill_registry_entry(skill_id)
    if skill is None:
        raise ApiError(
            status_code=404,
            code="skill_not_found",
            message="Skill not found.",
        )
    return SkillRegistryDetailResponse(
        data=SkillRegistryData(**skill.model_dump()),
        meta=SkillRegistryResourceMetaPayload(
            app=settings.app_name,
            version=settings.app_version,
            id=skill.id,
        ),
    )


@router.get(
    "/{skill_id}/versions",
    response_model=SkillRegistryVersionsResponse,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_skill_versions(skill_id: str) -> SkillRegistryVersionsResponse:
    versions = fetch_skill_registry_versions(skill_id)
    if not versions:
        raise ApiError(
            status_code=404,
            code="skill_not_found",
            message="Skill not found.",
        )
    return SkillRegistryVersionsResponse(
        data=[SkillRegistryVersionData(**version.model_dump()) for version in versions],
        meta=SkillRegistryResourceMetaPayload(
            app=settings.app_name,
            version=settings.app_version,
            id=skill_id.strip().lower(),
        ),
    )


@router.get(
    "/{skill_id}/content",
    response_model=SkillRegistryContentResponse,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_skill_content(
    skill_id: str,
    version: str | None = Query(
        default=None,
        description="Optional exact version selector for install payload retrieval.",
    ),
) -> SkillRegistryContentResponse:
    skill_content = fetch_skill_registry_content(skill_id, version=version)
    if skill_content is None:
        raise ApiError(
            status_code=404,
            code="skill_not_found",
            message="Skill not found.",
        )
    return SkillRegistryContentResponse(
        data=SkillRegistryContentData(**skill_content.model_dump()),
        meta=SkillRegistryResourceMetaPayload(
            app=settings.app_name,
            version=settings.app_version,
            id=skill_content.id,
        ),
    )


@router.get(
    "/{skill_id}/test-results",
    response_model=SkillRegistryTestResultsResponse,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_skill_test_results(skill_id: str) -> SkillRegistryTestResultsResponse:
    suite_result = run_skill_test_suite(skill_id.strip().lower())
    if suite_result is None:
        raise ApiError(
            status_code=404,
            code="skill_not_found",
            message="Skill not found.",
        )
    return SkillRegistryTestResultsResponse(
        data=SkillTestResultsData(**suite_result.model_dump()),
        meta=SkillRegistryResourceMetaPayload(
            app=settings.app_name,
            version=settings.app_version,
            id=suite_result.skill_id,
        ),
    )
