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
            or not _matches(row["params"], self.parameters)
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


@dataclass(frozen=True)
class ExecutionResult:
    items: tuple[CallResult, ...]
    attempts: int
    elapsed_seconds: float
    partial: bool


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
                    partial = (
                        any(
                            response.get(k)
                            for k in (
                                "NextToken",
                                "NextMarker",
                                "Marker",
                                "IsTruncated",
                                "LastEvaluatedKey",
                            )
                        )
                        if isinstance(response, dict)
                        else True
                    )
                    return CallResult(
                        call.capability, "incomplete" if partial else "recorded"
                    )

                return authorize(row["iam_action"], construct)
            except Exception:
                # Never format provider exception messages or raw payloads.
                return CallResult(call.capability, "unreadable", row["iam_action"])
            finally:
                self._slots.release()

        def submit(i, call):
            future = Future()

            def run():
                future.set_result(issue(i, call))

            # No executor atexit join: a broken injected transport cannot hold
            # application shutdown hostage. Its slot stays held until return.
            threading.Thread(target=run, daemon=True).start()
            return future

        try:
            next_start = start
            while index < len(calls) or pending:
                now = time.monotonic()
                if cancel.is_set() or now >= deadline:
                    break
                while (
                    index < len(calls)
                    and len(pending) < limits.concurrency
                    and attempts + len(pending) < limits.call_budget
                    and now >= next_start
                ):
                    if not self._slots.acquire(blocking=False):
                        break
                    f = submit(index, calls[index])
                    pending[f] = (index, now)
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
                for f in done:
                    i, _ = pending.pop(f)
                    results[i] = f.result()
                    if results[i].status == "unreadable":
                        next_start = time.monotonic() + limits.backoff
                for f, (i, began) in list(pending.items()):
                    if time.monotonic() - began >= limits.per_call_timeout:
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
