"""One bounded live adapter probe in the disposable Actions consumer only.

Synthetic binding data is a transport fixture, never a production approval.
Credentials are explicitly passed to the adapter and never serialized.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

from pydantic import ValidationError

from infra_automation.contracts import SAFE_INTEGER
from infra_automation.decisions import DecisionBinding
from infra_automation.handoff import DeliveryEnvelope
from infra_automation.receiver_protocol import (
    ReceiverMessage,
    receiver_binding_digest,
    receiver_binding_from_decision,
    receiver_message_bytes,
)
from infra_automation.target_transport import PinnedGithubTransport, TransportError
from infra_automation.targets import (
    TargetDefinition,
    TargetSnapshot,
    semantic_payload,
)
from integrations.github.infra_automation_adapter import (
    GithubAdapterError,
    GithubInfraAutomationAdapter,
)

SANDBOX = "deploywhisper/receiver-smoke-consumer"
WORKFLOW = "receiver.yml"
REF = "main"
CREDENTIAL_REF = "sandbox-ephemeral-dispatch"
ERROR_CODES = frozenset(
    (
        "sandbox_context_unqualified",
        "sandbox_credential_unavailable",
        "sandbox_metadata_unavailable",
        "sandbox_metadata_unqualified",
        "sandbox_identity_unqualified",
        "sandbox_observation_deadline",
        "sandbox_preflight_flag_unqualified",
        "github_target_unqualified",
        "github_dispatch_unqualified",
        "github_poll_unqualified",
        "invalid_request",
        "destination_denied",
        "tls_unavailable",
        "redirect_denied",
        "response_too_large",
        "delivery_unknown",
        "connection_failed",
    )
)


def failure_diagnostic(error, progress):
    """Emit finite classifications only, never exception messages or input values."""
    names = {
        ValueError,
        KeyError,
        FileExistsError,
        OSError,
        TypeError,
        ValidationError,
        GithubAdapterError,
        TransportError,
    }
    name = type(error).__name__ if type(error) in names else "OtherError"
    code = "unclassified"
    if isinstance(error, (GithubAdapterError, TransportError)):
        code = error.code if error.code in ERROR_CODES else "unclassified"
    elif type(error) is ValueError and str(error) in ERROR_CODES:
        code = str(error)
    diagnostic = dict(
        stage=progress["stage"],
        exception_class=name,
        code=code,
        dispatch_may_have_sent=progress["dispatch_attempted"]
        and (error.may_have_sent if isinstance(error, GithubAdapterError) else True),
        automatic_resend=False,
    )
    if "metadata_http_status" in progress:
        diagnostic["metadata_http_status"] = progress["metadata_http_status"]
    if isinstance(error, ValidationError):
        allowed_fields = (
            set(TargetDefinition.model_fields)
            | set(TargetSnapshot.model_fields)
            | set(DecisionBinding.model_fields)
            | {
                "source",
                "custody",
                "kind",
                "repository_id",
                "commit_sha",
                "collector_id",
                "profile_digest",
                "screened_transport_digest",
                "collected_at",
                "source_deadline",
                "handle",
                "raw_local_digest",
                "expires_at",
                "operation",
                "operation_id",
                "audience",
                "binding",
                "binding_digest",
                "sequence",
                "state",
            }
        )
        allowed_types = {
            "missing",
            "extra_forbidden",
            "int_type",
            "string_type",
            "bool_type",
            "value_error",
            "literal_error",
            "greater_than_equal",
            "less_than_equal",
            "string_pattern_mismatch",
            "string_too_short",
            "string_too_long",
        }
        diagnostic["validation_errors"] = [
            dict(
                path=[
                    part if part in allowed_fields else "unknown_field"
                    for part in item["loc"]
                ],
                type=item["type"]
                if item["type"] in allowed_types
                else "validation_error",
            )
            for item in error.errors(
                include_input=False, include_context=False, include_url=False
            )[:8]
        ]
    return {"qualification_failure": diagnostic}


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


def resolve_snapshot(transport, token, expected_sha, now, progress=None):
    owner, repository = SANDBOX.split("/")

    def get(resource, selector=None):
        if progress is not None:
            progress["stage"] = "metadata_" + resource
        response = transport.get_registered(
            origin="https://api.github.com",
            owner=owner,
            repository=repository,
            resource=resource,
            selector=selector,
            token=token,
        )
        if progress is not None:
            progress["metadata_http_status"] = response.status
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
    if progress is not None:
        progress["stage"] = "target_snapshot"
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


def qualify(
    env,
    *,
    transport=None,
    sleep=time.sleep,
    monotonic=time.monotonic,
    progress=None,
    preflight_only=None,
):
    progress = progress if progress is not None else {}
    progress.update(stage="environment", dispatch_attempted=False)
    flag = env.get("SANDBOX_PREFLIGHT_ONLY", "true")
    if flag not in ("true", "false") or (
        preflight_only is not None and type(preflight_only) is not bool
    ):
        raise ValueError("sandbox_preflight_flag_unqualified")
    if preflight_only is None:
        preflight_only = flag == "true"
    token = validated_environment(env)
    transport = transport or PinnedGithubTransport(
        timeout=10, max_response_bytes=1048576
    )
    now = datetime.now(timezone.utc).replace(microsecond=0)
    snapshot = resolve_snapshot(
        transport,
        token,
        env["GITHUB_SHA"],
        now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        progress,
    )
    operation_id = "packet1-" + env["GITHUB_RUN_ID"]
    progress["stage"] = "synthetic_binding"
    envelope = synthetic_envelope(snapshot, operation_id, now)
    adapter = GithubInfraAutomationAdapter(
        transport, target_resolver=lambda _: snapshot
    )
    if preflight_only:
        progress["stage"] = "protected_revision"
        adapter.protected_revision(snapshot, token)
        result = {
            "qualification_preflight": "qualified",
            "dispatch_attempted": False,
            "validated_stages": [
                "environment",
                "metadata_repository",
                "metadata_workflow",
                "metadata_branch",
                "target_snapshot",
                "synthetic_binding",
                "protected_revision",
            ],
        }
        emit(result, env)
        return result
    # Exclusive marker is retained even on failure: uncertainty cannot cause resend.
    marker = Path(env["RUNNER_TEMP"]) / (operation_id + ".dispatch-attempted")
    progress["stage"] = "dispatch_marker"
    with marker.open("x", encoding="utf-8") as handle:
        handle.write("Dispatch may have been sent. Do not retry this operation.\n")
    credentials = {CREDENTIAL_REF: token}
    progress.update(stage="dispatch", dispatch_attempted=True)
    accepted = adapter.dispatch(
        envelope, credentials[snapshot.definition.credential_ref]
    )
    progress["stage"] = "acceptance_evidence"
    emit(
        {"acceptance": accepted.model_dump(mode="json"), "dispatch_http_status": 200},
        env,
    )
    deadline = monotonic() + 300
    progress["stage"] = "observation"
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


def main(*, preflight_only=None):
    progress = dict(stage="startup", dispatch_attempted=False)
    try:
        qualify(os.environ, progress=progress, preflight_only=preflight_only)
    except Exception as error:
        print(
            json.dumps(failure_diagnostic(error, progress), sort_keys=True), flush=True
        )
        # Transport/validation bodies, local envelopes and credential values stay private.
        print(
            "sandbox_qualification_failed; do not resend; inspect safe acceptance evidence if present",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preflight-only",
        action="store_const",
        const=True,
        default=None,
        help="Validate metadata and synthetic binding without dispatch or marker",
    )
    raise SystemExit(main(preflight_only=parser.parse_args().preflight_only))
