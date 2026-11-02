"""Closed handoff commands and ephemeral, representation-safe port credentials."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field, StrictStr

from infra_automation.contracts import Identifier
from infra_automation.decisions import Version
from infra_automation.lifecycle import MutationRequest, Positive


class PrepareHandoffRequest(MutationRequest):
    version: Version = 1
    project_id: Positive
    workspace_id: Positive
    approval_id: Identifier
    handoff_step_id: Identifier
    idempotency_key: Annotated[StrictStr, Field(min_length=1, max_length=128)]


class DispatchHandoffRequest(MutationRequest):
    version: Version = 1
    project_id: Positive
    workspace_id: Positive
    expected_version: Positive


@dataclass(frozen=True, repr=False)
class ReceiverCredential:
    receiver_id: str
    secret: str
    audience: Literal["receiver-operation-v1"] = "receiver-operation-v1"


@dataclass(frozen=True, repr=False)
class DeliveryEnvelope:
    """Ephemeral trusted-port input; never serialize or log this whole object."""

    operation_id: str
    payload_bytes: bytes
    message_bytes: bytes
    grant_token: str
