"""Internal cloud orchestration with an installed server authorization boundary."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Callable, ContextManager, Iterator, Literal, Protocol
from uuid import uuid4

from pydantic import (
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    ValidationError,
)
from sqlalchemy import event, or_, select
from sqlalchemy.orm import Session

from cloud.base import (
    FrozenModel,
    LiveContextSnapshot,
    ResourceIdentity,
    ReadStatus,
    validate_snapshot,
)
from cloud.redaction import redact_snapshot
from cloud.registry import (
    create_connector,
    UnknownProviderError,
    UnimplementedProviderError,
)
from evidence.models import (
    ContextSourceFreshness,
    ContextSourceMetadata,
    EvidenceItem,
    RiskSeverity,
)
from models.repositories.projects import get_project
from models.repositories.settings import get_setting, upsert_setting
from models.tables import (
    AnalysisReport,
    ProjectWorkspace,
    Project,
    EvidenceItem as StoredEvidence,
    Finding as StoredFinding,
)

CloudOperation = Literal["configure", "collect", "read", "admit", "purge"]


class AuthorizedCloudUnitOfWork(Protocol):
    """Installed by trusted server code, never supplied through request parameters.

    The port owns transaction commit/rollback, reserves the writer before reads,
    and rechecks its existing authorization policy whenever check() is called.
    Callers publishing reports inside admission must use commit=False.
    """

    def session(
        self, project_id: int, operation: CloudOperation
    ) -> ContextManager[Session]: ...

    def check(
        self, session: Session, project_id: int, operation: CloudOperation
    ) -> None: ...


class CloudContextError(ValueError):
    """Closed cause codes deliberately exclude provider/validation payloads."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class CloudProjectConfiguration(FrozenModel):
    project_id: StrictInt = Field(ge=1)
    enabled: StrictBool = False
    provider: StrictStr | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,31}$")
    scope_id: StrictStr | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    mask_accounts: StrictBool = True


class GroundingOutcome(FrozenModel):
    state: Literal["disabled", "snapshot"]
    snapshot: LiveContextSnapshot | None = None
    context: ContextSourceMetadata | None = None


def _utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise CloudContextError("invalid_clock")
    return value.astimezone(timezone.utc)


def snapshot_context(
    snapshot: LiveContextSnapshot | None,
    *,
    now: datetime,
    conflicting: bool = False,
    stale_after: timedelta = timedelta(hours=1),
) -> ContextSourceMetadata:
    now = _utc(now)
    if not isinstance(stale_after, timedelta) or stale_after.total_seconds() < 0:
        raise CloudContextError("invalid_freshness_policy")
    if snapshot is None:
        return ContextSourceMetadata(
            source_id="live_state:missing",
            source_type="live_state",
            scope="unavailable",
            freshness_status="missing",
            confidence=0,
        )
    snapshot = validate_snapshot(snapshot)
    age = now - snapshot.read_window_end
    state: ContextSourceFreshness = (
        "conflicting"
        if conflicting
        else "unknown"
        if age.total_seconds() < 0
        else "incomplete"
        if snapshot.partial
        else "stale"
        if age > stale_after
        else "current"
    )
    return ContextSourceMetadata(
        source_id="live_state:" + snapshot.digest,
        source_type="live_state",
        source_ref=f"live_state://{snapshot.project_id}/{snapshot.digest}",
        scope=snapshot.scope_id,
        freshness_status=state,
        last_observed_at=snapshot.read_window_end.isoformat(),
        age_days=max(0, age.days),
        confidence=1 if state == "current" else 0,
        conflicts=["configured_scope_conflict"] if conflicting else [],
        limitations=["partial_observation"] if snapshot.partial else [],
    )


class _EvidenceAdmission:
    def __init__(self, service, session, project_id, snapshot, check):
        self.session = session
        self._service = service
        self._project_id = project_id
        self._snapshot = snapshot
        self._check = check
        self._active = True
        self._minted: dict[str, EvidenceItem] = {}
        self._nonce = uuid4().hex
        self._before_live_rows = self._live_rows()
        self._before_live_ids = set(self._before_live_rows)

    def _live_rows(self):
        # Read columns, not ORM identities: pending ORM edits and bulk SQL must
        # be compared with the actual retained values after flush.
        return {
            row.evidence_id: tuple(row)
            for row in self.session.execute(
                select(StoredEvidence.__table__).where(
                    or_(
                        StoredEvidence.source_type == "live_state",
                        StoredEvidence.source_kind == "live_state",
                        StoredEvidence.source_ref.startswith(
                            "live_state://", autoescape=True
                        ),
                    )
                )
            )
        }

    def _live_ids(self, report_ids=None):
        # The reserved writer transaction makes newly appearing live evidence
        # part of this publication unit, including rows in other projects.
        predicate = or_(
            StoredEvidence.source_type == "live_state",
            StoredEvidence.source_kind == "live_state",
            StoredEvidence.source_ref.startswith("live_state://", autoescape=True),
        )
        statement = select(StoredEvidence.evidence_id).where(predicate)
        if report_ids is not None:
            if not report_ids:
                return set()
            statement = statement.where(StoredEvidence.analysis_id.in_(report_ids))
        return set(self.session.scalars(statement))

    @staticmethod
    def _finding_refs(finding):
        try:
            refs = json.loads(finding.evidence_refs_json)
        except (ValueError, TypeError, AttributeError):
            raise CloudContextError("invalid_evidence_publication") from None
        if (
            not isinstance(refs, list)
            or any(not isinstance(value, str) or not value for value in refs)
            or len(refs) != len(set(refs))
        ):
            raise CloudContextError("invalid_evidence_publication")
        return refs

    def evidence_for(
        self,
        resource_address: str,
        fact_name: str,
        finding_id: str,
        analysis_id: int = 0,
        severity_hint: RiskSeverity = "low",
    ) -> EvidenceItem:
        if not self._active:
            raise CloudContextError("admission_closed")
        self._check()
        resource = next(
            (
                r
                for r in self._snapshot.resources
                if r.identity.address == resource_address
            ),
            None,
        )
        if resource is None or resource.status != ReadStatus.READ:
            raise CloudContextError("resource_not_observed")
        fact = next((f for f in resource.facts if f.name == fact_name), None)
        if fact is None:
            raise CloudContextError("fact_not_observed")
        if type(analysis_id) is not int or analysis_id < 0:
            raise CloudContextError("invalid_report_scope")
        if analysis_id:
            report = self.session.get(AnalysisReport, analysis_id)
            if report is None or report.project_id != self._project_id:
                raise CloudContextError("invalid_report_scope")
        if (
            not isinstance(finding_id, str)
            or not finding_id.strip()
            or len(finding_id) > 64
        ):
            raise CloudContextError("invalid_finding_identity")
        from models.repositories.cloud_snapshots import source_ref

        resource_hash = hashlib.sha256(resource_address.encode()).hexdigest()
        evidence_id = hashlib.sha256(
            json.dumps(
                [
                    self._nonce,
                    self._project_id,
                    self._snapshot.digest,
                    resource_address,
                    fact_name,
                    finding_id,
                ],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        try:
            evidence = EvidenceItem(
                evidence_id=evidence_id,
                analysis_id=analysis_id,
                finding_id=finding_id,
                project_id=self._project_id,
                source_type="live_state",
                source_ref=source_ref(
                    self._project_id, self._snapshot.digest, resource_hash
                ),
                artifact=self._snapshot.digest,
                resource=resource_address,
                operation="read",
                summary=f"{fact.name} = {json.dumps(fact.value, ensure_ascii=True)}",
                severity_hint=severity_hint,
                deterministic=True,
                confidence=1,
                redaction_status=self._snapshot.redaction_status,
                related_change_ids=[resource_address],
                context_source=snapshot_context(
                    self._snapshot, now=self._service._now()
                ),
            )
        except (ValidationError, ValueError, TypeError):
            raise CloudContextError("invalid_evidence_claim") from None
        self._minted[evidence_id] = evidence.model_copy(deep=True)
        return evidence

    def _verify_publication(self):
        self._check()
        self.session.flush()
        current_rows = self._live_rows()
        if any(
            current_rows.get(evidence_id) != row
            for evidence_id, row in self._before_live_rows.items()
        ):
            raise CloudContextError("invalid_evidence_publication")
        minted_ids = set(self._minted)
        if not (self._live_ids() - self._before_live_ids) <= minted_ids:
            raise CloudContextError("invalid_evidence_publication")
        report_ids = set()
        for evidence in self._minted.values():
            row = self.session.get(
                StoredEvidence, evidence.evidence_id, populate_existing=True
            )
            if row is None:
                raise CloudContextError("evidence_not_published")
            report = self.session.get(
                AnalysisReport, row.analysis_id, populate_existing=True
            )
            finding = self.session.get(
                StoredFinding, row.finding_id, populate_existing=True
            )
            project = self.session.get(
                Project, self._project_id, populate_existing=True
            )
            workspace = (
                self.session.get(
                    ProjectWorkspace, report.workspace_id, populate_existing=True
                )
                if report is not None and report.workspace_id is not None
                else None
            )
            scope_metadata_valid = (
                project is not None
                and report is not None
                and (
                    report.workspace_id is None
                    or (
                        workspace is not None
                        and workspace.project_id == self._project_id
                    )
                )
                and row.project_key in (None, project.project_key)
                and (
                    row.workspace_id is None
                    or report is not None
                    and row.workspace_id == report.workspace_id
                )
                and (
                    row.workspace_key is None
                    or workspace is not None
                    and workspace.project_id == self._project_id
                    and row.workspace_key == workspace.workspace_key
                )
            )
            refs = self._finding_refs(finding)
            if (
                not scope_metadata_valid
                or report is None
                or report.project_id != self._project_id
                or finding is None
                or finding.analysis_id != row.analysis_id
                or row.project_id != self._project_id
                or row.finding_id != evidence.finding_id
                or row.source_ref != evidence.source_ref
                or row.source_type != "live_state"
                or row.source_kind != "live_state"
                or row.determinism_level != "deterministic"
                or not row.deterministic
                or row.evidence_id not in refs
                or row.artifact != evidence.artifact
                or row.location != evidence.location
                or row.operation != evidence.operation
                or row.confidence != evidence.confidence
                or row.redaction_status != evidence.redaction_status
                or row.severity_hint != evidence.severity_hint
                or json.loads(row.context_source_json or "null")
                != evidence.context_source.model_dump(mode="json")
                or json.loads(row.related_change_ids_json or "null")
                != evidence.related_change_ids
                or row.summary != evidence.summary
                or row.resource != evidence.resource
                or (evidence.analysis_id and evidence.analysis_id != row.analysis_id)
            ):
                raise CloudContextError("invalid_evidence_publication")
            report_ids.add(row.analysis_id)
        # This is one snapshot admission, not a path to smuggle extra live
        # evidence alongside a valid minted claim, even in an existing report.
        if not self._live_ids(report_ids) <= minted_ids:
            raise CloudContextError("invalid_evidence_publication")
        for finding in self.session.scalars(
            select(StoredFinding)
            .where(StoredFinding.analysis_id.in_(report_ids))
            .execution_options(populate_existing=True)
        ):
            for evidence_ref in self._finding_refs(finding):
                linked = self.session.get(
                    StoredEvidence, evidence_ref, populate_existing=True
                )
                if linked is None or linked.analysis_id != finding.analysis_id:
                    raise CloudContextError("invalid_evidence_publication")
        self._check()


class CloudContextService:
    """Foundation only: no routes, default analysis hook or production auth adapter."""

    def __init__(
        self,
        *,
        unit_of_work: AuthorizedCloudUnitOfWork | None = None,
        connector_factory: Callable = create_connector,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self._uow = unit_of_work
        self._connector_factory = connector_factory
        self._clock = clock

    def _now(self):
        return _utc(self._clock())

    @contextmanager
    def _transaction(self, project_id, operation):
        if type(project_id) is not int or not 1 <= project_id <= 2**63 - 1:
            raise CloudContextError("invalid_project_scope")
        if (
            self._uow is None
            or not callable(getattr(self._uow, "session", None))
            or not callable(getattr(self._uow, "check", None))
        ):
            raise CloudContextError("authorization_unavailable")
        try:
            with self._uow.session(project_id, operation) as session:
                transaction = session.get_transaction()
                if transaction is None or not transaction.is_active:
                    raise CloudContextError("authorization_transaction_required")

                early_commit_attempted = False

                def check():
                    if (
                        early_commit_attempted
                        or session.get_transaction() is not transaction
                        or not transaction.is_active
                    ):
                        raise CloudContextError("authorization_transaction_changed")
                    try:
                        result = self._uow.check(session, project_id, operation)
                        if result is not None:
                            raise CloudContextError("authorization_unavailable")
                    except PermissionError:
                        raise CloudContextError("authorization_denied") from None

                check()
                if get_project(session, project_id) is None:
                    raise CloudContextError("project_not_found")

                def reject_early_commit(_transaction_owner):
                    nonlocal early_commit_attempted
                    early_commit_attempted = True
                    raise CloudContextError("authorization_transaction_changed")

                def reject_sql_commit(
                    conn, cursor, statement, parameters, context, executemany
                ):
                    # SQLite accepts END as COMMIT and permits leading comments.
                    if re.match(
                        r"(?:[\s;\ufeff]|--[^\r\n]*(?:\r?\n|$)|/\*.*?\*/)*(?:COMMIT|END)\b",
                        statement,
                        re.IGNORECASE | re.DOTALL,
                    ):
                        reject_early_commit(conn)

                connection = session.connection()
                # Connection.commit() does not dispatch Session.before_commit.
                # Reject it before the DBAPI commit can make publication durable.
                event.listen(session, "before_commit", reject_early_commit)
                event.listen(connection, "commit", reject_early_commit)
                event.listen(connection, "before_cursor_execute", reject_sql_commit)
                try:
                    yield session, check
                    check()
                finally:
                    event.remove(connection, "before_cursor_execute", reject_sql_commit)
                    event.remove(connection, "commit", reject_early_commit)
                    event.remove(session, "before_commit", reject_early_commit)
        except CloudContextError:
            raise
        except PermissionError:
            raise CloudContextError("authorization_denied") from None
        except Exception:
            raise CloudContextError("cloud_context_unavailable") from None

    def _configuration(self, session, project_id):
        setting = get_setting(session, f"cloud_context:{project_id}")
        if setting is None:
            return CloudProjectConfiguration(project_id=project_id)
        try:
            config = CloudProjectConfiguration.model_validate_json(setting.value)
            if config.project_id != project_id:
                raise ValueError("scope mismatch")
            if config.enabled and (not config.provider or not config.scope_id):
                raise ValueError("incomplete configuration")
            return config
        except (ValueError, TypeError):
            raise CloudContextError("invalid_configuration") from None

    def configure(
        self,
        project_id,
        *,
        enabled: bool,
        provider: str | None = None,
        mask_accounts: bool = True,
    ):
        if type(enabled) is not bool or type(mask_accounts) is not bool:
            raise CloudContextError("invalid_configuration")
        if provider is not None and (
            not isinstance(provider, str)
            or re.fullmatch(r"[a-z][a-z0-9_]{0,31}", provider) is None
        ):
            raise CloudContextError("invalid_configuration")
        if enabled and provider is None:
            raise CloudContextError("invalid_configuration")
        with self._transaction(project_id, "configure") as (session, check):
            previous = self._configuration(session, project_id)
            config = CloudProjectConfiguration(
                project_id=project_id,
                enabled=enabled,
                provider=provider if enabled else previous.provider,
                scope_id=uuid4().hex if enabled else previous.scope_id,
                mask_accounts=mask_accounts,
            )
            check()
            if enabled:
                from cloud.schema import (
                    initialize_snapshot_schema,
                    CloudSnapshotSchemaError,
                )

                try:
                    initialize_snapshot_schema(session)
                except CloudSnapshotSchemaError:
                    raise CloudContextError("snapshot_storage_unavailable") from None
                check()
            upsert_setting(
                session,
                key=f"cloud_context:{project_id}",
                value=config.model_dump_json(),
                commit=False,
            )
            check()
            return config

    def collect(
        self, project_id, identities: tuple[ResourceIdentity, ...]
    ) -> GroundingOutcome:
        with self._transaction(project_id, "collect") as (session, check):
            config = self._configuration(session, project_id)
            if not config.enabled:
                return GroundingOutcome(state="disabled")
            check()
            from cloud.schema import require_snapshot_schema, CloudSnapshotSchemaError

            try:
                require_snapshot_schema(session)
            except CloudSnapshotSchemaError:
                raise CloudContextError("snapshot_storage_unavailable") from None
            check()
            try:
                identities = tuple(
                    ResourceIdentity.model_validate(i) for i in identities
                )
                if len({i.address for i in identities}) != len(identities):
                    raise ValueError("duplicate identity")
                connector = self._connector_factory(config.provider)
                raw = validate_snapshot(
                    connector.collect(
                        identities, project_id=project_id, scope_id=config.scope_id
                    )
                )
                expected = {i.address: i for i in identities}
                if (
                    raw.provider != config.provider
                    or raw.project_id != project_id
                    or raw.scope_id != config.scope_id
                    or {r.identity.address: r.identity for r in raw.resources}
                    != expected
                    or raw.read_window_end > self._now()
                ):
                    raise ValueError("observation binding mismatch")
                snapshot = redact_snapshot(
                    raw,
                    mask_accounts=config.mask_accounts,
                    account_identifiers=(raw.scope,),
                )
            except UnknownProviderError:
                raise CloudContextError("unknown_provider") from None
            except UnimplementedProviderError:
                raise CloudContextError("unimplemented_provider") from None
            except Exception:
                raise CloudContextError("invalid_observation") from None
            check()
            from models.repositories.cloud_snapshots import put_snapshot, get_snapshot

            put_snapshot(
                session, snapshot, mask_accounts=config.mask_accounts, now=self._now()
            )
            check()
            retained = get_snapshot(
                session, project_id=project_id, digest=snapshot.digest, now=self._now()
            )
            if retained is None or retained.digest != snapshot.digest:
                raise CloudContextError("snapshot_unavailable")
            snapshot = retained
            check()
            return GroundingOutcome(
                state="snapshot",
                snapshot=snapshot,
                context=snapshot_context(snapshot, now=self._now()),
            )

    def get_snapshot(self, project_id, digest):
        with self._transaction(project_id, "read") as (session, check):
            from models.repositories.cloud_snapshots import get_snapshot

            result = get_snapshot(
                session, project_id=project_id, digest=digest, now=self._now()
            )
            check()
            return result

    def purge_expired(self, project_id):
        with self._transaction(project_id, "purge") as (session, check):
            from models.repositories.cloud_snapshots import purge_expired_snapshots

            check()
            return purge_expired_snapshots(
                session, project_id=project_id, now=self._now()
            )

    @contextmanager
    def admit_evidence(self, project_id, digest) -> Iterator[_EvidenceAdmission]:
        with self._transaction(project_id, "admit") as (session, check):
            config = self._configuration(session, project_id)
            if not config.enabled:
                raise CloudContextError("grounding_disabled")
            from models.repositories.cloud_snapshots import get_snapshot

            snapshot = get_snapshot(
                session, project_id=project_id, digest=digest, now=self._now()
            )
            if snapshot is None:
                raise CloudContextError("snapshot_unavailable")
            if (
                snapshot.scope_id != config.scope_id
                or snapshot.provider != config.provider
            ):
                raise CloudContextError("snapshot_scope_changed")
            check()
            admission = _EvidenceAdmission(self, session, project_id, snapshot, check)
            try:
                yield admission
                admission._verify_publication()
                retained = get_snapshot(
                    session, project_id=project_id, digest=digest, now=self._now()
                )
                if retained is None or retained.digest != snapshot.digest:
                    raise CloudContextError("snapshot_unavailable")
                check()
            finally:
                admission._active = False
