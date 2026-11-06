"""Raw-byte signed ingress precedes every JSON parser and human-only alias."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool

from api.dependencies import (
    require_human_principal,
    check_identity_transport,
    identity_service,
)
from api.errors import ApiRoute, ApiError
from api.routes.infra_automation import (
    AutomationRoute,
    _bounded_body,
    _error,
    _response,
)
from api.schemas import (
    AutomationMeta,
    AutomationRunResponse,
    AutomationRunListResponse,
    AutomationValidationResponse,
    AutomationErrorResponse,
)
from infra_automation.contracts import ClosedModel
from infra_automation.lifecycle import LifecycleError, ValidateWorkflowRequest
from infra_automation.state import RunRequest
from infra_automation.preflight_contracts import PreflightRequest
from infra_automation.trigger_contracts import (
    TriggerRequest,
    TriggerStatusRequest,
    TriggerListRequest,
)
from infra_automation.trigger_signing import (
    KEY_ID_HEADER,
    TIMESTAMP_HEADER,
    NONCE_HEADER,
    SIGNATURE_HEADER,
    MAX_BODY_BYTES,
    TriggerSignatureError,
    SIGNED_PATHS,
)
from services.infra_automation_trigger_authority import TriggerAuthority
from services.infra_automation_triggers import (
    ProvisionPrincipalRequest,
    ProvisionedPrincipal,
)
from services import infra_automation_triggers as service
from services import project_service as auth
from services.identity_service import IdentityError


class SignedTriggerRoute(ApiRoute):
    def get_route_handler(self):
        original = APIRoute.get_route_handler(self)

        async def handler(request: Request):
            try:
                check_identity_transport(request, mutation=False)
                if (
                    request.scope.get("raw_path") != self.path.encode("ascii")
                    or request.scope.get("query_string")
                    or request.headers.getlist("cookie")
                    or request.headers.getlist("authorization")
                ):
                    raise LifecycleError(401)
                headers = {}
                for name, field in (
                    (KEY_ID_HEADER, "key_id"),
                    (TIMESTAMP_HEADER, "timestamp"),
                    (NONCE_HEADER, "nonce"),
                    (SIGNATURE_HEADER, "signature"),
                ):
                    values = request.headers.getlist(name)
                    if len(values) != 1 or len(values[0]) > 200:
                        raise LifecycleError(401)
                    headers[field] = values[0]
                body = bytearray()
                async for chunk in request.stream():
                    if len(body) + len(chunk) > MAX_BODY_BYTES:
                        raise LifecycleError(429)
                    body.extend(chunk)
                identity = identity_service()
                credential = TriggerAuthority(
                    **headers,
                    method=request.method,
                    path=self.path,
                    body=bytes(body),
                    session_factory=identity.session_factory,
                    now=identity.now,
                )
                await run_in_threadpool(credential.reserve_nonce)
                # Only a valid MAC and committed replay fence reach JSON decoding.
                request._body = bytes(body)
                await _bounded_body(request)
                credential.decoded_body()
                with credential.credentials(
                    transport_check=lambda: check_identity_transport(
                        request, mutation=False
                    )
                ):
                    response = await original(request)
                response.headers["Cache-Control"] = "no-store"
                return response
            except TriggerSignatureError:
                return _error(401)
            except (
                LifecycleError,
                ApiError,
                IdentityError,
                auth.TrustedAuthorizationError,
            ) as exc:
                return _error(exc.status_code)
            except RequestValidationError:
                return _error(422)
            except Exception:
                return _error(503)

        return handler


errors = {
    status: {"model": AutomationErrorResponse}
    for status in (401, 403, 409, 422, 429, 503)
}
router = APIRouter(
    prefix="/api/v1/infra-automation/triggers",
    route_class=SignedTriggerRoute,
    tags=["infra-automation"],
    responses=errors,
)


@router.post("/webhook", response_model=AutomationRunResponse)
@router.post("/cli/run", response_model=AutomationRunResponse)
def webhook(payload: TriggerRequest):
    return _response(service.request_trigger(payload))


@router.post("/validate", response_model=AutomationValidationResponse)
def validate(payload: ValidateWorkflowRequest):
    return _response(service.validate_signed(payload))


@router.post("/status", response_model=AutomationRunResponse)
def status(payload: TriggerStatusRequest):
    return _response(service.signed_status(payload))


@router.post("/list", response_model=AutomationRunListResponse)
def list_runs(payload: TriggerListRequest):
    return _response(service.signed_list(payload))


human_router = APIRouter(
    prefix="/api/v1/infra-automation",
    route_class=AutomationRoute,
    tags=["infra-automation"],
    dependencies=[Depends(require_human_principal)],
    responses=errors,
)


class ProvisionedPrincipalResponse(ClosedModel):
    data: ProvisionedPrincipal
    meta: AutomationMeta


@human_router.post("/triggers/principals", response_model=ProvisionedPrincipalResponse)
def provision(payload: ProvisionPrincipalRequest):
    return _response(service.provision_principal(payload))


@human_router.post("/cli/runs", response_model=AutomationRunResponse)
def human_run(payload: RunRequest):
    from services.infra_automation_engine_service import request_run

    with service.cli_origin():
        return _response(request_run(payload))


@human_router.post("/cli/preflights", response_model=AutomationRunResponse)
def human_preflight(payload: PreflightRequest):
    from services.infra_automation_preflight import request_preflight

    with service.cli_origin():
        return _response(request_preflight(payload))


async def reject_signed_path_alias():
    """Reject signed endpoint suffixes without consuming or parsing their body."""
    return _error(401)


for signed_path in sorted(SIGNED_PATHS):
    # A path converter also catches repeated trailing slashes before Starlette's
    # redirect fallback; unsupported descendants confer no alternate operation.
    router.routes.append(
        APIRoute(
            signed_path + "/{remainder:path}",
            reject_signed_path_alias,
            methods=["POST"],
            include_in_schema=False,
        )
    )
