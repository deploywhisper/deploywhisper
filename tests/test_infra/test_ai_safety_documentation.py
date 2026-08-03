"""Documentation contract for safe AI-agent review workflows."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
AI_SAFETY_DOCS = {
    "review": ROOT / "docs/ai-safety/reviewing-ai-generated-iac.md",
    "agent_json": ROOT / "docs/ai-safety/agent-json-output.md",
    "mcp": ROOT / "docs/ai-safety/mcp-server.md",
    "threat_model": ROOT / "docs/security/prompt-injection-threat-model.md",
}
INTERNAL_LINKS = {
    ROOT / "docs/ai-safety/agent-api-interface.md": ("./mcp-server.md",),
    ROOT / "docs/ai-safety/agent-json-output.md": (
        "./mcp-server.md",
        "./reviewing-ai-generated-iac.md",
    ),
    ROOT / "docs/ai-safety/ai-generated-iac-review.md": (
        "./reviewing-ai-generated-iac.md",
    ),
    ROOT / "docs/ai-safety/mcp-server.md": (
        "./agent-json-output.md",
        "./reviewing-ai-generated-iac.md",
    ),
    ROOT / "docs/ai-safety/prompt-injection-testing.md": (
        "../security/prompt-injection-threat-model.md",
    ),
    ROOT / "docs/ai-safety/reviewing-ai-generated-iac.md": (
        "../security/prompt-injection-threat-model.md",
        "./agent-json-output.md",
        "./mcp-server.md",
    ),
    ROOT / "docs/security/prompt-injection-threat-model.md": (
        "../ai-safety/prompt-injection-testing.md",
    ),
}


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


class AiSafetyDocumentationTests(unittest.TestCase):
    """Keep the public AI-safety guidance complete and advisory-first."""

    def test_required_ai_safety_documents_exist(self) -> None:
        missing = [
            str(path.relative_to(ROOT))
            for path in AI_SAFETY_DOCS.values()
            if not path.is_file()
        ]

        self.assertEqual([], missing)

    def test_review_guide_covers_the_complete_safe_workflow(self) -> None:
        content = _normalized(AI_SAFETY_DOCS["review"])

        for required_text in (
            "safe invocation",
            "interpret the output",
            "human review",
            "prompt-injection",
            "forbidden auto-approval patterns",
        ):
            with self.subTest(required_text=required_text):
                self.assertIn(required_text, content)

    def test_agent_surfaces_preserve_non_approval_guardrails(self) -> None:
        for name in ("agent_json", "mcp"):
            content = _normalized(AI_SAFETY_DOCS[name])
            with self.subTest(document=name):
                self.assertIn("advisory_only", content)
                self.assertIn("deployment_approval", content)
                self.assertIn("human_decision_required", content)
                self.assertIn("operational error", content)
                self.assertIn("must not", content)

    def test_mcp_guide_documents_operation_and_bounded_response_contract(self) -> None:
        content = _normalized(AI_SAFETY_DOCS["mcp"])

        for required_text in (
            '"operation": "analysis.submit"',
            '"operation": "report.read"',
            "data.schema_version",
            "meta.interface_schema_version",
            "meta.output_limits",
            "max_string_characters",
            "max_collection_items",
            "max_findings",
            "max_evidence",
        ):
            with self.subTest(required_text=required_text):
                self.assertIn(required_text, content)

    def test_each_agent_guide_preserves_its_local_first_guardrail(self) -> None:
        requirements = {
            "review": ("http://localhost:8080", "raw iac", "stay local"),
            "agent_json": ("local-first",),
            "mcp": ("self-hosted", "http://localhost:8080", "raw iac", "stay local"),
            "threat_model": ("local-first", "raw iac", "stay local"),
        }

        for name, required_phrases in requirements.items():
            content = _normalized(AI_SAFETY_DOCS[name])
            for required_text in required_phrases:
                with self.subTest(document=name, required_text=required_text):
                    self.assertIn(required_text, content)

    def test_review_guide_protects_generated_output_and_http_versions(self) -> None:
        content = _normalized(AI_SAFETY_DOCS["review"])

        for required_text in (
            "potentially sensitive",
            "do not commit",
            "data.schema_version",
            "meta.interface_schema_version",
            "meta.operation",
        ):
            with self.subTest(required_text=required_text):
                self.assertIn(required_text, content)

    def test_threat_model_covers_untrusted_sources_and_controls(self) -> None:
        content = _normalized(AI_SAFETY_DOCS["threat_model"])

        for required_text in (
            "iac comments",
            "pull-request",
            "incident",
            "scanner",
            "documentation-like",
            "prompt isolation",
            "redaction",
            "tool",
            "credentials",
            "human",
        ):
            with self.subTest(required_text=required_text):
                self.assertIn(required_text, content)

    def test_readme_links_all_canonical_guides(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        for path in AI_SAFETY_DOCS.values():
            with self.subTest(path=path):
                self.assertIn(str(path.relative_to(ROOT)), readme)

    def test_internal_relative_links_have_expected_targets(self) -> None:
        for source, targets in INTERNAL_LINKS.items():
            content = source.read_text(encoding="utf-8")
            for target in targets:
                with self.subTest(source=source.relative_to(ROOT), target=target):
                    self.assertIn(f"]({target})", content)
                    self.assertTrue((source.parent / target).resolve().is_file())


if __name__ == "__main__":
    unittest.main()
