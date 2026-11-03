"""One bounded live adapter probe in the disposable Actions consumer only.

Synthetic binding data is a transport fixture, never a production approval.
Credentials are explicitly passed to the adapter and never serialized.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

from infra_automation.contracts import SAFE_INTEGER
from infra_automation.decisions import DecisionBinding
from infra_automation.handoff import DeliveryEnvelope
from infra_automation.receiver_protocol import (
    ReceiverMessage,
    receiver_binding_digest,
    receiver_binding_from_decision,
    receiver_message_bytes,
)
from infra_automation.target_transport import PinnedGithubTransport
from infra_automation.targets import (
    TargetDefinition,
    TargetSnapshot,
    semantic_payload,
)
from integrations.github.infra_automation_adapter import GithubInfraAutomationAdapter

SANDBOX = "deploywhisper/receiver-smoke-consumer"
WORKFLOW = "receiver.yml"
REF = "main"
CREDENTIAL_REF = "sandbox-ephemeral-dispatch"


def validated_environment(env):
    """Reject scope/ref/rerun overrides before opening a network connection."""
    if (
        env.get("GITHUB_REPOSITORY") != SANDBOX
        or env.get("GITHUB_REF") != "refs/heads/main"
        or env.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or env.get("GITHUB_RUN_ATTEMPT") != "1"
        or env.get("GITHUB_ACTIONS") != "true"
        or not re.fullmatch(r"[1-9][0-9]{0,15}", env.get("GITHUB_RUN_ID", ""))
        or not re.fullmatch(r"[0-9a-f]{40}", env.get("GITHUB_SHA", ""))
        or not re.fullmatch(r"[0-9a-f]{40}", env.get("APP_COMMIT", ""))
        or not env.get("RUNNER_TEMP")
    ):
        raise ValueError("sandbox_context_unqualified")
    token = env.get("SANDBOX_DISPATCH_TOKEN", "")
    if (
        not token
        or len(token) > 8192
        or not token.isascii()
        or any(ord(c) <= 32 or ord(c) == 127 for c in token)
    ):
        raise ValueError("sandbox_credential_unavailable")
    return token


def resolve_snapshot(transport, token, expected_sha, now):
    owner, repository = SANDBOX.split("/")

    def get(resource, selector=None):
        response = transport.get_registered(
            origin="https://api.github.com",
            owner=owner,
            repository=repository,
            resource=resource,
            selector=selector,
            token=token,
        )
        if response.status != 200:
            raise ValueError("sandbox_metadata_unavailable")
        value = json.loads(response.body)
        if type(value) is not dict:
            raise ValueError("sandbox_metadata_unqualified")
        return value

    repo = get("repository")
    workflow = get("workflow", WORKFLOW)
    branch = get("branch", REF)
    if (
        repo.get("full_name") != SANDBOX
        or workflow.get("path") != ".github/workflows/receiver.yml"
        or workflow.get("state") != "active"
        or branch.get("name") != REF
        or branch.get("protected") is not True
        or branch.get("commit", {}).get("sha") != expected_sha
        or any(
            type(value) is not int or not 1 <= value <= SAFE_INTEGER
            for value in (repo.get("id"), workflow.get("id"))
        )
    ):
        raise ValueError("sandbox_identity_unqualified")
    definition = TargetDefinition.model_validate_json(
        json.dumps(
            dict(
                canonical_target="sandbox-packet1",
                allowed_scopes=[dict(project_id=1, workspace_id=1)],
                environment="disposable",
                receiver_id="sandbox-noop",
                pipeline_repository_id=str(repo["id"]),
                pipeline_workflow_id=str(workflow["id"]),
                pipeline_workflow_revision=expected_sha,
                github_owner=owner,
                github_repository=repository,
                github_workflow=WORKFLOW,
                workflow_ref=REF,
                credential_ref=CREDENTIAL_REF,
                receiver_credential_ref="synthetic-unused",
            )
        )
    )
    return TargetSnapshot(
        definition=definition,
        target_version=1,
        target_epoch=1,
        receiver_principal_id="synthetic-unused",
        receiver_authentication_version=1,
        captured_at=now,
    )


def synthetic_envelope(snapshot, operation_id, now):
    def timestamp(value):
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")

    deadline = timestamp(now + timedelta(minutes=10))
    digest = "sha256:" + "a" * 64
    # Deliberately separate analyzed source identity from the receiver workflow SHA.
    source_sha = (
        "1" * 40
        if snapshot.definition.pipeline_workflow_revision != "1" * 40
        else "2" * 40
    )
    target = snapshot.definition
    value = dict(
        authorization_kind="exact_plan",
        workflow_id="synthetic-workflow",
        revision_id="synthetic-revision",
        workflow_revision_digest=digest,
        input_digest=digest,
        provenance=dict(
            authorization_kind="exact_plan",
            source=dict(
                kind="collected",
                repository_id="synthetic-source-repository",
                commit_sha=source_sha,
                collector_id="synthetic-collector",
                profile_digest=digest,
                screened_transport_digest=digest,
                redaction_version=1,
                collected_at=timestamp(now),
                source_deadline=deadline,
            ),
            custody=dict(
                handle="synthetic-no-custody",
                raw_local_digest=digest,
                expires_at=deadline,
            ),
        ),
        project_id=1,
        workspace_id=1,
        environment=target.environment,
        canonical_target=target.canonical_target,
        receiver_id=target.receiver_id,
        pipeline_repository_id=target.pipeline_repository_id,
        pipeline_workflow_id=target.pipeline_workflow_id,
        pipeline_workflow_revision=target.pipeline_workflow_revision,
        report_id=1,
        report_schema_version="v2",
        report_bytes_digest=digest,
        policy_version=1,
        policy_result="passed",
        policy_digest=digest,
        unit_waves_digest=digest,
        screened_artifact_digests=[digest],
        redaction_version=1,
        payload_digest=digest,
        evidence_deadline=deadline,
        approval_deadline=deadline,
        authorization_epoch=1,
        restore_epoch=1,
    )
    decision = DecisionBinding.model_validate_json(json.dumps(value))
    payload = semantic_payload(decision, snapshot)
    decision = decision.model_copy(
        update={"payload_digest": "sha256:" + hashlib.sha256(payload).hexdigest()}
    )
    binding = receiver_binding_from_decision(decision)
    message = ReceiverMessage(
        operation="consume",
        operation_id=operation_id,
        audience="receiver-operation-v1",
        binding=binding,
        binding_digest=receiver_binding_digest(binding),
        sequence=1,
        state="consumed",
    )
    return DeliveryEnvelope(
        operation_id=operation_id,
        payload_bytes=payload,
        message_bytes=receiver_message_bytes(message),
        grant_token="synthetic-unused-never-transmitted",
    )


def qualify(env, *, transport=None, sleep=time.sleep, monotonic=time.monotonic):
    token = validated_environment(env)
    transport = transport or PinnedGithubTransport(
        timeout=10, max_response_bytes=1048576
    )
    now = datetime.now(timezone.utc).replace(microsecond=0)
    snapshot = resolve_snapshot(
        transport, token, env["GITHUB_SHA"], now.strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    operation_id = "packet1-" + env["GITHUB_RUN_ID"]
    envelope = synthetic_envelope(snapshot, operation_id, now)
    adapter = GithubInfraAutomationAdapter(
        transport, target_resolver=lambda _: snapshot
    )
    # Exclusive marker is retained even on failure: uncertainty cannot cause resend.
    marker = Path(env["RUNNER_TEMP"]) / (operation_id + ".dispatch-attempted")
    with marker.open("x", encoding="utf-8") as handle:
        handle.write("Dispatch may have been sent. Do not retry this operation.\n")
    credentials = {CREDENTIAL_REF: token}
    accepted = adapter.dispatch(
        envelope, credentials[snapshot.definition.credential_ref]
    )
    emit(
        {"acceptance": accepted.model_dump(mode="json"), "dispatch_http_status": 200},
        env,
    )
    deadline = monotonic() + 300
    while monotonic() < deadline:
        observation = adapter.poll(snapshot, accepted, credentials[CREDENTIAL_REF])
        if observation.status == "completed":
            result = {
                "observation": observation.model_dump(mode="json"),
                "receiver_evidence": "not_established",
                "deployment_evidence": "not_established",
            }
            emit(result, env)
            return result
        sleep(5)
    raise ValueError("sandbox_observation_deadline")


def emit(value, env):
    safe_json = json.dumps(value, sort_keys=True)
    print(safe_json, flush=True)
    summary = env.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write("```json\n" + safe_json + "\n```\n")
            dto = value.get("acceptance") or value.get("observation")
            if dto:
                handle.write(
                    "[Correlated harmless Actions run](" + dto["html_url"] + ")\n\n"
                )


def main():
    try:
        qualify(os.environ)
    except Exception:
        # Transport/validation bodies, local envelopes and credential values stay private.
        print(
            "sandbox_qualification_failed; do not resend; inspect safe acceptance evidence if present",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
