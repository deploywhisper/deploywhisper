"""Operator-installed exact-assignment collector bridge; never server-selected code."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import threading
import time

from infra_automation.collection_contracts import (
    CollectedArtifact,
    CollectionProvenance,
    CollectionUpload,
)
from infra_automation.receiver_custody import canonical
from infra_automation.runner.client import RunnerClientError
from infra_automation.runner.protocol import TaskScope, parse_message


_SEND_SLOTS = threading.BoundedSemaphore(8)


def _digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _utc(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


class CollectionHandler:
    """One locally authorized assignment, admitted snapshot and custody broker.

    Operators bind the exact task scope and repository to a protected source
    registration before installing this callable in RunnerClient.run. The
    server cannot supply paths, commands, credential resolvers or custody stores.
    The snapshot remains caller-owned and must be closed after this invocation.
    """

    def __init__(
        self,
        *,
        scope,
        repository_id,
        snapshot,
        runner,
        custody,
        tool,
        credential_resolver,
        evidence_ttl_seconds,
        execution_timeout_seconds,
    ):
        self.scope = TaskScope.model_validate(scope.model_dump())
        self.repository_id = repository_id
        self.snapshot = snapshot
        self.runner = runner
        self.custody = custody
        if tool not in ("opentofu", "terraform"):
            raise RunnerClientError()
        self.tool = tool
        self.credential_resolver = credential_resolver
        if (
            type(evidence_ttl_seconds) is not int
            or not 60 <= evidence_ttl_seconds <= 3600
        ):
            raise RunnerClientError()
        self.evidence_ttl_seconds = evidence_ttl_seconds
        if (
            type(execution_timeout_seconds) is not int
            or not 1 <= execution_timeout_seconds <= 600
        ):
            raise RunnerClientError()
        self.execution_timeout_seconds = execution_timeout_seconds

    def __call__(self, client, assignment):
        message = parse_message(assignment.message)
        if (
            message.scope.model_dump(exclude={"lease_deadline"})
            != self.scope.model_dump(exclude={"lease_deadline"})
            or message.profile_digest != self.runner.profile_digest
            or message.operation != "heartbeat"
        ):
            raise RunnerClientError()
        entered = time.monotonic()
        now = datetime.now(timezone.utc)
        lease = datetime.strptime(
            message.scope.lease_deadline, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        task_deadline = entered + min(
            self.execution_timeout_seconds, (lease - now).total_seconds()
        )
        if time.monotonic() >= task_deadline:
            raise RunnerClientError()
        self.snapshot.verify()
        lock = threading.Lock()
        closed = threading.Event()
        state = [message]
        started = datetime.now(timezone.utc).replace(microsecond=0)
        deadline = started + timedelta(seconds=self.evidence_ttl_seconds)
        provenance_source = {}

        def send(operation, **fields):
            # Never queue behind an outstanding operation whose response may be
            # ambiguous. Only the waiting caller may advance sequence and scope.
            if closed.is_set() or not lock.acquire(blocking=False):
                closed.set()
                raise RunnerClientError()
            try:
                if closed.is_set() or time.monotonic() >= task_deadline:
                    raise RunnerClientError()
                current = state[0]
                payload = current.model_dump(mode="json", exclude_none=True)
                for key in ("log", "upload_digest", "atomic_upload_id", "state"):
                    payload.pop(key, None)
                outgoing = parse_message(payload | {"operation": operation} | fields)
                data = {"upload_bytes": upload[0]} if operation == "upload" else {}
                if not _SEND_SLOTS.acquire(blocking=False):
                    raise RunnerClientError()
                done = threading.Event()
                response = []

                def invoke():
                    try:
                        if closed.is_set() or time.monotonic() >= task_deadline:
                            return
                        response.append(
                            client.send(outgoing, assignment.task_token, **data)
                        )
                    except Exception:
                        pass  # Ambiguous errors never expose response/credential text.
                    finally:
                        _SEND_SLOTS.release()
                        done.set()

                thread = threading.Thread(
                    target=invoke, daemon=True, name="collection-send"
                )
                try:
                    thread.start()
                except Exception:
                    _SEND_SLOTS.release()
                    raise RunnerClientError() from None
                # Heartbeats return before ExecutionRunner's own callback ceiling.
                cutoff = min(
                    task_deadline,
                    time.monotonic() + (0.4 if operation == "heartbeat" else 10),
                )
                while not done.wait(min(0.02, max(0, cutoff - time.monotonic()))):
                    if closed.is_set() or time.monotonic() >= cutoff:
                        raise RunnerClientError()
                if closed.is_set() or time.monotonic() >= cutoff or len(response) != 1:
                    raise RunnerClientError()
                result = response[0]
                state[0] = parse_message(
                    current.model_dump(mode="json", exclude_none=True)
                    | {"scope": result["scope"], "sequence": result["sequence"] + 1}
                )
                return result
            except Exception:
                closed.set()
                raise RunnerClientError() from None
            finally:
                lock.release()

        def authority():
            return send("heartbeat")["state"] in ("claimed", "running")

        def finalize(raw, screened, plan_exit, argv_digest):
            del plan_exit, argv_digest
            self.snapshot.verify()
            checksum = _digest(canonical([["plan.json", screened.decode("utf-8")]]))
            provenance_source.update(
                kind="collected",
                repository_id=self.repository_id,
                commit_sha=self.snapshot.commit,
                collector_id=self.scope.runner_id,
                profile_digest=message.profile_digest,
                screened_transport_digest=checksum,
                redaction_version=1,
                collected_at=_utc(started),
                source_deadline=_utc(deadline),
            )
            return self.custody.publish(
                secrets.token_hex(24), raw, provenance_source, _utc(deadline)
            ).model_dump(mode="json")

        upload = [b""]
        try:
            result = self.runner.execute(
                message.scope,
                "collect_plan",
                {"tool": self.tool},
                self.snapshot,
                expected_profile_digest=message.profile_digest,
                credential_resolver=self.credential_resolver,
                authority_check=authority,
                custody_finalizer=finalize,
            )
            if not result.finalizable or not result.collection:
                send("complete", state="failed")
                return
            self.snapshot.verify()
            metadata = result.collection
            custody = metadata["custody"]
            provenance = CollectionProvenance(
                scope=state[0].scope,
                repository_id=self.repository_id,
                commit_sha=self.snapshot.commit,
                profile_digest=message.profile_digest,
                tool=metadata["tool"],
                tool_version=metadata["tool_version"],
                command_digest=metadata["command_digest"],
                argv_digest=metadata["argv_digest"],
                raw_local_digest=custody["raw_local_digest"],
                sanitized_digest=provenance_source["screened_transport_digest"],
                exit_code=metadata["exit_code"],
                collected_at=_utc(started),
                source_deadline=_utc(deadline),
                custody=custody,
            )
            envelope = CollectionUpload(
                provenance=provenance,
                artifacts=[CollectedArtifact(name="plan.json", content=result.output)],
            )
            upload[0] = canonical(envelope.model_dump(mode="json"))
            identity = secrets.token_hex(24)
            send("upload", upload_digest=_digest(upload[0]), atomic_upload_id=identity)
            send("complete", state="succeeded", atomic_upload_id=identity)
        except Exception:
            # Ambiguous upload/completion is never replayed or assigned a new ID.
            raise RunnerClientError() from None
        finally:
            closed.set()
            upload[0] = b""
