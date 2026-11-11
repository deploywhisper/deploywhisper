"""Authenticated outbound runner task channel and bounded ephemeral delivery."""

from __future__ import annotations

from collections import OrderedDict
from datetime import timedelta
from threading import RLock

from sqlalchemy import select

from infra_automation import claims as engine
from infra_automation.lifecycle import LifecycleError
from infra_automation.runner import claims
from models.repositories import infra_automation_runs as repo
from models.repositories import infra_automation_runners as runner_repo
from services import project_service as authorization
from services import infra_automation_support as support

# Grants are revealed once. Restart/lost delivery requires fenced engine recovery;
# credential values and private task handles are never written to disk.
_MAILBOX = OrderedDict()
_LOCK = RLock()
_MAX_PENDING = 1000


def queue_assignment(
    coordinator, attempt_id, requirements, *, now=None, clock=None, session_factory=None
):
    """Trusted coordinator port; no HTTP caller can enqueue or select task scope."""
    from models.tables import (
        InfraAutomationRunnerTask,
        InfraAutomationAttempt,
    )
    from services import infra_automation_runners as runners

    supplied_now = now

    def current_time():
        return engine._now(
            clock() if supplied_now is None and clock is not None else supplied_now
        )

    requirements = support.revalidate(requirements, claims.RunnerRequirements)
    with _LOCK:
        mailbox_now = current_time()
        for key in list(_MAILBOX):
            if _MAILBOX[key][0] <= mailbox_now:
                del _MAILBOX[key]
        if len(_MAILBOX) >= _MAX_PENDING:
            raise LifecycleError(429)
        with authorization.authorized_session(session_factory) as session:
            # BEGIN IMMEDIATE and the mailbox mutex may both wait. Production
            # authority is evaluated only after those reservations are held.
            now = current_time()
            engine._coordinator(session, coordinator, now)
            attempt = repo.get_attempt(session, attempt_id)
            if attempt is None or attempt.state != "pending":
                raise LifecycleError(409)
            rows = runner_repo.routing_candidates(
                session, attempt.project_id, attempt.workspace_id, now
            )
            busy = set(
                session.scalars(
                    select(InfraAutomationRunnerTask.runner_id)
                    .join(
                        InfraAutomationAttempt,
                        InfraAutomationAttempt.id
                        == InfraAutomationRunnerTask.attempt_id,
                    )
                    .where(InfraAutomationAttempt.state.in_(("claimed", "running")))
                ).all()
            )
            selected = None
            for row in rows:
                if row.id in busy:
                    continue
                if (
                    not claims.eligible(row, requirements)
                    or row.last_seen_at is None
                    or not now - timedelta(seconds=60)
                    <= repo.utc(row.last_seen_at)
                    <= now
                ):
                    continue
                try:
                    runners.validate_runner(session, row, now=now)
                except (LifecycleError, authorization.TrustedAuthorizationError):
                    continue
                selected = row
                break
            now = current_time()
            if selected is None:
                # Explicit finite no-runner failure is durable, not a silent local
                # fallback. The caller may submit a new run after fixing routing.
                before = repo._binding_digest(attempt)
                failed = engine.safety_cleanup(
                    session,
                    coordinator,
                    attempt_id=attempt.id,
                    expected_version=attempt.version,
                    state="failed",
                    now=now,
                )
                from services.infra_automation_engine_support import engine_actor

                actor = engine_actor(session)
                repo.append_audit(
                    session,
                    project_id=attempt.project_id,
                    workspace_id=attempt.workspace_id,
                    actor_principal_id=actor.principal_id,
                    actor_type=actor.principal_type,
                    actor_role=actor.role,
                    event_type="runner.no_eligible_runner",
                    target_id=attempt.id,
                    reason="No eligible runner; finite wait is zero seconds.",
                    before_digest=before,
                    after_digest=repo._binding_digest(failed),
                    now=now,
                )
                return None
            runners.validate_runner(session, selected, now=now)
            assignment = claims.assign(
                session,
                coordinator,
                attempt_id=attempt_id,
                runner=selected,
                requirements=requirements,
                now=now,
            )
            deadline = claims.wire_deadline(assignment["scope"]["lease_deadline"])
        _MAILBOX[attempt_id] = (deadline, selected.id, selected.generation, assignment)
        return {"runner_id": selected.id, "attempt_id": attempt_id}


def poll(credential, *, now=None):
    from services import infra_automation_runners as runners

    supplied_now = now
    with _LOCK, authorization.authorized_session() as session:
        now = engine._now(now)
        runner = runners.authenticate(session, credential, now=now)
        from infra_automation.operator_recovery import assert_effects_allowed

        assert_effects_allowed(session)
        runner.last_seen_at = now
        for key in list(_MAILBOX):
            deadline, runner_id, generation, assignment = _MAILBOX[key]
            if deadline <= now:
                del _MAILBOX[key]
                continue
            if runner_id != runner.id:
                continue
            del _MAILBOX[key]
            if generation != runner.generation:
                continue
            row = repo.get_attempt(session, key)
            if row is None or row.state != "claimed":
                continue
            run, document = engine._run(session, row.run_id, now)
            current_scope = claims.scope_for(row, runner.id, document)
            if assignment["scope"] != current_scope.model_dump():
                continue
            try:
                reveal_now = engine._now(supplied_now)
                runners.validate_runner(session, runner, now=reveal_now)
                claims.require_live_wire_lease(current_scope, reveal_now)
            except LifecycleError:
                continue
            return assignment
        return None


def operate(message, credential, task_token, *, upload_bytes=None, now=None):
    from services import infra_automation_runners as runners

    with authorization.authorized_session() as session:
        timestamp = engine._now(now)
        runner = runners.authenticate(session, credential, now=timestamp)
        result = claims.operate(
            session,
            message,
            runner,
            task_token,
            upload_bytes=upload_bytes,
            runner_token=credential.token,
            now=now,
        )
        # authenticate already recorded the request's live observation. Avoid
        # another mutation after the domain's final expiry/rollback guard.
        return result


def live_remote_attempt(session, attempt, coordinator, now):
    """Scheduler liveness: network connectivity never proves task authority."""
    from models.tables import InfraAutomationRunnerTask, InfraAutomationRunner
    from services import infra_automation_runners as runners

    binding = session.get(InfraAutomationRunnerTask, attempt.id, populate_existing=True)
    if binding is None:
        return False
    runner = session.get(
        InfraAutomationRunner, binding.runner_id, populate_existing=True
    )
    if (
        runner is None
        or binding.credential_generation != runner.generation
        or attempt.coordinator_generation != coordinator.generation
        or attempt.owner_id != coordinator.owner_id
        or attempt.lease_until is None
        or not repo.utc(attempt.last_observed_at) <= now < repo.utc(attempt.lease_until)
        or now >= repo.utc(attempt.deadline_at)
    ):
        return False
    try:
        runners.validate_runner(session, runner, now=now)
        engine._run(session, attempt.run_id, now)
    except (LifecycleError, authorization.TrustedAuthorizationError):
        return False
    return True
