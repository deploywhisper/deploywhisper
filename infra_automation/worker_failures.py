"""Bounded retry classification for trusted worker persistence boundaries."""

from __future__ import annotations

import sqlite3

from sqlalchemy.exc import OperationalError

from infra_automation.lifecycle import LifecycleError


class InfrastructureOperationError(Exception):
    """Mark a failure from wrapper infrastructure, never handler code."""

    def __init__(self, error: Exception):
        super().__init__("Worker persistence unavailable.")
        self.error = error


def failure_outcome(error: Exception, *, external_started: bool, retry_safe: bool):
    """Return fixed diagnostics without reflecting exception text or SQL."""
    if external_started:
        return "external_unknown"
    if not retry_safe or not isinstance(error, InfrastructureOperationError):
        return "permanent_local_failure"
    cause: BaseException | None = error.error
    if isinstance(cause, LifecycleError):
        transient = cause.status_code == 429
    else:
        if isinstance(cause, OperationalError):
            cause = cause.orig
        # The low byte is SQLite's primary result code; extended BUSY/LOCKED
        # codes retain that meaning. IOERR is intentionally excluded because
        # it also represents persistent filesystem and corruption failures.
        code = getattr(cause, "sqlite_errorcode", None)
        transient = isinstance(cause, sqlite3.OperationalError) and (
            type(code) is int
            and code & 0xFF
            in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_FULL)
        )
    return "retryable_local_failure" if transient else "permanent_local_failure"
