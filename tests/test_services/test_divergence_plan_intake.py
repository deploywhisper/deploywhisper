"""The CI gate uses the Terraform plan selected by shared artifact intake."""

from contextlib import ExitStack, nullcontext
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cloud.base import build_snapshot
from services import divergence_service
from services.intake_service import build_parse_batch


FIXTURES = (
    Path(__file__).resolve().parents[1] / "fixtures" / "live_environment_divergence"
)
_MANIFEST = (
    b"apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: demo\n"
    b"data:\n  example: value\n"
)


class DivergencePlanIntakeTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((FIXTURES / "plan.json").read_text())
        self.plan["resource_changes"] = []
        self.snapshot = build_snapshot(
            **json.loads((FIXTURES / "snapshot.json").read_text())
        )
        patches = ExitStack()
        self.addCleanup(patches.close)
        self.admission = patches.enter_context(
            patch.object(
                divergence_service,
                "divergence_admission",
                return_value=nullcontext(SimpleNamespace(snapshot=self.snapshot)),
            )
        )
        clock = patches.enter_context(patch.object(divergence_service, "datetime"))
        clock.now.return_value = self.snapshot.read_window_end
        patches.enter_context(
            patch.object(
                divergence_service, "provider_credential_values", return_value=()
            )
        )

    def compare(self, files, **kwargs):
        return divergence_service.compare_retained_plan(
            files,
            project_id=self.snapshot.project_id,
            snapshot_digest=self.snapshot.digest,
            stale_after_seconds=None,
            **kwargs,
        )

    def assert_rejected(self, files):
        with self.assertRaises(divergence_service.DivergenceRequestError) as raised:
            self.compare(files)
        self.assertEqual(raised.exception.code, "invalid_grounding_plan")
        self.admission.assert_not_called()

    def test_excluded_plan_cannot_be_selected_when_another_artifact_is_admitted(self):
        self.assert_rejected(
            [
                ("credentials-plan.json", json.dumps(self.plan).encode()),
                ("manifest.yaml", _MANIFEST),
            ]
        )

    def test_additional_admitted_plan_is_ambiguous_even_with_another_format(self):
        other = {**self.plan, "format_version": "1.0"}
        self.assert_rejected(
            [
                ("plan.json", json.dumps(self.plan).encode()),
                ("other-plan.json", json.dumps(other).encode()),
            ]
        )

    def test_plan_filename_classification_matches_shared_parser(self):
        self.assert_rejected(
            [
                ("plan.json", json.dumps(self.plan).encode()),
                ("other-plan.json/", json.dumps(self.plan).encode()),
            ]
        )

    def test_admitted_plan_must_have_parsed_successfully(self):
        files = [("plan.json", json.dumps(self.plan).encode())]
        batch = build_parse_batch(files)
        batch.files[0].status = "failed"
        with self.assertRaises(divergence_service.DivergenceRequestError) as raised:
            self.compare(files, parse_batch=batch)
        self.assertEqual(raised.exception.code, "invalid_grounding_plan")
        self.admission.assert_not_called()

    def test_admitted_noop_can_reuse_the_analysis_batch_with_other_artifacts(self):
        files = [
            ("plan.json", json.dumps(self.plan).encode()),
            ("manifest.yaml", _MANIFEST),
        ]
        batch = build_parse_batch(files)
        with patch.object(divergence_service, "build_parse_batch") as parse:
            result = self.compare(files, parse_batch=batch)
        parse.assert_not_called()
        self.assertEqual(result.resources, ())
        self.assertEqual(divergence_service.divergence_gate_exit_code(result), 0)

    def test_supplied_batch_cannot_select_an_ambiguous_filename(self):
        selected = ("plan.json", json.dumps(self.plan).encode())
        batch = build_parse_batch([selected])
        with self.assertRaises(divergence_service.DivergenceRequestError) as raised:
            self.compare(
                [selected, ("plan.json", b'{"unrelated": true}')], parse_batch=batch
            )
        self.assertEqual(raised.exception.code, "invalid_grounding_plan")
        self.admission.assert_not_called()
