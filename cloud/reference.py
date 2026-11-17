"""Explicitly injected, network-free reference observations for contract tests.

This provider is deliberately absent from the default registry. It proves the
connector boundary without claiming access to any live cloud environment.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import StrictStr, model_validator

from cloud.base import (
    FrozenModel,
    LiveContextSnapshot,
    ReadStatus,
    ResourceIdentity,
    ResourceRead,
    build_snapshot,
)


class ReferenceCloudConnector(FrozenModel):
    """Return only supplied synthetic observations of the requested identities."""

    observations: tuple[ResourceRead, ...] = ()
    read_window_start: datetime
    read_window_end: datetime
    scope: StrictStr = "reference-account"
    regions: tuple[StrictStr, ...] = ()

    @model_validator(mode="after")
    def _validate_observations(self):
        # Reuse snapshot normalization, uniqueness and window validation rather
        # than introducing a second observation vocabulary or canonicalizer.
        template = build_snapshot(
            provider="reference",
            project_id=1,
            scope_id="reference-constructor-validation",
            scope=self.scope,
            regions=self.regions,
            read_window_start=self.read_window_start,
            read_window_end=self.read_window_end,
            resources=self.observations,
        )
        object.__setattr__(self, "observations", template.resources)
        object.__setattr__(self, "regions", template.regions)
        object.__setattr__(self, "read_window_start", template.read_window_start)
        object.__setattr__(self, "read_window_end", template.read_window_end)
        return self

    def collect(
        self,
        identities: tuple[ResourceIdentity, ...],
        *,
        project_id: int,
        scope_id: str,
    ) -> LiveContextSnapshot:
        requested = tuple(ResourceIdentity.model_validate(item) for item in identities)
        if len({item.address for item in requested}) != len(requested):
            raise ValueError("reference_duplicate_identity")
        observed = {item.identity.address: item for item in self.observations}
        results = []
        for identity in requested:
            result = observed.get(identity.address)
            if result is None:
                results.append(
                    ResourceRead(
                        identity=identity,
                        status=ReadStatus.UNKNOWN,
                        cause="reference_observation_missing",
                    )
                )
            elif result.identity != identity:
                raise ValueError("reference_identity_mismatch")
            else:
                results.append(ResourceRead.model_validate(result))
        return build_snapshot(
            provider="reference",
            project_id=project_id,
            scope_id=scope_id,
            scope=self.scope,
            regions=self.regions,
            read_window_start=self.read_window_start,
            read_window_end=self.read_window_end,
            resources=tuple(results),
            # In-memory fixture lookups issue no provider API actions.
            issued_actions=(),
        )
