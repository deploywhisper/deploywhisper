"""Immutable application-supplied data and fixed workflow resource contracts."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    model_validator,
)


SAFE_INTEGER = 2**53 - 1
Identifier = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$",
    ),
]
CommitSha = Annotated[
    str,
    StringConstraints(
        strict=True, min_length=40, max_length=40, pattern=r"^[0-9a-f]{40}$"
    ),
]
Digest = Annotated[
    str,
    StringConstraints(
        strict=True, min_length=71, max_length=71, pattern=r"^sha256:[0-9a-f]{64}$"
    ),
]
AuthorizationKind = Literal["advisory_request", "exact_plan"]
OutputKind = Literal[
    "screened_artifacts", "report", "action_binding", "decision_receipt"
]
StepKind = Literal[
    "uploaded_intake",
    "admitted_collection",
    "shared_analysis",
    "policy_evaluation",
    "human_decision",
    "registered_github_handoff",
]


class ClosedModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, validate_default=True
    )


class ValidationLimits(ClosedModel):
    max_bytes: Annotated[StrictInt, Field(ge=1, le=131072)] = 131072
    max_depth: Annotated[StrictInt, Field(ge=1, le=16)] = 16
    max_steps: Annotated[StrictInt, Field(ge=1, le=50)] = 50
    max_inputs: Annotated[StrictInt, Field(ge=1, le=32)] = 32
    max_errors: Annotated[StrictInt, Field(ge=1, le=50)] = 50


class ProfileContract(ClosedModel):
    digest: Digest
    tool: Literal["opentofu", "terraform"]
    authorization_kinds: Annotated[
        tuple[AuthorizationKind, ...], Field(min_length=1, max_length=2)
    ]

    @model_validator(mode="after")
    def unique_authorization_kinds(self) -> ProfileContract:
        if len(set(self.authorization_kinds)) != len(self.authorization_kinds):
            raise ValueError("Authorization kinds must be unique.")
        return self


class RegistryContract(ClosedModel):
    profiles: Annotated[tuple[ProfileContract, ...], Field(max_length=16)] = ()

    @model_validator(mode="after")
    def unique_profile_digests(self) -> RegistryContract:
        if len({profile.digest for profile in self.profiles}) != len(self.profiles):
            raise ValueError("Profile digests must be unique.")
        return self


@dataclass(frozen=True)
class StepContract:
    """Fixed domain input/output names; carries no executable implementation."""

    inputs: tuple[tuple[str, OutputKind], ...]
    output: OutputKind | None


STEP_CONTRACTS = MappingProxyType(
    {
        "uploaded_intake": StepContract((), "screened_artifacts"),
        "admitted_collection": StepContract((), "screened_artifacts"),
        "shared_analysis": StepContract(
            (("artifact", "screened_artifacts"),), "report"
        ),
        "policy_evaluation": StepContract((("report", "report"),), "action_binding"),
        "human_decision": StepContract(
            (("binding", "action_binding"),), "decision_receipt"
        ),
        "registered_github_handoff": StepContract(
            (("binding", "action_binding"), ("decision", "decision_receipt")), None
        ),
    }
)
