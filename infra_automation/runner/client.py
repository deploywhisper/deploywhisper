"""Bounded outbound HTTPS protocol client; no execution or tool discovery."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import http.client
import json
import ssl
import time
from urllib.parse import urlsplit

from pydantic import TypeAdapter
from infra_automation.contracts import Identifier
from infra_automation.runner.protocol import (
    MAX_BYTES,
    RunnerMessage,
    TaskScope,
    _wire,
    parse_message,
    parse_enrollment,
)


class RunnerClientError(Exception):
    def __init__(self):
        super().__init__("Runner operation unavailable.")


def _transport(method, url, headers, body, timeout):
    """Direct verified TLS: no ambient proxies, redirects, or retries."""
    parsed = urlsplit(url)
    connection = http.client.HTTPSConnection(
        parsed.hostname,
        parsed.port,
        timeout=timeout,
        context=ssl.create_default_context(),
    )
    try:
        connection.request(method, parsed.path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, response.read(MAX_BYTES + 1)
    finally:
        connection.close()


@dataclass(frozen=True)
class TaskAssignment:
    message: RunnerMessage
    task_token: str = field(repr=False)


class RunnerClient:
    def __init__(self, base_url, runner_id, token, *, transport=None, sleep=time.sleep):
        try:
            parsed = urlsplit(base_url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or parsed.path not in ("", "/")
                or any(ord(c) < 33 for c in base_url)
            ):
                raise ValueError
            parsed.port
            TypeAdapter(Identifier).validate_python(runner_id)
            self._token(token)
        except Exception:
            raise RunnerClientError() from None
        self.base_url = base_url.rstrip("/")
        self.runner_id = runner_id
        self._credential = token
        self._transport = transport or _transport
        self._sleep = sleep

    @staticmethod
    def _token(token):
        if (
            type(token) is not str
            or not 1 <= len(token) <= 256
            or any(ord(c) < 33 or ord(c) > 126 for c in token)
        ):
            raise RunnerClientError()

    def _request(self, method, suffix, payload=None, *, task_token=None):
        try:
            headers = {
                "Authorization": "Bearer " + self._credential,
                "X-Runner-Id": self.runner_id,
                "Accept": "application/json",
            }
            if task_token is not None:
                self._token(task_token)
                headers["X-Runner-Task-Token"] = task_token
            body = None
            if payload is not None:
                body = json.dumps(
                    _wire(payload),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
                headers["Content-Type"] = "application/json"
            status, raw = self._transport(
                method,
                self.base_url + "/api/v1/infra-automation/runners" + suffix,
                headers,
                body,
                10,
            )
            if status != 200 or type(raw) is not bytes or len(raw) > MAX_BYTES:
                raise RunnerClientError()
            envelope = _wire(raw)
            if (
                type(envelope) is not dict
                or "data" not in envelope
                or set(envelope) - {"data", "meta"}
            ):
                raise RunnerClientError()
            return envelope["data"]
        except Exception:
            raise RunnerClientError() from None

    def redeem(self, enrollment):
        """Redeem once using the constructor's enrollment bearer; never retry."""
        try:
            enrollment = parse_enrollment(enrollment)
            if enrollment.runner_id != self.runner_id:
                raise RunnerClientError()
            result = self._request(
                "POST",
                "/enrollments/" + enrollment.enrollment_id + "/redeem",
                enrollment.model_dump(mode="json"),
            )
            if (
                type(result) is not dict
                or result.get("runner_id") != self.runner_id
                or result.get("audience") != "runner-task-v1"
            ):
                raise RunnerClientError()
            self._token(result.get("token"))
            return result
        except Exception:
            raise RunnerClientError() from None

    def send(self, message, task_token, *, upload_bytes=None):
        try:
            message = parse_message(message)
            if message.scope.runner_id != self.runner_id:
                raise RunnerClientError()
            path = {
                "claim": "/claim",
                "heartbeat": "/heartbeat",
                "log": "/logs",
                "upload": "/uploads",
                "complete": "/complete",
            }[message.operation]
            payload = message.model_dump(mode="json")
            if message.operation == "upload":
                if type(upload_bytes) is not bytes:
                    raise RunnerClientError()
                payload = {
                    "message": payload,
                    "screened_content": base64.b64encode(upload_bytes).decode("ascii"),
                }
            elif upload_bytes is not None:
                raise RunnerClientError()
            result = self._request("POST", path, payload, task_token=task_token)
            if type(result) is not dict or set(result) != {
                "scope",
                "sequence",
                "state",
            }:
                raise RunnerClientError()
            scope = TaskScope.model_validate(result["scope"])
            if (
                scope.model_dump(exclude={"lease_deadline"})
                != message.scope.model_dump(exclude={"lease_deadline"})
                or type(result["sequence"]) is not int
                or result["sequence"] != message.sequence
                or result["state"] not in {"claimed", "running", "succeeded", "failed"}
            ):
                raise RunnerClientError()
            return result
        except Exception:
            # Never echo validation bodies, response text or transport errors.
            raise RunnerClientError() from None

    def poll(self, *, max_polls=20):
        if type(max_polls) is not int or not 1 <= max_polls <= 100:
            raise RunnerClientError()
        for index in range(max_polls):
            value = self._request("GET", "/" + self.runner_id + "/tasks")
            if value is not None:
                try:
                    if type(value) is not dict or set(value) != {
                        "scope",
                        "profile_digest",
                        "capabilities",
                        "task_token",
                    }:
                        raise RunnerClientError()
                    self._token(value["task_token"])
                    message = parse_message(
                        {
                            key: child
                            for key, child in value.items()
                            if key != "task_token"
                        }
                        | {"operation": "claim", "sequence": 1}
                    )
                    if message.scope.runner_id != self.runner_id:
                        raise RunnerClientError()
                    return TaskAssignment(message, value["task_token"])
                except Exception:
                    raise RunnerClientError() from None
            if index + 1 < max_polls:
                self._sleep(min(0.25 * (2 ** min(index, 5)), 5.0))
        return None

    def run(self, *, handler=None, max_polls=20):
        """Only a locally installed trusted handler can execute collected work.

        The application has no qualified collection handler until 16.13/16.14.
        A server response can never select or supply Python/shell commands.
        """
        if handler is None or not callable(handler):
            raise RunnerClientError()
        assignment = self.poll(max_polls=max_polls)
        if assignment is None:
            return False
        result = self.send(assignment.message, assignment.task_token)
        if result["state"] not in {"claimed", "running"}:
            raise RunnerClientError()
        next_message = parse_message(
            assignment.message.model_dump(mode="json")
            | {
                "scope": result["scope"],
                "operation": "heartbeat",
                "sequence": result["sequence"] + 1,
            }
        )
        handler(self, TaskAssignment(next_message, assignment.task_token))
        return True
