"""Strict registry identities and noncircular approved semantic payloads."""

from __future__ import annotations

import json
import unittest

from pydantic import ValidationError

from infra_automation.targets import (
    TargetDefinition,
    TargetSnapshot,
    RegisterTargetRequest,
    semantic_payload,
    target_snapshot_bytes,
)
from infra_automation.decisions import DecisionBinding, content_digest
from tests.test_infra_automation.test_decisions import binding_payload, D


def definition_payload():
    return dict(
        canonical_target="target",
        aliases=["alias"],
        allowed_scopes=[dict(project_id=1, workspace_id=1)],
        environment="prod",
        receiver_id="receiver",
        pipeline_repository_id="pipeline-repository",
        pipeline_workflow_id="pipeline",
        pipeline_workflow_revision="a" * 40,
        github_owner="owner",
        github_repository="repository",
        github_workflow="deploy.yml",
        workflow_ref="main",
        api_origin="https://api.github.com",
        credential_ref="github",
        receiver_credential_ref="receiver",
        enabled=True,
    )


class TargetContractTests(unittest.TestCase):
    def test_registry_is_closed_strict_and_aliases_share_normalized_identity(self):
        raw = definition_payload()
        raw.update(canonical_target="TARGET", aliases=["ALIAS"])
        value = TargetDefinition.model_validate_json(json.dumps(raw))
        self.assertEqual(value.canonical_target, "target")
        self.assertEqual(value.aliases, ("alias",))
        for change in (
            {"version": True},
            {"enabled": "true"},
            {"grant": "secret"},
            {"aliases": ["one", "ONE"]},
            {"allowed_scopes": []},
            {"workflow_ref": "../other"},
            {"github_workflow": "../deploy.yml"},
        ):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                TargetDefinition.model_validate_json(
                    json.dumps({**definition_payload(), **change})
                )

    def test_registration_scope_and_cas_are_strict(self):
        raw = dict(
            project_id=1,
            workspace_id=1,
            expected_version=0,
            definition=definition_payload(),
            reason="Register exact destination",
        )
        RegisterTargetRequest.model_validate_json(json.dumps(raw))
        for key, value in (
            ("project_id", True),
            ("expected_version", -1),
            ("reason", ""),
        ):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                RegisterTargetRequest.model_validate_json(
                    json.dumps({**raw, key: value})
                )

    def test_action_payload_excludes_its_own_digest_and_postapproval_authority(self):
        snapshot = TargetSnapshot.model_validate_json(
            json.dumps(
                dict(
                    definition={
                        **definition_payload(),
                        "allowed_scopes": [{"project_id": 100, "workspace_id": 100}],
                        "environment": "test",
                        "pipeline_repository_id": "pipeline",
                        "pipeline_workflow_id": "workflow",
                    },
                    target_version=1,
                    target_epoch=1,
                    receiver_principal_id="receiver-actor",
                    receiver_authentication_version=1,
                    captured_at="2026-10-30T00:00:00Z",
                )
            )
        )
        binding = DecisionBinding.model_validate_json(json.dumps(binding_payload()))
        first = semantic_payload(binding, snapshot)
        changed = DecisionBinding.model_validate_json(
            binding.model_copy(
                update={"payload_digest": "sha256:" + "b" * 64}
            ).model_dump_json()
        )
        self.assertEqual(first, semantic_payload(changed, snapshot))
        raw = json.loads(first)
        self.assertNotIn("payload_digest", raw["decision"])
        self.assertNotIn("operation_id", raw)
        self.assertNotIn("grant", raw)
        self.assertEqual(
            raw["destination"]["target_snapshot_digest"],
            content_digest(target_snapshot_bytes(snapshot)),
        )
        self.assertNotEqual(content_digest(first), D)


if __name__ == "__main__":
    unittest.main()
