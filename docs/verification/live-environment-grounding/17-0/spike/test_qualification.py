"""Disposable feasibility checks; synthetic fixtures do not qualify AWS support."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

from qualification import (
    ALLOWED,
    authorize,
    collect,
    dry_run,
    extract,
    policy_actions,
    validate_config,
)


class QualificationTests(unittest.TestCase):
    def test_readiness_fails_closed(self):
        from qualification import readiness

        gates = dict(
            rfc_accepted=True,
            dependency_approved=True,
            feasibility_complete=True,
            no_blocking_gaps=True,
            independent_review=True,
        )
        self.assertEqual(readiness(**gates), "READY")
        for key in gates:
            with self.subTest(missing=key):
                self.assertEqual(readiness(**dict(gates, **{key: False})), "NOT READY")

    def test_all_families_exact_parameters(self):
        rows = []
        for family, identity in [
            ("aws_instance", "i-synthetic"),
            ("aws_security_group", "sg-synthetic"),
            ("aws_db_instance", "db-synthetic"),
        ]:
            rows.append(
                dict(
                    address=family + ".test",
                    type=family,
                    change=dict(actions=["update"], before=dict(id=identity)),
                )
            )
        self.assertEqual(
            dry_run(dict(format_version="1.2", resource_changes=rows)),
            [
                {
                    "action": "ec2:DescribeInstances",
                    "params": {"InstanceIds": ["i-synthetic"]},
                },
                {
                    "action": "ec2:DescribeSecurityGroups",
                    "params": {"GroupIds": ["sg-synthetic"]},
                },
                {
                    "action": "rds:DescribeDBInstances",
                    "params": {"DBInstanceIdentifier": "db-synthetic"},
                },
            ],
        )

    def test_denies_before_construction(self):
        factory = Mock()
        for action in (
            "ec2:TerminateInstances",
            "ec2:DescribeEverything",
            "*",
            "s3:PutObject",
        ):
            with self.subTest(action=action), self.assertRaises(PermissionError):
                authorize(action, {}, factory)
        factory.assert_not_called()

    def test_exact_policy_and_mutating_verb_assertion(self):
        self.assertEqual(policy_actions(), set(ALLOWED))
        from qualification import assert_read_only

        with self.assertRaises(ValueError):
            assert_read_only(set(ALLOWED) | {"ec2:TerminateInstances"})

    def test_config_corpus(self):
        for key in ("endpoint_url", "role_arn", "account", "host", "profile", "region"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_config({key: "http://169.254.169.254/latest/meta-data/"})
        self.assertEqual(
            validate_config({"region": "us-east-1"}), {"region": "us-east-1"}
        )

    def test_empty_environment_dry_run(self):
        script = Path(__file__).with_name("qualification.py").resolve()
        with tempfile.TemporaryDirectory() as home:
            result = subprocess.run(
                [sys.executable, str(script), "dry-run"],
                env={"HOME": home},
                capture_output=True,
                text=True,
                check=True,
            )
        self.assertEqual(
            json.loads(result.stdout)["calls"],
            dry_run(json.loads(script.with_name("plan.json").read_text())),
        )
        self.assertEqual(json.loads(result.stdout)["issued"], 0)
        self.assertEqual(result.stderr, "")

    def test_formats_and_sources(self):
        base = Path(__file__).parent
        for fixture in sorted(base.glob("plan-*.json")):
            plan = json.loads(fixture.read_text())
            rows = extract(plan)
            self.assertEqual(rows[0]["source"], "prior_state")
            self.assertEqual(rows[0]["values"]["id"], "i-00000000000000001")
        plan = json.loads((base / "plan.json").read_text())
        plan["prior_state"] = None
        self.assertEqual(extract(plan)[0]["source"], "change.before")
        plan.pop("prior_state")
        self.assertEqual(extract(plan)[0]["source"], "change.before")
        plan["resource_changes"][0]["change"]["before"] = None
        self.assertEqual(extract(plan)[0]["status"], "unknown")
        plan["resource_changes"][0]["change"]["actions"] = ["create"]
        self.assertEqual(extract(plan)[0]["status"], "no_live_counterpart")
        plan["format_version"] = "99.0"
        with self.assertRaises(ValueError):
            extract(plan)

    def test_bounded_collection(self):
        import threading

        calls = [("ec2:DescribeInstances", {})] * 100
        report = collect(calls, deadline=0.03, concurrency=2, budget=10, delay=0.01)
        self.assertLessEqual(report["issued"], 10)
        self.assertLessEqual(report["peak_concurrency"], 2)
        self.assertTrue(report["partial"])
        self.assertLess(report["elapsed_seconds"], 0.15)
        stop = threading.Event()
        stop.set()
        self.assertEqual(collect(calls, cancel=stop)["issued"], 0)

    def test_secret_absence(self):
        from qualification import screened_observation

        secret = "SYNTHETIC-credential-canary-17-0"
        output = json.dumps(
            screened_observation({"password": secret, "echo": secret}, secret)
        )
        self.assertNotIn(secret, output)
        self.assertIn("REDACTED", output)


if __name__ == "__main__":
    unittest.main()
