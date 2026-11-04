"""Trusted carrier composition preserves unavailable material and live credentials."""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from infra_automation.lifecycle import LifecycleError
from services.infra_automation_receiver_composition import create_github_handoff_service
from tests.test_infra_automation.test_github_adapter import envelope_fixture


class ReceiverCompositionTests(unittest.TestCase):
    def setUp(self):
        self.snapshot, self.envelope = envelope_fixture()
        self.adapter = Mock()
        self.adapter.protected_revision.return_value = (
            self.snapshot.definition.pipeline_workflow_revision
        )
        self.material = Mock()
        self.transport = Mock()
        self.patch = patch(
            "services.infra_automation_receiver_composition.GithubInfraAutomationAdapter",
            return_value=self.adapter,
        )
        self.adapter_class = self.patch.start()
        self.addCleanup(self.patch.stop)
        self.service = create_github_handoff_service(
            decision_service=self.material, _transport=self.transport
        )

    def test_ports_share_one_adapter_without_replacing_material_authority(self):
        self.assertIs(self.service.decision_service, self.material)
        self.service.delivery_port(self.envelope, "synthetic-credential")
        self.adapter.dispatch.assert_called_once_with(
            self.envelope, "synthetic-credential"
        )
        with patch("config.handoff_credentials", return_value={"dispatch": "first"}):
            self.service.ref_port(self.snapshot)
        self.adapter.protected_revision.assert_called_once_with(self.snapshot, "first")
        acceptance = Mock()
        with patch("config.handoff_credentials", return_value={"dispatch": "rotated"}):
            self.service.observation_port(acceptance, self.snapshot)
        self.adapter.poll.assert_called_once_with(self.snapshot, acceptance, "rotated")
        self.material.assert_not_called()

    def test_missing_config_denies_before_metadata_or_poll(self):
        for port, args in (
            (self.service.ref_port, (self.snapshot,)),
            (self.service.observation_port, (Mock(), self.snapshot)),
        ):
            with patch("config.handoff_credentials", return_value={}):
                with self.assertRaises(LifecycleError) as caught:
                    port(*args)
            self.assertEqual(caught.exception.status_code, 503)
        self.adapter.protected_revision.assert_not_called()
        self.adapter.poll.assert_not_called()

    def test_resolver_reads_captured_snapshot_and_rejects_broken_operation(self):
        resolver = self.adapter_class.call_args.kwargs["target_resolver"]
        row = SimpleNamespace(broken=False)
        with (
            patch.object(
                self.service, "_load", return_value=(row, None, None, self.snapshot)
            ) as load,
            patch(
                "services.infra_automation_receiver_composition.authorization.authorized_session",
                return_value=nullcontext("reserved-session"),
            ),
        ):
            self.assertEqual(resolver("operation-1"), self.snapshot)
            load.assert_called_once_with("reserved-session", "operation-1")
            row.broken = True
            with self.assertRaises(LifecycleError) as caught:
                resolver("operation-1")
            self.assertEqual(caught.exception.status_code, 409)
