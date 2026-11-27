"""Headless CI exit codes preserve the advisory report payload."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pydantic import BaseModel, Field

from analysis.divergence import DivergenceAssessment, PlanFreshness, ResourceComparison
from cli.analyze import main


_DIGEST = "a" * 64


class _RunData(BaseModel):
    live_context: DivergenceAssessment | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    advisory: dict


class DivergenceGateCliTests(unittest.TestCase):
    def setUp(self):
        def patched(name, **kwargs):
            patcher = patch(f"cli.analyze.{name}", **kwargs)
            self.addCleanup(patcher.stop)
            return patcher.start()

        self.analyze = patched("analyze_uploaded_files")
        self.permissions = patched("_require_cli_project_permission")
        patched(
            "resolve_analysis_project_scope",
            return_value=SimpleNamespace(id=1, project_key="demo"),
        )
        patched("_load_artifacts", return_value=[("plan.json", b"{}")])
        patched("build_pending_analysis", return_value=SimpleNamespace(ready_count=1))
        patched("_analysis_run_advisory")
        patched("build_share_summary")
        self.serialize = patched("build_analysis_run_data")
        patched(
            "build_agent_analysis_data",
            return_value=SimpleNamespace(
                model_dump=lambda **_: {
                    "schema_version": "v1",
                    "deployment_approval": False,
                }
            ),
        )

    def command(
        self, *options, status=None, observation="current", chronology="current"
    ):
        out, err = io.StringIO(), io.StringIO()
        observed_at = datetime(2026, 11, 20, tzinfo=timezone.utc)
        comparison = (
            DivergenceAssessment(
                snapshot_digest=_DIGEST,
                observation_status=observation,
                freshness=PlanFreshness(
                    status=chronology,
                    observed_at=observed_at,
                    threshold_seconds=3600,
                    reason="plan_timestamp_unavailable"
                    if chronology == "unknown"
                    else None,
                ),
                resources=(
                    ResourceComparison(
                        address="aws_instance.demo",
                        resource_type="aws_instance",
                        status=status,
                    ),
                ),
                diverged=status == "diverged",
                requires_caution=False,
            )
            if status is not None
            else None
        )
        self.analyze.return_value = SimpleNamespace(
            persisted_report={"id": 1}, live_context=comparison
        )
        self.serialize.return_value = _RunData(
            live_context=comparison, advisory={"should_block": False}
        )
        argv = ["deploywhisper", "analyze", "--project-id", "1", *options, "plan.json"]
        with patch("sys.argv", argv), redirect_stdout(out), redirect_stderr(err):
            with self.assertRaises(SystemExit) as exited:
                main()
        return exited.exception.code, out.getvalue(), err.getvalue()

    def test_confirmed_divergence_returns_three_and_the_advisory_report(self):
        code, out, err = self.command(
            "--snapshot-digest",
            _DIGEST,
            "--plan-stale-after-seconds",
            "1800",
            "--fail-on-divergence",
            status="diverged",
        )
        self.assertEqual(code, 3, err)
        self.assertEqual(err, "")
        data = json.loads(out)["data"]
        self.assertFalse(data["advisory"]["should_block"])
        self.assertEqual(data["live_context"]["snapshot_digest"], _DIGEST)
        self.assertEqual(data["live_context"]["resources"][0]["status"], "diverged")
        self.assertEqual(self.analyze.call_args.kwargs["snapshot_digest"], _DIGEST)
        self.assertEqual(
            self.analyze.call_args.kwargs["plan_stale_after_seconds"], 1800
        )
        self.assertNotIn("fail_on_divergence", self.analyze.call_args.kwargs)
        self.permissions.assert_any_call(capability="report.read", project_key="demo")

    def test_unverified_comparisons_are_ci_exit_two_but_still_return_reports(self):
        for status in ("unknown", "unreadable", None):
            with self.subTest(status=status):
                code, out, err = self.command(
                    "--snapshot-digest", _DIGEST, "--fail-on-divergence", status=status
                )
                self.assertEqual(code, 2, err)
                self.assertEqual(err, "")
                self.assertFalse(json.loads(out)["data"]["advisory"]["should_block"])

    def test_complete_match_passes_and_reporting_without_gate_is_advisory(self):
        for flags, status in ((("--fail-on-divergence",), "match"), ((), "diverged")):
            with self.subTest(flags=flags, status=status):
                code, out, err = self.command(
                    "--snapshot-digest", _DIGEST, *flags, status=status
                )
                self.assertEqual(code, 0, err)
                self.assertEqual(
                    json.loads(out)["data"]["live_context"]["diverged"],
                    status == "diverged",
                )
                self.assertNotIn(
                    "plan_stale_after_seconds", self.analyze.call_args.kwargs
                )

    def test_stale_or_unordered_matches_do_not_pass_the_gate(self):
        for observation, chronology in (("stale", "current"), ("current", "unknown")):
            with self.subTest(observation=observation, chronology=chronology):
                code, out, err = self.command(
                    "--snapshot-digest",
                    _DIGEST,
                    "--fail-on-divergence",
                    status="match",
                    observation=observation,
                    chronology=chronology,
                )
                self.assertEqual(code, 2, err)
                self.assertEqual(
                    json.loads(out)["data"]["live_context"]["observation_status"],
                    observation,
                )

    def test_agent_contract_retains_the_opt_in_live_context(self):
        code, out, err = self.command(
            "--agent-json",
            "--snapshot-digest",
            _DIGEST,
            "--fail-on-divergence",
            status="diverged",
        )
        self.assertEqual(code, 3, err)
        payload = json.loads(out)
        self.assertFalse(payload["deployment_approval"])
        self.assertEqual(payload["schema_version"], "v1")
        self.assertEqual(payload["live_context"]["snapshot_digest"], _DIGEST)

    def test_legacy_command_does_not_add_snapshot_kwargs_or_fields(self):
        for flags in ((), ("--agent-json",)):
            with self.subTest(flags=flags):
                code, out, err = self.command(*flags)
                self.assertEqual(code, 0, err)
                payload = json.loads(out)
                self.assertNotIn("live_context", payload.get("data", payload))
                self.assertNotIn("snapshot_digest", self.analyze.call_args.kwargs)
                self.assertNotIn(
                    "plan_stale_after_seconds", self.analyze.call_args.kwargs
                )
        self.assertTrue(
            all(
                call.kwargs["capability"] != "report.read"
                for call in self.permissions.call_args_list
            )
        )

    def test_invalid_options_fail_before_analysis(self):
        for options, expected in (
            (("--fail-on-divergence",), "snapshot_digest_required"),
            (("--plan-stale-after-seconds", "60"), "snapshot_digest_required"),
            (("--snapshot-digest", "invalid"), "invalid_grounding_snapshot"),
            (
                ("--snapshot-digest", _DIGEST, "--plan-stale-after-seconds", "0"),
                "invalid_plan_staleness",
            ),
        ):
            with self.subTest(options=options):
                code, out, err = self.command(*options)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertEqual(json.loads(err)["error"]["code"], expected)
                self.analyze.assert_not_called()

    def test_snapshot_read_permission_is_checked_before_analysis(self):
        def require(*, capability, **_):
            if capability == "report.read":
                raise PermissionError("Project read restricted.")

        self.permissions.side_effect = require
        code, out, err = self.command("--snapshot-digest", _DIGEST)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertEqual(json.loads(err)["error"]["code"], "project_permission_denied")
        self.analyze.assert_not_called()
