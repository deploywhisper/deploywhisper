"""Regression tests for the seeded launch-day skills catalog."""

from __future__ import annotations

import json
import unittest

from services.skill_manifest_service import REPO_ROOT, load_skill_document
from services.skill_test_harness_service import run_skill_test_suites


LAUNCH_SKILL_IDS = {
    "helm",
    "argocd",
    "pulumi",
    "crossplane",
    "istio",
    "nginx-ingress",
    "cert-manager",
    "flux",
    "tekton",
    "opa-gatekeeper",
    "datadog-monitors",
    "prometheus-rules",
    "aws-cdk",
    "bicep",
    "pulumi-gcp",
    "pulumi-azure",
    "kustomize",
    "helmfile",
    "tanka",
    "jsonnet",
}
FEATURED_COMMUNITY_SKILL_IDS = {
    "terragrunt",
}
SUPPORTED_RUNTIME_TOOLS = {
    "terraform",
    "kubernetes",
    "ansible",
    "jenkins",
    "cloudformation",
}


class SeededCommunitySkillsTests(unittest.TestCase):
    def test_launch_catalog_contains_expected_first_party_skills(self) -> None:
        skill_paths = {path.stem for path in (REPO_ROOT / "skills").glob("*.md")}

        self.assertTrue(
            LAUNCH_SKILL_IDS.issubset(skill_paths),
            f"Missing launch skills: {sorted(LAUNCH_SKILL_IDS - skill_paths)}",
        )

        for skill_id in sorted(LAUNCH_SKILL_IDS):
            document = load_skill_document(
                REPO_ROOT / "skills" / f"{skill_id}.md",
                strict_manifest=True,
                allow_legacy_name=False,
                project_root=REPO_ROOT,
            )

            assert document.manifest is not None
            self.assertEqual(document.manifest.author, "DeployWhisper")
            self.assertEqual(
                document.manifest.test_suite_path,
                f"tests/skill-tests/{skill_id}",
            )
            self.assertIn("## Critical risk patterns", document.body)

    def test_featured_catalog_contains_real_community_skill(self) -> None:
        for skill_id in sorted(FEATURED_COMMUNITY_SKILL_IDS):
            document = load_skill_document(
                REPO_ROOT / "skills" / f"{skill_id}.md",
                strict_manifest=True,
                allow_legacy_name=False,
                project_root=REPO_ROOT,
            )

            assert document.manifest is not None
            self.assertTrue(document.manifest.featured)
            self.assertNotEqual(document.manifest.author, "DeployWhisper")
            self.assertNotEqual(
                document.manifest.maintainer or "",
                "DeployWhisper",
            )
            self.assertIn("## Critical risk patterns", document.body)

    def test_launch_catalog_suites_have_three_passing_scenarios(self) -> None:
        for skill_id in sorted(LAUNCH_SKILL_IDS):
            suite_files = list(
                (REPO_ROOT / "tests" / "skill-tests" / skill_id).glob("*.json")
            )
            self.assertGreaterEqual(
                len(suite_files),
                3,
                f"{skill_id} must ship at least 3 deterministic scenarios.",
            )
            scenario = json.loads(
                (
                    REPO_ROOT
                    / "tests"
                    / "skill-tests"
                    / skill_id
                    / "tool-selection.json"
                ).read_text(encoding="utf-8")
            )
            self.assertIn(
                scenario["assessment_tool"],
                SUPPORTED_RUNTIME_TOOLS,
                f"{skill_id} tool-selection scenario must use a runtime-supported contributor tool.",
            )

        results = run_skill_test_suites(sorted(LAUNCH_SKILL_IDS))

        self.assertEqual({result.skill_id for result in results}, LAUNCH_SKILL_IDS)
        for result in results:
            self.assertEqual(result.summary.status, "passing", result.skill_id)
            self.assertGreaterEqual(result.summary.total_scenarios, 3)

        featured_results = run_skill_test_suites(sorted(FEATURED_COMMUNITY_SKILL_IDS))

        self.assertEqual(
            {result.skill_id for result in featured_results},
            FEATURED_COMMUNITY_SKILL_IDS,
        )
        for result in featured_results:
            self.assertEqual(result.summary.status, "passing", result.skill_id)
            self.assertGreaterEqual(result.summary.total_scenarios, 3)


if __name__ == "__main__":
    unittest.main()
