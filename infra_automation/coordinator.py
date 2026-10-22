"""Short fenced scheduler ticks; handler execution belongs to spawned workers."""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
import logging
import threading

from sqlalchemy import func, select

import config
from infra_automation import claims
from infra_automation.storage import ensure_capacity
from infra_automation.lifecycle import LifecycleError, SnapshotDocument
from infra_automation.local_workers import (
    DEFAULT_REGISTRY,
    WorkerInput,
    WorkerTerminationError,
)
from infra_automation.state import ACTIVE_STATES, EngineBounds
from models.repositories import infra_automation_runs as repository
from models.tables import InfraAutomationRun
from services import project_service as authorization

logger = logging.getLogger(__name__)


def deadline_outcome(snapshot_bytes: bytes, deadline_at: datetime) -> str:
    """Distinguish immutable evidence expiry from an earlier total timeout."""
    document = SnapshotDocument.model_validate_json(snapshot_bytes)
    captured = datetime.strptime(document.captured_at, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    evidence_deadline = captured + timedelta(
        seconds=document.policy.evidence_ttl_seconds
    )
    return (
        "expired" if repository.utc(deadline_at) >= evidence_deadline else "timed_out"
    )


class Coordinator:
    def __init__(
        self,
        session_factory,
        workers,
        *,
        registry=DEFAULT_REGISTRY,
        bounds=None,
        clock=None,
    ):
        self.factory = session_factory
        self.workers = workers
        self.registry = registry
        self.bounds = EngineBounds.model_validate(
            (config.engine_bounds() if bounds is None else bounds).model_dump()
        )
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._owner = None
        self._scope = None
        self._heartbeat_at = None
        self._lock = threading.Lock()
        self._task = None
        self._stopping = False
        self._pending_completions = {}
        self._candidate_sequence = 0
        self._candidate_ceiling = None
        self._candidate_rotation = 0

    @property
    def _can_submit(self):
        return self.workers.can_submit and (
            len(self._pending_completions) + len(self.workers.handles)
            < min(self.bounds.analysis_workers, self.workers.max_workers)
        )

    def _operation(self, function, *args, **kwargs):
        with authorization.authorized_session(self.factory) as session:
            return function(session, *args, **kwargs)

    def _signal_committed_cancel(self, run_id):
        self._pending_completions = {
            attempt_id: completion
            for attempt_id, completion in self._pending_completions.items()
            if completion.handle.run_id != run_id
        }
        failed = False
        for handle in self.workers.handles:
            if handle.run_id == run_id:
                try:
                    self.workers.cancel(handle.attempt_id)
                except WorkerTerminationError:
                    failed = True
        if failed:
            raise WorkerTerminationError()

    def cancel_run(self, run_id):
        """Signal this process's workers only after observing durable cancellation."""
        if authorization.has_authorized_session():
            raise LifecycleError(409)
        with self._lock:
            with authorization.authorized_session(self.factory) as session:
                run = repository.get_run(session, run_id)
                cancelled = run is not None and run.cancel_requested
            if not cancelled:
                return False
            self._signal_committed_cancel(run_id)
            return True

    def _observe_cancellations(self):
        run_ids = {handle.run_id for handle in self.workers.handles}
        run_ids.update(
            completion.handle.run_id
            for completion in self._pending_completions.values()
        )
        if not run_ids:
            return
        with authorization.authorized_session(self.factory) as session:
            cancelled = tuple(
                session.scalars(
                    select(InfraAutomationRun.id).where(
                        InfraAutomationRun.id.in_(run_ids),
                        InfraAutomationRun.cancel_requested.is_(True),
                    )
                )
            )
        for run_id in cancelled:
            self._signal_committed_cancel(run_id)

    def _stop(self, run_id, state, now):
        with authorization.authorized_session(self.factory) as session:
            now = self.clock()
            row = repository.get_run(session, run_id)
            if row is not None and row.state in (
                "queued",
                "running",
                "handing_off",
                "external_running",
            ):
                if row.external_possible:
                    state = "delivery_unknown"
                claims.stop_run(
                    session,
                    self._owner,
                    run_id=run_id,
                    expected_version=row.version,
                    state=state,
                    now=now,
                )

    def _complete(self, completion, now):
        handle, result = completion.handle, completion.result
        if handle.generation != self._owner.generation:
            raise LifecycleError(409)
        with authorization.authorized_session(self.factory) as session:
            now = self.clock()
            attempt = repository.get_attempt(session, handle.attempt_id)
            run = repository.get_run(session, handle.run_id)
            if run is not None and run.external_possible:
                if run.state in ("handing_off", "external_running"):
                    claims.stop_run(
                        session,
                        self._owner,
                        run_id=run.id,
                        expected_version=run.version,
                        state="delivery_unknown",
                        now=now,
                    )
                return
            if (
                run is not None
                and run.state == "running"
                and now >= repository.utc(run.deadline_at)
            ):
                claims.stop_run(
                    session,
                    self._owner,
                    run_id=run.id,
                    expected_version=run.version,
                    state=deadline_outcome(run.snapshot_bytes, run.deadline_at),
                    now=now,
                )
                return
            if attempt is None or attempt.state not in ("claimed", "running"):
                return
            expired = (
                now >= repository.utc(attempt.deadline_at)
                or attempt.lease_until is None
                or now >= repository.utc(attempt.lease_until)
            )
            if completion.crashed or attempt.state == "claimed" or expired:
                claims.safety_cleanup(
                    session,
                    self._owner,
                    attempt_id=attempt.id,
                    expected_version=attempt.version,
                    state="timed_out" if expired else "failed",
                    now=now,
                )
            else:
                claims.complete_attempt(
                    session,
                    handle,
                    expected_version=attempt.version,
                    state="succeeded"
                    if result.outcome == "local_success"
                    else "failed",
                    now=now,
                )
            run = repository.get_run(session, handle.run_id)
            if result.outcome in ("stopped_by_gate", "rejected") and not expired:
                claims.finish_run(
                    session,
                    self._owner,
                    run_id=run.id,
                    expected_version=run.version,
                    state=result.outcome,
                    now=now,
                )
            elif result.outcome != "local_success" and not (
                (completion.crashed or result.outcome == "retryable_local_failure")
                and attempt.retry_safe
                and attempt.attempt_number < 3
                and now < repository.utc(run.deadline_at)
            ):
                claims.stop_run(
                    session,
                    self._owner,
                    run_id=run.id,
                    expected_version=run.version,
                    state="failed",
                    now=now,
                )

    def _recover_abandoned(self, handle, now):
        with authorization.authorized_session(self.factory) as session:
            now = self.clock()
            run = repository.get_run(session, handle.run_id)
            if run is None or run.state not in (
                "running",
                "handing_off",
                "external_running",
            ):
                return
            if run.external_possible:
                claims.stop_run(
                    session,
                    self._owner,
                    run_id=run.id,
                    expected_version=run.version,
                    state="delivery_unknown",
                    now=now,
                )
                return
            row = repository.get_attempt(session, handle.attempt_id)
            if row is not None and row.state in ("claimed", "running"):
                claims.safety_cleanup(
                    session,
                    self._owner,
                    attempt_id=row.id,
                    expected_version=row.version,
                    state="failed",
                    now=now,
                )

    def _ownership(self):
        with authorization.authorized_session(self.factory) as session:
            now = self.clock()
            eligible = InfraAutomationRun.state.in_(
                ("queued", "running", "handing_off", "external_running")
            )
            if self._candidate_ceiling is None:
                self._candidate_ceiling = (
                    session.scalar(
                        select(func.max(InfraAutomationRun.sequence)).where(eligible)
                    )
                    or 0
                )
            candidates = list(
                session.scalars(
                    select(InfraAutomationRun)
                    .where(
                        eligible,
                        InfraAutomationRun.sequence > self._candidate_sequence,
                        InfraAutomationRun.sequence <= self._candidate_ceiling,
                    )
                    .order_by(InfraAutomationRun.sequence)
                    .limit(100)
                )
            )
            # Freeze each sweep's tail so sustained arrivals cannot extend it
            # indefinitely and delay revisiting older blocked runs/deadlines.
            if (
                len(candidates) < 100
                or candidates[-1].sequence >= self._candidate_ceiling
            ):
                self._candidate_sequence = 0
                self._candidate_ceiling = None
            else:
                self._candidate_sequence = candidates[-1].sequence
            owner = self._owner
            scope = self._scope
            if owner is None:
                if not candidates:
                    return [], now
                first = candidates[0]
                scope = (first.project_id, first.workspace_id)
                owner = claims.acquire_coordinator(
                    session, project_id=scope[0], workspace_id=scope[1], now=now
                )
                if owner is None:
                    return [], now
            elif (now - self._heartbeat_at).total_seconds() >= 10:
                claims.renew_coordinator(
                    session, owner, project_id=scope[0], workspace_id=scope[1], now=now
                )
        # Only retain a capability whose acquisition actually committed.
        self._owner, self._scope = owner, scope
        self._heartbeat_at = (
            now
            if self._heartbeat_at is None
            or (now - self._heartbeat_at).total_seconds() >= 10
            else self._heartbeat_at
        )
        # Interleave projects, then workflows within each project, so a hot
        # workflow cannot consume every available slot in a mixed page.
        projects = {}
        for candidate in candidates:
            projects.setdefault(candidate.project_id, {}).setdefault(
                candidate.workflow_id, deque()
            ).append(candidate)
        project_queues = deque()
        for workflows in projects.values():
            lanes = deque(workflows.values())
            lanes.rotate(-self._candidate_rotation)
            project_queues.append(lanes)
        project_queues.rotate(-self._candidate_rotation)
        self._candidate_rotation += 1
        candidates = []
        while project_queues:
            workflows = project_queues.popleft()
            lane = workflows.popleft()
            candidates.append(lane.popleft())
            if lane:
                workflows.append(lane)
            if workflows:
                project_queues.append(workflows)
        return candidates, now

    def _stop_invalid_workers(self, stopping_attempts):
        """Terminal database state is not proof an owned process has exited."""
        for handle in self.workers.handles:
            if handle.attempt_id in stopping_attempts:
                continue
            try:
                with authorization.authorized_session(self.factory) as session:
                    run = repository.get_run(session, handle.run_id)
                    attempt = repository.get_attempt(session, handle.attempt_id)
                    invalid = (
                        run is None
                        or run.state
                        not in ("running", "handing_off", "external_running")
                        or attempt is None
                        or attempt.state not in ("claimed", "running")
                    )
                if invalid:
                    # The worker port keeps its slot until termination succeeds.
                    self.workers.cancel(handle.attempt_id)
            except Exception:
                logger.warning("Local engine terminal worker stop rejected.")

    def tick(self):
        if not self.registry or self._stopping:
            return
        with self._lock:
            self._observe_cancellations()
            try:
                candidates, now = self._ownership()
            except LifecycleError:
                for handle in self.workers.handles:
                    self.workers.cancel(handle.attempt_id)
                self._owner = self._scope = self._heartbeat_at = None
                self._pending_completions.clear()
                logger.warning("Local engine ownership lost.")
                return
            if self._owner is None:
                return
            for completion in self.workers.poll():
                self._pending_completions[completion.handle.attempt_id] = completion
            for attempt_id, completion in tuple(self._pending_completions.items()):
                try:
                    self._complete(completion, now)
                except Exception:
                    # Preserve known outcome semantics until its transaction commits.
                    logger.warning("Local engine completion rejected.")
                else:
                    del self._pending_completions[attempt_id]
            heartbeat_handles = {
                handle.attempt_id: handle for handle in self.workers.handles
            }
            heartbeat_handles.update(
                {
                    attempt_id: completion.handle
                    for attempt_id, completion in self._pending_completions.items()
                }
            )
            stopping_attempts = set()
            for handle in heartbeat_handles.values():
                try:
                    stop_external = False
                    with authorization.authorized_session(self.factory) as session:
                        heartbeat_now = self.clock()
                        row = repository.get_attempt(session, handle.attempt_id)
                        run = repository.get_run(session, handle.run_id)
                        if (
                            run is None
                            or run.state
                            not in ("running", "handing_off", "external_running")
                            or row is None
                            or row.state not in ("claimed", "running")
                        ):
                            stop_external = True
                        elif run.external_possible:
                            stop_external = run.state == "delivery_unknown" or (
                                row is not None
                                and heartbeat_now >= repository.utc(row.deadline_at)
                            )
                            if stop_external and run.state in (
                                "handing_off",
                                "external_running",
                            ):
                                claims.stop_run(
                                    session,
                                    self._owner,
                                    run_id=run.id,
                                    expected_version=run.version,
                                    state="delivery_unknown",
                                    now=heartbeat_now,
                                )
                        elif row is not None and row.state in ("claimed", "running"):
                            claims.heartbeat_attempt(
                                session,
                                handle,
                                expected_version=row.version,
                                now=heartbeat_now,
                            )
                    if stop_external:
                        stopping_attempts.add(handle.attempt_id)
                        self.workers.cancel(handle.attempt_id)
                except WorkerTerminationError:
                    logger.warning("Local engine worker stop unconfirmed.")
                except Exception:
                    if handle.attempt_id in self._pending_completions:
                        logger.warning(
                            "Local engine pending completion heartbeat rejected."
                        )
                        continue
                    try:
                        stopping_attempts.add(handle.attempt_id)
                        self.workers.cancel(handle.attempt_id)
                    except WorkerTerminationError:
                        logger.warning("Local engine worker stop unconfirmed.")
                        continue
                    try:
                        self._recover_abandoned(handle, now)
                    except Exception:
                        logger.warning("Local engine heartbeat safety stop rejected.")
            for candidate in candidates:
                try:
                    if any(
                        completion.handle.run_id == candidate.id
                        for completion in self._pending_completions.values()
                    ):
                        continue
                    if candidate.state in ("handing_off", "external_running"):
                        handles = tuple(
                            handle
                            for handle in self.workers.handles
                            if handle.run_id == candidate.id
                        )
                        expired = repository.utc(candidate.deadline_at) <= now
                        if expired or not handles:
                            self._stop(candidate.id, "delivery_unknown", now)
                            for handle in handles:
                                self.workers.cancel(handle.attempt_id)
                        continue
                    if repository.utc(candidate.deadline_at) <= now:
                        self._stop(
                            candidate.id,
                            deadline_outcome(
                                candidate.snapshot_bytes, candidate.deadline_at
                            ),
                            now,
                        )
                        continue
                    self._schedule(candidate.id, now)
                except Exception as error:
                    if isinstance(error, LifecycleError) and error.status_code in (
                        429,
                        503,
                    ):
                        logger.warning("Local engine admission backpressure.")
                        continue
                    logger.warning("Local engine candidate rejected.")
                    try:
                        self._stop(candidate.id, "failed", now)
                    except Exception:
                        logger.warning("Local engine candidate safety stop rejected.")

            # Scheduling can terminalize a run after its heartbeat (for example
            # a failed non-retryable step). Stop its live siblings in this tick.
            self._stop_invalid_workers(stopping_attempts)

    def _schedule(self, run_id, now):
        submission = None
        with authorization.authorized_session(self.factory) as session:
            now = self.clock()
            run = repository.get_run(session, run_id)
            if run is None or run.state not in ("queued", "running"):
                return
            document = SnapshotDocument.model_validate_json(run.snapshot_bytes)
            if run.state == "queued":
                project_active = session.scalar(
                    select(func.count())
                    .select_from(InfraAutomationRun)
                    .where(
                        InfraAutomationRun.project_id == run.project_id,
                        InfraAutomationRun.state.in_(ACTIVE_STATES),
                    )
                )
                workflow_active = session.scalar(
                    select(func.count())
                    .select_from(InfraAutomationRun)
                    .where(
                        InfraAutomationRun.project_id == run.project_id,
                        InfraAutomationRun.workflow_id == run.workflow_id,
                        InfraAutomationRun.state.in_(ACTIVE_STATES),
                    )
                )
                if (
                    project_active >= document.policy.max_active_runs
                    or workflow_active >= self.bounds.workflow_active_runs
                ):
                    return
                run = claims.start_run(
                    session,
                    self._owner,
                    run_id=run.id,
                    expected_version=run.version,
                    now=now,
                    bounds=self.bounds,
                )
                if run is None:
                    return
            attempts = repository.list_attempts(session, run_id=run.id)
            if len(
                {row.step_id for row in attempts if row.state == "succeeded"}
            ) == len(document.definition.steps):
                run = repository.get_run(session, run.id)
                claims.finish_run(
                    session,
                    self._owner,
                    run_id=run.id,
                    expected_version=run.version,
                    state="succeeded",
                    now=now,
                )
                return
            if not self._can_submit:
                return
            for step in document.definition.steps:
                registration = self.registry.get(step.kind)
                if registration is None:
                    continue
                previous = [row for row in attempts if row.step_id == step.id]
                if previous:
                    attempt = previous[-1]
                    if attempt.state == "succeeded":
                        continue
                    if (
                        attempt.handler_id,
                        attempt.handler_version,
                        attempt.retry_safe,
                    ) != (
                        registration.handler_id,
                        registration.handler_version,
                        registration.retry_safe,
                    ):
                        run = repository.get_run(session, run.id)
                        claims.stop_run(
                            session,
                            self._owner,
                            run_id=run.id,
                            expected_version=run.version,
                            state="failed",
                            now=now,
                        )
                        return
                    if attempt.state in ("claimed", "running"):
                        if any(
                            handle.attempt_id == attempt.id
                            for handle in self.workers.handles
                        ):
                            continue
                        attempt = claims.safety_cleanup(
                            session,
                            self._owner,
                            attempt_id=attempt.id,
                            expected_version=attempt.version,
                            state="failed",
                            now=now,
                        )
                    if attempt.state in ("failed", "timed_out"):
                        if not attempt.retry_safe or attempt.attempt_number >= 3:
                            run = repository.get_run(session, run.id)
                            claims.stop_run(
                                session,
                                self._owner,
                                run_id=run.id,
                                expected_version=run.version,
                                state="failed",
                                now=now,
                            )
                            return
                        attempt = claims.prepare_retry(
                            session,
                            self._owner,
                            previous_attempt_id=attempt.id,
                            expected_version=attempt.version,
                            now=now,
                            bounds=self.bounds,
                        )
                    if attempt is None or attempt.state != "pending":
                        continue
                else:
                    attempt = claims.prepare_attempt(
                        session,
                        self._owner,
                        run_id=run.id,
                        step_id=step.id,
                        handler_id=registration.handler_id,
                        handler_version=registration.handler_version,
                        retry_safe=registration.retry_safe,
                        now=now,
                        bounds=self.bounds,
                    )
                    if attempt is None:
                        continue
                ensure_capacity(session, bounds=self.bounds)
                handle = claims.claim_attempt(
                    session,
                    self._owner,
                    attempt_id=attempt.id,
                    expected_version=attempt.version,
                    now=now,
                )
                if handle is None:
                    continue
                prerequisites = tuple(
                    (
                        dependency,
                        next(
                            row
                            for row in reversed(attempts)
                            if row.step_id == dependency and row.state == "succeeded"
                        ).output_json.encode(),
                    )
                    for dependency in step.depends_on
                )
                submission = (
                    handle,
                    registration,
                    WorkerInput(bytes(run.snapshot_bytes), step.id, prerequisites),
                )
                break
        # Commit the private capability and its immutable binding before spawning.
        if submission is not None:
            try:
                self.workers.submit(*submission)
            except Exception:
                self._stop(run_id, "failed", now)
                logger.warning("Local engine worker start failed.")

    def close(self):
        self._stopping = True
        with self._lock:
            if not self.registry:
                return
            handles = self.workers.handles
            self.workers.close()
            if self._owner is not None:
                now = self.clock()
                for completion in tuple(self._pending_completions.values()):
                    try:
                        self._complete(completion, now)
                    except Exception:
                        logger.warning("Local engine shutdown completion rejected.")
                for handle in handles:
                    try:
                        self._stop(handle.run_id, "failed", now)
                    except Exception:
                        logger.warning("Local engine shutdown stop rejected.")
                try:
                    self._operation(
                        claims.release_coordinator,
                        self._owner,
                        project_id=self._scope[0],
                        workspace_id=self._scope[1],
                        now=now,
                    )
                except Exception:
                    logger.warning("Local engine ownership release rejected.")
                self._owner = None
            self._pending_completions.clear()

    async def start(self):
        if self._task is None and self.registry:
            self._stopping = False
            self._task = asyncio.create_task(self._loop())

    async def _loop(self):
        while not self._stopping:
            try:
                await asyncio.to_thread(self.tick)
            except Exception:
                logger.warning("Local engine scheduler tick failed.")
            await asyncio.sleep(0.25)

    async def stop(self):
        self._stopping = True
        if self._task is not None:
            await self._task
            self._task = None
        await asyncio.to_thread(self.close)
