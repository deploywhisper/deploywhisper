"""Explicit synthetic collected transport fixtures for authenticated runner tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
import config

from infra_automation.runner.collector import command_digests
from services.infra_automation_support import canonical, digest


def collection_bytes(case):
    manifest = canonical(
        [
            dict(
                profile_digest=case.profile,
                tool="opentofu",
                tool_version="1.13.1",
                runner_version="1.0",
                tags=["isolated"],
            )
        ]
    )
    path = Path(case.temp.name).resolve() / "synthetic-profiles.json"
    path.write_bytes(manifest)
    path.chmod(0o600)
    case.enterContext(
        patch.object(
            config,
            "settings",
            replace(
                config.settings,
                collection_profiles_path=str(path),
                collection_profiles_sha256=digest(manifest),
            ),
        )
    )
    text = '{"format_version":"1.2","terraform_version":"1.13.1","resource_changes":[]}'
    command, argv = command_digests("opentofu")
    expiry = (case.now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw = digest(b"synthetic protected plan")
    return canonical(
        dict(
            version=1,
            artifacts=[dict(name="plan.json", content=text)],
            provenance=dict(
                version=1,
                kind="collected",
                scope=case.assignment["scope"],
                repository_id="synthetic-repo",
                commit_sha="b" * 40,
                profile_digest=case.profile,
                tool="opentofu",
                tool_version="1.13.1",
                command_digest=command,
                argv_digest=argv,
                raw_local_digest=raw,
                sanitized_digest=digest(canonical([["plan.json", text]])),
                redaction_version=1,
                exit_code=0,
                collected_at=case.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                source_deadline=expiry,
                custody=dict(
                    version=1,
                    handle="synthetic-custody",
                    raw_local_digest=raw,
                    expires_at=expiry,
                ),
            ),
        )
    )
