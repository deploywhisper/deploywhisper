"""Tests for configured policy-adapter output generation."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.policy_adapter_service as policy_adapter_service_module
import services.project_service as project_service_module
import services.settings_service as settings_service_module
from services.adapter_output_contract import (
    AdapterMetadata,
    build_adapter_output_contract,
)
from services.analysis_service import build_share_summary
from services.policy_adapter_settings import PolicyAdapterStatus


class PolicyAdapterServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "policy-adapter.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        reload(settings_service_module)
        reload(policy_adapter_service_module)
        database_module.init_db()
        self.project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_generation_resolves_integration_then_project_then_built_in(self) -> None:
        adapter_output = _adapter_output(project_key="payments", adapter="jenkins")

        built_in = policy_adapter_service_module.build_configured_policy_adapter_output(
            adapter_output
        )
        settings_service_module.save_policy_adapter_settings(
            project_key="payments",
            warn_at="high",
            soft_block_at="critical",
            hard_block_at=None,
            reporting_default="advisory",
        )
        project = policy_adapter_service_module.build_configured_policy_adapter_output(
            adapter_output
        )
        settings_service_module.save_policy_adapter_settings(
            project_key="payments",
            integration="jenkins",
            warn_at="low",
            soft_block_at="medium",
            hard_block_at="high",
            reporting_default="advisory",
        )
        integration = (
            policy_adapter_service_module.build_configured_policy_adapter_output(
                adapter_output
            )
        )

        self.assertEqual(built_in.status, PolicyAdapterStatus.SOFT_BLOCK)
        self.assertEqual(built_in.applied_settings.source, "built-in")
        self.assertEqual(project.status, PolicyAdapterStatus.WARN)
        self.assertEqual(project.applied_settings.source, "project")
        self.assertEqual(integration.status, PolicyAdapterStatus.HARD_BLOCK)
        self.assertEqual(integration.applied_settings.source, "integration")
        self.assertEqual(
            integration.adapter_output.canonical_summary.model_dump(mode="json"),
            adapter_output.canonical_summary.model_dump(mode="json"),
        )

    def test_generation_resolves_and_validates_project_id_scope(self) -> None:
        settings_service_module.save_policy_adapter_settings(
            project_key="payments",
            warn_at="high",
            soft_block_at="critical",
            hard_block_at=None,
            reporting_default="advisory",
        )
        adapter_output = _adapter_output(project_id=self.project.id, adapter="jenkins")

        output = policy_adapter_service_module.build_configured_policy_adapter_output(
            adapter_output
        )

        self.assertEqual(output.status, PolicyAdapterStatus.WARN)
        self.assertEqual(output.applied_settings.project_key, "payments")
        self.assertEqual(
            output.adapter_output.adapter_metadata.project_id, self.project.id
        )

    def test_enforcement_mode_caps_without_escalating_raw_policy_status(self) -> None:
        statuses = tuple(PolicyAdapterStatus)
        status_rank = {status: rank for rank, status in enumerate(statuses)}
        severity_by_status = {
            PolicyAdapterStatus.ADVISORY: "low",
            PolicyAdapterStatus.WARN: "medium",
            PolicyAdapterStatus.SOFT_BLOCK: "high",
            PolicyAdapterStatus.HARD_BLOCK: "critical",
        }

        for raw_status in statuses:
            for mode in statuses:
                expected_status = min((raw_status, mode), key=status_rank.__getitem__)
                with self.subTest(raw_status=raw_status, mode=mode):
                    settings_service_module.save_policy_adapter_settings(
                        project_key="payments",
                        integration="jenkins",
                        enforcement_mode=mode,
                    )
                    adapter_output = _adapter_output(
                        project_key="payments",
                        adapter="jenkins",
                        severity=severity_by_status[raw_status],
                    )

                    decision = policy_adapter_service_module.build_integration_enforcement_decision(
                        adapter_output
                    )

                    self.assertEqual(decision.policy_output.status, raw_status)
                    self.assertEqual(decision.configured_mode, mode)
                    self.assertEqual(decision.effective_status, expected_status)
                    self.assertEqual(
                        decision.should_block,
                        expected_status
                        in {
                            PolicyAdapterStatus.SOFT_BLOCK,
                            PolicyAdapterStatus.HARD_BLOCK,
                        },
                    )
                    self.assertTrue(decision.policy_output.canonical_report_advisory)
                    self.assertFalse(
                        decision.policy_output.adapter_output.canonical_summary.should_block
                    )

    def test_enforcement_decision_uses_advisory_built_in_default(self) -> None:
        decision = policy_adapter_service_module.build_integration_enforcement_decision(
            _adapter_output(
                project_key="payments",
                adapter="future-integration",
                severity="critical",
            )
        )

        self.assertEqual(decision.policy_output.applied_settings.source, "built-in")
        self.assertEqual(decision.policy_output.status, PolicyAdapterStatus.HARD_BLOCK)
        self.assertEqual(decision.configured_mode, PolicyAdapterStatus.ADVISORY)
        self.assertEqual(decision.effective_status, PolicyAdapterStatus.ADVISORY)
        self.assertFalse(decision.should_block)


def _adapter_output(
    *,
    adapter: str,
    project_key: str | None = None,
    project_id: int | None = None,
    severity: str = "high",
):
    report = {
        "id": 17,
        "report_schema_version": "v2",
        "severity": severity,
        "recommendation": "caution",
        "top_risk": "Terraform opened database ingress.",
        "narrative_opening": "CAUTION: review database ingress.",
        "narrative_available": True,
        "warnings": [],
        "findings": [],
        "evidence_items": [],
        "blast_radius": {},
        "rollback_plan": {},
        "context_completeness": {"context_score": 0.9},
    }
    return build_adapter_output_contract(
        build_share_summary(report),
        AdapterMetadata(
            adapter=adapter,
            format="workflow_decision",
            project_key=project_key,
            project_id=project_id,
        ),
    )
