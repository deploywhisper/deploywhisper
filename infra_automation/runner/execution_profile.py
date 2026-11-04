"""Closed operator-owned controls for the qualified offline Linux execution slice."""

from __future__ import annotations

from typing import Annotated, Literal
from pydantic import Field, StrictInt, StrictStr
from infra_automation.contracts import ClosedModel

Positive = Annotated[StrictInt, Field(ge=1)]


class IsolationError(ValueError):
    def __init__(self):
        super().__init__("Isolated runner operation unavailable.")


class ExecutionProfile(ClosedModel):
    image_id: Annotated[StrictStr, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
    architecture: Literal["arm64"] = "arm64"
    docker_version: Literal["29.1.3"] = "29.1.3"
    kernel_version: Literal["6.12.54-linuxkit"] = "6.12.54-linuxkit"
    uid: Literal[10001] = 10001
    gid: Literal[10001] = 10001
    network: Literal["none"] = "none"
    memory_bytes: Annotated[StrictInt, Field(ge=33554432, le=1073741824)] = 268435456
    nano_cpus: Annotated[StrictInt, Field(ge=100000000, le=2000000000)] = 500000000
    pids_limit: Annotated[StrictInt, Field(ge=8, le=128)] = 64
    work_bytes: Annotated[StrictInt, Field(ge=1048576, le=268435456)] = 67108864
    tmp_bytes: Annotated[StrictInt, Field(ge=1048576, le=16777216)] = 8388608
    timeout_seconds: Annotated[StrictInt, Field(ge=1, le=600)] = 60
    output_bytes: Annotated[StrictInt, Field(ge=128, le=131072)] = 65536
    cleanup_seconds: Annotated[StrictInt, Field(ge=1, le=15)] = 5
    collector_identity: Annotated[
        StrictStr, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")
    ] = "qualification-collector"
    credential_names: tuple[Literal["COLLECTOR_TOKEN"], ...] = ()
