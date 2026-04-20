"""Tests for narrative orchestration."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from analysis.risk_scorer import RiskAssessment, RiskContributor
from evidence.models import Finding
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

    def _findings(self) -> list[Finding]:
        return [
            Finding(
                finding_id="finding-001",
                analysis_id=0,
                title="MEDIUM: aws_security_group.main",
                description="Terraform aws_security_group.main widened database access.",
                severity="medium",
                category="networking/ingress",
                deterministic=True,
                confidence=1.0,
                uncertainty_note=None,
                evidence_refs=["ev-001"],
                skill_id=None,
            )
        ]

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

        narrative = generate_narrative(
            self._assessment(), self._findings(), completion_client=fake_completion
        )
        self.assertFalse(narrative.degraded)
        self.assertEqual(narrative.source, "llm")
        self.assertIn("terraform", narrative.skills_applied)
        self.assertEqual(narrative.guidance[0], "Inspect the change table.")

    def test_generate_narrative_gracefully_degrades_on_provider_error(self) -> None:
        def broken_completion(**_: object):
            raise RuntimeError("provider offline")

        narrative = generate_narrative(
            self._assessment(), self._findings(), completion_client=broken_completion
        )
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

        narrative = generate_narrative(
            self._assessment(), self._findings(), completion_client=fake_completion
        )
        self.assertTrue(narrative.degraded)
        self.assertTrue(
            any("Expecting value" in warning for warning in narrative.warnings)
        )

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

        narrative = generate_narrative(
            self._assessment(), self._findings(), completion_client=fake_completion
        )
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

        narrative = generate_narrative(
            self._assessment(), self._findings(), completion_client=fake_completion
        )
        self.assertIn("unknown downstream impact", narrative.opening_sentence)
        self.assertIn("unknown downstream impact", narrative.explanation)

    def test_generate_narrative_payload_includes_findings(self) -> None:
        class Message:
            def __init__(self, content: str) -> None:
                self.content = content

        class Choice:
            def __init__(self, content: str) -> None:
                self.message = Message(content)

        class Response:
            def __init__(self, content: str) -> None:
                self.choices = [Choice(content)]

        captured: dict[str, object] = {}

        def fake_completion(**kwargs: object) -> Response:
            captured["messages"] = kwargs["messages"]
            return Response(
                '{"opening_sentence":"CAUTION: review the security group update.",'
                '"explanation":"The deployment widens database access and should be reviewed.",'
                '"guidance":["Inspect the findings before deploy."]}'
            )

        generate_narrative(
            self._assessment(),
            self._findings(),
            completion_client=fake_completion,
        )

        user_payload = captured["messages"][1]["content"]  # type: ignore[index]
        self.assertIn('"findings"', user_payload)
        self.assertIn('"evidence_refs"', user_payload)

    def test_generate_narrative_can_be_disabled_with_fallback(self) -> None:
        with patch(
            "llm.narrator.settings",
            SimpleNamespace(narrator_enabled=False),
        ):
            narrative = generate_narrative(self._assessment(), self._findings())

        self.assertTrue(narrative.degraded)
        self.assertEqual(narrative.source, "fallback")
        self.assertTrue(
            any(
                "Narrator disabled by configuration." in warning
                for warning in narrative.warnings
            )
        )


if __name__ == "__main__":
    unittest.main()
