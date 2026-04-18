"""Standard API error envelope helpers."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
import logging
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.schemas import ErrorResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(
        self, status_code: int, code: str, message: str, details: dict | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def is_api_request(request: Request) -> bool:
    return request.url.path.startswith("/api/")


def build_error(code: str, message: str, details: dict[str, Any] | None = None) -> dict:
    return ErrorResponse(
        error={
            "code": code,
            "message": message,
            "details": details or {},
        }
    ).model_dump()


def build_error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=build_error(code=code, message=message, details=details),
    )


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return build_error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def validation_error_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    if not is_api_request(_):
        return await request_validation_exception_handler(_, exc)

    issues: list[dict[str, Any]] = []
    for error in exc.errors():
        issue = {key: value for key, value in error.items() if key != "url"}
        if "loc" in issue:
            issue["loc"] = list(issue["loc"])
        issues.append(issue)

    return build_error_response(
        status_code=422,
        code="request_validation_failed",
        message="Request validation failed.",
        details={"issues": issues},
    )


def _http_error_code(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase.lower().replace(" ", "_")
    except ValueError:
        return f"http_{status_code}"


async def http_error_envelope_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    if not is_api_request(request):
        return await http_exception_handler(request, exc)

    detail = (
        exc.detail
        if isinstance(exc.detail, str)
        else HTTPStatus(exc.status_code).phrase
    )
    details = exc.detail if isinstance(exc.detail, dict) else {}
    return build_error_response(
        status_code=exc.status_code,
        code=_http_error_code(exc.status_code),
        message=detail,
        details=details,
    )


async def internal_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API exception", exc_info=exc)
    return build_error_response(
        status_code=500,
        code="internal_error",
        message="Internal server error.",
    )


class ApiRoute(APIRoute):
    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def custom_route_handler(request: Request):
            try:
                return await original_handler(request)
            except ApiError as exc:
                return await api_error_handler(request, exc)
            except RequestValidationError as exc:
                return await validation_error_handler(request, exc)
            except StarletteHTTPException as exc:
                return await http_error_envelope_handler(request, exc)
            except Exception as exc:  # noqa: BLE001
                return await internal_error_handler(request, exc)

        return custom_route_handler
