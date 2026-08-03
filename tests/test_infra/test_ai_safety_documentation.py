"""Documentation contract for safe AI-agent review workflows."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPRINT_STATUS = ROOT / "_bmad-output/implementation-artifacts/sprint-status.yaml"
AI_SAFETY_DOCS = {
    "review": ROOT / "docs/ai-safety/reviewing-ai-generated-iac.md",
    "agent_json": ROOT / "docs/ai-safety/agent-json-output.md",
    "mcp": ROOT / "docs/ai-safety/mcp-server.md",
    "threat_model": ROOT / "docs/security/prompt-injection-threat-model.md",
}
LEGACY_SECTION_LINKS = {
    ROOT / "docs/ai-safety/agent-api-interface.md": (
        (
            "## Submit artifacts",
            "./mcp-server.md#safe-invocation",
            "## Safe invocation",
        ),
        (
            "## Retrieve a report",
            "./mcp-server.md#safe-invocation",
            "## Safe invocation",
        ),
        (
            "## Scope and authorization",
            "./mcp-server.md#scope-and-authorization",
            "## Scope and authorization",
        ),
        (
            "## Safety requirements for consumers",
            "./mcp-server.md#errors-and-human-control",
            "## Errors and human control",
        ),
    ),
    ROOT / "docs/ai-safety/ai-generated-iac-review.md": (
        (
            "## Provenance classification",
            "./reviewing-ai-generated-iac.md#provenance-and-ai-assisted-risk-labels",
            "## Provenance and AI-assisted risk labels",
        ),
        (
            "## Risk labels",
            "./reviewing-ai-generated-iac.md#provenance-and-ai-assisted-risk-labels",
            "## Provenance and AI-assisted risk labels",
        ),
        (
            "## Review workflow",
            "./reviewing-ai-generated-iac.md#human-review-expectations",
            "## Human review expectations",
        ),
        (
            "## Current limitations",
            "./reviewing-ai-generated-iac.md#provenance-and-ai-assisted-risk-labels",
            "## Provenance and AI-assisted risk labels",
        ),
    ),
}
INTERNAL_LINKS = {
    ROOT / "README.md": (
        "docs/ai-safety/agent-json-output.md",
        "docs/ai-safety/mcp-server.md",
        "docs/ai-safety/reviewing-ai-generated-iac.md",
        "./docs/security/prompt-injection-threat-model.md",
    ),
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
    ROOT / "docs/ci-advisory-consumption.md": ("./ai-safety/mcp-server.md",),
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
            "abbreviates `data`",
            '"operation": "analysis.submit"',
            '"operation": "report.read"',
            "data.schema_version",
            "meta.interface_schema_version",
            "meta.output_limits",
            "meta.truncated",
            "max_string_characters",
            "max_collection_items",
            "max_findings",
            "max_evidence",
            "`artifact_paths` must include exactly one safe repository-relative path for each uploaded file, in the same order as the `files` values",
            '"truncated": false',
            '"truncated_fields": []',
            "human reviewer must inspect the canonical report",
        ):
            with self.subTest(required_text=required_text):
                self.assertIn(required_text, content)

        self.assertNotIn("following complete example", content)

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

    def test_internal_relative_links_have_expected_targets(self) -> None:
        for source, targets in INTERNAL_LINKS.items():
            content = source.read_text(encoding="utf-8")
            for target in targets:
                with self.subTest(source=source.relative_to(ROOT), target=target):
                    self.assertIn(f"]({target})", content)
                    self.assertTrue((source.parent / target).resolve().is_file())

    def test_compatibility_guides_preserve_legacy_section_links(self) -> None:
        for source, section_links in LEGACY_SECTION_LINKS.items():
            content = source.read_text(encoding="utf-8")
            for legacy_heading, target, canonical_heading in section_links:
                with self.subTest(source=source.name, heading=legacy_heading):
                    self.assertIn(legacy_heading, content)
                    self.assertIn(f"]({target})", content)
                    target_path = target.partition("#")[0]
                    canonical = (source.parent / target_path).read_text(
                        encoding="utf-8"
                    )
                    self.assertIn(canonical_heading, canonical)

    def test_sprint_status_update_dates_are_consistent(self) -> None:
        lines = SPRINT_STATUS.read_text(encoding="utf-8").splitlines()
        header_date = next(
            line.removeprefix("# last_updated: ")
            for line in lines
            if line.startswith("# last_updated: ")
        )
        data_date = next(
            line.removeprefix("last_updated: ")
            for line in lines
            if line.startswith("last_updated: ")
        )

        self.assertEqual(header_date, data_date)


if __name__ == "__main__":
    unittest.main()
