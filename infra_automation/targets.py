"""Closed registry configuration and immutable registered action identity."""

from __future__ import annotations

import ipaddress
import json
import re
from typing import Annotated, TypeVar

from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from infra_automation.contracts import (
    ClosedModel,
    CommitSha,
    Digest,
    Identifier,
    SAFE_INTEGER,
)
from infra_automation.decisions import DecisionBinding, Version, content_digest
from infra_automation.lifecycle import CursorEnvelope, MutationRequest, Positive
from infra_automation.state import UTCText

Nonnegative = Annotated[StrictInt, Field(ge=0, le=SAFE_INTEGER)]
T = TypeVar("T", bound=BaseModel)


def _values(value, depth=0):
    if depth > 16:
        raise ValueError("Registry nesting exceeds its bound.")
    if isinstance(value, BaseModel):
        value = {**value.__dict__, **(value.__pydantic_extra__ or {})}
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("Registry keys must be text.")
        return {key: _values(child, depth + 1) for key, child in value.items()}
    if type(value) in {list, tuple}:
        return [_values(child, depth + 1) for child in value]
    if value is not None and type(value) not in {str, int, bool}:
        raise ValueError("Unsupported registry scalar.")
    return value


def canonical(value) -> bytes:
    """Canonical typed JSON; no secret or authority is inferred from a digest."""
    return json.dumps(
        _values(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def checked(value, model: type[T]) -> T:
    """Revalidate unchecked copies/constructs and all nested model fields."""
    return model.model_validate_json(canonical(value))


class TargetScope(ClosedModel):
    project_id: Positive
    workspace_id: Positive


class TargetDefinition(ClosedModel):
    version: Version = 1
    canonical_target: Identifier
    aliases: Annotated[tuple[Identifier, ...], Field(max_length=32)] = ()
    allowed_scopes: Annotated[
        tuple[TargetScope, ...], Field(min_length=1, max_length=50)
    ]
    environment: Identifier
    receiver_id: Identifier
    pipeline_repository_id: Identifier
    pipeline_workflow_id: Identifier
    pipeline_workflow_revision: CommitSha
    github_owner: Annotated[str, Field(strict=True, min_length=1, max_length=39)]
    github_repository: Annotated[str, Field(strict=True, min_length=1, max_length=100)]
    github_workflow: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    workflow_ref: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    api_origin: Annotated[str, Field(strict=True, max_length=512)] = (
        "https://api.github.com"
    )
    allowed_private_addresses: Annotated[tuple[str, ...], Field(max_length=16)] = ()
    credential_ref: Identifier
    receiver_credential_ref: Identifier
    enabled: StrictBool = True

    @field_validator("canonical_target")
    @classmethod
    def canonical_name(cls, value):
        return value.lower()

    @field_validator("aliases")
    @classmethod
    def alias_names(cls, value):
        normalized = tuple(item.lower() for item in value)
        if len(normalized) != len(set(normalized)):
            raise ValueError("Duplicate canonical alias.")
        return normalized

    @field_validator("api_origin")
    @classmethod
    def safe_origin(cls, value):
        from infra_automation.target_transport import canonical_origin

        return canonical_origin(value)

    @field_validator("workflow_ref")
    @classmethod
    def safe_ref(cls, value):
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", value)
            or any(part in value for part in ("..", "//", "@{"))
            or value.endswith(("/", ".", ".lock"))
            or re.fullmatch(r"[0-9a-fA-F]{40}", value)
        ):
            raise ValueError("A pinned branch/tag workflow reference is required.")
        return value

    @field_validator("allowed_private_addresses")
    @classmethod
    def private_addresses(cls, value):
        from infra_automation.target_transport import validate_addresses

        result = []
        for item in value:
            if type(item) is not str or "%" in item:
                raise ValueError("An exact private address is required.")
            address = ipaddress.ip_address(item)
            address = getattr(address, "ipv4_mapped", None) or address
            if address.is_global:
                raise ValueError("Public addresses need no private exception.")
            normalized = str(address)
            validate_addresses("registered.invalid", (normalized,), (normalized,))
            result.append(normalized)
        if len(result) != len(set(result)):
            raise ValueError("Duplicate private address exception.")
        return tuple(result)

    @model_validator(mode="after")
    def valid_registry(self):
        from infra_automation.target_transport import github_dispatch_path

        github_dispatch_path(
            self.github_owner, self.github_repository, self.github_workflow
        )
        scopes = [
            (scope.project_id, scope.workspace_id) for scope in self.allowed_scopes
        ]
        if len(scopes) != len(set(scopes)):
            raise ValueError("Duplicate target scope.")
        if (
            self.allowed_private_addresses
            and self.api_origin == "https://api.github.com"
        ):
            raise ValueError("Private exceptions require an operator-owned origin.")
        return self


class RegisterTargetRequest(MutationRequest):
    version: Version = 1
    project_id: Positive
    workspace_id: Positive
    expected_version: Nonnegative
    definition: TargetDefinition

    @field_validator("definition", mode="before")
    @classmethod
    def definition_from_wire(cls, value):
        if isinstance(value, dict):
            return TargetDefinition.model_validate_json(
                json.dumps(value, allow_nan=False)
            )
        return value


class TargetSnapshot(ClosedModel):
    version: Version = 1
    definition: TargetDefinition
    target_version: Positive
    target_epoch: Positive
    receiver_principal_id: Identifier
    receiver_authentication_version: Positive
    captured_at: UTCText


class TargetLockView(TargetScope):
    id: Identifier
    target_id: Identifier
    run_id: Identifier
    version: Positive
    status: Annotated[str, Field(pattern=r"^(held|resolved|broken)$")]
    created_at: UTCText
    updated_at: UTCText


class TargetView(TargetScope):
    id: Identifier
    version: Positive
    epoch: Positive
    definition: TargetDefinition
    definition_digest: Digest
    receiver_principal_id: Identifier
    created_at: UTCText
    updated_at: UTCText
    lock: TargetLockView | None = None


class TargetSummary(TargetScope):
    id: Identifier
    version: Positive
    epoch: Positive
    enabled: StrictBool
    environment: Identifier
    receiver_id: Identifier
    created_at: UTCText


class TargetPage(ClosedModel):
    items: tuple[TargetSummary, ...]
    cursor: CursorEnvelope


class BreakLockRequest(MutationRequest):
    version: Version = 1
    project_id: Positive
    workspace_id: Positive
    expected_lock_id: Identifier
    expected_version: Positive
    acknowledge_uncertainty: StrictBool

    @field_validator("acknowledge_uncertainty")
    @classmethod
    def acknowledge(cls, value):
        if value is not True:
            raise ValueError("Explicit uncertainty acknowledgement is required.")
        return value


def target_definition_bytes(value: TargetDefinition) -> bytes:
    return canonical(checked(value, TargetDefinition))


def target_snapshot_bytes(value: TargetSnapshot) -> bytes:
    return canonical(checked(value, TargetSnapshot))


def semantic_payload(binding: DecisionBinding, snapshot: TargetSnapshot) -> bytes:
    """Build exactly the preapproval action bytes, without circular/new authority."""
    binding = checked(binding, DecisionBinding)
    snapshot = checked(snapshot, TargetSnapshot)
    target = snapshot.definition
    if (
        binding.canonical_target,
        binding.environment,
        binding.receiver_id,
        binding.pipeline_repository_id,
        binding.pipeline_workflow_id,
        binding.pipeline_workflow_revision,
    ) != (
        target.canonical_target,
        target.environment,
        target.receiver_id,
        target.pipeline_repository_id,
        target.pipeline_workflow_id,
        target.pipeline_workflow_revision,
    ):
        raise ValueError("Action and registered target differ.")
    if (binding.project_id, binding.workspace_id) not in {
        (scope.project_id, scope.workspace_id) for scope in target.allowed_scopes
    }:
        raise ValueError("Action scope is not registered.")
    payload = canonical(
        {
            "version": 1,
            "kind": "registered_github_handoff",
            "decision": binding.model_dump(mode="json", exclude={"payload_digest"}),
            "destination": {
                "api_origin": target.api_origin,
                "github_owner": target.github_owner,
                "github_repository": target.github_repository,
                "github_workflow": target.github_workflow,
                "workflow_ref": target.workflow_ref,
                "target_version": snapshot.target_version,
                "target_epoch": snapshot.target_epoch,
                "target_snapshot_digest": content_digest(
                    target_snapshot_bytes(snapshot)
                ),
            },
        }
    )
    if len(payload) > 131072:
        raise ValueError("Action payload exceeds its bound.")
    return payload
