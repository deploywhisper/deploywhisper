"""Provider extension registry with explicit unknown and unimplemented states."""

from __future__ import annotations

import re
from typing import Callable
from cloud.base import CloudConnector

ConnectorFactory = Callable[[], CloudConnector]
CONNECTORS: dict[str, ConnectorFactory | None] = {
    "aws": None,
    "azure": None,
    "gcp": None,
}


class CloudProviderError(ValueError):
    """A provider cannot supply the requested observation."""


class UnknownProviderError(CloudProviderError):
    """The provider is not registered."""


class UnimplementedProviderError(CloudProviderError):
    """The registered provider has no implemented connector."""


def register_connector(name: str, factory: ConnectorFactory) -> None:
    if not isinstance(name, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,31}", name) is None:
        raise ValueError("Provider name is invalid")
    if not callable(factory):
        raise TypeError("Connector factory must be callable")
    if name in CONNECTORS and CONNECTORS[name] is not None:
        raise ValueError("Provider is already registered")
    CONNECTORS[name] = factory


def create_connector(name: str) -> CloudConnector:
    if not isinstance(name, str) or name not in CONNECTORS:
        raise UnknownProviderError("Cloud provider is not registered")
    factory = CONNECTORS[name]
    if factory is None:
        raise UnimplementedProviderError(
            "Cloud provider is registered but not implemented"
        )
    connector = factory()
    if not callable(getattr(connector, "collect", None)):
        raise CloudProviderError("Registered connector does not implement collection")
    return connector
