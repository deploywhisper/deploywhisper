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


def _adapter_output(
    *,
    adapter: str,
    project_key: str | None = None,
    project_id: int | None = None,
):
    report = {
        "id": 17,
        "report_schema_version": "v2",
        "severity": "high",
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
