"""Deterministic checks for credential and raw artifact boundaries."""

from __future__ import annotations

import json
import tempfile
import unittest
from urllib.parse import quote, quote_plus
from pathlib import Path
from types import SimpleNamespace
from typing import get_args
from unittest.mock import patch
from unittest.mock import MagicMock

from services import artifact_snapshot_service
from services.content_security import (
    BLOCKED_CONTENT,
    REDACTED,
    redact_text,
    redact_value,
    sensitive_artifact_values,
)


class ContentSecurityTests(unittest.TestCase):
    def test_plural_credential_assignments_are_screened_in_text(self):
        for raw in (
            "CREDENTIALS=synthetic-value",
            'resource "example" "test" { credentials = "synthetic-value" }',
            "received auth.credentials: synthetic-value",
            "DB-CREDENTIALS='synthetic-value'",
        ):
            with self.subTest(raw=raw):
                self.assertNotIn("synthetic-value", redact_text(raw))
                self.assertIn(
                    "synthetic-value", sensitive_artifact_values(raw.encode())
                )

    def test_maximal_identifiers_preserve_assignment_and_url_detection(self):
        for label in ("auth.password", "db-password", "AUTH.API_KEY"):
            with self.subTest(label=label):
                self.assertEqual(
                    redact_text(f"{label}=synthetic-value"), f"{label}={REDACTED}"
                )
        for scheme in ("https", "git+https", "vendor.proto-v1"):
            raw = f"{scheme}://reader:synthetic-value@db.example.com/path"
            with self.subTest(scheme=scheme):
                self.assertEqual(
                    redact_text(raw), f"{scheme}://{REDACTED}@db.example.com/path"
                )
                self.assertIn(
                    "synthetic-value", sensitive_artifact_values(raw.encode())
                )
        long_label = "component." * 2048 + "password"
        self.assertEqual(
            redact_text(f"{long_label}=synthetic-value"),
            f"{long_label}={REDACTED}",
        )
        long_scheme = "vendor." * 2048 + "proto"
        self.assertEqual(
            redact_text(f"{long_scheme}://reader:synthetic-value@db.example.com"),
            f"{long_scheme}://{REDACTED}@db.example.com",
        )
        self.assertEqual(
            redact_text("db.example.com ordinary-identifier"),
            "db.example.com ordinary-identifier",
        )

    def test_submission_values_collect_filename_and_artifact_credentials(self):
        from services.content_security import sensitive_submission_values

        files = [
            ("CREDENTIALS=synthetic-filename.tf", b"password=synthetic-body"),
            ("secret.yaml", b"kind: Secret\nstringData:\n  opaque: synthetic-k8s\n"),
            ("public.tf", b"label=ordinary"),
        ]
        values = sensitive_submission_values(files)
        self.assertIn("synthetic-filename.tf", values)
        self.assertIn("synthetic-body", values)
        self.assertIn("synthetic-k8s", values)
        self.assertNotIn("ordinary", values)
        self.assertEqual(values, tuple(sorted(set(values))))
        self.assertEqual(sensitive_submission_values([]), ())

    def test_escaped_hcl_credentials_keep_literal_and_decoded_variants(self):
        for literal, decoded in (
            (r"\u0073ynthetic-value", "synthetic-value"),
            (r"synthetic\"value", 'synthetic"value'),
            (r"synthetic\nvalue", "synthetic\nvalue"),
            (r"synthetic\U0000002fvalue", "synthetic/value"),
        ):
            with self.subTest(literal=literal):
                raw = f'resource "example" "test" {{\n password = "{literal}"\n}}'
                values = sensitive_artifact_values(raw.encode())
                self.assertIn(literal, values)
                self.assertIn(decoded, values)
                self.assertNotIn(
                    decoded,
                    redact_value({"echo": decoded}, sensitive_values=values)["echo"],
                )

    def test_local_credentials_screen_sibling_echoes_and_skill_prose(self):
        for payload in (
            {"echo": "synthetic-value", "api_key": "synthetic-value"},
            {"echo": "synthetic-value", "skill": "password=synthetic-value"},
            {"echo": 'synthetic"value', "skill": r'password="synthetic\"value"'},
            {
                "echo": "synthetic-value",
                "env": [{"name": "AUTH_TOKEN", "value": "synthetic-value"}],
            },
        ):
            with self.subTest(payload=payload):
                self.assertEqual(redact_value(payload)["echo"], REDACTED)

    def test_metadata_protocol_spellings_do_not_exempt_credentials(self):
        safe = redact_value(
            {
                "source": "database",
                "metadata": {"source": "database", "status": "ready"},
            },
            sensitive_values=("database", "ready"),
        )
        self.assertEqual(safe["source"], "database")
        self.assertEqual(safe["metadata"], {"source": REDACTED, "status": REDACTED})

    def test_kubernetes_base64_block_scalars_collect_decoded_credentials(self):
        for marker in ("|", "|-", ">", ">-"):
            with self.subTest(marker=marker):
                raw = (
                    f"kind: Secret\r\ndata:\r\n  opaque: {marker}\r\n"
                    "    c3ludGhldGlj\r\n    LXZhbHVl\r\n"
                ).encode()
                values = sensitive_artifact_values(raw)
                self.assertIn("synthetic-value", values)
                self.assertEqual(
                    redact_value({"echo": "synthetic-value"}, sensitive_values=values)[
                        "echo"
                    ],
                    REDACTED,
                )

    def test_cloudformation_tags_and_noecho_defaults_are_screened(self):
        raw = b"""Parameters:
  Opaque:
    Type: String
    NoEcho: true
    Default: synthetic-default
Resources:
  Database:
    Type: AWS::RDS::DBInstance
    Properties:
      MasterUserPassword: synthetic-password
      Name: !Sub '${AWS::StackName}-db'
      Other: !Join [':', [one, two]]
"""
        values = sensitive_artifact_values(raw)
        self.assertIn("synthetic-password", values)
        self.assertIn("synthetic-default", values)
        self.assertEqual(
            redact_value({"NoEcho": True, "Default": "synthetic-default"})["Default"],
            REDACTED,
        )

    def test_known_credentials_screen_url_encoded_evidence_references(self):
        secret = 'synthetic value/"quoted"'
        for encoded in (quote(secret), quote(secret, safe=""), quote_plus(secret)):
            with self.subTest(encoded=encoded):
                safe = redact_value(
                    {
                        "api_key": secret,
                        "evidence_reference": f"file:///source/{encoded}.tf",
                    }
                )
                self.assertNotIn(encoded, safe["evidence_reference"])
                self.assertIn(REDACTED, safe["evidence_reference"])

    def test_large_valid_payload_preserves_container_and_numeric_contracts(self):
        payload = {
            "tasks": [
                {"id": index, "metadata": {f"field_{n}": n for n in range(40)}}
                for index in range(300)
            ]
        }
        self.assertEqual(redact_value(payload), payload)

    def test_alias_graph_is_screened_once_and_cycles_are_blocked(self):
        import yaml

        raw = "leaf: &leaf {label: ordinary}\n"
        previous = "leaf"
        for index in range(24):
            name = f"branch{index}"
            raw += f"{name}: &{name} [*{previous}, *{previous}]\n"
            previous = name
        self.assertEqual(sensitive_artifact_values(raw.encode()), ())
        screened = redact_value(yaml.safe_load(raw))
        self.assertIs(screened["branch23"][0], screened["branch23"][1])
        cycle = []
        cycle.append(cycle)
        self.assertEqual(redact_value(cycle), [BLOCKED_CONTENT])

    def test_shared_secret_values_and_masks_remain_screened(self):
        import yaml

        raw = b"kind: Secret\ndata: &data {opaque: c3ludGhldGljLXZhbHVl}\ncopy: *data\n"
        self.assertIn("synthetic-value", sensitive_artifact_values(raw))
        values = {"opaque": "synthetic-value", "port": 443}
        mask = {"opaque": True}
        payload = [
            {"after": values, "after_sensitive": mask},
            {"after": {"opaque": "second-value", "port": 80}, "after_sensitive": mask},
        ]
        screened = redact_value(payload)
        self.assertEqual(screened[0]["after"], {"opaque": REDACTED, "port": 443})
        self.assertEqual(screened[1]["after"], {"opaque": REDACTED, "port": 80})
        self.assertEqual(redact_value(screened), screened)
        self.assertNotIn(
            "synthetic-value",
            json.dumps(
                redact_value(
                    yaml.safe_load(raw), sensitive_values=sensitive_artifact_values(raw)
                )
            ),
        )

    def test_secret_key_labels_preserve_innocuous_key_labels(self):
        for label in ("SECRET_KEY", "secretkey"):
            with self.subTest(label=label):
                self.assertEqual(
                    redact_text(f"{label}=synthetic-value"), f"{label}={REDACTED}"
                )
                self.assertEqual(
                    redact_value({label: "synthetic-value"}), {label: REDACTED}
                )
                self.assertEqual(
                    redact_value({"name": label, "value": "synthetic-value"})["value"],
                    REDACTED,
                )
        self.assertEqual(
            redact_value({"monkey": "banana", "public_key": "public"}),
            {"monkey": "banana", "public_key": "public"},
        )

    def test_quoted_yaml_keys_binary_and_decoded_secret_variants(self):
        for raw in (
            b"'kind': Secret\nstringData:\n  opaque: synthetic-value\n",
            b"kind : Secret\nstringData:\n  opaque: synthetic-value\n",
            b"kind: Secret\ndata:\n  opaque: c3ludGhldGljLXZhbHVl\n",
            b"'kind': Secret\ndata:\n  opaque: !!binary c3ludGhldGljLXZhbHVl\n",
            b"kind: Secret\nstringData:\n  opaque: |\n    synthetic-value\n",
        ):
            with self.subTest(raw=raw):
                values = sensitive_artifact_values(raw)
                self.assertIn("synthetic-value", values)
                self.assertEqual(
                    redact_text("echo synthetic-value", sensitive_values=values),
                    "echo " + REDACTED,
                )

    def test_yaml_implicit_scalar_credentials_are_collected(self):
        values = sensitive_artifact_values(
            b"kind: Secret\nstringData:\n  opaque: 2026-10-05\n"
        )
        self.assertIn("2026-10-05", values)
        self.assertEqual(
            redact_text("echo 2026-10-05", sensitive_values=values), "echo " + REDACTED
        )

    def test_terraform_output_descriptors_collect_values(self):
        values = sensitive_artifact_values(
            b'{"outputs":{"opaque":{"sensitive":true,"value":"synthetic-output"}}}'
        )
        self.assertIn("synthetic-output", values)
        self.assertEqual(
            redact_value({"sensitive": True, "value": "synthetic-output"})["value"],
            REDACTED,
        )

    def test_known_numeric_credentials_are_screened_only_in_metadata(self):
        payload = {
            "risk_score": 123456,
            "id": 123456,
            "count": 123456,
            "metadata": {
                "echo": 123456,
                "values": [123456],
                "synthetic-value": "public",
            },
        }
        safe = redact_value(payload, sensitive_values=("123456", "synthetic-value"))
        self.assertEqual(safe["risk_score"], 123456)
        self.assertEqual(safe["id"], 123456)
        self.assertEqual(safe["count"], 123456)
        self.assertEqual(safe["metadata"]["echo"], REDACTED)
        self.assertEqual(safe["metadata"]["values"], [REDACTED])
        self.assertNotIn("synthetic-value", safe["metadata"])

    def test_all_evidence_contract_enums_survive_matching_secret_values(self):
        from evidence.models import (
            ContextSourceType,
            EvidenceSourceType,
            DeterminismLevel,
            FindingEvidenceClassification,
            ContextSourceFreshness,
            OwnerSignalScope,
        )

        for field, contract in (
            ("source_type", ContextSourceType),
            ("source_kind", EvidenceSourceType),
            ("determinism_level", DeterminismLevel),
            ("evidence_classification", FindingEvidenceClassification),
            ("freshness_status", ContextSourceFreshness),
            ("scope", OwnerSignalScope),
        ):
            for value in get_args(contract):
                with self.subTest(field=field, value=value):
                    self.assertEqual(
                        redact_value({field: value}, sensitive_values=(value,)),
                        {field: value},
                    )

    def test_parser_exception_does_not_echo_artifact_source(self):
        from parsers.registry import parse_uploaded_files

        with patch.dict(
            "parsers.registry.PARSERS",
            {
                "terraform": MagicMock(
                    side_effect=ValueError("raw confidential artifact body")
                )
            },
        ):
            batch = parse_uploaded_files([("main.tf", b"invalid")])
        self.assertEqual(batch.failed_count, 1)
        self.assertNotIn("raw confidential artifact body", batch.model_dump_json())
        self.assertIn("ValueError", batch.files[0].issue.message)

    def test_secondary_confidence_prompt_redacts_locally_detected_values(self):
        from analysis.risk_scorer import RiskAssessment
        from services.analysis_service import _interaction_confidence_prompt_payload

        assessment = RiskAssessment(
            score=10,
            severity="low",
            recommendation="go",
            top_risk="echo synthetic-opaque-value",
            partial_context=False,
        )
        payload = _interaction_confidence_prompt_payload(
            assessment, sensitive_values=("synthetic-opaque-value",)
        )
        self.assertNotIn("synthetic-opaque-value", payload)
        self.assertIn(REDACTED, payload)

    def test_generated_content_redaction_rolls_up_without_sensitive_uploads(self):
        from services.report_service import _report_redaction_status

        self.assertEqual(
            _report_redaction_status(
                {
                    "items": [{"redaction_status": "none"}],
                    "redaction": {"content_redacted": True},
                }
            ),
            "redacted",
        )

    def test_repository_screens_direct_writes_and_preserves_visible_notice(self):
        from models.repositories.analysis_reports import create_analysis_report
        from services.content_security import REDACTION_WARNING

        report = create_analysis_report(
            MagicMock(),
            project_id=1,
            risk_score=10,
            severity="low",
            recommendation="go",
            top_risk="Low change",
            report_schema_version="v2",
            parse_summary="1 parsed",
            narrative_opening="GO: low change",
            narrative_explanation="password=synthetic-direct-value",
            warnings_json="[]",
            contributors_json=json.dumps(
                [{"metadata": {"api_key": "synthetic-direct-metadata"}}]
            ),
            analyzed_files_json='["main.tf"]',
            submission_manifest_json="{}",
            submission_manifest_fallback_json="[]",
            blast_radius_json="{}",
            rollback_plan_json="{}",
            llm_provider="ollama",
            llm_model="local-model",
            llm_local_mode="true",
            assessment_source="heuristic-only",
            narrative_source="llm",
            narrative_skills_json="[]",
            source_interface="api",
            trigger_type=None,
            trigger_id=None,
            dashboard_display_duration_seconds=None,
            findings_payload=[
                {
                    "finding_id": "finding-cross-model",
                    "analysis_id": 0,
                    "title": "LOW: review",
                    "description": "Echo synthetic-direct-metadata",
                    "severity": "low",
                    "category": "generic infrastructure",
                    "deterministic": True,
                    "confidence": 1.0,
                    "evidence_refs": [],
                }
            ],
        )
        self.assertNotIn("synthetic-direct-value", report.narrative_explanation)
        self.assertNotIn("synthetic-direct-metadata", report.contributors_json)
        self.assertNotIn("synthetic-direct-metadata", report.findings[0].description)
        self.assertIn(REDACTION_WARNING, json.loads(report.warnings_json))

    def test_credentials_are_redacted_in_text_without_hiding_risk_flags(self):
        for value in (
            'password="synthetic password with spaces"',
            '"api_key": "synthetic-api-value"',
            "Authorization: Bearer synthetic-auth-value",
            "postgres://operator:synthetic-db-value@localhost/app",
            "AKIA" + "X" * 16,
            "ghp_" + "x" * 36,
            "-----BEGIN PRIVATE KEY-----\nsynthetic key body\n-----END PRIVATE KEY-----",
        ):
            with self.subTest(value=value):
                self.assertNotEqual(redact_text(value), value)
                self.assertIn(REDACTED, redact_text(value))
        self.assertEqual(
            redact_text("KMS encryption appears disabled."),
            "KMS encryption appears disabled.",
        )

    def test_nested_credentials_secret_objects_and_sensitive_masks(self):
        payload = {
            "api_key": "synthetic-api-value",
            "nested": [{"database_password": "synthetic-db-value"}],
            "secret": {"kind": "Secret", "data": {"arbitrary": "encoded-value"}},
            "env": [{"name": "AUTH_TOKEN", "value": "synthetic-env-value"}],
            "change": {
                "after": {"opaque": "masked-value", "port": 443},
                "after_sensitive": {"opaque": True},
            },
            "count": 1,
            "security_flags": ["Public endpoint access enabled."],
        }
        sanitized = redact_value(payload)
        for secret in (
            "synthetic-api-value",
            "synthetic-db-value",
            "encoded-value",
            "synthetic-env-value",
            "masked-value",
        ):
            self.assertNotIn(secret, json.dumps(sanitized))
        self.assertEqual(sanitized["change"]["after"]["port"], 443)
        self.assertEqual(sanitized["count"], 1)
        self.assertEqual(payload["api_key"], "synthetic-api-value")
        self.assertEqual(redact_value(sanitized), sanitized)

    def test_sensitive_artifact_snapshot_is_blocked_and_clean_snapshot_preserved(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(
                artifact_snapshot_service,
                "settings",
                SimpleNamespace(artifact_snapshot_dir=directory),
            ),
        ):
            artifact_snapshot_service.save_report_artifacts(
                1,
                {
                    "deployment.yaml": b"kind: Secret\ndata:\n  opaque: synthetic-secret-value\n",
                    "main.tf": b'password = "synthetic-hcl-value"',
                    "clean.tf": b'resource "aws_instance" "web" {}',
                    ".env": b"opaque=synthetic-env-value",
                },
            )
            self.assertEqual(
                artifact_snapshot_service.load_report_artifact(
                    1, "deployment.yaml"
                ).content,
                BLOCKED_CONTENT,
            )
            self.assertEqual(
                artifact_snapshot_service.load_report_artifact(1, "main.tf").content,
                BLOCKED_CONTENT,
            )
            self.assertIsNone(artifact_snapshot_service.load_report_artifact(1, ".env"))
            self.assertEqual(
                artifact_snapshot_service.load_report_artifact(1, "clean.tf").content,
                'resource "aws_instance" "web" {}',
            )
            for path in Path(directory).rglob("*"):
                if path.is_file():
                    self.assertNotIn("synthetic-secret-value", path.read_text())

    def test_detected_values_are_removed_from_unlabelled_derived_text(self):
        values = sensitive_artifact_values(
            b"kind: Secret\ndata:\n  opaque: synthetic-secret-value\n"
        )
        self.assertIn("synthetic-secret-value", values)
        self.assertEqual(
            redact_value(
                {"summary": "contains synthetic-secret-value"}, sensitive_values=values
            ),
            {"summary": "contains " + REDACTED},
        )

    def test_quoted_flow_and_json_secret_documents_and_opaque_auth_values(self):
        for raw in (
            b'kind: "Secret"\nstringData:\n  opaque: synthetic-opaque-value\n',
            b"{kind: Secret, stringData: {opaque: synthetic-opaque-value}}",
            b"Authorization: Bearer synthetic-opaque-value",
            b"postgres://operator:synthetic-opaque-value@localhost/app",
        ):
            with self.subTest(raw=raw):
                self.assertIn("synthetic-opaque-value", sensitive_artifact_values(raw))

    def test_known_short_credentials_preserve_schema_keys_and_protocol_enums(self):
        payload = {
            "explanation": "example x",
            "severity": "low",
            "source_type": "artifact",
            "metadata": {"password": "low"},
        }
        sanitized = redact_value(payload, sensitive_values=("x", "low"))
        self.assertEqual(sanitized["severity"], "low")
        self.assertEqual(sanitized["explanation"], "example " + REDACTED)
        self.assertEqual(sanitized["metadata"]["password"], REDACTED)

    def test_arbitrary_protocol_field_values_and_numeric_sensitive_masks(self):
        payload = {
            "source": "synthetic-opaque-value",
            "status": "synthetic-opaque-value",
        }
        self.assertNotIn(
            "synthetic-opaque-value",
            json.dumps(
                redact_value(payload, sensitive_values=("synthetic-opaque-value",))
            ),
        )
        values = sensitive_artifact_values(
            b'{"change":{"after":{"pin":123456},"after_sensitive":{"pin":true}}}'
        )
        self.assertIn("123456", values)
        self.assertEqual(
            redact_text("PIN 123456", sensitive_values=values), "PIN " + REDACTED
        )


if __name__ == "__main__":
    unittest.main()
