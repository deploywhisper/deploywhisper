"""Rendered smoke tests for incident and public risk pattern matches."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import app as app_module
from fastapi.testclient import TestClient
from nicegui import ui

from analysis.incident_matcher import IncidentMatch
from ui.components.incident_match_card import render_incident_matches
from ui.components.report_detail_page import render_report_detail_page


@ui.page("/_test/incident-match-card")
def incident_match_card_test_page() -> None:
    render_incident_matches(
        [
            IncidentMatch(
                incident_id=0,
                match_type="public_risk_pattern",
                public_pattern_id="public-ingress-wide-open",
                title="Wide-open administrative ingress",
                severity="high",
                source_file="plan.json",
                incident_date=None,
                similarity=0.86,
                confidence=0.86,
                reason="The change exposes administrative ingress publicly.",
                evidence=["plan.json: aws_security_group.main (modify) - public SSH"],
                verification_guidance=[
                    "Confirm public CIDR is intentional.",
                    "Restrict ingress to trusted networks.",
                ],
                summary="Public risk pattern match: wide-open administrative ingress.",
            )
        ]
    )


@ui.page("/_test/incident-match-card-empty")
def incident_match_card_empty_test_page() -> None:
    render_incident_matches([])


@ui.page("/_test/report-detail-incident-matches")
def report_detail_incident_matches_test_page() -> None:
    match = IncidentMatch(
        incident_id=0,
        match_type="public_risk_pattern",
        public_pattern_id="public-ingress-wide-open",
        title="Wide-open administrative ingress",
        severity="high",
        source_file="plan.json",
        incident_date=None,
        similarity=0.86,
        confidence=0.86,
        reason="The change exposes administrative ingress publicly.",
        evidence=["plan.json: aws_security_group.main (modify) - public SSH"],
        verification_guidance=["Confirm public CIDR is intentional."],
        summary="Public risk pattern match: wide-open administrative ingress.",
    )
    with patch(
        "ui.components.report_detail_page.fetch_report_feedback_state",
        return_value={"finding_feedback": {}, "false_negative_notes": []},
    ):
        render_report_detail_page(
            {
                "id": 1,
                "created_at": "2026-05-21T10:00:00Z",
                "severity": "high",
                "recommendation": "caution",
                "risk_score": 82,
                "confidence": 0.86,
                "top_risk": "Wide-open administrative ingress",
                "summary": "Review public ingress.",
                "narrative_opening": "Review public ingress.",
                "parse_summary": "1 Terraform change parsed.",
                "incident_matches": [match.model_dump(mode="json")],
                "findings": [],
                "evidence_items": [],
                "audit": {"files_analyzed": ["plan.json"]},
                "context_completeness": {},
                "blast_radius": {},
                "rollback_plan": {},
            }
        )


class IncidentMatchCardRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app_module.create_app())

    def test_public_risk_pattern_card_renders_confidence_evidence_and_guidance(
        self,
    ) -> None:
        response = self.client.get("/_test/incident-match-card")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Incident and risk pattern similarity", response.text)
        self.assertIn("Public risk pattern", response.text)
        self.assertIn("86% confidence", response.text)
        self.assertIn("Evidence:", response.text)
        self.assertIn("aws_security_group.main", response.text)
        self.assertIn("Confirm public CIDR is intentional.", response.text)
        self.assertIn("Restrict ingress to trusted networks.", response.text)

    def test_empty_card_renders_no_matches_state(self) -> None:
        response = self.client.get("/_test/incident-match-card-empty")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Incident and risk pattern similarity", response.text)
        self.assertIn("No similar incidents found.", response.text)

    def test_report_detail_renders_persisted_public_risk_pattern(self) -> None:
        response = self.client.get("/_test/report-detail-incident-matches")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Public risk pattern", response.text)
        self.assertIn("86% confidence", response.text)
        self.assertIn("Evidence:", response.text)
        self.assertIn("Confirm public CIDR is intentional.", response.text)


if __name__ == "__main__":
    unittest.main()
