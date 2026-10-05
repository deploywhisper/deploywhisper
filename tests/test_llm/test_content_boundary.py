"""Regression coverage for the normalized-data provider boundary."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from analysis.risk_scorer import (
    RiskAssessment,
    RiskContributor,
    _apply_llm_scores,
    _assessment_prompt_payload,
    score_changes,
)
from llm.adapters.base import NarrativeProviderError
from llm.narrator import generate_narrative
from llm.prompts import build_user_payload
from llm.providers import (
    generate_completion_with_settings,
    validate_provider_configuration,
)
from parsers.base import UnifiedChange

TOKEN = "ghp_" + "a" * 36
OPAQUE_KEY = "configured-provider-credential"
RUNTIME = {
    "provider": "openai",
    "model": "gpt-4.1-mini",
    "api_base": "https://api.openai.com/v1",
    "api_key": OPAQUE_KEY,
    "local_mode": False,
}


def contributor() -> RiskContributor:
    return RiskContributor(
        source_file="plan.json",
        tool="terraform",
        resource_id="aws_instance.web",
        action="modify",
        contribution=20,
        summary=f"Update instance; token={TOKEN}",
        metadata={"raw_blob": "RAW-ARTIFACT-CONTENT", "custom": {"token": TOKEN}},
    )


def assessment() -> RiskAssessment:
    return RiskAssessment(
        score=20,
        severity="medium",
        recommendation="caution",
        top_risk="Update instance",
        contributors=[contributor()],
        partial_context=False,
    )


class ContentBoundaryTests(unittest.TestCase):
    def test_assessment_payload_excludes_arbitrary_metadata_and_redacts_secrets(self):
        payload = _assessment_prompt_payload([contributor()], False)
        self.assertNotIn("metadata", payload)
        self.assertNotIn("RAW-ARTIFACT-CONTENT", payload)
        self.assertNotIn(TOKEN, payload)
        self.assertIn("aws_instance.web", payload)
        self.assertIn("[REDACTED]", payload)

    def test_narrative_payload_redacts_skill_and_normalized_content(self):
        payload = build_user_payload(
            assessment(), [], skill_context=f"Review the plan; token={TOKEN}"
        )
        self.assertNotIn(TOKEN, payload)
        self.assertIn("[REDACTED]", payload)

    def test_hosted_adapters_receive_sanitized_messages_and_keep_auth_runtime(self):
        for provider in ("openai", "anthropic", "gemini", "openrouter"):
            with self.subTest(provider=provider):
                captured = {}

                def fake_completion(**kwargs):
                    captured.update(kwargs)
                    return '{"ok":true}'

                generate_completion_with_settings(
                    [{"role": "user", "content": f"{TOKEN} {OPAQUE_KEY}"}],
                    **{**RUNTIME, "provider": provider},
                    completion_client=fake_completion,
                )
                prompt = str(captured.get("messages", captured.get("contents")))
                self.assertNotIn(TOKEN, prompt)
                self.assertNotIn(OPAQUE_KEY, prompt)
                self.assertIn("[REDACTED]", prompt)
                self.assertEqual(captured["api_key"], OPAQUE_KEY)

    def test_provider_and_health_errors_do_not_echo_response_or_credentials(self):
        def broken_completion(**kwargs):
            raise RuntimeError(f"RAW-ARTIFACT-CONTENT {TOKEN} {OPAQUE_KEY}")

        for operation in (
            lambda: generate_completion_with_settings(
                [{"role": "user", "content": "{}"}],
                **RUNTIME,
                completion_client=broken_completion,
            ),
            lambda: validate_provider_configuration(
                **RUNTIME, completion_client=broken_completion
            ),
        ):
            with self.subTest(operation=operation):
                with self.assertRaises(NarrativeProviderError) as raised:
                    operation()
                message = str(raised.exception)
                self.assertNotIn("RAW-ARTIFACT-CONTENT", message)
                self.assertNotIn(TOKEN, message)
                self.assertNotIn(OPAQUE_KEY, message)
                self.assertIn("RuntimeError", message)

    def test_facade_screens_structured_json_messages_before_adapters(self):
        captured = {}
        original = json.dumps(
            {
                "raw_artifact": "RAW-ARTIFACT-CONTENT",
                "resources": [
                    {"kind": "Secret", "data": {"value": "opaque-encoded-value"}}
                ],
                "env": [{"name": "API_TOKEN", "value": "opaque-env-value"}],
                "summary": "Review the instance update.",
            }
        )

        def fake_completion(**kwargs):
            captured.update(kwargs)
            return '{"ok":true}'

        generate_completion_with_settings(
            [{"role": "user", "content": original}],
            **RUNTIME,
            completion_client=fake_completion,
        )
        outgoing = captured["messages"][0]["content"]
        self.assertNotIn("RAW-ARTIFACT-CONTENT", outgoing)
        self.assertNotIn("opaque-encoded-value", outgoing)
        self.assertNotIn("opaque-env-value", outgoing)
        self.assertEqual(json.loads(outgoing)["summary"], "Review the instance update.")

    def test_facade_preserves_benign_message_format(self):
        captured = {}
        original = '{ "summary": "Review the instance update." }'

        def fake_completion(**kwargs):
            captured.update(kwargs)
            return '{"ok":true}'

        generate_completion_with_settings(
            [{"role": "user", "content": original}],
            **RUNTIME,
            completion_client=fake_completion,
        )
        self.assertEqual(captured["messages"][0]["content"], original)

    def test_serialized_structured_redaction_never_restores_configured_key(self):
        captured = {}
        original = json.dumps(
            {
                "raw_artifact": "RAW-ARTIFACT-CONTENT",
                "source": OPAQUE_KEY,
                "summary": "Review the instance update.",
            }
        )

        def fake_completion(**kwargs):
            captured.update(kwargs)
            return '{"ok":true}'

        generate_completion_with_settings(
            [{"role": "user", "content": original}],
            **RUNTIME,
            completion_client=fake_completion,
        )
        outgoing = captured["messages"][0]["content"]
        self.assertNotIn(OPAQUE_KEY, outgoing)
        self.assertNotIn("RAW-ARTIFACT-CONTENT", outgoing)
        self.assertIn("[REDACTED]", outgoing)

    def test_sensitive_model_narrative_is_blocked_with_visible_notice(self):
        def fake_completion(**kwargs):
            return json.dumps(
                {
                    "opening_sentence": "CAUTION: review instance update.",
                    "explanation": f"Leaked {TOKEN} and {OPAQUE_KEY}",
                    "guidance": ["Review the plan."],
                }
            )

        with patch("llm.narrator.resolve_provider_runtime", return_value=RUNTIME):
            result = generate_narrative(
                assessment(), [], completion_client=fake_completion
            )
        self.assertTrue(result.degraded)
        self.assertFalse(result.available)
        self.assertIn("sensitive", result.failure_notice.lower())
        self.assertNotIn(TOKEN, result.model_dump_json())
        self.assertNotIn(OPAQUE_KEY, result.model_dump_json())

    def test_json_escaped_model_credentials_are_blocked(self):
        def fake_completion(**kwargs):
            payload = json.dumps(
                {
                    "opening_sentence": "CAUTION: review instance update.",
                    "explanation": f"Leaked {TOKEN}",
                    "guidance": [],
                }
            )
            return payload.replace("ghp_", "\\u0067hp_")

        with patch("llm.narrator.resolve_provider_runtime", return_value=RUNTIME):
            result = generate_narrative(
                assessment(), [], completion_client=fake_completion
            )
        self.assertTrue(result.degraded)
        self.assertIn("sensitive", result.failure_notice.lower())
        self.assertNotIn(TOKEN, result.model_dump_json())

    def test_sensitive_model_risk_reasoning_is_blocked(self):
        def fake_completion(**kwargs):
            return json.dumps(
                {
                    "change_scores": [
                        {
                            "source_file": "plan.json",
                            "resource_id": "aws_instance.web",
                            "severity": "high",
                            "reasoning": f"Leaked {TOKEN} and {OPAQUE_KEY}",
                        }
                    ]
                }
            )

        with patch(
            "analysis.risk_scorer.resolve_provider_runtime", return_value=RUNTIME
        ):
            results, warning, applied = _apply_llm_scores(
                [contributor()],
                partial_context=False,
                completion_client=fake_completion,
            )
        self.assertFalse(applied)
        self.assertIn("sensitive", warning.lower())
        self.assertEqual(results[0].severity, "medium")
        self.assertEqual(results[0].reasoning, "")

    def test_raw_secret_values_are_removed_from_derived_prose_in_both_prompts(self):
        secret = "opaque-application-value"
        raw_files = {
            "secret.yaml": f"kind: Secret\nstringData:\n  value: {secret}\n".encode()
        }
        captured = []

        def fake_completion(**kwargs):
            captured.append(kwargs["messages"])
            return json.dumps(
                {
                    "opening_sentence": "CAUTION: review instance update.",
                    "explanation": "Instance configuration changed.",
                    "guidance": [],
                    "change_scores": [],
                }
            )

        item = assessment()
        item.contributors[0].summary = f"Instance contains {secret}."
        with (
            patch("llm.narrator.resolve_provider_runtime", return_value=RUNTIME),
            patch(
                "analysis.risk_scorer.resolve_provider_runtime", return_value=RUNTIME
            ),
        ):
            generate_narrative(
                item, [], completion_client=fake_completion, raw_files=raw_files
            )
            score_changes(
                [
                    UnifiedChange(
                        source_file="plan.json",
                        tool="terraform",
                        resource_id="aws_instance.web",
                        action="modify",
                        summary=f"Instance contains {secret}.",
                    )
                ],
                raw_files=raw_files,
                completion_client=fake_completion,
            )
        self.assertEqual(len(captured), 2)
        for messages in captured:
            self.assertNotIn(secret, str(messages))
            self.assertIn("[REDACTED]", str(messages))

    def test_model_output_echoing_a_locally_detected_secret_is_blocked(self):
        secret = "opaque-application-value"
        raw_files = {
            "secret.yaml": f"kind: Secret\nstringData:\n  value: {secret}\n".encode()
        }

        def fake_completion(**kwargs):
            return json.dumps(
                {
                    "opening_sentence": "CAUTION: review instance update.",
                    "explanation": f"Instance contains {secret}.",
                    "guidance": [],
                }
            )

        with patch("llm.narrator.resolve_provider_runtime", return_value=RUNTIME):
            result = generate_narrative(
                assessment(), [], completion_client=fake_completion, raw_files=raw_files
            )
        self.assertTrue(result.degraded)
        self.assertIn("sensitive", result.failure_notice.lower())
        self.assertNotIn(secret, result.model_dump_json())

    def test_raw_files_are_used_for_local_skills_only(self):
        captured = {}
        raw_files = {"plan.json": b"RAW-ARTIFACT-CONTENT"}

        def fake_completion(**kwargs):
            captured.update(kwargs)
            return json.dumps(
                {
                    "opening_sentence": "CAUTION: review the instance update.",
                    "explanation": "Instance configuration changed.",
                    "guidance": [],
                }
            )

        with (
            patch("llm.narrator.resolve_provider_runtime", return_value=RUNTIME),
            patch("llm.narrator.resolve_skills", return_value=[]) as skills,
            patch(
                "llm.narrator.build_skill_context", return_value="Review instance"
            ) as context,
        ):
            result = generate_narrative(
                assessment(), [], completion_client=fake_completion, raw_files=raw_files
            )
        self.assertTrue(result.available)
        self.assertEqual(skills.call_args.kwargs["raw_files"], raw_files)
        self.assertEqual(context.call_args.kwargs["raw_files"], raw_files)
        self.assertNotIn("RAW-ARTIFACT-CONTENT", str(captured["messages"]))
