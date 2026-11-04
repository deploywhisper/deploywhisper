"""HTTPS-only runner channel, independent of human and receiver credentials."""

from __future__ import annotations

import base64
from typing import Annotated
from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import Field, StrictStr
from api.routes.infra_automation import _bounded_body, _error, _response, ObjectId
from infra_automation.contracts import ClosedModel
from infra_automation.lifecycle import LifecycleError
from infra_automation.runner.protocol import RunnerCredential, RunnerMessage, Enrollment
from services import infra_automation_runners as runners
from services import infra_automation_runner_tasks as tasks
from services import project_service as authorization


class RunnerRoute(APIRoute):
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
    prefix="/api/v1/infra-automation/runners",
    tags=["infra-automation-runner"],
    route_class=RunnerRoute,
)


def _bearer(request: Request) -> str:
    values = request.headers.getlist("authorization")
    if len(values) != 1 or not values[0].startswith("Bearer "):
        raise LifecycleError(401)
    token = values[0][7:]
    if not token or len(token) > 256:
        raise LifecycleError(401)
    return token


def _task_token(request: Request) -> str:
    values = request.headers.getlist("x-runner-task-token")
    if len(values) != 1 or not values[0] or len(values[0]) > 256:
        raise LifecycleError(401)
    return values[0]


@router.get("/{runner_id}/tasks")
def poll(runner_id: ObjectId, request: Request):
    return _response(tasks.poll(RunnerCredential(runner_id, _bearer(request))))


@router.post("/enrollments/{enrollment_id}/redeem")
def redeem(enrollment_id: ObjectId, payload: Enrollment, request: Request):
    if payload.enrollment_id != enrollment_id:
        raise LifecycleError(409)
    from api.routes.infra_automation_runner_admin import reveal

    return _response(
        reveal(runners.redeem(enrollment_id, _bearer(request), enrollment=payload))
    )


def _operate(
    operation: str, message: RunnerMessage, request: Request, upload_bytes=None
):
    if message.operation != operation:
        raise LifecycleError(409)
    return _response(
        tasks.operate(
            message,
            RunnerCredential(message.scope.runner_id, _bearer(request)),
            _task_token(request),
            upload_bytes=upload_bytes,
        )
    )


@router.post("/claim")
def claim(payload: RunnerMessage, request: Request):
    return _operate("claim", payload, request)


@router.post("/heartbeat")
def heartbeat(payload: RunnerMessage, request: Request):
    return _operate("heartbeat", payload, request)


@router.post("/logs")
def logs(payload: RunnerMessage, request: Request):
    return _operate("log", payload, request)


class UploadRequest(ClosedModel):
    message: RunnerMessage
    screened_content: Annotated[StrictStr, Field(max_length=120000, repr=False)]


@router.post("/uploads")
def upload(payload: UploadRequest, request: Request):
    try:
        content = base64.b64decode(payload.screened_content, validate=True)
    except ValueError:
        raise LifecycleError(422) from None
    return _operate("upload", payload.message, request, upload_bytes=content)


@router.post("/complete")
def complete(payload: RunnerMessage, request: Request):
    return _operate("complete", payload, request)
