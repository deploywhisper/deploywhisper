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

    def test_generate_narrative_keeps_clean_fallback_when_skill_resolution_fails(
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
                side_effect=RuntimeError("skill resolution failed"),
            ),
        ):
            narrative = generate_narrative(assessment, [])

        self.assertFalse(narrative.available)
        self.assertTrue(narrative.degraded)
        self.assertEqual(narrative.source, "fallback")
        self.assertIsNone(narrative.failure_notice)
        self.assertEqual(narrative.skills_applied, [])

    def test_generate_narrative_records_skills_when_narrator_disabled(
        self,
    ) -> None:
        with (
            patch("llm.narrator.settings", SimpleNamespace(narrator_enabled=False)),
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
            narrative = generate_narrative(self._assessment(), [])

        self.assertFalse(narrative.available)
        self.assertTrue(narrative.degraded)
        self.assertEqual(narrative.source, "fallback")
        self.assertEqual(narrative.provider, "ollama")
        self.assertEqual(narrative.model, "ollama/llama3")
        self.assertEqual(narrative.skills_applied, ["terraform"])
        self.assertIn("Narrator disabled", narrative.failure_notice or "")

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

    def test_generate_narrative_falls_back_when_provider_call_times_out(self) -> None:
        def timed_out_completion(**_: object):
            raise TimeoutError("provider timed out")

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
                completion_client=timed_out_completion,
            )

        self.assertFalse(narrative.available)
        self.assertTrue(narrative.degraded)
        self.assertEqual(narrative.source, "fallback")
        self.assertEqual(
            narrative.failure_notice,
            "Narrative provider unavailable: provider timed out",
        )

    def test_generate_narrative_passes_runtime_timeout_to_provider_call(self) -> None:
        captured: dict[str, object] = {}

        def completion(**kwargs: object):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                '{"opening_sentence": "CAUTION: review the change.", '
                                '"explanation": "Security group change requires review.", '
                                '"guidance": []}'
                            )
                        )
                    )
                ]
            )

        with (
            patch(
                "llm.narrator.resolve_provider_runtime",
                return_value={
                    "provider": "openai",
                    "model": "gpt-4.1-mini",
                    "api_base": "https://api.openai.com/v1",
                    "api_key": "sk-test",
                    "local_mode": False,
                    "request_timeout_seconds": 12.5,
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
                completion_client=completion,
            )

        self.assertFalse(narrative.degraded)
        self.assertEqual(captured["request_timeout_seconds"], 12.5)

    def test_generate_narrative_falls_back_when_prompt_building_fails(self) -> None:
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
            patch(
                "llm.narrator.build_skill_context",
                side_effect=RuntimeError("skill context failed"),
            ),
        ):
            narrative = generate_narrative(
                self._assessment(),
                [],
                completion_client=lambda **_: (_ for _ in ()).throw(
                    AssertionError("provider call should not happen")
                ),
            )

        self.assertFalse(narrative.available)
        self.assertTrue(narrative.degraded)
        self.assertEqual(narrative.source, "fallback")
        self.assertEqual(narrative.provider, "openai")
        self.assertEqual(narrative.model, "gpt-4.1-mini")
        self.assertEqual(narrative.skills_applied, ["terraform"])
        self.assertNotIn(
            "Narrative provider unavailable", narrative.failure_notice or ""
        )
        self.assertIn("Narrative setup unavailable", narrative.failure_notice or "")
        self.assertIn("skill context failed", narrative.failure_notice or "")

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

    def test_generate_narrative_falls_back_when_provider_returns_invisible_text(
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
                                content='{"opening_sentence": "\\u200b", "explanation": "\\u200b", "guidance": []}'
                            )
                        )
                    ]
                ),
            )

        self.assertFalse(narrative.available)
        self.assertTrue(narrative.degraded)
        self.assertEqual(narrative.source, "fallback")
        self.assertIn("empty output", narrative.failure_notice or "")

    def test_generate_narrative_falls_back_when_provider_returns_only_combining_marks(
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
                                content='{"opening_sentence": "\\u0301", "explanation": "\\u0301", "guidance": []}'
                            )
                        )
                    ]
                ),
            )

        self.assertFalse(narrative.available)
        self.assertTrue(narrative.degraded)
        self.assertEqual(narrative.source, "fallback")
        self.assertIn("empty output", narrative.failure_notice or "")

    def test_generate_narrative_accepts_string_guidance(
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
                                content=(
                                    '{"opening_sentence": "CAUTION: review the change.", '
                                    '"explanation": "Security group change requires review.", '
                                    '"guidance": "verify ingress rules"}'
                                )
                            )
                        )
                    ]
                ),
            )

        self.assertTrue(narrative.available)
        self.assertFalse(narrative.degraded)
        self.assertEqual(narrative.source, "llm")
        self.assertEqual(narrative.guidance, ["verify ingress rules"])

    def test_generate_narrative_accepts_object_guidance(self) -> None:
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
                                content=(
                                    '{"opening_sentence": "CAUTION: review the change.", '
                                    '"explanation": "Security group change requires review.", '
                                    '"guidance": {"verify": "check ingress", "rollback": ["prepare revert"]}}'
                                )
                            )
                        )
                    ]
                ),
            )

        self.assertTrue(narrative.available)
        self.assertFalse(narrative.degraded)
        self.assertEqual(narrative.source, "llm")
        self.assertEqual(narrative.guidance, ["check ingress", "prepare revert"])

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
