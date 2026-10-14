"""Closed strict domain models for authoring workflow major 2.

These models describe shape only. Admission, reference typing, graph validation,
scope authority and execution are separate concerns.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from infra_automation.contracts import (
    SAFE_INTEGER,
    AuthorizationKind,
    ClosedModel,
    CommitSha as ContractCommitSha,
    Digest as ContractDigest,
    Identifier as ContractIdentifier,
    OutputKind,
)


def _absolute_pattern_end(schema: dict[str, object]) -> None:
    # ECMA/Python `$` allows a final newline; match the runtime's strict end anchor.
    pattern = schema.get("pattern")
    if isinstance(pattern, str) and pattern.endswith("$"):
        schema["pattern"] = pattern[:-1] + r"(?![\s\S])"


Identifier = Annotated[
    ContractIdentifier, Field(json_schema_extra=_absolute_pattern_end)
]
CommitSha = Annotated[ContractCommitSha, Field(json_schema_extra=_absolute_pattern_end)]
Digest = Annotated[ContractDigest, Field(json_schema_extra=_absolute_pattern_end)]


class InputReference(ClosedModel):
    ref: Literal["input"]
    name: Identifier


class StepReference(ClosedModel):
    ref: Literal["step"]
    step_id: Identifier
    output: OutputKind


class ProjectReference(ClosedModel):
    ref: Literal["project"]
    field: Literal["id", "workspace_id"]


class RunReference(ClosedModel):
    ref: Literal["run"]
    field: Literal["project_id", "workspace_id", "environment"]


IdentifierReference = Annotated[
    InputReference | ProjectReference | RunReference, Field(discriminator="ref")
]
IdentifierValue = Identifier | IdentifierReference
CommitValue = CommitSha | InputReference
IntegerValue = (
    Annotated[StrictInt, Field(ge=-SAFE_INTEGER, le=SAFE_INTEGER)] | InputReference
)


class InputDeclarationBase(ClosedModel):
    required: StrictBool = True
    default: StrictStr | StrictInt | StrictBool | None = None

    @model_validator(mode="after")
    def default_required_consistency(self) -> InputDeclarationBase:
        if self.required and self.default is not None:
            raise ValueError("Required inputs cannot have a default.")
        if not self.required and self.default is None:
            raise ValueError("Optional inputs require a non-null default.")
        return self


class IdentifierInput(InputDeclarationBase):
    type: Literal["identifier"]
    default: Identifier | None = None


class CommitShaInput(InputDeclarationBase):
    type: Literal["commit_sha"]
    default: CommitSha | None = None


class StringInput(InputDeclarationBase):
    type: Literal["string"]
    max_length: Annotated[StrictInt, Field(ge=1, le=1024)] = 1024
    default: Annotated[StrictStr, Field(max_length=1024)] | None = None

    @model_validator(mode="after")
    def default_within_bound(self) -> StringInput:
        if self.default is not None and len(self.default) > self.max_length:
            raise ValueError("Default exceeds the declared string bound.")
        return self


class IntegerInput(InputDeclarationBase):
    type: Literal["integer"]
    minimum: Annotated[
        StrictInt, Field(ge=-SAFE_INTEGER, le=SAFE_INTEGER)
    ] = -SAFE_INTEGER
    maximum: Annotated[StrictInt, Field(ge=-SAFE_INTEGER, le=SAFE_INTEGER)] = (
        SAFE_INTEGER
    )
    default: Annotated[StrictInt, Field(ge=-SAFE_INTEGER, le=SAFE_INTEGER)] | None = (
        None
    )

    @model_validator(mode="after")
    def ordered_bounds_and_default(self) -> IntegerInput:
        if self.minimum > self.maximum:
            raise ValueError("Minimum exceeds maximum.")
        if (
            self.default is not None
            and not self.minimum <= self.default <= self.maximum
        ):
            raise ValueError("Default is outside the declared integer bounds.")
        return self


class BooleanInput(InputDeclarationBase):
    type: Literal["boolean"]
    default: StrictBool | None = None


InputDeclaration = Annotated[
    IdentifierInput | CommitShaInput | StringInput | IntegerInput | BooleanInput,
    Field(discriminator="type"),
]


class CollectionParameters(ClosedModel):
    max_artifact_bytes: (
        Annotated[StrictInt, Field(ge=1, le=8388608)] | InputReference
    ) = 8388608
    timeout_seconds: Annotated[StrictInt, Field(ge=1, le=600)] | InputReference = 600


class UploadedSource(ClosedModel):
    kind: Literal["uploaded"]
    repository_id: None = None
    commit_sha: None = None
    limitation: Literal[
        "Uploaded evidence does not establish repository identity or exact-plan custody."
    ] = "Uploaded evidence does not establish repository identity or exact-plan custody."


class CollectedSource(ClosedModel):
    kind: Literal["collected"]
    repository_id: IdentifierValue
    commit_sha: CommitValue
    profile_digest: Digest


class StepBase(ClosedModel):
    id: Identifier
    depends_on: Annotated[list[Identifier], Field(max_length=50)]


class UploadedIntakeStep(StepBase):
    kind: Literal["uploaded_intake"]
    source: UploadedSource
    parameters: CollectionParameters = Field(default_factory=CollectionParameters)


class AdmittedCollectionStep(StepBase):
    kind: Literal["admitted_collection"]
    source: CollectedSource
    parameters: CollectionParameters = Field(default_factory=CollectionParameters)


class SharedAnalysisStep(StepBase):
    kind: Literal["shared_analysis"]
    artifact: StepReference


class PolicyEvaluationStep(StepBase):
    kind: Literal["policy_evaluation"]
    report: StepReference
    target_id: IdentifierValue
    environment: IdentifierValue
    authorization_kind: AuthorizationKind


class HumanDecisionStep(StepBase):
    kind: Literal["human_decision"]
    binding: StepReference


class RegisteredGithubHandoffStep(StepBase):
    kind: Literal["registered_github_handoff"]
    binding: StepReference
    decision: StepReference
    target_id: IdentifierValue
    environment: IdentifierValue
    authorization_kind: AuthorizationKind


Step = Annotated[
    UploadedIntakeStep
    | AdmittedCollectionStep
    | SharedAnalysisStep
    | PolicyEvaluationStep
    | HumanDecisionStep
    | RegisteredGithubHandoffStep,
    Field(discriminator="kind"),
]


class Workflow(ClosedModel):
    workflow_version: Annotated[
        StrictInt, Field(ge=2, le=2, json_schema_extra={"const": 2})
    ]
    project_id: Identifier
    workspace_id: Identifier | None = None
    environment: Identifier | InputReference
    inputs: Annotated[dict[Identifier, InputDeclaration], Field(max_length=32)] = Field(
        default_factory=dict, json_schema_extra={"additionalProperties": False}
    )
    steps: Annotated[list[Step], Field(min_length=1, max_length=50)]
