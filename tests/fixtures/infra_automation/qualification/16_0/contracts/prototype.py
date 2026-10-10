"""Disposable closed protocol validators. Never imported by the production app."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)
import yaml
from yaml.tokens import AliasToken, AnchorToken

MAX_BYTES = 128 * 1024
MAX_DEPTH = 16
Opaque = Annotated[
    str, Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
]
Digest = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
Positive = Annotated[StrictInt, Field(ge=1, le=2**53 - 1)]
Timestamp = Annotated[str, Field(pattern=r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")]
RunState = Literal[
    "queued",
    "running",
    "waiting_approval",
    "ready_handoff",
    "handing_off",
    "external_running",
    "succeeded",
    "failed",
    "stopped_by_gate",
    "rejected",
    "expired",
    "timed_out",
    "cancelled",
    "delivery_unknown",
]
AttemptState = Literal[
    "pending", "claimed", "running", "succeeded", "failed", "timed_out", "cancelled"
]
Authorization = Literal["advisory_request", "exact_plan"]


def instant(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def bounded(value, depth=0):
    if depth > MAX_DEPTH:
        raise ValueError("maximum nesting exceeded")
    if isinstance(value, dict):
        for key, child in value.items():
            if type(key) is not str:
                raise ValueError("string keys required")
            bounded(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            bounded(child, depth + 1)
    elif type(value) is float or (type(value) is int and abs(value) > 2**53 - 1):
        raise ValueError("v1 canonical numbers are safe integers only")
    elif value is not None and type(value) not in (str, int, bool):
        raise ValueError("unsupported canonical value")


def canonical_bytes(value):
    bounded(value)
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def content_digest(value):
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def snapshot_digest(export_bytes):
    if type(export_bytes) is not bytes or len(export_bytes) > 8 * 1024 * 1024:
        raise ValueError("bounded immutable export bytes required")
    return "sha256:" + hashlib.sha256(export_bytes).hexdigest()


def freeze_report_snapshot(report_payload):
    """Capture report-only existing serializer output once, preserving all fields."""
    if (
        not isinstance(report_payload, dict)
        or report_payload.get("report_schema_version") != "v2"
    ):
        raise ValueError("existing report v2 payload required")
    raw = json.dumps(
        report_payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return raw, snapshot_digest(raw)


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Annotated[StrictInt, Field(ge=1, le=1)] = 1

    @model_validator(mode="before")
    @classmethod
    def reject_bad_timestamps(cls, value):
        def walk(item):
            if isinstance(item, dict):
                for key, child in item.items():
                    if (
                        key.endswith("_at") or key.endswith("_deadline")
                    ) and child is not None:
                        if type(child) is not str:
                            raise ValueError("UTC timestamp string required")
                        instant(child)
                    walk(child)
            elif isinstance(item, list):
                for child in item:
                    walk(child)

        walk(value)
        return value


class Uploaded(Closed):
    kind: Literal["uploaded"]
    repository_source: Literal["unavailable"]
    limitation: Literal[
        "Repository and immutable commit were not verified for uploaded evidence."
    ]


class Collected(Closed):
    kind: Literal["collected"]
    repository_id: Opaque
    commit_sha: Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
    collector_id: Opaque
    profile_digest: Digest
    screened_transport_digest: Digest
    redaction_version: Positive
    collected_at: Timestamp
    source_deadline: Timestamp

    @model_validator(mode="after")
    def ttl(self):
        seconds = (
            instant(self.source_deadline) - instant(self.collected_at)
        ).total_seconds()
        if not 0 < seconds <= 3600:
            raise ValueError("collection deadline must be within 60 minutes")
        return self


Source = Annotated[Uploaded | Collected, Field(discriminator="kind")]


class Custody(Closed):
    handle: Opaque
    raw_local_digest: Digest
    expires_at: Timestamp


class Provenance(Closed):
    authorization_kind: Authorization
    source: Source
    custody: Custody | None = None

    @model_validator(mode="after")
    def eligibility(self):
        if self.authorization_kind == "exact_plan" and (
            not isinstance(self.source, Collected) or self.custody is None
        ):
            raise ValueError(
                "exact plan requires admitted collected source and custody"
            )
        if isinstance(self.source, Uploaded) and self.custody is not None:
            raise ValueError("uploaded advisory has no fabricated custody")
        return self


class Ref(Closed):
    step_id: Opaque
    output: Literal[
        "screened_artifacts", "report", "action_binding", "decision_receipt"
    ]


class Step(Closed):
    id: Opaque
    kind: Literal[
        "uploaded_intake",
        "admitted_collection",
        "shared_analysis",
        "policy_evaluation",
        "human_decision",
        "registered_github_handoff",
    ]
    depends_on: Annotated[list[Opaque], Field(max_length=50)]
    refs: dict[Literal["artifact", "report", "binding", "decision"], Ref]
    target_id: Opaque | None = None
    authorization_kind: Authorization | None = None
    parameters: dict[Literal["max_artifact_bytes", "timeout_seconds"], Positive] = (
        Field(default_factory=dict)
    )

    @model_validator(mode="after")
    def parameters_bound(self):
        for key, value in self.parameters.items():
            if value > (8 * 1024 * 1024 if key == "max_artifact_bytes" else 600):
                raise ValueError("step parameter resource bound exceeded")
        if (
            self.kind not in ("uploaded_intake", "admitted_collection")
            and self.parameters
        ):
            raise ValueError("parameters allowed only on intake/collection")
        return self


OUTPUTS = {
    "uploaded_intake": "screened_artifacts",
    "admitted_collection": "screened_artifacts",
    "shared_analysis": "report",
    "policy_evaluation": "action_binding",
    "human_decision": "decision_receipt",
    "registered_github_handoff": None,
}
INPUTS = {
    "uploaded_intake": {},
    "admitted_collection": {},
    "shared_analysis": {"artifact": "screened_artifacts"},
    "policy_evaluation": {"report": "report"},
    "human_decision": {"binding": "action_binding"},
    "registered_github_handoff": {
        "binding": "action_binding",
        "decision": "decision_receipt",
    },
}


class Workflow(Closed):
    project_id: Opaque
    workspace_id: Opaque
    steps: Annotated[list[Step], Field(min_length=1, max_length=50)]

    @model_validator(mode="after")
    def graph(self):
        nodes = {step.id: step for step in self.steps}
        if len(nodes) != len(self.steps):
            raise ValueError("duplicate step identifier")
        visiting, ancestors = set(), {}

        def visit(identifier):
            if identifier in visiting or identifier not in nodes:
                raise ValueError("cycle or missing dependency")
            if identifier not in ancestors:
                visiting.add(identifier)
                step = nodes[identifier]
                if len(set(step.depends_on)) != len(step.depends_on):
                    raise ValueError("duplicate dependency")
                result = set(step.depends_on)
                for parent in step.depends_on:
                    result |= visit(parent)
                visiting.remove(identifier)
                ancestors[identifier] = result
            return ancestors[identifier]

        for step in self.steps:
            parents = visit(step.id)
            if set(step.refs) != set(INPUTS[step.kind]):
                raise ValueError("typed inputs required exactly")
            for name, ref in step.refs.items():
                if (
                    ref.step_id not in parents
                    or OUTPUTS[nodes[ref.step_id].kind] != ref.output
                    or INPUTS[step.kind][name] != ref.output
                ):
                    raise ValueError("reference type or dependency mismatch")
            if step.kind in ("policy_evaluation", "registered_github_handoff"):
                if not step.target_id or not step.authorization_kind:
                    raise ValueError("matching target and authorization required")
            elif step.target_id is not None or step.authorization_kind is not None:
                raise ValueError("unexpected target/authorization field")
        # Validate every local shape/type before following another step's fields.
        # Wire step ordering never substitutes for graph dependency ordering.
        for step in self.steps:
            if step.kind == "registered_github_handoff":
                gate = nodes[step.refs["binding"].step_id]
                decision = nodes[step.refs["decision"].step_id]
                if (
                    decision.refs["binding"] != step.refs["binding"]
                    or gate.id not in ancestors[decision.id]
                    or gate.target_id != step.target_id
                    or gate.authorization_kind != step.authorization_kind
                ):
                    raise ValueError(
                        "matching gate and decision must precede every handoff"
                    )
                if step.authorization_kind == "exact_plan":
                    report = nodes[gate.refs["report"].step_id]
                    intake = nodes[report.refs["artifact"].step_id]
                    if intake.kind != "admitted_collection":
                        raise ValueError("upload cannot authorize exact plan")
        return self


class TaskScope(Closed):
    runner_id: Opaque
    project_id: Opaque
    workspace_id: Opaque
    run_id: Opaque
    step_id: Opaque
    attempt: Positive
    fence: Positive
    coordinator_generation: Positive
    authorization_epoch: Positive
    restore_epoch: Positive
    lease_deadline: Timestamp
    audience: Literal["runner-task-v1"]


class Runner(Closed):
    operation: Literal["claim", "heartbeat", "log", "upload", "complete"]
    scope: TaskScope
    capabilities: Annotated[
        list[Literal["screened-collection-v1"]], Field(min_length=1, max_length=1)
    ]
    profile_digest: Digest
    sequence: Positive
    log: Annotated[str, Field(max_length=16384)] | None = None
    upload_digest: Digest | None = None
    atomic_upload_id: Opaque | None = None
    state: Literal["succeeded", "failed"] | None = None

    @model_validator(mode="after")
    def operation_fields(self):
        expected = {
            "claim": set(),
            "heartbeat": set(),
            "log": {"log"},
            "upload": {"upload_digest", "atomic_upload_id"},
            "complete": {"atomic_upload_id", "state"},
        }[self.operation]
        present = {
            key
            for key in ("log", "upload_digest", "atomic_upload_id", "state")
            if getattr(self, key) is not None
        }
        if present != expected or (
            self.log is not None and len(self.log.encode("utf-8")) > 16384
        ):
            raise ValueError("operation payload or byte bound mismatch")
        return self


class Enrollment(Closed):
    audience: Literal["runner-enrollment-v1"]
    enrollment_id: Opaque
    runner_id: Opaque
    project_id: Opaque
    workspace_id: Opaque
    expires_at: Timestamp
    one_use: Literal[True]

    @field_validator("one_use", mode="before")
    @classmethod
    def actual_boolean_true(cls, value):
        if type(value) is not bool or value is not True:
            raise ValueError("one_use requires actual boolean true")
        return value


class Binding(Closed):
    authorization_kind: Authorization
    workflow_id: Opaque
    workflow_revision_digest: Digest
    input_digest: Digest
    provenance: Provenance
    project_id: Opaque
    workspace_id: Opaque
    environment: Opaque
    canonical_target: Opaque
    receiver_id: Opaque
    pipeline_repository_id: Opaque
    pipeline_workflow_id: Opaque
    pipeline_workflow_revision: Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
    report_id: Positive
    report_schema_version: Literal["v2"]
    report_bytes_digest: Digest
    policy_version: Positive
    policy_result: Literal["passed"]
    policy_digest: Digest
    unit_waves_digest: Digest
    screened_artifact_digests: Annotated[
        list[Digest], Field(min_length=1, max_length=50)
    ]
    redaction_version: Positive
    payload_digest: Digest
    evidence_deadline: Timestamp
    approval_deadline: Timestamp
    authorization_epoch: Positive
    restore_epoch: Positive

    @model_validator(mode="after")
    def matching_provenance(self):
        if self.authorization_kind != self.provenance.authorization_kind:
            raise ValueError("authorization provenance mismatch")
        if isinstance(self.provenance.source, Collected):
            if (
                self.provenance.source.screened_transport_digest
                not in self.screened_artifact_digests
                or self.redaction_version != self.provenance.source.redaction_version
            ):
                raise ValueError("screened artifact/redaction mismatch")
        return self

    def deadline(self):
        values = [self.evidence_deadline, self.approval_deadline]
        if isinstance(self.provenance.source, Collected):
            values.append(self.provenance.source.source_deadline)
        if self.provenance.custody:
            values.append(self.provenance.custody.expires_at)
        return min(map(instant, values))


class Receiver(Closed):
    operation: Literal["consume", "receipt", "status", "outcome", "reconcile"]
    operation_id: Opaque
    audience: Literal["receiver-operation-v1"]
    binding: Binding
    binding_digest: Digest
    sequence: Positive
    state: Literal[
        "consumed",
        "accepted",
        "running",
        "succeeded",
        "failed",
        "delivery_unknown",
        "cancel_requested",
    ]

    @model_validator(mode="after")
    def digest_binding(self):
        if self.binding_digest != content_digest(self.binding.model_dump(mode="json")):
            raise ValueError("exact binding bytes mismatch")
        if self.operation == "consume" and self.state != "consumed":
            raise ValueError("consume before counted action")
        if self.operation == "outcome" and self.state not in (
            "succeeded",
            "failed",
            "delivery_unknown",
        ):
            raise ValueError("acceptance is not terminal outcome")
        return self


class State(Closed):
    run_state: RunState
    attempt_state: AttemptState


class Error(Closed):
    http_status: Literal[401, 403, 409, 422, 429, 503]
    code: Literal[
        "authentication_required",
        "permission_denied",
        "binding_conflict",
        "request_validation_failed",
        "quota_exceeded",
        "authority_unavailable",
    ]
    message: Literal[
        "Authentication required.",
        "Operation unavailable.",
        "Review current evidence again.",
        "Request validation failed.",
        "Request limit reached.",
        "Current authority could not be verified.",
    ]
    retryable: bool
    correlation_id: Opaque

    @model_validator(mode="after")
    def consistent(self):
        expected = {
            401: ("authentication_required", "Authentication required.", False),
            403: ("permission_denied", "Operation unavailable.", False),
            409: ("binding_conflict", "Review current evidence again.", False),
            422: ("request_validation_failed", "Request validation failed.", False),
            429: ("quota_exceeded", "Request limit reached.", True),
            503: (
                "authority_unavailable",
                "Current authority could not be verified.",
                True,
            ),
        }[self.http_status]
        if (self.code, self.message, self.retryable) != expected:
            raise ValueError("status/code/retryability mismatch")
        return self


class Cursor(Closed):
    snapshot_id: Opaque
    next_cursor: Opaque | None
    limit: Annotated[StrictInt, Field(ge=1, le=100)]
    last_sequence: Annotated[StrictInt, Field(ge=0, le=2**53 - 1)]
    truncated: bool
    gap: bool


MODELS = {
    "workflow": Workflow,
    "runner": Runner,
    "enrollment": Enrollment,
    "receiver": Receiver,
    "provenance": Provenance,
    "state": State,
    "error": Error,
    "cursor": Cursor,
}


def validate(kind, value):
    bounded(value)
    if len(canonical_bytes(value)) > MAX_BYTES:
        raise ValueError("contract byte bound exceeded")
    return MODELS[kind].model_validate(value)


class UniqueLoader(yaml.SafeLoader):
    pass


def mapping(loader, node, deep=False):
    result = {}
    for key, child in node.value:
        key = loader.construct_object(key, deep=deep)
        if type(key) is not str or key in result:
            raise ValueError("duplicate/nonstring YAML key")
        result[key] = loader.construct_object(child, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)


def parse_workflow(raw):
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError("workflow byte bound exceeded")
    try:
        text = raw.decode("utf-8")
        depth = 0
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken)):
                raise ValueError("YAML anchors/aliases forbidden")
            if isinstance(
                token,
                (
                    yaml.tokens.FlowSequenceStartToken,
                    yaml.tokens.FlowMappingStartToken,
                    yaml.tokens.BlockSequenceStartToken,
                    yaml.tokens.BlockMappingStartToken,
                ),
            ):
                depth += 1
                if depth > MAX_DEPTH:
                    raise ValueError("YAML nesting bound exceeded")
            elif isinstance(
                token,
                (
                    yaml.tokens.FlowSequenceEndToken,
                    yaml.tokens.FlowMappingEndToken,
                    yaml.tokens.BlockEndToken,
                ),
            ):
                depth -= 1
        loader = UniqueLoader(text)
        try:
            return validate("workflow", loader.get_single_data())
        finally:
            loader.dispose()
    except (yaml.YAMLError, UnicodeError, RecursionError) as error:
        raise ValueError("invalid bounded YAML") from error


def current_authority(runner):
    return {
        **runner.scope.model_dump(exclude={"version"}),
        "profile_digest": runner.profile_digest,
        "capabilities": runner.capabilities,
    }


def authorize_runner(runner, authority, now):
    if (
        any(
            type(authority.get(key)) is not type(value) or authority.get(key) != value
            for key, value in current_authority(runner).items()
        )
        or set(authority) != set(current_authority(runner))
        or instant(now) >= instant(runner.scope.lease_deadline)
    ):
        raise ValueError("stale/wrong current runner scope")


def authorize_receiver(receiver, authority, now):
    if (
        any(
            authority.get(key) is not True
            for key in ("available", "membership", "target_enabled", "feature_enabled")
        )
        or any(
            type(authority.get(key)) is not int
            or authority[key] != getattr(receiver.binding, key)
            for key in ("authorization_epoch", "restore_epoch")
        )
        or instant(now) >= receiver.binding.deadline()
    ):
        raise ValueError("current authority unavailable or stale")


PERMISSIONS = {
    "read": {
        "admin",
        "maintainer",
        "contributor",
        "reviewer",
        "read_only",
        "service",
        "agent",
    },
    "request": {"admin", "maintainer", "contributor", "service", "agent"},
    "publish": {"admin"},
    "draft": {"admin", "maintainer"},
    "cancel": {"admin", "maintainer", "contributor"},
    "manage_target": {"admin"},
    "enroll": {"admin"},
    "decide": {"admin", "maintainer", "reviewer"},
    "runner_task": {"runner"},
    "receiver_operation": {"receiver"},
    "reconcile": {"admin", "maintainer"},
}


def permission(
    role,
    operation,
    authenticated,
    scoped,
    requester=False,
    single_operator=False,
    audience="human-session-v1",
):
    if not authenticated:
        return 401
    if not scoped or role not in PERMISSIONS.get(operation, set()):
        return 403
    expected = (
        "runner-task-v1"
        if operation == "runner_task"
        else "receiver-operation-v1"
        if operation == "receiver_operation"
        else "service-request-v1"
        if role in ("agent", "service")
        else "human-session-v1"
    )
    if operation == "cancel" and role != "admin" and not requester:
        return 403
    if audience != expected or (
        operation == "decide" and requester and not single_operator
    ):
        return 403
    return 200
