"""Boundary checks for disposable mixed-plan measurement."""

from __future__ import annotations

import copy
import contextlib
from concurrent.futures import ALL_COMPLETED, wait as real_wait
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import benchmark

from benchmark import (
    build_calls,
    generate_plan,
    measure,
    validate_contract_calls,
    matches_postfilter,
)


class MeasurementTests(unittest.TestCase):
    def test_mixed_plan_and_no_counterpart(self):
        plan = generate_plan()
        self.assertEqual(len(plan["resource_changes"]), 1000)
        self.assertEqual(len({r["type"] for r in plan["resource_changes"]}), 25)
        calls = build_calls(plan)
        self.assertEqual(len(calls), 900)
        self.assertTrue(plan["prior_state"]["values"]["root_module"]["child_modules"])
        self.assertEqual(len({c["address"] for c in calls}), 900)

    def test_every_request_matches_frozen_family_keys_and_fixed_values(self):
        plan = generate_plan()
        calls = build_calls(plan)
        validate_contract_calls(plan, calls)
        asg = next(call for call in calls if call["family"] == "aws_autoscaling_group")
        bad = copy.deepcopy(asg)
        bad["params"]["MaxRecords"] = 1
        with self.assertRaises(ValueError):
            validate_contract_calls(plan, [bad])
        mapping = next(
            call
            for call in calls
            if call["family"] == "aws_lambda_event_source_mapping"
        )
        self.assertEqual(mapping["operation"], "ListEventSourceMappings")
        self.assertEqual(
            set(mapping["params"]), {"FunctionName", "EventSourceArn", "MaxItems"}
        )
        self.assertEqual(mapping["params"]["MaxItems"], 100)
        bad = copy.deepcopy(mapping)
        del bad["params"]["FunctionName"]
        with self.assertRaises(ValueError):
            validate_contract_calls(plan, [bad])

    def test_event_mapping_uuid_and_parent_postfilter(self):
        call = next(
            call
            for call in build_calls(generate_plan())
            if call["family"] == "aws_lambda_event_source_mapping"
        )
        matching = dict(call["postfilter"])
        self.assertTrue(matches_postfilter(call, matching))
        for key in ("UUID", "FunctionArn", "EventSourceArn"):
            with self.subTest(key=key):
                self.assertFalse(
                    matches_postfilter(call, dict(matching, **{key: "unrelated"}))
                )
        plan = generate_plan()
        resource = next(
            r
            for r in plan["resource_changes"]
            if r["type"] == "aws_lambda_event_source_mapping" and r["change"]["before"]
        )
        del resource["change"]["before"]["function_arn"]
        with self.assertRaises(KeyError):
            build_calls(plan)

    def test_queue_url_is_reconstructed_not_forwarded(self):
        plan = generate_plan()
        queue = next(
            r
            for r in plan["resource_changes"]
            if r["type"] == "aws_sqs_queue" and r["change"]["before"]
        )
        queue["change"]["before"]["canonical_queue_url"] = "http://169.254.169.254/"
        call = next(
            call for call in build_calls(plan) if call["address"] == queue["address"]
        )
        self.assertEqual(
            call["params"]["QueueUrl"],
            "https://sqs.us-east-1.amazonaws.com/000000000000/"
            + queue["change"]["before"]["name"],
        )
        self.assertEqual(
            call["params"]["AttributeNames"],
            [
                "QueueArn",
                "ApproximateNumberOfMessages",
                "RedrivePolicy",
                "MessageRetentionPeriod",
                "LastModifiedTimestamp",
            ],
        )

    def test_call_budget_and_partial_results(self):
        result = measure(build_calls(generate_plan()), latency=0.001, budget=13)
        self.assertEqual(result["issued"], 13)
        self.assertEqual(result["completed"], 13)
        self.assertEqual(result["unread"], 887)
        self.assertTrue(result["partial"])
        self.assertLessEqual(result["peak_concurrency"], 4)

    def test_deadline_and_inflight_cancel(self):
        calls = build_calls(generate_plan())
        result = measure(calls, latency=1, deadline=0.03)
        self.assertLess(result["elapsed_seconds"], 0.2)
        self.assertTrue(result["partial"])
        self.assertEqual(result["completed"], 0)
        stop = threading.Event()
        stop.set()
        self.assertEqual(measure(calls, cancel=stop)["issued"], 0)
        stop.clear()
        timer = threading.Timer(0.02, stop.set)
        timer.start()
        try:
            result = measure(calls, cancel=stop, latency=1)
        finally:
            timer.cancel()
        self.assertLess(result["elapsed_seconds"], 0.2)
        self.assertEqual(result["completed"], 0)

    def test_per_call_timeout_never_counts_as_complete(self):
        calls = build_calls(generate_plan())
        result = measure(calls, latency=0.05, per_call_timeout=0.005, budget=4)
        self.assertEqual(result["completed"], 0)
        self.assertTrue(result["partial"])
        self.assertLess(result["elapsed_seconds"], 0.2)

    def test_throttle_has_no_hidden_retry(self):
        calls = build_calls(generate_plan())
        result = measure(calls, latency=0.001, budget=12, throttle_every=3)
        self.assertEqual(result["issued"], 12)
        self.assertEqual(result["throttled"], 4)
        self.assertEqual(result["completed"], 8)
        self.assertTrue(result["partial"])
        self.assertGreaterEqual(result["backoff_events"], 1)

    def test_invalid_limits_fail_before_dispatch(self):
        for values in ({"concurrency": 0}, {"budget": -1}, {"deadline": -1}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                measure([], **values)

    def test_required_postfilters_cannot_be_removed_or_changed(self):
        plan = generate_plan()
        for call in build_calls(plan):
            if call["family"] not in {
                "aws_lambda_event_source_mapping",
                "aws_route53_record",
            }:
                continue
            bad = copy.deepcopy(call)
            bad.pop("postfilter")
            with self.subTest(family=call["family"]):
                with self.assertRaises(ValueError):
                    validate_contract_calls(plan, [bad])
                self.assertFalse(matches_postfilter(bad, {}))
            bad.pop("family")
            self.assertFalse(matches_postfilter(bad, {}))
            bad = copy.deepcopy(call)
            bad["postfilter"].pop(next(iter(bad["postfilter"])))
            with self.assertRaises(ValueError):
                validate_contract_calls(plan, [bad])
            self.assertFalse(matches_postfilter(bad, {}))
            bad = copy.deepcopy(call)
            bad["postfilter"] = dict.fromkeys(call["postfilter"])
            self.assertFalse(matches_postfilter(bad, {}))

    def test_route53_exact_set_identifier_and_simple_record(self):
        plan = generate_plan()
        resource = next(
            r
            for r in plan["resource_changes"]
            if r["type"] == "aws_route53_record" and r["change"]["before"]
        )
        for identifier in (None, "weighted-a"):
            values = resource["change"]["before"]
            if identifier is None:
                values.pop("set_identifier", None)
            else:
                values["set_identifier"] = identifier
            call = next(
                c for c in build_calls(plan) if c["address"] == resource["address"]
            )
            self.assertEqual(call["postfilter"]["SetIdentifier"], identifier)
            exact = dict(call["postfilter"])
            self.assertTrue(matches_postfilter(call, exact))
            self.assertFalse(
                matches_postfilter(call, dict(exact, SetIdentifier="other"))
            )
            if identifier is not None:
                exact.pop("SetIdentifier")
                self.assertFalse(matches_postfilter(call, exact))

    def test_model_validation_ignores_environment_and_home_models(self):
        try:
            import botocore
            from botocore.loaders import Loader
            from botocore.exceptions import ParamValidationError
        except ImportError:
            self.skipTest("isolated SDK interpreter required")
        trusted = str(Path(botocore.__file__).resolve().parent / "data")
        loader = Loader(
            extra_search_paths=[trusted], include_default_search_paths=False
        )
        model = loader.load_service_model("ec2", "service-2")
        model["shapes"]["DescribeInstancesRequest"]["members"]["ForgedInput"] = {
            "shape": "String"
        }
        forged = [
            {
                "service": "ec2",
                "operation": "DescribeInstances",
                "params": {"ForgedInput": "bad"},
            }
        ]
        for origin in ("environment", "home"):
            with self.subTest(origin=origin), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp) / "ec2" / "2016-11-15"
                folder.mkdir(parents=True)
                (folder / "service-2.json").write_text(json.dumps(model))
                with (
                    patch.dict(
                        os.environ,
                        {"AWS_DATA_PATH": temp if origin == "environment" else ""},
                    ),
                    patch.object(
                        Loader,
                        "CUSTOMER_DATA_PATH",
                        temp if origin == "home" else os.devnull,
                    ),
                ):
                    with self.assertRaises(ParamValidationError):
                        benchmark.validate_sdk_models(forged)

    def test_cooldown_drains_results_finished_before_deadline(self):
        def wait_one(futures, **kwargs):
            real_wait(futures, return_when=ALL_COMPLETED)
            selected = next(iter(futures))
            return {selected}, futures - {selected}

        with patch.object(benchmark, "wait", wait_one):
            result = measure(
                [{}] * 4,
                latency=0,
                deadline=0.03,
                concurrency=4,
                budget=4,
                throttle_every=1,
                backoff=0.1,
            )
        self.assertEqual(result["issued"], 4)
        self.assertEqual(result["throttled"], 4)

    def test_hardware_identity_never_inherits_another_hosts_label(self):
        with (
            patch.object(benchmark.platform, "system", return_value="Linux"),
            patch.object(benchmark.platform, "processor", return_value="Synthetic CPU"),
            patch.object(benchmark.subprocess, "run") as command,
        ):
            result = benchmark.hardware_identity()
        self.assertEqual(result["cpu"], "Synthetic CPU")
        self.assertEqual(result["model"], "unknown")
        command.assert_not_called()
        with (
            patch.object(benchmark.platform, "system", return_value="Darwin"),
            patch.object(
                benchmark.subprocess,
                "run",
                side_effect=[
                    benchmark.subprocess.CompletedProcess([], 0, "Detected CPU\n"),
                    benchmark.subprocess.CompletedProcess([], 0, "DetectedModel\n"),
                ],
            ) as command,
        ):
            result = benchmark.hardware_identity()
        self.assertEqual(result["cpu"], "Detected CPU")
        self.assertEqual(result["model"], "DetectedModel")
        self.assertTrue(
            all(call.kwargs["timeout"] == 1 for call in command.call_args_list)
        )

    def test_invalid_numeric_limits_fail_before_executor_creation(self):
        invalid = []
        for name in ("concurrency", "budget", "throttle_every"):
            invalid.extend(
                {name: value} for value in (True, 0.5, float("nan"), float("inf"))
            )
        for name in ("deadline", "latency", "backoff", "per_call_timeout"):
            invalid.extend(
                {name: value} for value in (True, float("nan"), float("inf"), -1)
            )
        with patch.object(
            benchmark,
            "ThreadPoolExecutor",
            side_effect=AssertionError(
                "executor constructed before invalid bounds rejected"
            ),
        ) as executor:
            for kwargs in invalid:
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    measure([{}], **kwargs)
        executor.assert_not_called()

    def test_cli_rejects_nonfinite_rate_before_planning(self):
        for rate in ("nan", "inf", "-1"):
            with (
                self.subTest(rate=rate),
                patch.object(
                    sys,
                    "argv",
                    ["benchmark.py", "--usd-per-1000-calls", rate],
                ),
                patch.object(benchmark, "generate_plan") as plan,
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as exit_code,
            ):
                benchmark.main()
            self.assertEqual(exit_code.exception.code, 2)
            plan.assert_not_called()
        for value in (True, None, 10**1000):
            with (
                self.subTest(value=value),
                self.assertRaises(benchmark.argparse.ArgumentTypeError),
            ):
                benchmark.finite_rate(value)

    def test_main_keeps_provider_cost_and_sensitivity_separate(self):
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["benchmark.py"]),
            patch.object(benchmark.socket.socket, "connect"),
            patch.object(benchmark.socket, "create_connection"),
            patch.object(benchmark, "measure", return_value={"issued": 100}),
            patch.object(benchmark, "hardware_identity", return_value={"cpu": "test"}),
            patch.object(
                benchmark,
                "validate_sdk_models",
                return_value={"validated_requests": 900},
            ),
            contextlib.redirect_stdout(output),
        ):
            benchmark.main()
        result = json.loads(output.getvalue())
        self.assertEqual(
            result["cost_estimate"]["full_manifest"]["status"], "complete_estimate"
        )
        self.assertAlmostEqual(
            result["cost_estimate"]["full_manifest"]["estimated_request_usd"], 0.0000288
        )
        self.assertAlmostEqual(
            result["cost_estimate"]["budget_prefix"]["estimated_request_usd"], 0.0000032
        )
        priced = {
            row["action"]: row
            for row in result["cost_estimate"]["full_manifest"]["per_action"]
        }
        for action in ("s3:GetBucketVersioning", "sqs:GetQueueAttributes"):
            self.assertEqual(priced[action]["usd_per_request"], 0.0000004)
            self.assertTrue(priced[action]["source_ids"])
        self.assertEqual(
            result["sensitivity_estimate"]["usd_per_1000_calls_input"], 0.005
        )


if __name__ == "__main__":
    unittest.main()
