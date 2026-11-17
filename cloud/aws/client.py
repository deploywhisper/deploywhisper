"""Credential-free manifests and bounded access to frozen read capabilities.

Response projection and plan parsing belong to the next connector story. This
primitive intentionally returns only safe execution metadata, never SDK payloads.
"""

from __future__ import annotations

from concurrent.futures import Future, wait, FIRST_COMPLETED
from dataclasses import dataclass
import json
import math
import re
import threading
import time
from pydantic import BaseModel, ConfigDict, Field, model_validator
from cloud.aws.allowlist import _CATALOG, authorize
from cloud.aws.session import validate_config
from cloud.aws.response_status import response_complete
from services.content_security import redact_text, redact_value


_SLOTS = threading.BoundedSemaphore(4)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _dns_selector(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 254:
        return False
    name = value.replace("\\052", "*")
    if name.endswith("."):
        name = name[:-1]
    labels = name.split(".")
    if labels[0] == "*":
        labels = labels[1:]
    return bool(labels) and all(
        re.fullmatch(r"[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?", label)
        for label in labels
    )


def _bucket_name(value):
    """Only ordinary bucket names belong to the frozen bucket capability."""
    if not isinstance(value, str) or not 3 <= len(value) <= 63:
        return False
    if value.startswith(("xn--", "sthree-", "amzn_s3_demo_")) or value.endswith(
        ("-s3alias", "--ol-s3", ".mrap", "--x-s3", "--table-s3")
    ):
        return False
    return re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}", value) is None and all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
        for label in value.split(".")
    )


def _matches(template, value):
    if isinstance(template, dict):
        return (
            isinstance(value, dict)
            and set(value) == set(template)
            and all(_matches(t, value[k]) for k, t in template.items())
        )
    if isinstance(template, list):
        return (
            isinstance(value, list)
            and len(value) == len(template)
            and all(_matches(t, v) for t, v in zip(template, value))
        )
    if isinstance(template, str) and template.startswith("${"):
        if not isinstance(value, str) or not 1 <= len(value) <= 2048:
            return False
        if template == "${id}":
            return (
                re.fullmatch(
                    r"(?:i|sg|eni|subnet|vpc|rtb|vol|snap)-(?:[0-9a-f]{8}|[0-9a-f]{17})",
                    value,
                )
                is not None
            )
        if template == "${account}":
            return re.fullmatch(r"[0-9]{12}", value) is not None
        if template.endswith("arn}"):
            return (
                re.fullmatch(
                    r"arn:aws:[a-z0-9-]+:(?:[a-z]+-[a-z]+-[1-9])?:[0-9]{12}:[A-Za-z0-9_:/+.,=@-]+",
                    value,
                )
                is not None
            )
        if template == "${canonical_queue_url}":
            return (
                re.fullmatch(
                    r"https://sqs\.[a-z]+-[a-z]+-[1-9]\.amazonaws\.com/[0-9]{12}/[A-Za-z0-9_-]+(?:\.fifo)?",
                    value,
                )
                is not None
            )
        return (
            re.fullmatch(r"[A-Za-z0-9_:/+.,=@-]+", value) is not None
            and "://" not in value
            and not value.startswith("/")
        )
    return type(value) is type(template) and value == template


class Call(BaseModel):
    """A validated exact request; copies are revalidated at execution."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    capability: str
    parameters: dict

    @model_validator(mode="after")
    def validate_request(self):
        row = _CATALOG["operations"].get(self.capability)
        if (
            row is None
            or not _matches(
                row["params"],
                {**self.parameters, "StartRecordName": "validated-dns-name"}
                if self.capability == "record"
                and _dns_selector(self.parameters.get("StartRecordName"))
                else self.parameters,
            )
            or (
                self.capability == "record"
                and not _dns_selector(self.parameters.get("StartRecordName"))
            )
            or (
                self.capability in ("bucket_versioning", "bucket_tags")
                and not _bucket_name(self.parameters.get("Bucket"))
            )
            or redact_value(self.parameters) != self.parameters
            or any(redact_text(v) != v for v in _strings(self.parameters))
        ):
            raise ValueError("AWS request scope denied")
        return self


def _calls(calls):
    if not isinstance(calls, (list, tuple)) or len(calls) > 1000:
        raise ValueError("AWS manifest bound exceeded")
    return [Call.model_validate(c.model_dump()) for c in calls]


def dry_run(calls):
    """Enumerate a recorded plan's validated manifest without touching the SDK."""
    return [
        dict(
            capability=c.capability,
            action=_CATALOG["operations"][c.capability]["iam_action"],
            service=_CATALOG["operations"][c.capability]["service"],
            operation=_CATALOG["operations"][c.capability]["operation"],
            parameters=c.parameters,
        )
        for c in _calls(calls)
    ]


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    per_call_timeout: float = Field(default=2.0, gt=0, le=2)
    total_deadline: float = Field(default=15.0, gt=0, le=15)
    concurrency: int = Field(default=4, ge=1, le=4, strict=True)
    call_budget: int = Field(default=100, ge=1, le=100, strict=True)
    backoff: float = Field(default=0.05, ge=0, le=1)

    @model_validator(mode="after")
    def finite(self):
        if not all(
            math.isfinite(x)
            for x in (self.per_call_timeout, self.total_deadline, self.backoff)
        ):
            raise ValueError("Finite bounds required")
        return self


@dataclass(frozen=True)
class CallResult:
    capability: str
    status: str
    missing_permission: str | None = None
    cause: str | None = None


@dataclass(frozen=True)
class ExecutionResult:
    items: tuple[CallResult, ...]
    attempts: int
    elapsed_seconds: float
    partial: bool


def _failure(error):
    from cloud.aws.session import SessionError

    if isinstance(error, SessionError):
        return error.cause, False
    response = getattr(error, "response", None)
    if isinstance(response, dict):
        detail = response.get("Error")
        code = detail.get("Code") if isinstance(detail, dict) else None
        if code in (
            "AccessDenied",
            "AccessDeniedException",
            "UnauthorizedOperation",
            "Forbidden",
        ):
            return "permission_denied", True
        if code in (
            "Throttling",
            "ThrottlingException",
            "RequestLimitExceeded",
            "SlowDown",
        ):
            return "throttled", False
        return "provider_error", False
    if type(error).__module__ == "botocore.exceptions" and type(error).__name__ in {
        "NoCredentialsError",
        "PartialCredentialsError",
        "CredentialRetrievalError",
        "TokenRetrievalError",
    }:
        return "credentials_unavailable", False
    if type(error).__module__ == "botocore.exceptions" and type(error).__name__ in {
        "EndpointConnectionError",
        "ConnectTimeoutError",
        "ReadTimeoutError",
        "ConnectionClosedError",
        "ProxyConnectionError",
        "SSLError",
        "HTTPClientError",
    }:
        return "transport_error", False
    if type(error).__module__ == "botocore.exceptions" and type(error).__name__ in {
        "ParamValidationError",
        "UnknownParameterError",
        "ValidationError",
    }:
        return "invalid_request", False
    if isinstance(error, (ConnectionError, TimeoutError, OSError)):
        return "transport_error", False
    if isinstance(error, (ValueError, TypeError)):
        return "invalid_request", False
    return "provider_error", False


class AwsReader:
    """Server-owned session only; no endpoint/credential inputs from requests."""

    def __init__(self, session, *, config=None):
        self._session = session
        self._config = validate_config(
            config if config is not None else {"region": "us-east-1"}
        )
        # Retain process-wide concurrency even after an uncooperative timed-out
        # call. Subsequent executions cannot pile up abandoned workers.
        self._slots = _SLOTS

    dry_run = staticmethod(dry_run)

    def execute(self, calls, *, limits=None, cancel=None):
        calls = _calls(calls)
        limits = Limits.model_validate((limits or Limits()).model_dump())
        cancel = cancel or threading.Event()
        start = time.monotonic()
        deadline = start + limits.total_deadline
        stop = threading.Event()
        attempts = 0
        results = {}
        pending = {}
        index = 0
        lock = threading.Lock()

        def issue(i, call):
            nonlocal attempts
            row = _CATALOG["operations"][call.capability]
            try:
                if cancel.is_set() or stop.is_set() or time.monotonic() >= deadline:
                    return CallResult(call.capability, "cancelled")

                def construct():
                    nonlocal attempts
                    with lock:
                        if (
                            cancel.is_set()
                            or stop.is_set()
                            or time.monotonic() >= deadline
                            or attempts >= limits.call_budget
                        ):
                            return CallResult(call.capability, "bounded")
                        attempts += 1
                    client = self._session.create_client(
                        row["service"],
                        self._config,
                        timeout=min(
                            limits.per_call_timeout,
                            max(0.001, deadline - time.monotonic()),
                        ),
                    )
                    if cancel.is_set() or stop.is_set() or time.monotonic() >= deadline:
                        return CallResult(call.capability, "cancelled")
                    response = client._make_api_call(
                        row["operation"], json.loads(json.dumps(call.parameters))
                    )
                    return CallResult(
                        call.capability,
                        "recorded"
                        if response_complete(call.capability, call.parameters, response)
                        else "incomplete",
                    )

                return authorize(row["iam_action"], construct)
            except Exception as error:
                # Keep a closed diagnostic vocabulary, never provider messages.
                cause, denied = _failure(error)
                return CallResult(
                    call.capability,
                    "unreadable",
                    row["iam_action"] if denied else None,
                    cause,
                )
            finally:
                self._slots.release()

        def submit(i, call):
            future = Future()

            def run():
                result = issue(i, call)
                # Capture completion in the worker, before scheduler wakeup.
                future.set_result((result, time.monotonic()))

            # No executor atexit join: a broken injected transport cannot hold
            # application shutdown hostage. Its slot stays held until return.
            threading.Thread(target=run, daemon=True).start()
            return future

        next_start = start

        def collect(done):
            nonlocal next_start
            for future in done:
                i, began = pending.pop(future)
                result, completed_at = future.result()
                if (
                    completed_at >= began + limits.per_call_timeout
                    or completed_at >= deadline
                ):
                    result = CallResult(calls[i].capability, "timeout")
                    stop.set()
                results[i] = result
                if result.status == "unreadable":
                    next_start = time.monotonic() + limits.backoff

        try:
            while index < len(calls) or pending:
                # Preserve already-completed timely work even if this polling
                # thread was delayed beyond the collection deadline.
                collect([future for future in pending if future.done()])
                now = time.monotonic()
                if cancel.is_set():
                    break
                if stop.is_set() or now >= deadline:
                    # Publication can race the snapshot above. Drain known
                    # completions once more after observing expiry; timestamps
                    # still decide whether those results were actually timely.
                    collect([future for future in pending if future.done()])
                    break
                while (
                    index < len(calls)
                    and len(pending) < limits.concurrency
                    and attempts + len(pending) < limits.call_budget
                    and now >= next_start
                ):
                    if not self._slots.acquire(blocking=False):
                        break
                    began = time.monotonic()
                    f = submit(index, calls[index])
                    pending[f] = (index, began)
                    index += 1
                if not pending:
                    if now < next_start:
                        cancel.wait(
                            min(0.005, next_start - now, max(0, deadline - now))
                        )
                        continue
                    if index >= len(calls) or attempts >= limits.call_budget:
                        break
                    break
                done, _ = wait(
                    pending,
                    timeout=min(0.005, max(0, deadline - now)),
                    return_when=FIRST_COMPLETED,
                )
                collect(done)
                for f, (i, began) in list(pending.items()):
                    # A future can finish after wait's returned snapshot.
                    # Its captured completion time remains authoritative.
                    expired = time.monotonic() - began >= limits.per_call_timeout
                    if f.done():
                        collect([f])
                        continue
                    if expired:
                        results[i] = CallResult(calls[i].capability, "timeout")
                        # No further dispatch after a timed-out provider call.
                        stop.set()
                if stop.is_set():
                    break
        finally:
            stop.set()

        for i, c in enumerate(calls):
            if i not in results:
                results[i] = CallResult(
                    c.capability, "cancelled" if cancel.is_set() else "bounded"
                )
        items = tuple(results[i] for i in range(len(calls)))
        return ExecutionResult(
            items,
            attempts,
            time.monotonic() - start,
            any(x.status != "recorded" for x in items),
        )
