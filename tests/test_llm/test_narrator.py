"""Tests for narrative orchestration."""

from __future__ import annotations

import unittest

from analysis.risk_scorer import RiskAssessment, RiskContributor
from llm.narrator import generate_narrative


class NarrativeTests(unittest.TestCase):
    def _assessment(self) -> RiskAssessment:
        return RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Terraform aws_security_group.main (modify) is the highest-impact change.",
            partial_context=False,
            warnings=[],
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=12,
                    summary="Terraform aws_security_group.main widened database access.",
                )
            ],
        )

    def test_generate_narrative_uses_completion_client_when_available(self) -> None:
        class Message:
            def __init__(self, content: str) -> None:
                self.content = content

        class Choice:
            def __init__(self, content: str) -> None:
                self.message = Message(content)

        class Response:
            def __init__(self, content: str) -> None:
                self.choices = [Choice(content)]

        def fake_completion(**_: object) -> Response:
            return Response(
                '{"opening_sentence":"CAUTION: review the security group update.",'
                '"explanation":"The deployment widens database access and should be reviewed.",'
                '"guidance":["Inspect the change table.","Verify rollback readiness."]}'
            )

        narrative = generate_narrative(self._assessment(), completion_client=fake_completion)
        self.assertFalse(narrative.degraded)
        self.assertEqual(narrative.source, "llm")
        self.assertIn("terraform", narrative.skills_applied)
        self.assertEqual(narrative.guidance[0], "Inspect the change table.")

    def test_generate_narrative_gracefully_degrades_on_provider_error(self) -> None:
        def broken_completion(**_: object):
            raise RuntimeError("provider offline")

        narrative = generate_narrative(self._assessment(), completion_client=broken_completion)
        self.assertTrue(narrative.degraded)
        self.assertEqual(narrative.source, "fallback")
        self.assertTrue(narrative.warnings)
        self.assertIn("provider offline", narrative.warnings[-1])

    def test_generate_narrative_gracefully_degrades_on_invalid_json(self) -> None:
        class Message:
            def __init__(self, content: str) -> None:
                self.content = content

        class Choice:
            def __init__(self, content: str) -> None:
                self.message = Message(content)

        class Response:
            def __init__(self, content: str) -> None:
                self.choices = [Choice(content)]

        def fake_completion(**_: object) -> Response:
            return Response("not-json")

        narrative = generate_narrative(self._assessment(), completion_client=fake_completion)
        self.assertTrue(narrative.degraded)
        self.assertTrue(any("Expecting value" in warning for warning in narrative.warnings))

    def test_generate_narrative_gracefully_degrades_on_missing_keys(self) -> None:
        class Message:
            def __init__(self, content: str) -> None:
                self.content = content

        class Choice:
            def __init__(self, content: str) -> None:
                self.message = Message(content)

        class Response:
            def __init__(self, content: str) -> None:
                self.choices = [Choice(content)]

        def fake_completion(**_: object) -> Response:
            return Response('{"opening_sentence":"ok"}')

        narrative = generate_narrative(self._assessment(), completion_client=fake_completion)
        self.assertTrue(narrative.degraded)
        self.assertTrue(any("explanation" in warning for warning in narrative.warnings))

    def test_generate_narrative_sanitizes_fabricated_scope_claims(self) -> None:
        class Message:
            def __init__(self, content: str) -> None:
                self.content = content

        class Choice:
            def __init__(self, content: str) -> None:
                self.message = Message(content)

        class Response:
            def __init__(self, content: str) -> None:
                self.choices = [Choice(content)]

        def fake_completion(**_: object) -> Response:
            return Response(
                '{"opening_sentence":"GO: affects 6 downstream services.",'
                '"explanation":"This has high blast radius.",'
                '"guidance":["Review 6 downstream services."]}'
            )

        narrative = generate_narrative(self._assessment(), completion_client=fake_completion)
        self.assertIn("unknown downstream impact", narrative.opening_sentence)
        self.assertIn("unknown downstream impact", narrative.explanation)


if __name__ == "__main__":
    unittest.main()
