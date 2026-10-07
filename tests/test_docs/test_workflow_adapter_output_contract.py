"""Documentation checks for workflow adapter output contracts."""

from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_GUIDE = REPO_ROOT / "docs" / "workflow-adapter-output-contract.md"
CI_GUIDE = REPO_ROOT / "docs" / "ci-advisory-consumption.md"


class WorkflowAdapterOutputContractDocumentationTests(unittest.TestCase):
    def test_contract_guide_documents_canonical_summary_and_adapter_metadata(
        self,
    ) -> None:
        content = CONTRACT_GUIDE.read_text(encoding="utf-8")

        expected_clauses = (
            "AdapterMetadata",
            "build_adapter_output_contract",
            "GitLab, Jenkins, Atlantis, Argo CD, Flux, chat, and policy adapters",
            "`canonical_summary.severity`",
            "`canonical_summary.json_payload.evidence_law_status`",
            "`adapter_metadata`",
            "`adapter_payload`",
            "Project scope is mandatory",
            "must not shadow canonical fields",
            "PolicyAdapterOutputContract",
            "PolicyAdapterStatus",
            "advisory`, `warn`, `soft-block`, and `hard-block`",
            "canonical_report_advisory",
            "at least one structured reason",
            "PolicyAdapterSettings",
            "project defaults",
            "integration-specific defaults",
            "reporting_default",
            "enforcement_mode",
            "/api/v1/settings/policy-adapter",
            "DELETE",
            "build_configured_policy_adapter_output",
            "build_integration_enforcement_decision",
            "/api/v1/analyses/{report_id}/policy-adapter",
            "/api/v1/analyses/{report_id}/enforcement-decision",
            "`configured_mode`, `effective_status`, `should_block`",
        )
        for expected in expected_clauses:
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

    def test_ci_guide_links_to_future_adapter_contract(self) -> None:
        content = CI_GUIDE.read_text(encoding="utf-8")

        self.assertIn("workflow-adapter-output-contract.md", content)
        self.assertTrue(CONTRACT_GUIDE.exists())
