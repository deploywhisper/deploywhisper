"""Regression tests for narrative fallback behavior."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from analysis.risk_scorer import RiskAssessment, RiskContributor
from llm.narrator import generate_narrative


class NarratorTests(unittest.TestCase):
    def _assessment(self) -> RiskAssessment:
        return RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Terraform security group change requires review.",
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=12,
                    summary="Terraform security group change requires review.",
                    downstream_scope=2,
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )

    def test_generate_narrative_falls_back_when_provider_returns_invalid_json(
        self,
    ) -> None:
        with (
            patch(
                "llm.narrator.resolve_provider_runtime",
                return_value={
                    "provider": "openai",
                    "model": "gpt-4.1-mini",
                    "api_base": "https://api.openai.com/v1",
                    "api_key": "sk-test",
                    "local_mode": False,
                },
            ),
            patch(
                "llm.narrator.resolve_skills",
                return_value=[SimpleNamespace(name="terraform")],
            ),
            patch("llm.narrator.build_skill_context", return_value="skill context"),
            patch("llm.narrator.build_system_prompt", return_value="system prompt"),
            patch("llm.narrator.build_user_payload", return_value="{}"),
        ):
            narrative = generate_narrative(
                self._assessment(),
                [],
                completion_client=lambda **_: SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="{"))]
                ),
            )

        self.assertFalse(narrative.available)
        self.assertTrue(narrative.degraded)
        self.assertEqual(narrative.source, "fallback")
        self.assertEqual(narrative.provider, "openai")
        self.assertEqual(narrative.model, "gpt-4.1-mini")
        self.assertFalse(narrative.local_mode)
        self.assertEqual(narrative.skills_applied, ["terraform"])
        self.assertIsNotNone(narrative.failure_notice)
        self.assertIn("Narrative provider unavailable", narrative.failure_notice or "")
        self.assertIn("Expecting property name", " ".join(narrative.warnings))

    def test_generate_narrative_falls_back_when_provider_call_raises(self) -> None:
        def broken_completion(**_: object):
            raise RuntimeError("provider offline")

        with (
            patch(
                "llm.narrator.resolve_provider_runtime",
                return_value={
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-latest",
                    "api_base": "https://api.anthropic.com",
                    "api_key": "sk-test",
                    "local_mode": False,
                },
            ),
            patch(
                "llm.narrator.resolve_skills",
                return_value=[SimpleNamespace(name="terraform")],
            ),
            patch("llm.narrator.build_skill_context", return_value="skill context"),
            patch("llm.narrator.build_system_prompt", return_value="system prompt"),
            patch("llm.narrator.build_user_payload", return_value="{}"),
        ):
            narrative = generate_narrative(
                self._assessment(),
                [],
                completion_client=broken_completion,
            )

        self.assertFalse(narrative.available)
        self.assertTrue(narrative.degraded)
        self.assertEqual(narrative.source, "fallback")
        self.assertEqual(narrative.provider, "anthropic")
        self.assertEqual(narrative.model, "claude-3-5-sonnet-latest")
        self.assertEqual(
            narrative.failure_notice, "Narrative provider unavailable: provider offline"
        )
        self.assertIn(
            "Narrative provider unavailable: provider offline",
            narrative.warnings,
        )

    def test_generate_narrative_falls_back_when_provider_returns_empty_text(
        self,
    ) -> None:
        with (
            patch(
                "llm.narrator.resolve_provider_runtime",
                return_value={
                    "provider": "openai",
                    "model": "gpt-4.1-mini",
                    "api_base": "https://api.openai.com/v1",
                    "api_key": "sk-test",
                    "local_mode": False,
                },
            ),
            patch(
                "llm.narrator.resolve_skills",
                return_value=[SimpleNamespace(name="terraform")],
            ),
            patch("llm.narrator.build_skill_context", return_value="skill context"),
            patch("llm.narrator.build_system_prompt", return_value="system prompt"),
            patch("llm.narrator.build_user_payload", return_value="{}"),
        ):
            narrative = generate_narrative(
                self._assessment(),
                [],
                completion_client=lambda **_: SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content='{"opening_sentence": "", "explanation": "", "guidance": []}'
                            )
                        )
                    ]
                ),
            )

        self.assertFalse(narrative.available)
        self.assertTrue(narrative.degraded)
        self.assertEqual(narrative.source, "fallback")
        self.assertEqual(narrative.provider, "openai")
        self.assertIn("empty output", narrative.failure_notice or "")

    def test_generate_narrative_returns_deterministic_fallback_without_provider_call_when_no_contributors(
        self,
    ) -> None:
        assessment = self._assessment().model_copy(update={"contributors": []})

        with (
            patch(
                "llm.narrator.resolve_provider_runtime",
                return_value={
                    "provider": "ollama",
                    "model": "ollama/llama3",
                    "api_base": "http://localhost:11434",
                    "api_key": None,
                    "local_mode": True,
                },
            ),
            patch(
                "llm.narrator.resolve_skills",
                return_value=[SimpleNamespace(name="terraform")],
            ),
            patch(
                "llm.narrator.generate_completion_with_settings",
                side_effect=AssertionError("provider call should not happen"),
            ),
        ):
            narrative = generate_narrative(assessment, [])

        self.assertFalse(narrative.available)
        self.assertTrue(narrative.degraded)
        self.assertEqual(narrative.source, "fallback")
        self.assertEqual(narrative.provider, "ollama")
        self.assertEqual(narrative.model, "ollama/llama3")
        self.assertTrue(narrative.local_mode)
        self.assertEqual(narrative.skills_applied, ["terraform"])
        self.assertIsNone(narrative.failure_notice)
        self.assertEqual(narrative.warnings, [])


if __name__ == "__main__":
    unittest.main()
