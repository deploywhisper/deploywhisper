"""Additive authenticated HTTP envelopes around the unchanged receiver-v1 wire."""

from __future__ import annotations

import hashlib
from typing import Annotated
from pydantic import Field, StrictStr
from infra_automation.contracts import ClosedModel, Digest, Identifier
from infra_automation.decisions import Version
from infra_automation.lifecycle import Positive
from infra_automation.receiver_protocol import ReceiverBinding, ReceiverMessage
from infra_automation.targets import canonical
from infra_automation.handoff import DispatchHandoffRequest


class BootstrapRequest(ClosedModel):
    version: Version = 1
    binding_digest: Digest


class ReceiverRequest(ClosedModel):
    version: Version = 1


class ConsumeRequest(ReceiverRequest):
    message: ReceiverMessage
    grant_token: Annotated[StrictStr, Field(min_length=1, max_length=256, repr=False)]


class CallbackEnvelope(ReceiverRequest):
    operation_id: Identifier
    run_id: Identifier
    binding_digest: Digest
    source_identity_digest: Digest
    nonce: Identifier
    sequence: Positive
    message: ReceiverMessage
    signature: Digest


class ReconcileRequest(DispatchHandoffRequest):
    pass


def source_identity_digest(binding: ReceiverBinding) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            canonical(binding.provenance.source.model_dump(mode="json"))
        ).hexdigest()
    )


def callback_signing_bytes(envelope: CallbackEnvelope | dict) -> bytes:
    value = (
        envelope.model_dump(mode="json")
        if isinstance(envelope, CallbackEnvelope)
        else dict(envelope)
    )
    value.pop("signature", None)
    return b"deploywhisper-receiver-callback-v1\0" + canonical(value)
