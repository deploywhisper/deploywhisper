"""Registered GitHub metadata is evidence; dispatch acceptance is not success."""

from __future__ import annotations

from dataclasses import replace
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, Mock, patch

from infra_automation.decisions import DecisionBinding
from infra_automation.github_contracts import DispatchAcceptance, GithubRunObservation
from infra_automation.handoff import DeliveryEnvelope
from infra_automation.receiver_protocol import (
    ReceiverMessage,
    receiver_binding_digest,
    receiver_binding_from_decision,
    receiver_message_bytes,
)
from infra_automation.target_transport import DispatchResponse, TransportError
from infra_automation.targets import (
    TargetDefinition,
    TargetSnapshot,
    canonical,
    semantic_payload,
)
from integrations.github.infra_automation_adapter import (
    GithubAdapterError,
    GithubInfraAutomationAdapter,
)


SHA = "a" * 40
OTHER_SHA = "b" * 40
SECRET = "synthetic-dispatch-secret"
GRANT = "synthetic-grant-never-in-github"
FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures/infra_automation/qualification/16_0/contracts/valid.json"
)


def envelope_fixture():
    value = copy.deepcopy(json.loads(FIXTURE.read_text())["receiver"][0]["binding"])
    value.update(
        project_id=100,
        workspace_id=200,
        revision_id="revision-1",
        pipeline_repository_id="12",
        pipeline_workflow_id="34",
        pipeline_workflow_revision=SHA,
    )
    decision = DecisionBinding.model_validate_json(json.dumps(value))
    target = TargetDefinition.model_validate_json(
        json.dumps(
            dict(
                canonical_target=decision.canonical_target,
                allowed_scopes=[dict(project_id=100, workspace_id=200)],
                environment=decision.environment,
                receiver_id=decision.receiver_id,
                pipeline_repository_id="12",
                pipeline_workflow_id="34",
                pipeline_workflow_revision=SHA,
                github_owner="owner",
                github_repository="repo",
                github_workflow="deploy.yml",
                workflow_ref="main",
                credential_ref="dispatch",
                receiver_credential_ref="receiver",
            )
        )
    )
    snapshot = TargetSnapshot(
        definition=target,
        target_version=1,
        target_epoch=1,
        receiver_principal_id="receiver",
        receiver_authentication_version=1,
        captured_at="2026-11-02T00:00:00Z",
    )
    payload = semantic_payload(decision, snapshot)
    decision = decision.model_copy(
        update={"payload_digest": "sha256:" + hashlib.sha256(payload).hexdigest()}
    )
    binding = receiver_binding_from_decision(decision)
    message = ReceiverMessage(
        operation="consume",
        operation_id="operation-1",
        audience="receiver-operation-v1",
        binding=binding,
        binding_digest=receiver_binding_digest(binding),
        sequence=1,
        state="consumed",
    )
    return snapshot, DeliveryEnvelope(
        operation_id="operation-1",
        payload_bytes=payload,
        message_bytes=receiver_message_bytes(message),
        grant_token=GRANT,
    )


class GithubAdapterTests(unittest.TestCase):
    def setUp(self):
        self.snapshot, self.envelope = envelope_fixture()
        self.transport = Mock()
        self.metadata = {
            ("repository", None): {"id": 12, "full_name": "owner/repo"},
            ("workflow", "deploy.yml"): {
                "id": 34,
                "path": ".github/workflows/deploy.yml",
                "state": "active",
            },
            ("branch", "main"): {
                "name": "main",
                "protected": True,
                "commit": {"sha": SHA},
            },
            ("tag_ref", "main"): None,
            ("run", "56"): {
                "id": 56,
                "workflow_id": 34,
                "repository": {"id": 12, "full_name": "owner/repo"},
                "head_sha": SHA,
                "head_branch": "main",
                "event": "workflow_dispatch",
                "status": "in_progress",
                "conclusion": None,
                "url": "https://api.github.com/repos/owner/repo/actions/runs/56",
                "html_url": "https://github.com/owner/repo/actions/runs/56",
            },
        }
        self.transport.get_registered.side_effect = self.get
        self.transport.post_registered.return_value = DispatchResponse(
            status=200,
            body=canonical(
                dict(
                    workflow_run_id=56,
                    run_url="https://api.github.com/repos/owner/repo/actions/runs/56",
                    html_url="https://github.com/owner/repo/actions/runs/56",
                )
            ),
        )
        self.adapter = GithubInfraAutomationAdapter(
            self.transport, target_resolver=lambda operation_id: self.snapshot
        )

    def get(self, **fields):
        value = self.metadata[(fields["resource"], fields["selector"])]
        return DispatchResponse(
            status=404 if value is None else 200,
            body=b"{}" if value is None else canonical(value),
        )

    def dispatch(self):
        return self.adapter.dispatch(self.envelope, SECRET)

    def test_internal_dto_versions_require_exact_integer_one(self):
        accepted = self.dispatch()
        observed = self.adapter.poll(self.snapshot, accepted, SECRET)
        for model, instance in (
            (DispatchAcceptance, accepted),
            (GithubRunObservation, observed),
        ):
            for version in (True, 1.0, "1", 2):
                value = {**instance.model_dump(mode="json"), "version": version}
                with (
                    self.subTest(model=model.__name__, version=version),
                    self.assertRaises(ValueError),
                ):
                    model.model_validate(value)
                with (
                    self.subTest(model=model.__name__, json_version=version),
                    self.assertRaises(ValueError),
                ):
                    model.model_validate_json(json.dumps(value))

    def test_acceptance_contains_correlated_run_and_only_two_nonsecret_inputs(self):
        accepted = self.dispatch()
        self.assertEqual(accepted.state, "accepted")
        self.assertEqual(accepted.run_id, 56)
        sent = self.transport.post_registered.call_args.kwargs
        body = json.loads(sent["payload_bytes"])
        message = json.loads(self.envelope.message_bytes)
        self.assertEqual(
            body,
            {
                "ref": "main",
                "inputs": {
                    "operation_id": "operation-1",
                    "binding_digest": message["binding_digest"],
                },
            },
        )
        self.assertEqual(sent["token"], SECRET)
        self.assertNotIn(GRANT, repr(sent))
        self.assertNotIn(SECRET, repr(accepted))
        self.assertNotEqual(
            json.loads(self.envelope.payload_bytes)["decision"]["provenance"][
                "source"
            ].get("commit_sha"),
            SHA,
        )

    def test_poll_returns_observation_without_manufacturing_receiver_success(self):
        accepted = self.dispatch()
        observation = self.adapter.poll(self.snapshot, accepted, SECRET)
        self.assertEqual(
            (observation.status, observation.conclusion), ("in_progress", None)
        )
        run = self.metadata[("run", "56")]
        run.update(status="completed", conclusion="success")
        self.assertEqual(
            self.adapter.poll(self.snapshot, accepted, SECRET).conclusion, "success"
        )
        self.assertFalse(hasattr(observation, "receiver_state"))

    def test_response_204_or_uncorrelated_acceptance_denies(self):
        for body, status in (
            ({}, 204),
            ({"workflow_run_id": True}, 200),
            (
                {
                    "workflow_run_id": 56,
                    "run_url": "https://evil.example/run",
                    "html_url": "https://github.com/owner/repo/actions/runs/56",
                },
                200,
            ),
            (
                {
                    "workflow_run_id": 56,
                    "run_url": "https://api.github.com/repos/owner/repo/actions/runs/57",
                    "html_url": "https://github.com/owner/repo/actions/runs/56",
                },
                200,
            ),
        ):
            self.transport.post_registered.return_value = DispatchResponse(
                status=status, body=canonical(body)
            )
            with (
                self.subTest(body=body, status=status),
                self.assertRaises(GithubAdapterError) as caught,
            ):
                self.dispatch()
            self.assertTrue(caught.exception.may_have_sent)

    def test_registered_identity_revision_and_protection_fail_before_post(self):
        changes = [
            (("repository", None), {"id": 13}),
            (("repository", None), {"id": "12"}),
            (("repository", None), {"full_name": "owner/other"}),
            (("workflow", "deploy.yml"), {"id": 35}),
            (("workflow", "deploy.yml"), {"state": "disabled_manually"}),
            (("workflow", "deploy.yml"), {"path": ".github/workflows/other.yml"}),
            (("branch", "main"), {"protected": False}),
            (("branch", "main"), {"commit": {"sha": OTHER_SHA}}),
        ]
        baseline = copy.deepcopy(self.metadata)
        for key, delta in changes:
            self.metadata = copy.deepcopy(baseline)
            self.metadata[key].update(delta)
            with (
                self.subTest(delta=delta),
                self.assertRaises(GithubAdapterError) as caught,
            ):
                self.dispatch()
            self.assertFalse(caught.exception.may_have_sent)
        self.transport.post_registered.assert_not_called()

    def test_ambiguous_or_absent_ref_denies(self):
        self.metadata[("tag_ref", "main")] = {
            "ref": "refs/tags/main",
            "object": {"type": "commit", "sha": SHA},
        }
        with self.assertRaises(GithubAdapterError):
            self.dispatch()
        self.metadata[("tag_ref", "main")] = None
        self.metadata[("branch", "main")] = None
        with self.assertRaises(GithubAdapterError):
            self.dispatch()
        self.transport.post_registered.assert_not_called()

    def test_exact_effective_tag_protection_and_annotated_tag_are_required(self):
        self.metadata[("branch", "main")] = None
        self.metadata[("tag_ref", "main")] = {
            "ref": "refs/tags/main",
            "object": {"type": "tag", "sha": OTHER_SHA},
        }
        self.metadata[("tag_object", OTHER_SHA)] = {
            "sha": OTHER_SHA,
            "object": {"type": "commit", "sha": SHA},
        }
        self.metadata[("rulesets", None)] = [{"id": 7}]
        rule = {
            "id": 7,
            "target": "tag",
            "enforcement": "active",
            "bypass_actors": [],
            "conditions": {"ref_name": {"include": ["refs/tags/main"], "exclude": []}},
            "rules": [{"type": "update"}, {"type": "deletion"}],
        }
        self.metadata[("ruleset", "7")] = copy.deepcopy(rule)
        self.assertEqual(self.adapter.protected_revision(self.snapshot, SECRET), SHA)
        for delta in (
            {"rules": [{"type": "update"}]},
            {"enforcement": "evaluate"},
            {"bypass_actors": [{"actor_id": 1}]},
            {"conditions": {"ref_name": {"include": ["refs/tags/m*"], "exclude": []}}},
            {
                "conditions": {
                    "ref_name": {"include": ["~ALL"], "exclude": ["refs/tags/main"]}
                }
            },
            {
                "conditions": {
                    "ref_name": {"include": ["~ALL"], "exclude": ["refs/tags/other*"]}
                }
            },
        ):
            self.metadata[("ruleset", "7")] = {**rule, **delta}
            with self.subTest(delta=delta), self.assertRaises(GithubAdapterError):
                self.adapter.protected_revision(self.snapshot, SECRET)

    def test_tag_protection_aggregates_only_qualified_applicable_rulesets(self):
        self.metadata[("branch", "main")] = None
        self.metadata[("tag_ref", "main")] = {
            "ref": "refs/tags/main",
            "object": {"type": "commit", "sha": SHA},
        }
        self.metadata[("rulesets", None)] = [{"id": 7}, {"id": 8}]
        for rule_id, kind in ((7, "update"), (8, "deletion")):
            self.metadata[("ruleset", str(rule_id))] = {
                "id": rule_id,
                "target": "tag",
                "enforcement": "active",
                "bypass_actors": [],
                "conditions": {
                    "ref_name": {"include": ["refs/tags/main"], "exclude": []}
                },
                "rules": [{"type": kind}],
            }
        baseline = copy.deepcopy(self.metadata)
        for order in ([{"id": 7}, {"id": 8}], [{"id": 8}, {"id": 7}]):
            self.metadata[("rulesets", None)] = order
            with self.subTest(order=order):
                self.assertEqual(self.dispatch().state, "accepted")

        for rule_id in (7, 8):
            for delta in (
                {"rules": []},
                {"rules": [{"type": "creation"}]},
                {"target": "branch"},
                {"enforcement": "evaluate"},
                {"enforcement": "disabled"},
                {"bypass_actors": [{"actor_id": 1}]},
                {
                    "conditions": {
                        "ref_name": {"include": ["refs/tags/other"], "exclude": []}
                    }
                },
                {
                    "conditions": {
                        "ref_name": {
                            "include": ["~ALL"],
                            "exclude": ["refs/tags/main"],
                        }
                    }
                },
                {
                    "conditions": {
                        "ref_name": {"include": ["refs/tags/m*"], "exclude": []}
                    }
                },
            ):
                self.metadata = copy.deepcopy(baseline)
                self.metadata[("ruleset", str(rule_id))].update(delta)
                self.transport.post_registered.reset_mock()
                with (
                    self.subTest(rule_id=rule_id, delta=delta),
                    self.assertRaises(GithubAdapterError) as caught,
                ):
                    self.dispatch()
                self.assertFalse(caught.exception.may_have_sent)
                self.transport.post_registered.assert_not_called()

    def test_envelope_tampering_never_opens_network(self):
        for envelope in (
            replace(self.envelope, operation_id="different"),
            replace(self.envelope, payload_bytes=self.envelope.payload_bytes + b" "),
            replace(self.envelope, message_bytes=b"{}"),
        ):
            with (
                self.subTest(envelope=envelope.operation_id),
                self.assertRaises(GithubAdapterError),
            ):
                self.adapter.dispatch(envelope, SECRET)
        self.transport.get_registered.assert_not_called()
        self.transport.post_registered.assert_not_called()

    def test_poll_validates_captured_revision_and_correlated_run_fields(self):
        accepted = self.dispatch()
        original = copy.deepcopy(self.metadata)
        for delta in (
            {"id": 57},
            {"workflow_id": 35},
            {"head_sha": OTHER_SHA},
            {"head_branch": "other"},
            {"event": "push"},
            {"repository": {"id": 13, "full_name": "owner/repo"}},
            {"url": "https://evil.example"},
            {"status": "completed", "conclusion": None},
            {"status": "in_progress", "conclusion": "success"},
        ):
            self.metadata = copy.deepcopy(original)
            self.metadata[("run", "56")].update(delta)
            with self.subTest(delta=delta), self.assertRaises(GithubAdapterError):
                self.adapter.poll(self.snapshot, accepted, SECRET)
        self.metadata = copy.deepcopy(original)
        self.metadata[("branch", "main")]["commit"]["sha"] = OTHER_SHA
        self.assertEqual(
            self.adapter.poll(self.snapshot, accepted, SECRET).workflow_revision, SHA
        )
        self.metadata[("branch", "main")]["protected"] = False
        self.metadata[("workflow", "deploy.yml")]["state"] = "disabled_manually"
        revoked = self.snapshot.model_copy(
            update={
                "definition": self.snapshot.definition.model_copy(
                    update={"enabled": False}
                )
            }
        )
        self.assertEqual(
            self.adapter.poll(revoked, accepted, SECRET).workflow_revision, SHA
        )
        with self.assertRaises(GithubAdapterError):
            self.adapter.protected_revision(revoked, SECRET)

    def test_metadata_get_failure_never_implies_dispatch_may_have_sent(self):
        self.transport.get_registered.side_effect = TransportError(
            "delivery_unknown", may_have_sent=True
        )
        with self.assertRaises(GithubAdapterError) as caught:
            self.dispatch()
        self.assertFalse(caught.exception.may_have_sent)
        self.transport.post_registered.assert_not_called()

    def test_post_failure_retains_delivery_uncertainty_without_secrets(self):
        for may_have_sent in (False, True):
            self.transport.post_registered.side_effect = TransportError(
                "delivery_unknown", may_have_sent=may_have_sent
            )
            with (
                self.subTest(sent=may_have_sent),
                self.assertRaises(GithubAdapterError) as caught,
            ):
                self.dispatch()
            self.assertEqual(caught.exception.may_have_sent, may_have_sent)
            self.assertNotIn(SECRET, repr(caught.exception))
            self.assertNotIn(GRANT, str(caught.exception))

    def test_legacy_api_version_remains_separate(self):
        from integrations.github import app_service

        self.dispatch()
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"{}"
        opener = Mock()
        opener.open.return_value = response
        with patch.object(app_service.request, "build_opener", return_value=opener):
            self.assertEqual(
                app_service._github_api_request(
                    "https://api.github.com/repos/owner/repo",
                    token=SECRET,
                    method="GET",
                    body=None,
                ),
                b"{}",
            )
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header("X-github-api-version"), "2022-11-28")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + SECRET)

    def test_missing_web_origin_mapping_denies_before_dispatch(self):
        self.adapter.web_origins.clear()
        with self.assertRaises(GithubAdapterError) as caught:
            self.dispatch()
        self.assertFalse(caught.exception.may_have_sent)
        self.transport.post_registered.assert_not_called()

    def test_malformed_or_unbounded_metadata_and_acceptance_are_screened(self):
        for raw in (
            b'{"workflow_run_id":56,"workflow_run_id":57}',
            b'{"workflow_run_id":NaN}',
            b"\xff",
            b"[" * 18 + b"null" + b"]" * 18,
            b" " * (1048576 + 1),
        ):
            self.transport.post_registered.return_value = DispatchResponse(
                status=200, body=raw
            )
            with (
                self.subTest(length=len(raw)),
                self.assertRaises(GithubAdapterError) as caught,
            ):
                self.dispatch()
            self.assertTrue(caught.exception.may_have_sent)
            self.assertIsNone(caught.exception.__cause__)
            self.assertTrue(caught.exception.__suppress_context__)


if __name__ == "__main__":
    unittest.main()
