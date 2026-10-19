"""Short fenced scheduler ticks; handler execution belongs to spawned workers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import threading

from sqlalchemy import func, select

from infra_automation import claims
from infra_automation.lifecycle import SnapshotDocument
from infra_automation.local_workers import DEFAULT_REGISTRY, WorkerInput
from infra_automation.state import ACTIVE_STATES, EngineBounds
from models.repositories import infra_automation_runs as repository
from models.tables import InfraAutomationRun
from services import project_service as authorization

logger = logging.getLogger(__name__)


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
            (bounds or EngineBounds()).model_dump()
        )
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._owner = None
        self._scope = None
        self._heartbeat_at = None
        self._lock = threading.Lock()
        self._task = None
        self._stopping = False

    def _operation(self, function, *args, **kwargs):
        with authorization.authorized_session(self.factory) as session:
            return function(session, *args, **kwargs)

    def _stop(self, run_id, state, now):
        with authorization.authorized_session(self.factory) as session:
            now = self.clock()
            row = repository.get_run(session, run_id)
            if row is not None and row.state in ("queued", "running"):
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
        with authorization.authorized_session(self.factory) as session:
            now = self.clock()
            attempt = repository.get_attempt(session, handle.attempt_id)
            if attempt is None or attempt.state not in ("claimed", "running"):
                return
            if completion.crashed or attempt.state == "claimed":
                claims.safety_cleanup(
                    session,
                    self._owner,
                    attempt_id=attempt.id,
                    expected_version=attempt.version,
                    state="failed",
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
            if result.outcome in ("stopped_by_gate", "rejected"):
                claims.finish_run(
                    session,
                    self._owner,
                    run_id=run.id,
                    expected_version=run.version,
                    state=result.outcome,
                    now=now,
                )
            elif result.outcome != "local_success":
                claims.stop_run(
                    session,
                    self._owner,
                    run_id=run.id,
                    expected_version=run.version,
                    state="failed",
                    now=now,
                )

    def tick(self):
        if not self.registry or self._stopping:
            return
        with self._lock:
            now = self.clock()
            with authorization.authorized_session(self.factory) as session:
                now = self.clock()
                candidates = list(
                    session.scalars(
                        select(InfraAutomationRun)
                        .where(InfraAutomationRun.state.in_(("queued", "running")))
                        .order_by(InfraAutomationRun.sequence)
                        .limit(100)
                    )
                )
                if self._owner is None:
                    if not candidates:
                        return
                    first = candidates[0]
                    self._scope = (first.project_id, first.workspace_id)
                    self._owner = claims.acquire_coordinator(
                        session,
                        project_id=self._scope[0],
                        workspace_id=self._scope[1],
                        now=now,
                    )
                    if self._owner is None:
                        return
                    self._heartbeat_at = now
                elif (now - self._heartbeat_at).total_seconds() >= 10:
                    claims.renew_coordinator(
                        session,
                        self._owner,
                        project_id=self._scope[0],
                        workspace_id=self._scope[1],
                        now=now,
                    )
                    self._heartbeat_at = now
            for completion in self.workers.poll():
                try:
                    self._complete(completion, now)
                except Exception:
                    # A stale result cannot be promoted to another attempt.
                    logger.warning("Local engine completion rejected.")
                    try:
                        self._stop(completion.handle.run_id, "failed", now)
                    except Exception:
                        logger.warning("Local engine completion safety stop rejected.")
            for handle in self.workers.handles:
                try:
                    with authorization.authorized_session(self.factory) as session:
                        heartbeat_now = self.clock()
                        row = repository.get_attempt(session, handle.attempt_id)
                        if row is not None and row.state in ("claimed", "running"):
                            claims.heartbeat_attempt(
                                session,
                                handle,
                                expected_version=row.version,
                                now=heartbeat_now,
                            )
                except Exception:
                    self.workers.cancel(handle.attempt_id)
                    try:
                        self._stop(handle.run_id, "failed", now)
                    except Exception:
                        logger.warning("Local engine heartbeat safety stop rejected.")
            for candidate in candidates:
                try:
                    if repository.utc(candidate.deadline_at) <= now:
                        self._stop(candidate.id, "timed_out", now)
                        continue
                    self._schedule(candidate.id, now)
                except Exception:
                    logger.warning("Local engine candidate rejected.")
                    try:
                        self._stop(candidate.id, "failed", now)
                    except Exception:
                        logger.warning("Local engine candidate safety stop rejected.")

    def _schedule(self, run_id, now):
        submission = None
        with authorization.authorized_session(self.factory) as session:
            now = self.clock()
            run = repository.get_run(session, run_id)
            if run is None or run.state not in ("queued", "running"):
                return
            document = SnapshotDocument.model_validate_json(run.snapshot_bytes)
            if run.state == "queued":
                if not self.workers.can_submit:
                    return
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
            if not self.workers.can_submit:
                return
            for step in document.definition.steps:
                registration = self.registry.get(step.kind)
                if registration is None or registration.output_kind is None:
                    continue
                previous = [row for row in attempts if row.step_id == step.id]
                if previous:
                    attempt = previous[-1]
                    if attempt.state != "pending" or (
                        attempt.handler_id,
                        attempt.handler_version,
                        attempt.retry_safe,
                    ) != (
                        registration.handler_id,
                        registration.handler_version,
                        registration.retry_safe,
                    ):
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
