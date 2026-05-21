"""Tests for API response schemas."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from api.schemas import IncidentMatchData, PersistedReportData


class ApiSchemaTests(unittest.TestCase):
    def _persisted_report_payload(self) -> dict:
        return {
            "id": 17,
            "project": {
                "id": 1,
                "project_key": "default",
                "display_name": "Default",
                "created_at": "2026-05-11T00:00:00Z",
                "updated_at": "2026-05-11T00:00:00Z",
            },
            "risk_score": 42,
            "severity": "medium",
            "recommendation": "caution",
            "top_risk": "Terraform changed a security group.",
            "report_schema_version": "v2",
            "parse_summary": "Parsed 1 file.",
            "narrative_opening": "CAUTION: review the security group update.",
            "narrative_degraded": False,
            "created_at": "2026-05-11T00:00:00Z",
            "audit": {"files_analyzed": ["plan.json"]},
        }

    def test_persisted_report_requires_explicit_confidence(self) -> None:
        with self.assertRaises(ValidationError):
            PersistedReportData.model_validate(self._persisted_report_payload())

    def test_persisted_report_accepts_bounded_confidence(self) -> None:
        payload = self._persisted_report_payload()
        payload["confidence"] = 0.52

        report = PersistedReportData.model_validate(payload)

        self.assertEqual(report.confidence, 0.52)

    def test_persisted_report_exposes_confidence_ledger(self) -> None:
        payload = self._persisted_report_payload()
        payload["confidence"] = 0.72
        payload["confidence_ledger"] = {
            "contributors": ["aws_security_group.main"],
            "confidence_factors": ["Report confidence is Medium (0.72)."],
            "why_not_lower": ["Severity stays elevated."],
            "why_not_higher": ["The risk score is below the next threshold."],
            "uncertainty_drivers": ["No additional uncertainty drivers were recorded."],
        }

        report = PersistedReportData.model_validate(payload)

        self.assertEqual(
            report.confidence_ledger.why_not_higher,
            ["The risk score is below the next threshold."],
        )

    def test_persisted_report_normalizes_legacy_confidence_ledger(self) -> None:
        payload = self._persisted_report_payload()
        payload["confidence"] = 0.72
        payload["confidence_ledger"] = {
            "contributors": "single contributor",
            "why_not_higher": "single higher reason",
        }

        report = PersistedReportData.model_validate(payload)

        self.assertEqual(report.confidence_ledger.contributors, ["single contributor"])
        self.assertEqual(
            report.confidence_ledger.why_not_higher, ["single higher reason"]
        )
        self.assertEqual(report.confidence_ledger.why_not_lower, [])

    def test_persisted_report_requires_explicit_narrative_degraded(self) -> None:
        payload = self._persisted_report_payload()
        payload["confidence"] = 0.52
        payload.pop("narrative_degraded")

        with self.assertRaises(ValidationError):
            PersistedReportData.model_validate(payload)

    def test_incident_match_schema_exposes_public_risk_pattern_context(self) -> None:
        match = IncidentMatchData.model_validate(
            {
                "incident_id": 0,
                "match_type": "public_risk_pattern",
                "public_pattern_id": "public-ingress-wide-open",
                "title": "Wide-open administrative ingress",
                "severity": "high",
                "source_file": "plan.json",
                "incident_date": None,
                "similarity": 0.86,
                "confidence": 0.86,
                "reason": "Public ingress matched a built-in failure mode.",
                "evidence": ["plan.json: aws_security_group.ssh"],
                "verification_guidance": ["Restrict SSH ingress."],
                "summary": "Public risk pattern match.",
            }
        )

        self.assertEqual(match.match_type, "public_risk_pattern")
        self.assertEqual(match.public_pattern_id, "public-ingress-wide-open")
        self.assertEqual(match.verification_guidance, ["Restrict SSH ingress."])


if __name__ == "__main__":
    unittest.main()
