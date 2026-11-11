"""Production policy worker registration and direct-call boundaries."""

import unittest
from types import SimpleNamespace

from services import project_service as authorization
from infra_automation.local_workers import default_registry
from services.infra_automation_policy_worker import execute_policy_step
from services.infra_automation_engine_service import _require_handlers
from infra_automation.lifecycle import LifecycleError


class ProductionPolicyWorkerTests(unittest.TestCase):
    def test_registry_installs_fixed_policy_handler_without_human_or_handoff(self):
        registry = default_registry()
        policy = registry.get("policy_evaluation")
        self.assertIsNotNone(policy)
        self.assertEqual(policy.handler_id, "policy-evaluation-v1")
        self.assertEqual(policy.output_kind, "action_binding")
        self.assertTrue(policy.retry_safe)
        self.assertIsNone(registry.get("human_decision"))
        self.assertIsNone(registry.get("registered_github_handoff"))

    def test_policy_handler_cannot_be_called_without_worker_authority(self):
        with self.assertRaises(authorization.TrustedAuthorizationError):
            execute_policy_step(object())

    def test_engine_requires_local_handlers_but_keeps_human_handoff_api_driven(self):
        registry = default_registry()
        document = SimpleNamespace(
            definition=SimpleNamespace(
                steps=[
                    SimpleNamespace(kind="uploaded_intake"),
                    SimpleNamespace(kind="shared_analysis"),
                    SimpleNamespace(kind="policy_evaluation"),
                    SimpleNamespace(kind="human_decision"),
                    SimpleNamespace(kind="registered_github_handoff"),
                ]
            )
        )
        _require_handlers(document, registry)
        document.definition.steps.append(SimpleNamespace(kind="missing-handler"))
        with self.assertRaises(LifecycleError):
            _require_handlers(document, registry)


if __name__ == "__main__":
    unittest.main()
