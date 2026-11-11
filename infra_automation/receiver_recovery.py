"""Closed internal authority stamp for receiver reconciliation only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PREFIX = "receiver-reconcile-v1-"
MAX_ISSUES = 100
RecoveryMode = Literal["status_only", "status_terminal"]


@dataclass(frozen=True)
class RecoveryAuthentication:
    operation_id: str
    version: int
    credential_digest: str
    mode: RecoveryMode
    issuer_id: str
    generation: int
