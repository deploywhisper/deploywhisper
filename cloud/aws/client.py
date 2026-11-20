"""Credential-free manifests and bounded access to frozen read capabilities."""

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
from cloud.aws.session import DispatchInterrupted, bind_dispatch_fence, validate_config
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
        if code in ("ExpiredToken", "ExpiredTokenException", "RequestExpired"):
            return "credentials_expired", False
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


@dataclass(frozen=True)
class SelectedCallResult(CallResult):
    facts: tuple = ()


@dataclass(frozen=True)
class SelectedExecutionResult(ExecutionResult):
    actual_call_count: int = 0
    issued_indices: tuple[int, ...] = ()


class ExecutionProgress:
    """Single-use accounting shared with the outer collection deadline."""

    def __init__(self):
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self._attempted = 0
        self._issued: set[int] = set()
        self._active_deadlines: dict[int, float] = {}

    def close(self) -> None:
        with self._lock:
            self._closed.set()

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def counts(self) -> tuple[int, int]:
        with self._lock:
            return self._attempted, len(self._issued)

    def _issued_indices(self) -> tuple[int, ...]:
        with self._lock:
            return tuple(sorted(self._issued))

    def _start(self, index, deadline):
        with self._lock:
            self._active_deadlines[index] = deadline

    def _complete(self, index, future, result):
        with self._lock:
            completed_at = time.monotonic()
            deadline = self._active_deadlines.pop(index)
            # Expose the captured result before closing admission. The reader
            # can still drain completions when it observes a closed progress.
            future.set_result((result, completed_at))
            if completed_at >= deadline:
                self._closed.set()

    def _can_dispatch(self, cancel):
        if self.closed or cancel.is_set():
            return False
        now = time.monotonic()
        if any(now >= deadline for deadline in self._active_deadlines.values()):
            self._closed.set()
            return False
        return True

    def _reserve(self, *, cancel, budget):
        with self._lock:
            if not self._can_dispatch(cancel) or self._attempted >= budget:
                return False
            self._attempted += 1
            return True

    def _admit_dispatch(self, index, *, cancel):
        with self._lock:
            if index in self._issued or not self._can_dispatch(cancel):
                return False
            self._issued.add(index)
            return True

    def _permit_send(self, index, *, cancel):
        with self._lock:
            return index in self._issued and self._can_dispatch(cancel)


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
        return self._execute(calls, limits=limits, cancel=cancel)

    def execute_selected(
        self,
        manifest,
        *,
        indices,
        target,
        resources,
        limits=None,
        cancel=None,
        deadline=None,
        all_regions=False,
        sensitive_values=(),
        progress: ExecutionProgress | None = None,
    ):
        from cloud.reflection import guard_manifest

        started = time.monotonic()
        limits = Limits.model_validate((limits or Limits()).model_dump())
        if deadline is not None and (
            type(deadline) not in (int, float) or not math.isfinite(deadline)
        ):
            raise ValueError("invalid_collection_deadline")
        deadline = (
            min(started + limits.total_deadline, deadline)
            if deadline is not None
            else started + limits.total_deadline
        )
        approved = guard_manifest(manifest, target=target, resources=resources)
        if (
            not isinstance(indices, tuple)
            or len(set(indices)) != len(indices)
            or any(
                type(i) is not int or not 0 <= i < len(approved.entries)
                for i in indices
            )
        ):
            raise ValueError("invalid_selected_manifest")
        entries = tuple(approved.entries[i] for i in indices)
        if not all_regions and any(
            entry.region != self._config["region"] for entry in entries
        ):
            raise ValueError("selected_region_mismatch")
        configs = (
            tuple(validate_config({"region": entry.region}) for entry in entries)
            if all_regions
            else None
        )
        return self._execute(
            [entry.call() for entry in entries],
            limits=limits,
            cancel=cancel,
            selections=entries,
            projection_scope=(approved, target, tuple(resources)),
            absolute_deadline=deadline,
            configs=configs,
            sensitive_values=tuple(sensitive_values),
            progress=progress,
        )

    def _execute(
        self,
        calls,
        *,
        limits=None,
        cancel=None,
        selections=None,
        projection_scope=None,
        absolute_deadline=None,
        configs=None,
        sensitive_values=(),
        progress: ExecutionProgress | None = None,
    ):
        calls = _calls(calls)
        limits = Limits.model_validate((limits or Limits()).model_dump())
        cancel = cancel or threading.Event()
        start = time.monotonic()
        deadline = (
            min(start + limits.total_deadline, absolute_deadline)
            if absolute_deadline is not None
            else start + limits.total_deadline
        )
        progress = progress or ExecutionProgress()
        results = {}
        pending = {}
        index = 0

        def issue(i, call, call_deadline):
            row = _CATALOG["operations"][call.capability]
            dispatched = False
            try:

                def construct():
                    if not progress._reserve(cancel=cancel, budget=limits.call_budget):
                        return CallResult(call.capability, "bounded")
                    client = self._session.create_client(
                        row["service"],
                        self._config if configs is None else configs[i],
                        timeout=max(0.001, call_deadline - time.monotonic()),
                    )
                    invoke = client._make_api_call
                    operation = row["operation"]
                    parameters = json.loads(json.dumps(call.parameters))

                    def admit():
                        nonlocal dispatched
                        dispatched = progress._admit_dispatch(i, cancel=cancel)
                        return dispatched

                    sdk_fenced = bind_dispatch_fence(
                        client,
                        operation,
                        admit=admit,
                        permit_send=lambda: progress._permit_send(i, cancel=cancel),
                    )
                    if not sdk_fenced and not admit():
                        return CallResult(call.capability, "cancelled")
                    response = invoke(operation, parameters)
                    if selections is not None:
                        from cloud.aws.projection import project_response

                        try:
                            projected = project_response(
                                selections[i],
                                response,
                                scope=projection_scope,
                                sensitive_values=sensitive_values,
                            )
                        except Exception:
                            return SelectedCallResult(
                                call.capability,
                                "incomplete",
                                cause="projection_unavailable",
                            )
                        return SelectedCallResult(
                            call.capability,
                            "recorded" if projected.complete else "incomplete",
                            facts=projected.facts,
                        )
                    return CallResult(
                        call.capability,
                        "recorded"
                        if response_complete(call.capability, call.parameters, response)
                        else "incomplete",
                    )

                return authorize(row["iam_action"], construct)
            except DispatchInterrupted:
                return CallResult(call.capability, "cancelled")
            except Exception as error:
                # Keep a closed diagnostic vocabulary, never provider messages.
                cause, denied = _failure(error)
                if denied and selections is not None and not dispatched:
                    cause, denied = "credentials_unavailable", False
                return CallResult(
                    call.capability,
                    "unreadable",
                    row["iam_action"] if denied else None,
                    cause,
                )
            finally:
                self._slots.release()

        def submit(i, call, began):
            future = Future()
            call_deadline = min(began + limits.per_call_timeout, deadline)
            progress._start(i, call_deadline)

            def run():
                # Capture completion in the worker, before scheduler wakeup.
                progress._complete(i, future, issue(i, call, call_deadline))

            # No executor atexit join: a broken injected transport cannot hold
            # application shutdown hostage. Its slot stays held until return.
            try:
                threading.Thread(target=run, daemon=True).start()
            except RuntimeError:
                self._slots.release()
                raise
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
                    progress.close()
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
                if progress.closed or now >= deadline:
                    # Publication can race the snapshot above. Drain known
                    # completions once more after observing expiry; timestamps
                    # still decide whether those results were actually timely.
                    collect([future for future in pending if future.done()])
                    break
                while (
                    index < min(len(calls), limits.call_budget)
                    and len(pending) < limits.concurrency
                    and now >= next_start
                ):
                    if not self._slots.acquire(blocking=False):
                        break
                    began = time.monotonic()
                    f = submit(index, calls[index], began)
                    pending[f] = (index, began)
                    index += 1
                if not pending:
                    if now < next_start:
                        cancel.wait(
                            min(0.005, next_start - now, max(0, deadline - now))
                        )
                        continue
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
                        progress.close()
                if progress.closed:
                    break
        finally:
            progress.close()

        for i, c in enumerate(calls):
            if i not in results:
                results[i] = CallResult(
                    c.capability, "cancelled" if cancel.is_set() else "bounded"
                )
        items = tuple(results[i] for i in range(len(calls)))
        final_attempts, final_actual_calls = progress.counts()
        values = (
            items,
            final_attempts,
            time.monotonic() - start,
            any(x.status != "recorded" for x in items),
        )
        return (
            SelectedExecutionResult(
                *values,
                actual_call_count=final_actual_calls,
                issued_indices=progress._issued_indices(),
            )
            if selections is not None
            else ExecutionResult(*values)
        )
