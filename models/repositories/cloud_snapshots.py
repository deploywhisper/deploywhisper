"""Caller-transaction storage for immutable screened project cloud observations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from sqlalchemy import exists, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from cloud.base import LiveContextSnapshot, canonical_snapshot_json, validate_snapshot
from cloud.redaction import redact_snapshot
from models.tables import AnalysisReport, EvidenceItem
from models.cloud_snapshots import CloudContextSnapshot
from cloud.schema import require_snapshot_schema, snapshot_schema_available

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_RETENTION = timedelta(days=7)


class CloudSnapshotIntegrityError(ValueError):
    code = "cloud_snapshot_unavailable"

    def __init__(self):
        super().__init__("Cloud snapshot unavailable.")


def _require_transaction(session):
    if not isinstance(session, Session) or not session.in_transaction():
        raise CloudSnapshotIntegrityError()
    try:
        if session.get_bind().dialect.name != "sqlite":
            raise CloudSnapshotIntegrityError()
        connection = session.connection()
        if (
            connection.exec_driver_sql("PRAGMA foreign_keys").scalar() != 1
            or not connection.connection.driver_connection.in_transaction
        ):
            raise CloudSnapshotIntegrityError()
    except SQLAlchemyError:
        raise CloudSnapshotIntegrityError() from None


def _wall_now(now=None):
    if now is not None and (
        not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None
    ):
        raise CloudSnapshotIntegrityError()
    # Eligibility is never advanced or postponed by a caller-supplied clock.
    return datetime.now(timezone.utc)


def _aware(value):
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def source_ref_prefix(project_id, digest):
    if (
        type(project_id) is not int
        or project_id < 1
        or not isinstance(digest, str)
        or not _DIGEST.fullmatch(digest)
    ):
        raise CloudSnapshotIntegrityError()
    return f"live_state://{project_id}/{digest}"


def source_ref(project_id, digest, resource_hash):
    if not isinstance(resource_hash, str) or not _DIGEST.fullmatch(resource_hash):
        raise CloudSnapshotIntegrityError()
    return source_ref_prefix(project_id, digest) + "#" + resource_hash


def _retained(session, project_id, digest):
    prefix = source_ref_prefix(project_id, digest)
    return bool(
        session.scalar(
            select(
                exists().where(
                    AnalysisReport.id == EvidenceItem.analysis_id,
                    AnalysisReport.project_id == project_id,
                    EvidenceItem.source_type == "live_state",
                    or_(
                        EvidenceItem.source_ref == prefix,
                        EvidenceItem.source_ref.like(prefix + "#%"),
                    ),
                )
            )
        )
    )


def _checked_row(record):
    source_ref_prefix(record.project_id, record.digest)
    if _aware(record.expires_at) != _aware(record.read_window_end) + _RETENTION:
        raise CloudSnapshotIntegrityError()
    if record.payload_json is None:
        if record.purged_at is None:
            raise CloudSnapshotIntegrityError()
        return None
    if record.purged_at is not None:
        raise CloudSnapshotIntegrityError()
    try:
        snapshot = LiveContextSnapshot.model_validate_json(record.payload_json)
        screened = redact_snapshot(snapshot, mask_accounts=record.mask_accounts)
        if (
            canonical_snapshot_json(snapshot) != record.payload_json
            or canonical_snapshot_json(screened) != record.payload_json
        ):
            raise ValueError("screening changed observation")
        if (
            snapshot.project_id,
            snapshot.digest,
            snapshot.provider,
            snapshot.scope_id,
            snapshot.read_window_start,
            snapshot.read_window_end,
        ) != (
            record.project_id,
            record.digest,
            record.provider,
            record.scope_id,
            _aware(record.read_window_start),
            _aware(record.read_window_end),
        ):
            raise ValueError("column identity changed")
        return snapshot
    except (ValueError, TypeError, AttributeError):
        raise CloudSnapshotIntegrityError() from None


def put_snapshot(
    session, snapshot, *, mask_accounts: bool, now: datetime | None = None
):
    _require_transaction(session)
    clock = _wall_now(now)
    try:
        require_snapshot_schema(session)
        if type(mask_accounts) is not bool:
            raise ValueError("mask policy must be explicit")
        observation = validate_snapshot(snapshot)
        canonical = canonical_snapshot_json(observation)
        if (
            canonical_snapshot_json(
                redact_snapshot(observation, mask_accounts=mask_accounts)
            )
            != canonical
            or observation.read_window_end > clock
        ):
            raise ValueError("unscreened or future observation")
        existing = session.get(
            CloudContextSnapshot,
            (observation.project_id, observation.digest),
            populate_existing=True,
        )
        if existing is not None:
            _checked_row(existing)
            if (
                existing.provider,
                existing.scope_id,
                _aware(existing.read_window_start),
                _aware(existing.read_window_end),
            ) != (
                observation.provider,
                observation.scope_id,
                observation.read_window_start,
                observation.read_window_end,
            ):
                raise ValueError("duplicate metadata changed")
            return existing
        record = CloudContextSnapshot(
            project_id=observation.project_id,
            digest=observation.digest,
            provider=observation.provider,
            scope_id=observation.scope_id,
            read_window_start=observation.read_window_start,
            read_window_end=observation.read_window_end,
            expires_at=observation.read_window_end + _RETENTION,
            created_at=clock,
            mask_accounts=mask_accounts,
            payload_json=canonical,
            purged_at=None,
        )
        session.add(record)
        session.flush()
        return record
    except (ValueError, TypeError, SQLAlchemyError):
        raise CloudSnapshotIntegrityError() from None


def get_snapshot(session, *, project_id, digest, now: datetime | None = None):
    _require_transaction(session)
    clock = _wall_now(now)
    source_ref_prefix(project_id, digest)
    try:
        if not snapshot_schema_available(session):
            return None
        record = session.get(
            CloudContextSnapshot, (project_id, digest), populate_existing=True
        )
        if record is None:
            return None
        snapshot = _checked_row(record)
        if snapshot is None or (
            _aware(record.expires_at) <= clock
            and not _retained(session, project_id, digest)
        ):
            return None
        return snapshot
    except (ValueError, TypeError, SQLAlchemyError):
        raise CloudSnapshotIntegrityError() from None


def purge_expired_snapshots(session, *, project_id, now: datetime | None = None):
    _require_transaction(session)
    clock = _wall_now(now)
    if type(project_id) is not int or project_id < 1:
        raise CloudSnapshotIntegrityError()
    try:
        if not snapshot_schema_available(session):
            return 0
        records = session.scalars(
            select(CloudContextSnapshot).where(
                CloudContextSnapshot.project_id == project_id,
                CloudContextSnapshot.payload_json.is_not(None),
                CloudContextSnapshot.expires_at <= clock,
            )
        ).all()
        purged = 0
        for record in records:
            _checked_row(record)
            if _retained(session, project_id, record.digest):
                continue
            record.payload_json = None
            record.purged_at = clock
            session.flush()
            purged += 1
        return purged
    except (ValueError, TypeError, SQLAlchemyError):
        raise CloudSnapshotIntegrityError() from None
