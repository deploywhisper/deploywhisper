"""Live probe scope and nonsecret evidence checks without remote mutations."""

from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

import yaml

from infra_automation.target_transport import DispatchResponse
from scripts.qualify_github_receiver import (
    SANDBOX,
    qualify,
    resolve_snapshot,
    synthetic_envelope,
)

SHA = "a" * 40
TOKEN = "synthetic-dispatch-secret"


class LiveQualificationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.env = dict(
            GITHUB_ACTIONS="true",
            GITHUB_REPOSITORY=SANDBOX,
            GITHUB_REF="refs/heads/main",
            GITHUB_EVENT_NAME="workflow_dispatch",
            GITHUB_RUN_ATTEMPT="1",
            GITHUB_RUN_ID="123",
            GITHUB_SHA=SHA,
            APP_COMMIT="b" * 40,
            SANDBOX_DISPATCH_TOKEN=TOKEN,
            RUNNER_TEMP=self.directory.name,
            GITHUB_STEP_SUMMARY=str(Path(self.directory.name) / "summary"),
        )
        self.transport = Mock()
        self.transport.get_registered.side_effect = self.get
        self.transport.post_registered.return_value = DispatchResponse(
            200,
            json.dumps(
                dict(
                    workflow_run_id=56,
                    run_url=f"https://api.github.com/repos/{SANDBOX}/actions/runs/56",
                    html_url=f"https://github.com/{SANDBOX}/actions/runs/56",
                )
            ).encode(),
        )
        self.protected = True

    def get(self, **fields):
        self.assertEqual(fields["owner"] + "/" + fields["repository"], SANDBOX)
        self.assertEqual(fields["origin"], "https://api.github.com")
        self.assertEqual(fields["token"], TOKEN)
        resource, selector = fields["resource"], fields["selector"]
        values = {
            ("repository", None): dict(id=12, full_name=SANDBOX),
            ("workflow", "receiver.yml"): dict(
                id=34, path=".github/workflows/receiver.yml", state="active"
            ),
            ("branch", "main"): dict(
                name="main", protected=self.protected, commit=dict(sha=SHA)
            ),
            ("tag_ref", "main"): None,
            ("run", "56"): dict(
                id=56,
                workflow_id=34,
                repository=dict(id=12, full_name=SANDBOX),
                head_sha=SHA,
                head_branch="main",
                event="workflow_dispatch",
                status="completed",
                conclusion="success",
                url=f"https://api.github.com/repos/{SANDBOX}/actions/runs/56",
                html_url=f"https://github.com/{SANDBOX}/actions/runs/56",
            ),
        }
        value = values[(resource, selector)]
        return DispatchResponse(
            404 if value is None else 200, json.dumps(value).encode()
        )

    def test_live_probe_dispatches_exact_two_inputs_once_and_only_emits_safe_dtos(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = qualify(self.env, transport=self.transport)
        sent = self.transport.post_registered.call_args.kwargs
        body = json.loads(sent["payload_bytes"])
        self.assertEqual(set(body["inputs"]), {"operation_id", "binding_digest"})
        self.assertEqual(body["ref"], "main")
        self.assertEqual(sent["workflow"], "receiver.yml")
        self.transport.post_registered.assert_called_once()
        self.assertEqual(result["receiver_evidence"], "not_established")
        self.assertEqual(result["deployment_evidence"], "not_established")
        safe = output.getvalue() + Path(self.env["GITHUB_STEP_SUMMARY"]).read_text()
        self.assertIn('"dispatch_http_status": 200', safe)
        self.assertIn("/actions/runs/56", safe)
        self.assertNotIn(TOKEN, safe)
        self.assertNotIn("synthetic-unused-never-transmitted", safe)
        self.assertNotIn("payload_bytes", safe)
        with self.assertRaises(FileExistsError):
            qualify(self.env, transport=self.transport)
        self.transport.post_registered.assert_called_once()

    def test_context_overrides_and_reruns_fail_before_network(self):
        for field, value in (
            ("GITHUB_REPOSITORY", "other/repo"),
            ("GITHUB_REF", "refs/heads/other"),
            ("GITHUB_RUN_ATTEMPT", "2"),
            ("APP_COMMIT", "main"),
            ("APP_COMMIT", "a" * 40 + "\n"),
            ("GITHUB_SHA", "bad"),
            ("GITHUB_EVENT_NAME", "pull_request"),
            ("GITHUB_ACTIONS", "false"),
            ("SANDBOX_DISPATCH_TOKEN", ""),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                qualify({**self.env, field: value}, transport=self.transport)
        self.transport.get_registered.assert_not_called()
        self.transport.post_registered.assert_not_called()

    def test_unprotected_or_moved_main_denies_before_dispatch(self):
        self.protected = False
        with self.assertRaises(ValueError):
            qualify(self.env, transport=self.transport)
        self.protected = True
        with self.assertRaises(ValueError):
            qualify({**self.env, "GITHUB_SHA": "c" * 40}, transport=self.transport)
        self.transport.post_registered.assert_not_called()

    def test_synthetic_source_revision_and_fresh_deadlines_are_distinct(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        snapshot = resolve_snapshot(
            self.transport, TOKEN, SHA, now.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        envelope = synthetic_envelope(snapshot, "packet1-123", now)
        decision = json.loads(envelope.payload_bytes)["decision"]
        self.assertNotEqual(decision["provenance"]["source"]["commit_sha"], SHA)
        self.assertEqual(decision["pipeline_workflow_revision"], SHA)
        expiry = datetime.strptime(
            decision["approval_deadline"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        self.assertEqual((expiry - now).total_seconds(), 600)

    def test_dispatch_failure_is_not_retried_and_marker_survives(self):
        self.transport.post_registered.side_effect = RuntimeError(
            "sensitive remote body"
        )
        with self.assertRaises(Exception):
            qualify(self.env, transport=self.transport)
        self.assertTrue(
            (Path(self.directory.name) / "packet1-123.dispatch-attempted").exists()
        )
        with self.assertRaises(FileExistsError):
            qualify(self.env, transport=self.transport)
        self.transport.post_registered.assert_called_once()

    def test_exact_workflow_heredoc_preserves_five_locked_hash_blocks(self):
        root = Path(__file__).resolve().parents[2]
        workflow = yaml.safe_load(
            (
                root / "docs/verification/infra-automation/16-11/sandbox/qualify.yml"
            ).read_text()
        )
        step = next(
            step
            for step in workflow["jobs"]["qualify"]["steps"]
            if step.get("name") == "Install only existing locked adapter dependencies"
        )
        code = step["run"].split("python - <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        app = Path(self.directory.name) / "app"
        app.mkdir()
        shutil.copyfile(root / "requirements.txt", app / "requirements.txt")
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=app,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        locked = (app.parent / "adapter-requirements.txt").read_text()
        self.assertEqual(locked.count("=="), 5)
        self.assertGreaterEqual(locked.count("--hash=sha256:"), 5)
        self.assertNotIn("\\n", locked)
        self.assertTrue(locked.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
