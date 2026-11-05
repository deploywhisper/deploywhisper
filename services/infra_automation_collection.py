"""Authenticated collected evidence admission using the existing runner transaction."""

from __future__ import annotations

from datetime import timedelta
import json
from uuid import uuid4

from pydantic import TypeAdapter

from infra_automation import claims
from infra_automation.artifact_intake import screen_artifacts, screen_metadata
from infra_automation.collection_contracts import CollectionProfile, CollectionUpload
from infra_automation.contracts import ProfileContract, RegistryContract
from infra_automation.lifecycle import LifecycleError
from infra_automation.runner.catalog import read_protected, _unique
from infra_automation.runner.protocol import TaskScope
from models.repositories import infra_automation_runs as runs
from services import infra_automation_support as support


def configured_profiles():
    """Operator-owned allow-list, reloaded and digest checked for every admission."""
    import config

    path = config.settings.collection_profiles_path
    expected = config.settings.collection_profiles_sha256
    if not path and not expected:
        return ()
    try:
        raw = read_protected(path)
        if support.digest(raw) != expected:
            raise ValueError
        value = json.loads(raw, object_pairs_hook=_unique)
        profiles = TypeAdapter(list[CollectionProfile]).validate_python(value)
        if not 1 <= len(profiles) <= 16 or len(
            {p.profile_digest for p in profiles}
        ) != len(profiles):
            raise ValueError
        return tuple(profiles)
    except (OSError, ValueError, TypeError, RecursionError):
        raise LifecycleError(503) from None


def configured_registry():
    return RegistryContract(
        profiles=tuple(
            ProfileContract(
                digest=p.profile_digest,
                tool=p.tool,
                authorization_kinds=("advisory_request", "exact_plan"),
            )
            for p in configured_profiles()
        )
    )


def configured_requirements():
    from infra_automation.runner.claims import RunnerRequirements

    return {
        p.profile_digest: RunnerRequirements(
            tags=p.tags,
            tool=p.tool,
            profile_digest=p.profile_digest,
            runner_version=p.runner_version,
        )
        for p in configured_profiles()
    }


def parse_upload(raw, expected_digest):
    """Only complete canonical screened JSON crosses this boundary."""
    from infra_automation.runner.collector import command_digests
    from infra_automation.runner.collection_output import _sensitive

    if type(raw) is not bytes or not 1 <= len(raw) <= 131072:
        raise LifecycleError(422)
    if support.digest(raw) != expected_digest:
        raise LifecycleError(409)
    try:
        value = json.loads(raw, object_pairs_hook=_unique)
        if support.canonical(value) != raw:
            raise ValueError
        upload = CollectionUpload.model_validate(value)
        provenance = upload.provenance
        profile = next(
            (
                p
                for p in configured_profiles()
                if p.profile_digest == provenance.profile_digest
            ),
            None,
        )
        if profile is None:
            raise LifecycleError(503)
        if (provenance.tool, provenance.tool_version) != (
            profile.tool,
            profile.tool_version,
        ):
            raise LifecycleError(409)
        if (provenance.command_digest, provenance.argv_digest) != command_digests(
            profile.tool
        ):
            raise LifecycleError(409)
        files = [(item.name, item.content.encode()) for item in upload.artifacts]
        if files[0][0] != "plan.json":
            raise ValueError
        plan = json.loads(files[0][1], object_pairs_hook=_unique)
        support.canonical(plan)  # Reject NaN/Infinity even inside artifact text.
        if (
            type(plan) is not dict
            or not isinstance(plan.get("resource_changes", []), list)
            or _sensitive(plan)
            or plan.get("errored") is True
            or plan.get("complete") is False
            or plan.get("incomplete") is True
            or "format_version" not in plan
            or plan.get("terraform_version") != provenance.tool_version
        ):
            raise ValueError
        screen_artifacts(files, max_bytes=131072)
        screen_metadata(provenance.model_dump(mode="json"))
        if (
            support.digest(
                support.canonical([[name, content.decode()] for name, content in files])
            )
            != provenance.sanitized_digest
        ):
            raise LifecycleError(409)
        return upload
    except LifecycleError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise LifecycleError(422) from None


def validate_bound_upload(session, handle, scope, runner, upload, *, now):
    """Called only after live runner + task bearer checks in the same transaction."""
    from infra_automation.runner.claims import wire_deadline

    attempt = claims._attempt(session, handle, now)
    run, document = claims._run(session, handle.run_id, now)
    provenance = upload.provenance
    source = next((s for s in document.sources if s.step_id == attempt.step_id), None)
    if (
        attempt.state != "running"
        or attempt.step_kind != "admitted_collection"
        or provenance.scope.model_dump(exclude={"lease_deadline"})
        != TaskScope.model_validate(scope.model_dump()).model_dump(
            exclude={"lease_deadline"}
        )
        or provenance.scope.runner_id != runner.id
        or provenance.tool != runner.tool
        or provenance.profile_digest != runner.profile_digest
        or source is None
        or source.kind != "collected"
        or (provenance.repository_id, provenance.commit_sha, provenance.profile_digest)
        != (source.repository_id, source.commit_sha, source.profile_digest)
    ):
        raise LifecycleError(409)
    collected = wire_deadline(provenance.collected_at)
    deadline = wire_deadline(provenance.source_deadline)
    expiry = wire_deadline(provenance.custody.expires_at)
    if not (
        collected
        < wire_deadline(provenance.scope.lease_deadline)
        <= wire_deadline(scope.lease_deadline)
        and runs.utc(run.created_at).replace(microsecond=0)
        <= collected
        <= now
        < deadline
        <= expiry
        and deadline
        <= collected
        + timedelta(seconds=min(3600, document.policy.evidence_ttl_seconds))
        and expiry <= collected + timedelta(seconds=3600)
    ):
        raise LifecycleError(409)
    step = next(s for s in document.definition.steps if s.id == attempt.step_id)
    maximum = step.parameters.max_artifact_bytes
    if not isinstance(maximum, int):
        maximum = document.inputs[maximum.name]
    screen_artifacts(
        [(x.name, x.content.encode()) for x in upload.artifacts],
        max_bytes=min(maximum, document.policy.max_artifact_bytes, 131072),
    )
    return run


def finalize_upload(session, handle, scope, runner, upload, *, now):
    """Publish an immutable manifest only within successful fenced completion."""
    from models.repositories import infra_automation_reports as reports
    from models.tables import InfraAutomationArtifactManifest

    run = validate_bound_upload(session, handle, scope, runner, upload, now=now)
    payload = support.canonical([[x.name, x.content] for x in upload.artifacts])
    collection = support.canonical(upload.provenance.model_dump(mode="json"))
    if reports.get_manifest_for_step(session, run.id, handle.step_id) is not None:
        raise LifecycleError(409)
    claims._charge(session, run, len(payload) + len(collection), now)
    row = InfraAutomationArtifactManifest(
        id=uuid4().hex,
        run_id=run.id,
        step_id=handle.step_id,
        project_id=run.project_id,
        workspace_id=run.workspace_id,
        requested_by=run.requested_by,
        artifacts_bytes=payload,
        digest=support.digest(payload),
        collection_bytes=collection,
        collection_digest=support.digest(collection),
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row


def remote_only(value):
    """A collection registration is routable only through the fenced remote runner."""
    raise LifecycleError(503)
