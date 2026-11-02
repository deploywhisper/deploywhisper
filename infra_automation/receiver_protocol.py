"""Frozen receiver-v1 wire values and explicit decision-to-wire identity mapping."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from infra_automation.contracts import (
    AuthorizationKind,
    ClosedModel,
    CommitSha,
    Digest,
    Identifier,
    SAFE_INTEGER,
)
from infra_automation.decisions import DecisionBinding
from infra_automation.lifecycle import Positive
from infra_automation.state import UTCText


CANONICALIZATION = "tuple-json-utf8-v1"
MAX_BYTES = 128 * 1024
MAX_DEPTH = 16
Version = Annotated[StrictInt, Field(ge=1, le=1)]
ReceiverOperation = Literal["consume", "receipt", "status", "outcome", "reconcile"]
ReceiverState = Literal[
    "consumed",
    "accepted",
    "running",
    "succeeded",
    "failed",
    "delivery_unknown",
    "cancel_requested",
]


def _materialize(value: Any, depth: int = 0, *, decision: bool = False) -> Any:
    """Inspect model fields too, including unchecked copy updates and children."""
    if depth > MAX_DEPTH:
        raise ValueError("Receiver nesting limit exceeded.")
    if isinstance(value, BaseModel):
        value = {**value.__dict__, **(value.__pydantic_extra__ or {})}
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("Receiver object keys must be strings.")
        return {
            key: _materialize(child, depth + 1, decision=decision)
            for key, child in value.items()
        }
    if type(value) is list or (decision and type(value) is tuple):
        return [_materialize(child, depth + 1, decision=decision) for child in value]
    if type(value) is int and abs(value) > SAFE_INTEGER:
        raise ValueError("Receiver integers must be canonical safe integers.")
    if value is not None and type(value) not in (str, int, bool):
        raise ValueError("Unsupported receiver canonical value.")
    return value


def _canonical_bytes(value: Any) -> bytes:
    try:
        raw = json.dumps(
            _materialize(value),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (UnicodeError, RecursionError) as error:
        raise ValueError("Invalid receiver canonical value.") from error
    if len(raw) > MAX_BYTES:
        raise ValueError("Receiver byte limit exceeded.")
    return raw


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate receiver object key.")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError("Nonfinite receiver number.")


def _wire_input(value: Any) -> Any:
    if type(value) in (bytes, str):
        try:
            raw = value.encode("utf-8") if type(value) is str else value
            if len(raw) > MAX_BYTES:
                raise ValueError("Receiver byte limit exceeded.")
            value = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except (UnicodeError, RecursionError) as error:
            raise ValueError("Invalid receiver JSON.") from error
    value = _materialize(value)
    _canonical_bytes(value)
    return value


class _ReceiverClosed(ClosedModel):
    model_config = ConfigDict(revalidate_instances="always")
    version: Version = 1

    @model_validator(mode="before")
    @classmethod
    def bounded_wire_value(cls, value: Any) -> Any:
        # Revalidate even existing/nested models: frozen models still permit
        # unchecked model_copy/model_construct, and lists can be mutated.
        return _wire_input(value)


class Uploaded(_ReceiverClosed):
    kind: Literal["uploaded"]
    repository_source: Literal["unavailable"]
    limitation: Literal[
        "Repository and immutable commit were not verified for uploaded evidence."
    ]


class Collected(_ReceiverClosed):
    kind: Literal["collected"]
    repository_id: Identifier
    commit_sha: CommitSha
    collector_id: Identifier
    profile_digest: Digest
    screened_transport_digest: Digest
    redaction_version: Positive
    collected_at: UTCText
    source_deadline: UTCText

    @model_validator(mode="after")
    def finite_ttl(self):
        if (
            not 0
            < (
                _instant(self.source_deadline) - _instant(self.collected_at)
            ).total_seconds()
            <= 3600
        ):
            raise ValueError("Collection deadline must be within 60 minutes.")
        return self


class Custody(_ReceiverClosed):
    handle: Identifier
    raw_local_digest: Digest
    expires_at: UTCText


class Provenance(_ReceiverClosed):
    authorization_kind: AuthorizationKind
    source: Annotated[Uploaded | Collected, Field(discriminator="kind")]
    custody: Custody | None = None

    @model_validator(mode="after")
    def source_custody(self):
        if self.authorization_kind == "exact_plan" and (
            not isinstance(self.source, Collected) or self.custody is None
        ):
            raise ValueError("Exact plan requires collected source and custody.")
        if isinstance(self.source, Uploaded) and self.custody is not None:
            raise ValueError("Uploaded evidence cannot manufacture custody.")
        return self


def _instant(value: str) -> datetime:
    # Match frozen receiver-v1's UTC text and naive UTC deadline representation.
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


class ReceiverBinding(_ReceiverClosed):
    authorization_kind: AuthorizationKind
    workflow_id: Identifier
    workflow_revision_digest: Digest
    input_digest: Digest
    provenance: Provenance
    project_id: Identifier
    workspace_id: Identifier
    environment: Identifier
    canonical_target: Identifier
    receiver_id: Identifier
    pipeline_repository_id: Identifier
    pipeline_workflow_id: Identifier
    pipeline_workflow_revision: CommitSha
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
    evidence_deadline: UTCText
    approval_deadline: UTCText
    authorization_epoch: Positive
    restore_epoch: Positive

    @model_validator(mode="after")
    def matching_provenance(self):
        if self.authorization_kind != self.provenance.authorization_kind:
            raise ValueError("Authorization provenance mismatch.")
        source = self.provenance.source
        if isinstance(source, Collected) and (
            source.screened_transport_digest not in self.screened_artifact_digests
            or self.redaction_version != source.redaction_version
        ):
            raise ValueError("Screened artifact or redaction identity mismatch.")
        return self

    def deadline(self) -> datetime:
        # Validate again because mutable children/unchecked copies are possible.
        binding = ReceiverBinding.model_validate(_wire_input(self))
        values = [binding.evidence_deadline, binding.approval_deadline]
        if isinstance(binding.provenance.source, Collected):
            values.append(binding.provenance.source.source_deadline)
        if binding.provenance.custody is not None:
            values.append(binding.provenance.custody.expires_at)
        return min(map(_instant, values))


class ReceiverMessage(_ReceiverClosed):
    operation: ReceiverOperation
    operation_id: Identifier
    audience: Literal["receiver-operation-v1"]
    binding: ReceiverBinding
    binding_digest: Digest
    sequence: Positive
    state: ReceiverState

    @model_validator(mode="after")
    def binding_and_state(self):
        if self.binding_digest != receiver_binding_digest(self.binding):
            raise ValueError("Exact receiver binding bytes mismatch.")
        if self.operation == "consume" and self.state != "consumed":
            raise ValueError("Consume must precede counted action.")
        if self.operation == "outcome" and self.state not in (
            "succeeded",
            "failed",
            "delivery_unknown",
        ):
            raise ValueError("Acceptance is not a terminal outcome.")
        return self


def receiver_binding_from_decision(binding: DecisionBinding) -> ReceiverBinding:
    """Map scopes/revision explicitly; callers retain the separate decision ID."""
    if not isinstance(binding, DecisionBinding):
        raise ValueError("A validated decision binding is required.")
    # JSON mode permits DecisionBinding's immutable tuple but never coerces its
    # integer scopes, versions or nested fields. Inspect copies before dumping.
    raw = _canonical_bytes(_materialize(binding, decision=True))
    decision = DecisionBinding.model_validate_json(raw)
    wire = decision.model_dump(mode="json", exclude={"revision_id"})
    wire["project_id"] = str(decision.project_id)
    wire["workspace_id"] = str(decision.workspace_id)
    return ReceiverBinding.model_validate(wire)


BindingInput = DecisionBinding | ReceiverBinding | dict[str, Any] | bytes | str
MessageInput = ReceiverMessage | dict[str, Any] | bytes | str


def receiver_binding_bytes(binding: BindingInput) -> bytes:
    """Return canonical *receiver* bytes, never the decision tuple's bytes."""
    if isinstance(binding, DecisionBinding):
        typed = receiver_binding_from_decision(binding)
    else:
        typed = ReceiverBinding.model_validate(_wire_input(binding))
    return _canonical_bytes(typed.model_dump(mode="json"))


def receiver_binding_digest(binding: BindingInput) -> str:
    return "sha256:" + hashlib.sha256(receiver_binding_bytes(binding)).hexdigest()


def validate_receiver_message(message: MessageInput) -> ReceiverMessage:
    return ReceiverMessage.model_validate(_wire_input(message))


def receiver_message_bytes(message: MessageInput) -> bytes:
    return _canonical_bytes(validate_receiver_message(message).model_dump(mode="json"))
