"""Runner bindings over existing engine attempts; no independent execution engine."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated

from pydantic import Field
from sqlalchemy import select, update

from infra_automation import claims as engine
from infra_automation.artifact_intake import (
    screen_artifacts,
    screen_decoded_credentials,
)
from infra_automation.contracts import ClosedModel
from infra_automation.lifecycle import LifecycleError
from infra_automation.runner.protocol import TaskScope, parse_message
from infra_automation.state import AttemptHandle, LogChunk, OutputReference
from infra_automation.workflow_schema import Digest, Identifier
from models.repositories import infra_automation_runs as repo
from services import infra_automation_support as support
from services.content_security import redact_text


class RunnerRequirements(ClosedModel):
    tags: Annotated[list[Identifier], Field(max_length=32)]
    tool: Identifier
    profile_digest: Digest
    runner_version: Identifier


def eligible(runner, requirements):
    requirements = support.revalidate(requirements, RunnerRequirements)
    try:
        tags = json.loads(runner.tags_json)
        return (
            runner.status == "active"
            and type(tags) is list
            and all(type(tag) is str for tag in tags)
            and set(requirements.tags).issubset(tags)
            and runner.tool == requirements.tool
            and runner.profile_digest == requirements.profile_digest
            and runner.runner_version == requirements.runner_version
            and type(runner.protocol_version) is int
            and runner.protocol_version == 1
        )
    except (TypeError, ValueError):
        return False


def screened_upload(raw, expected_digest):
    if type(raw) is not bytes or not 1 <= len(raw) <= 131072:
        raise LifecycleError(422)
    if support.digest(raw) != expected_digest:
        raise LifecycleError(409)
    try:
        value = json.loads(raw.decode("utf-8"))
        if type(value) is not list or support.canonical(value) != raw:
            raise ValueError
        if any(
            type(item) is not dict
            or set(item) != {"name", "content"}
            or type(item["name"]) is not str
            or type(item["content"]) is not str
            for item in value
        ):
            raise ValueError
        # Terraform labels carry credential context that lexical assignment
        # screening cannot associate with a nested default/value. Parse source
        # without evaluating expressions; never retain parser diagnostics.
        import hcl2
        from services.content_security import _secret_key

        for item in value:
            name, content = item["name"].lower(), item["content"]
            if not name.endswith((".tf", ".tf.json")):
                continue
            try:
                document = (
                    json.loads(content)
                    if name.endswith(".json")
                    else hcl2.loads(content)
                )
            except Exception:
                raise ValueError("Invalid runner Terraform source.") from None
            if type(document) is not dict:
                raise ValueError("Invalid runner Terraform source.")
            for kind, value_key in (("variable", "default"), ("output", "value")):
                blocks = document.get(kind, {})
                blocks = blocks if type(blocks) is list else [blocks]
                for block in blocks:
                    if type(block) is not dict:
                        raise ValueError("Invalid runner Terraform declaration.")
                    for label, attributes in block.items():
                        if type(label) is not str or type(attributes) is not dict:
                            raise ValueError("Invalid runner Terraform declaration.")
                        # python-hcl2 retains quoted labels; decode escapes using
                        # JSON string rules before the existing secret-name rule.
                        label = json.loads(label) if label.startswith('"') else label
                        if value_key in attributes and (
                            _secret_key(label)
                            or (
                                "sensitive" in attributes
                                and attributes["sensitive"] is not False
                            )
                        ):
                            raise ValueError("Sensitive runner Terraform declaration.")
        screen_artifacts(
            [(item["name"], item["content"].encode("utf-8")) for item in value],
            max_bytes=131072,
        )
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise LifecycleError(422) from None
    return raw


def wire_deadline(value: str):
    """The advertised second-precision deadline is an exclusive upper bound."""
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def require_live_wire_lease(scope, now):
    if now >= wire_deadline(scope.lease_deadline):
        raise LifecycleError(409)


def scope_for(row, runner_id, document):
    return TaskScope(
        runner_id=runner_id,
        project_id=str(row.project_id),
        workspace_id=str(row.workspace_id),
        run_id=row.run_id,
        step_id=row.step_id,
        attempt=row.attempt_number,
        fence=row.fence,
        coordinator_generation=row.coordinator_generation,
        authorization_epoch=document.authority.authorization_epoch,
        restore_epoch=document.authority.restore_epoch,
        lease_deadline=support.utc(row.lease_until),
        audience="runner-task-v1",
    )


def assign(session, coordinator, *, attempt_id, runner, requirements, now=None):
    from models.tables import InfraAutomationRunnerTask

    now = engine._now(now)
    row = repo.get_attempt(session, attempt_id)
    if row is None or not eligible(runner, requirements):
        raise LifecycleError(409)
    run, document = engine._run(session, row.run_id, now, operation="claim")
    step = next((s for s in document.definition.steps if s.id == row.step_id), None)
    if (
        row.step_kind != "admitted_collection"
        or step is None
        or step.source.profile_digest != requirements.profile_digest
        or (runner.project_id, runner.workspace_id)
        != (run.project_id, run.workspace_id)
        or session.get(InfraAutomationRunnerTask, attempt_id) is not None
    ):
        raise LifecycleError(409)
    handle = engine.claim_attempt(
        session,
        coordinator,
        attempt_id=attempt_id,
        expected_version=row.version,
        now=now,
    )
    if handle is None:
        raise LifecycleError(409)
    session.add(
        InfraAutomationRunnerTask(
            attempt_id=attempt_id,
            runner_id=runner.id,
            credential_generation=runner.generation,
            profile_digest=requirements.profile_digest,
            sequence=0,
            created_at=now,
        )
    )
    session.flush()
    row = repo.get_attempt(session, attempt_id)
    scope = scope_for(row, runner.id, document)
    require_live_wire_lease(scope, now)
    return {
        "scope": scope.model_dump(),
        "profile_digest": requirements.profile_digest,
        "capabilities": ["screened-collection-v1"],
        "task_token": handle.owner_secret,
    }


def _secret_free(value, task_token, runner_token):
    # This is an additional credential boundary, not a general secret detector.
    # Prefix denial also protects other/rotated enrollment and runner bearers.
    forbidden = tuple(
        secret
        for secret in ("enroll-v1-", "runner-v1-", task_token, runner_token)
        if type(secret) is str and secret
    )
    if redact_text(value, sensitive_values=forbidden) != value:
        raise LifecycleError(422)


def _collection_secret_free(raw, collected, retained_logs, task_token, runner_token):
    """Recheck both staged and fresh artifacts with the current bearer corpus."""
    forbidden = tuple(
        secret
        for secret in ("enroll-v1-", "runner-v1-", task_token, runner_token)
        if type(secret) is str and secret
    )
    _secret_free(raw.decode("utf-8"), task_token, runner_token)
    screen_decoded_credentials(
        collected.provenance.model_dump(mode="json"), sensitive_values=forbidden
    )
    for artifact in collected.artifacts:
        _secret_free(
            retained_logs + artifact.name + artifact.content, task_token, runner_token
        )
        screen_decoded_credentials(
            json.loads(artifact.content), sensitive_values=forbidden
        )


def operate(
    session,
    message,
    runner,
    task_token,
    *,
    upload_bytes=None,
    runner_token=None,
    now=None,
):
    from models.tables import InfraAutomationRunnerTask, InfraAutomationAttempt

    supplied_now = now
    try:
        message = parse_message(message)
    except (ValueError, TypeError):
        raise LifecycleError(422) from None
    # Deserialization is untrusted work and may outlive the caller's earlier
    # credential check. Production clocks are sampled again inside this transaction.
    from services.infra_automation_runners import validate_runner

    now = engine._now(supplied_now)
    validate_runner(session, runner, now=now)
    scope = message.scope
    if scope.runner_id != runner.id or (scope.project_id, scope.workspace_id) != (
        str(runner.project_id),
        str(runner.workspace_id),
    ):
        raise LifecycleError(403)
    row = session.scalar(
        select(InfraAutomationAttempt)
        .where(
            InfraAutomationAttempt.run_id == scope.run_id,
            InfraAutomationAttempt.step_id == scope.step_id,
            InfraAutomationAttempt.attempt_number == scope.attempt,
        )
        .execution_options(populate_existing=True)
    )
    binding = (
        session.get(InfraAutomationRunnerTask, row.id, populate_existing=True)
        if row
        else None
    )
    if (
        row is None
        or binding is None
        or binding.runner_id != runner.id
        or binding.credential_generation != runner.generation
        or binding.profile_digest != message.profile_digest
        or message.sequence != binding.sequence + 1
    ):
        raise LifecycleError(409)
    run, document = engine._run(session, row.run_id, now)
    if scope != scope_for(row, runner.id, document):
        raise LifecycleError(409)
    require_live_wire_lease(scope, now)
    handle = AttemptHandle(
        row.owner_id,
        task_token,
        scope.coordinator_generation,
        row.project_id,
        row.workspace_id,
        row.requested_by,
        row.run_id,
        row.step_id,
        row.id,
        row.attempt_number,
        scope.fence,
        scope.authorization_epoch,
        scope.restore_epoch,
    )

    def live_authority():
        timestamp = engine._now(supplied_now)
        require_live_wire_lease(scope, timestamp)
        validate_runner(session, runner, now=timestamp)
        coordinator = engine._coordinator(
            session, handle, timestamp, allow_attempt=True
        )
        attempt = engine._attempt(session, handle, timestamp)
        # Authorization itself reads/parses retained state. Bracket that work
        # with a final clock read against the same reserved authority windows.
        checked_at = engine._now(supplied_now)
        require_live_wire_lease(scope, checked_at)
        if checked_at < timestamp or checked_at >= min(
            repo.utc(runner.credential_expires_at).replace(microsecond=0),
            repo.utc(coordinator.lease_until),
            repo.utc(attempt.lease_until),
            repo.utc(attempt.deadline_at),
            repo.utc(run.deadline_at),
        ):
            raise LifecycleError(409)
        return checked_at

    live_authority()
    if upload_bytes is not None and message.operation != "upload":
        raise LifecycleError(422)
    retained_logs = "".join(item["text"] for item in json.loads(row.logs_json))
    _secret_free(retained_logs + (message.log or ""), task_token, runner_token)
    _secret_free(
        support.canonical(message.model_dump()).decode("utf-8"),
        task_token,
        runner_token,
    )
    before = repo._binding_digest(row)
    with repo._atomic(session):
        now = live_authority()
        changed = session.execute(
            update(InfraAutomationRunnerTask)
            .where(
                InfraAutomationRunnerTask.attempt_id == row.id,
                InfraAutomationRunnerTask.sequence == binding.sequence,
            )
            .values(sequence=message.sequence)
        )
        if changed.rowcount != 1:
            raise LifecycleError(409)
        if message.operation == "claim":
            now = live_authority()
            row = engine.start_attempt(
                session, handle, expected_version=row.version, now=now
            )
        elif message.operation == "heartbeat":
            now = live_authority()
            row = engine.heartbeat_attempt(
                session, handle, expected_version=row.version, now=now
            )
        elif message.operation == "log":
            now = live_authority()
            row = engine.append_log(
                session,
                handle,
                expected_version=row.version,
                chunk=LogChunk(sequence=row.last_log_sequence + 1, text=message.log),
                now=now,
            )
        elif message.operation == "upload":
            if binding.upload_id is not None:
                raise LifecycleError(409)
            from services import infra_automation_collection as collection

            collected = None
            if type(upload_bytes) is bytes and upload_bytes.startswith(b"{"):
                collected = collection.parse_upload(upload_bytes, message.upload_digest)
                collection.validate_bound_upload(
                    session, handle, scope, runner, collected, now=live_authority()
                )
                raw = upload_bytes
            else:
                # Collection attempts cannot manufacture success from an unbound
                # legacy artifact list; every upload needs authenticated provenance.
                raise LifecycleError(422)
            _collection_secret_free(
                raw, collected, retained_logs, task_token, runner_token
            )
            # Screening/parsing can consume lease time. Recheck the current
            # credential, coordinator and attempt before retaining any bytes.
            now = live_authority()
            engine._charge(
                session, run, len(raw) + len(message.atomic_upload_id) + 128, now
            )
            binding.upload_id, binding.upload_digest, binding.upload_bytes = (
                message.atomic_upload_id,
                message.upload_digest,
                raw,
            )
            session.flush()
            now = live_authority()
            row = engine.register_upload(
                session,
                handle,
                expected_version=row.version,
                reference=OutputReference(
                    kind="screened_artifacts",
                    reference=message.atomic_upload_id,
                    digest=message.upload_digest,
                ),
                now=now,
            )
        elif message.operation == "complete":
            if message.state == "failed":
                if (
                    message.atomic_upload_id is not None
                    and message.atomic_upload_id != binding.upload_id
                ):
                    raise LifecycleError(409)
                binding.upload_bytes = None
                row = engine._write(
                    session,
                    row,
                    row.version,
                    {"uploads_json": "[]"},
                    "engine.attempt_upload_cleanup",
                    live_authority(),
                )
            else:
                if (
                    binding.upload_id is None
                    or binding.upload_id != message.atomic_upload_id
                    or binding.upload_bytes is None
                    or support.digest(binding.upload_bytes) != binding.upload_digest
                ):
                    raise LifecycleError(409)
                output = OutputReference(
                    kind="screened_artifacts",
                    reference=binding.upload_id,
                    digest=binding.upload_digest,
                )
                if not binding.upload_bytes.startswith(b"{"):
                    raise LifecycleError(422)
                if binding.upload_bytes.startswith(b"{"):
                    from services import infra_automation_collection as collection

                    collected = collection.parse_upload(
                        binding.upload_bytes, binding.upload_digest
                    )
                    _collection_secret_free(
                        binding.upload_bytes,
                        collected,
                        retained_logs,
                        task_token,
                        runner_token,
                    )
                    manifest = collection.finalize_upload(
                        session, handle, scope, runner, collected, now=live_authority()
                    )
                    output = OutputReference(
                        kind="screened_artifacts",
                        reference=manifest.id,
                        digest=manifest.digest,
                    )
                    row = engine.register_upload(
                        session,
                        handle,
                        expected_version=row.version,
                        reference=output,
                        now=live_authority(),
                    )
                    binding.upload_bytes = None
                row = engine.commit_output(
                    session,
                    handle,
                    expected_version=row.version,
                    output=output,
                    now=live_authority(),
                )
            row = engine.complete_attempt(
                session,
                handle,
                expected_version=row.version,
                state=message.state,
                now=live_authority(),
            )
        now = live_authority()
        repo.append_audit(
            session,
            project_id=row.project_id,
            workspace_id=row.workspace_id,
            actor_principal_id=runner.id,
            actor_type="runner",
            actor_role="runner",
            event_type="runner." + message.operation,
            target_id=row.id,
            reason="Authenticated fenced runner operation.",
            before_digest=before,
            after_digest=repo._binding_digest(row),
            now=now,
        )
        result = {
            "scope": scope_for(row, runner.id, document).model_dump(),
            "sequence": message.sequence,
            "state": row.state,
        }
        # Engine helpers may screen logs or retain output after their own initial
        # guard. Expiry during any helper/audit/projection rolls the whole savepoint
        # back, including sequence, evidence, quota accounting and audit rows.
        live_authority()
        return result
