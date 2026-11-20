"""The actual CLI preserves collected counters in normal and agent output."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from unittest.mock import patch

from cli.analyze import main
import services.analysis_service as analysis_service
from tests.test_services.test_analysis_cloud_grounding import CloudBudgetFixture


class CloudCollectionBudgetCliTests(CloudBudgetFixture):
    def command(self, observed, *, agent=False):
        out, err = io.StringIO(), io.StringIO()
        argv = ["deploywhisper", "analyze", "--project-id", str(self.project.id)]
        if agent:
            argv.append("--agent-json")
        argv.append(str(self.artifact))
        with (
            patch.object(
                analysis_service,
                "build_analysis_artifacts",
                side_effect=self.deterministic_build,
            ),
            patch(
                "cli.analyze.analyze_uploaded_files",
                side_effect=self.analyze_with(observed),
            ),
            patch("sys.argv", argv),
            redirect_stdout(out),
            redirect_stderr(err),
        ):
            with self.assertRaises(SystemExit) as exited:
                main()
        self.assertEqual(exited.exception.code, 0, err.getvalue())
        self.assertEqual(err.getvalue(), "")
        self.assertNotIn("synthetic-provider-credential-canary", out.getvalue())
        return json.loads(out.getvalue())

    def test_completion_and_cancel_budget_survive_both_cli_contracts(self):
        for agent in (False, True):
            for cancelled, failed in ((False, False), (True, False), (False, True)):
                with self.subTest(agent=agent, cancelled=cancelled, failed=failed):
                    self.sdk.reset_mock()
                    observed = self.collect(cancelled=cancelled, failed=failed)
                    payload = self.command(observed, agent=agent)
                    data = payload["data"] if "data" in payload else payload
                    budget = data["cloud_collection"]
                    self.assertEqual(budget, observed.budget.model_dump(mode="json"))
                    self.assertEqual(
                        budget["actual_call_count"],
                        self.sdk.create_client.return_value._make_api_call.call_count,
                    )
                    self.assertEqual(budget["cancelled"], cancelled)
                    self.assertGreaterEqual(budget["elapsed_seconds"], 0)
                    if agent:
                        self.assertEqual(data["schema_version"], "v1")
                        self.assertFalse(data["deployment_approval"])
                    else:
                        self.assertEqual(payload["meta"]["report_schema_version"], "v2")

    def test_absent_and_disabled_do_not_add_fields_to_cli(self):
        for observed in (None, self.collect(disabled=True)):
            for agent in (False, True):
                with self.subTest(observed=observed, agent=agent):
                    payload = self.command(observed, agent=agent)
                    data = payload["data"] if "data" in payload else payload
                    self.assertNotIn("cloud_collection", data)
