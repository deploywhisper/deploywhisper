"""Bounded human login, sessions and authenticated account administration."""

from __future__ import annotations

import json
import secrets
from typing import TypeVar

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool
from services.identity_service import IdentityError, validate_username

import config
from api import dependencies as identity
from api.errors import ApiError, ApiRoute
from api.schemas import (
    HumanAccountRequest,
    HumanLoginRequest,
    HumanSessionResponse,
    HumanPrincipalResponse,
    HumanAccountResponse,
    HumanLogoutResponse,
    ErrorResponse,
    build_meta,
)

MAX_AUTH_BODY_BYTES = 4096
AuthPayload = TypeVar("AuthPayload", HumanLoginRequest, HumanAccountRequest)


class IdentityRoute(ApiRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request: Request):
            request.state.identity_correlation = secrets.token_hex(16)
            response = await handler(request)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            response.headers["X-Correlation-ID"] = request.state.identity_correlation
            return response

        return handle


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["identity"],
    route_class=IdentityRoute,
    responses={
        status: {"model": ErrorResponse} for status in (400, 401, 403, 429, 503)
    },
)


async def _body(request: Request, schema: type[AuthPayload]) -> AuthPayload:
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise identity.auth_error(request, 400, "invalid_identity_request")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_AUTH_BODY_BYTES:
            raise identity.auth_error(request, 400, "invalid_identity_request")
        body.extend(chunk)
    try:

        def unique_object(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError
                value[key] = item
            return value

        payload = json.loads(body.decode("utf-8"), object_pairs_hook=unique_object)
        if not isinstance(payload, dict):
            raise ValueError
        value = schema.model_validate(payload)
        password = value.password.get_secret_value()
        if not 1 <= len(password.encode("utf-8")) <= 1024:
            raise ValueError
        validate_username(value.username)
        return value
    except (
        ValueError,
        TypeError,
        UnicodeError,
        RecursionError,
        ValidationError,
        IdentityError,
    ):
        raise identity.auth_error(request, 400, "invalid_identity_request") from None


def _wire(schema: type[BaseModel]) -> dict:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": schema.model_json_schema()}},
        }
    }


def _response(request: Request, data) -> JSONResponse:
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")
    return JSONResponse(
        {
            "data": data,
            "meta": build_meta(correlation_id=request.state.identity_correlation),
        }
    )


def _session_response(request: Request, issued) -> JSONResponse:
    response = _response(
        request,
        {
            "principal": issued.principal.model_dump(mode="json"),
            "csrf_token": issued.csrf_token.get_secret_value(),
        },
    )
    response.set_cookie(
        identity.identity_cookie_name(),
        issued.token.get_secret_value(),
        httponly=True,
        secure=config.settings.identity_profile == "https",
        samesite="strict",
        path="/",
    )
    return response


@router.post(
    "/login",
    response_model=HumanSessionResponse,
    openapi_extra=_wire(HumanLoginRequest),
)
async def login(request: Request):
    identity.check_identity_transport(request, mutation=True)
    service = identity.identity_service()
    try:
        payload = await _body(request, HumanLoginRequest)
    except ApiError:
        await run_in_threadpool(
            identity.call_identity, request, service.record_failed_login_attempt
        )
        raise
    issued = await run_in_threadpool(
        identity.call_identity,
        request,
        service.login,
        payload.username,
        payload.password.get_secret_value(),
    )
    return _session_response(request, issued)


@router.get("/session", response_model=HumanPrincipalResponse)
def current_principal(request: Request):
    return _response(request, identity.require_human_principal(request))


@router.post("/logout", response_model=HumanLogoutResponse)
def logout(request: Request):
    identity.check_identity_transport(request, mutation=True)
    identity.call_identity(
        request,
        identity.identity_service().logout,
        identity.session_token(request),
        csrf_token=identity.csrf_token(request),
    )
    response = _response(request, {"logged_out": True})
    response.delete_cookie(
        identity.identity_cookie_name(),
        path="/",
        secure=config.settings.identity_profile == "https",
        httponly=True,
        samesite="strict",
    )
    return response


@router.post("/session/rotate", response_model=HumanSessionResponse)
def rotate_session(request: Request):
    identity.check_identity_transport(request, mutation=True)
    issued = identity.call_identity(
        request,
        identity.identity_service().rotate_session,
        identity.session_token(request),
        csrf_token=identity.csrf_token(request),
    )
    return _session_response(request, issued)


@router.post(
    "/accounts",
    response_model=HumanAccountResponse,
    openapi_extra=_wire(HumanAccountRequest),
)
async def create_account(request: Request):
    identity.check_identity_transport(request, mutation=True)
    token, csrf = identity.session_token(request), identity.csrf_token(request)
    payload = await _body(request, HumanAccountRequest)
    account = await run_in_threadpool(
        identity.call_identity,
        request,
        identity.identity_service().create_account,
        token,
        payload.username,
        payload.password.get_secret_value(),
        csrf_token=csrf,
        is_admin=payload.is_admin,
    )
    return _response(request, account)


@router.post("/accounts/{principal_id}/revoke", response_model=HumanAccountResponse)
def revoke_account(request: Request, principal_id: str):
    identity.check_identity_transport(request, mutation=True)
    account = identity.call_identity(
        request,
        identity.identity_service().revoke_account,
        identity.session_token(request),
        principal_id,
        csrf_token=identity.csrf_token(request),
    )
    return _response(request, account)
