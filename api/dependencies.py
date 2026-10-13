"""Verified human identity dependencies, separate from project permissions."""

from __future__ import annotations

import secrets
from contextlib import contextmanager
from urllib.parse import urlsplit

from fastapi import Request

import config
from api.errors import ApiError
from services.identity_service import IdentityError, IdentityService, VerifiedPrincipal


def auth_error(request: Request, status: int, code: str) -> ApiError:
    correlation = getattr(request.state, "identity_correlation", None)
    if correlation is None:
        correlation = secrets.token_hex(16)
        request.state.identity_correlation = correlation
    return ApiError(
        status,
        code,
        "Authentication denied.",
        {
            "retryable": status in {429, 503},
            "correlation_id": correlation,
        },
    )


def identity_service() -> IdentityService:
    return IdentityService(
        security_profile=config.settings.identity_profile,
        trusted_origin=config.settings.identity_origin,
    )


def identity_cookie_name() -> str:
    return (
        "dw-local-session"
        if config.settings.identity_profile == "local-development"
        else "__Host-dw-session"
    )


def check_identity_transport(request: Request, *, mutation: bool = False) -> None:
    """Trust configured origin and ASGI transport, never caller proxy headers."""
    profile, origin = config.settings.identity_profile, config.settings.identity_origin
    try:
        parsed = urlsplit(origin)
        parsed.port
        valid = (
            0 < len(origin) <= 512
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
            and not any(c.isspace() for c in origin)
            and (
                (profile == "https" and parsed.scheme == "https")
                or (
                    profile == "local-development"
                    and parsed.scheme == "http"
                    and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                )
            )
        )
        actual_origin = f"{request.url.scheme}://{request.url.netloc}"
        if not valid or actual_origin != origin:
            raise ValueError
    except ValueError:
        raise auth_error(request, 403, "identity_profile_disabled") from None
    if len(request.headers.getlist("host")) != 1:
        raise auth_error(request, 403, "identity_origin_denied")
    origins = request.headers.getlist("origin")
    if (mutation and origins != [origin]) or (origins and origins != [origin]):
        raise auth_error(request, 403, "identity_origin_denied")
    if request.headers.getlist("authorization"):
        raise auth_error(request, 401, "authentication_failed")


def session_token(request: Request) -> str:
    # Duplicate cookies must not pick attacker-controlled order.
    name = identity_cookie_name()
    cookies = [
        part.strip()
        for value in request.headers.getlist("cookie")
        for part in value.split(";")
    ]
    candidates = [
        part.partition("=")[2] for part in cookies if part.partition("=")[0] == name
    ]
    if len(candidates) != 1 or len(candidates[0]) != 43:
        raise auth_error(request, 401, "authentication_failed")
    return candidates[0]


def csrf_token(request: Request) -> str:
    values = request.headers.getlist("x-csrf-token")
    if len(values) != 1 or len(values[0]) != 43:
        raise auth_error(request, 403, "csrf_failed")
    return values[0]


def call_identity(request: Request, function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except IdentityError as exc:
        raise auth_error(request, exc.status_code, exc.code) from None


def require_human_principal(request: Request) -> VerifiedPrincipal:
    """Future automation routes reuse identity and add their own live scope check."""
    mutation = request.method not in {"GET", "HEAD", "OPTIONS"}
    check_identity_transport(request, mutation=mutation)
    return call_identity(
        request,
        identity_service().resolve_session,
        session_token(request),
        csrf_token=csrf_token(request) if mutation else None,
    )


@contextmanager
def bind_project_credentials(request: Request):
    """Bind the request before running a route, validating only protected access.

    Invoke from an async route wrapper/middleware so synchronous route execution
    inherits the context. Legacy evaluation requests need no identity cookie.
    """
    from services.project_service import TrustedAuthorizationError, credential_context

    mutation = request.method not in {"GET", "HEAD", "OPTIONS"}
    try:
        token = session_token(request)
    except ApiError:
        token = ""
    try:
        csrf = csrf_token(request) if mutation else None
    except ApiError:
        csrf = ""

    def transport_check():
        try:
            check_identity_transport(request, mutation=mutation)
        except ApiError:
            raise TrustedAuthorizationError() from None

    with credential_context(
        identity_service(),
        token,
        csrf_token=csrf,
        mutation=mutation,
        transport_check=transport_check,
    ):
        yield
