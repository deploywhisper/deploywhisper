"""Disposable reference-bound retention decision, not a product purge service."""

from __future__ import annotations


def disposition(now, observed_at, retention_seconds, report_expiries):
    values = [now, observed_at, retention_seconds]
    if any(type(value) is not int or value < 0 for value in values):
        raise ValueError("invalid retention clock or duration")
    if observed_at > now:
        raise ValueError("future observation")
    for expiry in report_expiries:
        if expiry is None:
            return "retain"
        if type(expiry) is not int or expiry < 0:
            raise ValueError("invalid report expiry")
        if expiry > now:
            return "retain"
    if now < observed_at + retention_seconds:
        return "retain"
    return "purge_payload_keep_digest"
