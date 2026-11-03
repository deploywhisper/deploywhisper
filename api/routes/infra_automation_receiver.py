"""Receiver-only authenticated channel; human sessions never authorize this router."""

from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from infra_automation.handoff import ReceiverCredential
from infra_automation.lifecycle import LifecycleError
from infra_automation.receiver_http_contracts import (
    BootstrapRequest,
    ConsumeRequest,
    ReceiverRequest,
    CallbackEnvelope,
)
from api.routes.infra_automation import _bounded_body, _error, _response, ObjectId
from services import infra_automation_handoffs as handoffs
from services import project_service as authorization


class ReceiverRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                if request.url.scheme != "https" or request.query_params:
                    raise LifecycleError(403)
                if request.method == "POST":
                    await _bounded_body(request)
                response = await original(request)
                response.headers["Cache-Control"] = "no-store"
                return response
            except (LifecycleError, authorization.TrustedAuthorizationError) as exc:
                return _error(exc.status_code)
            except RequestValidationError:
                return _error(422)
            except Exception:
                return _error(503)

        return handler


router = APIRouter(
    prefix="/api/v1/infra-automation/handoffs",
    tags=["infra-automation-receiver"],
    route_class=ReceiverRoute,
)


def credential(request):
    receiver = request.headers.getlist("x-receiver-id")
    tokens = request.headers.getlist("authorization")
    if (
        len(receiver) != 1
        or len(tokens) != 1
        or not tokens[0].startswith("Bearer ")
        or not receiver[0]
    ):
        raise LifecycleError(401)
    return ReceiverCredential(receiver[0], tokens[0][7:])


@router.post("/{operation_id}/receipt")
def bootstrap(operation_id: ObjectId, payload: BootstrapRequest, request: Request):
    return _response(
        handoffs._default_service.bootstrap(
            operation_id, payload.binding_digest, credential(request)
        )
    )


@router.post("/{operation_id}/consume")
def consume(operation_id: ObjectId, payload: ConsumeRequest, request: Request):
    if payload.message.operation_id != operation_id:
        raise LifecycleError(409)
    return _response(
        handoffs._default_service.consume(
            payload.message, payload.grant_token, credential(request)
        )
    )


@router.get("/{operation_id}/status")
def status(operation_id: ObjectId, request: Request):
    return _response(
        handoffs._default_service.receiver_status(operation_id, credential(request))
    )


@router.post("/{operation_id}/authorize-action")
def authorize(operation_id: ObjectId, payload: ReceiverRequest, request: Request):
    return _response(
        handoffs._default_service.authorize_action(operation_id, credential(request))
    )


@router.post("/{operation_id}/outcome")
def outcome(operation_id: ObjectId, payload: CallbackEnvelope, request: Request):
    if payload.operation_id != operation_id:
        raise LifecycleError(409)
    return _response(handoffs._default_service.callback(payload, credential(request)))
