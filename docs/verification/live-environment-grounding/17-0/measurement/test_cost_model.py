"""Provider-price accounting checks for the disposable qualification estimate."""

from __future__ import annotations

import copy
import unittest

from cost_model import estimate_cost, load_catalog


def call(service, operation):
    return {
        "service": service,
        "operation": operation,
        "params": {
            "Bucket": "synthetic-bucket",
            "QueueUrl": "https://sqs.us-east-1.amazonaws.com/000000000000/synthetic",
        },
    }


class ProviderCostTests(unittest.TestCase):
    def test_provider_rates_and_ordered_attempt_budget(self):
        calls = [
            call("s3", "GetBucketVersioning"),
            call("sqs", "GetQueueAttributes"),
            call("ec2", "DescribeInstances"),
        ]
        result = estimate_cost(calls, budget=1)
        self.assertEqual(result["full_manifest"]["estimated_request_usd"], 0.0000008)
        self.assertEqual(result["budget_prefix"]["estimated_request_usd"], 0.0000004)
        self.assertEqual(result["full_manifest"]["intended_calls"], 3)
        self.assertEqual(result["budget_prefix"]["intended_calls"], 1)
        self.assertEqual(result["full_manifest"]["status"], "complete_estimate")

    def test_unknown_operation_is_not_implicitly_free(self):
        result = estimate_cost([call("s3", "GetObject")])
        self.assertIsNone(result["full_manifest"]["estimated_request_usd"])
        self.assertEqual(result["full_manifest"]["status"], "unknown_rates")
        self.assertEqual(result["full_manifest"]["unknown_actions"], ["s3:GetObject"])

    def test_other_region_requires_a_new_pricing_catalog(self):
        with self.assertRaises(ValueError):
            estimate_cost([call("sqs", "GetQueueAttributes")], region="eu-west-1")

    def test_invalid_budget_is_rejected(self):
        for budget in (-1, 0.5, True, float("nan"), float("inf")):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                estimate_cost([], budget=budget)

    def test_invalid_catalog_rate_is_rejected(self):
        for rate in ("NaN", "Infinity", "1e10000", "-0.1", True):
            catalog = copy.deepcopy(load_catalog())
            catalog["operations"]["sqs:GetQueueAttributes"]["usd_per_request"] = rate
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                estimate_cost([call("sqs", "GetQueueAttributes")], catalog=catalog)

    def test_finite_rates_cannot_overflow_charge_or_total_json_numbers(self):
        catalog = copy.deepcopy(load_catalog())
        for action in ("sqs:GetQueueAttributes", "s3:GetBucketVersioning"):
            catalog["operations"][action]["usd_per_request"] = "1e308"
        cases = [
            [call("sqs", "GetQueueAttributes")] * 2,
            [call("sqs", "GetQueueAttributes"), call("s3", "GetBucketVersioning")],
        ]
        for calls in cases:
            with self.subTest(calls=calls), self.assertRaises(ValueError):
                estimate_cost(calls, catalog=catalog)

    def test_every_frozen_operation_has_dated_source_and_classification(self):
        catalog = load_catalog()
        self.assertEqual(len(catalog["operations"]), 33)
        self.assertEqual(catalog["observed_on"], "2026-11-12")
        for item in catalog["operations"].values():
            self.assertIn(
                item["classification"],
                {
                    "metered_request",
                    "no_additional_charge",
                    "control_plane_meter_inference",
                },
            )
            self.assertTrue(item["source_ids"])
            for source in item["source_ids"]:
                self.assertIn(source, catalog["sources"])

    def test_empty_and_zero_budget_estimates_are_zero_not_unknown(self):
        result = estimate_cost([call("sqs", "GetQueueAttributes")], budget=0)
        self.assertEqual(result["budget_prefix"]["estimated_request_usd"], 0)
        self.assertEqual(result["budget_prefix"]["status"], "complete_estimate")
        self.assertEqual(estimate_cost([])["full_manifest"]["estimated_request_usd"], 0)

    def test_changing_catalog_to_missing_rate_never_defaults_to_zero(self):
        catalog = copy.deepcopy(load_catalog())
        del catalog["operations"]["sqs:GetQueueAttributes"]
        result = estimate_cost([call("sqs", "GetQueueAttributes")], catalog=catalog)
        self.assertIsNone(result["full_manifest"]["estimated_request_usd"])

    def test_per_action_counts_sum_to_manifest(self):
        result = estimate_cost([call("sqs", "GetQueueAttributes")] * 3)
        rows = result["full_manifest"]["per_action"]
        self.assertEqual(rows[0]["calls"], 3)
        self.assertEqual(rows[0]["estimated_request_usd"], 0.0000012)

    def test_unsupported_queue_and_bucket_profiles_are_unknown(self):
        for service, operation, params in [
            (
                "sqs",
                "GetQueueAttributes",
                {
                    "QueueUrl": "https://sqs.us-east-1.amazonaws.com/000000000000/synthetic.fifo"
                },
            ),
            (
                "sqs",
                "GetQueueAttributes",
                {
                    "QueueUrl": "https://sqs.eu-west-1.amazonaws.com/000000000000/synthetic"
                },
            ),
            ("s3", "GetBucketVersioning", {"Bucket": "synthetic--x-s3"}),
            (
                "s3",
                "GetBucketTagging",
                {"Bucket": "arn:aws:s3:us-east-1:000000000000:accesspoint/synthetic"},
            ),
        ]:
            with self.subTest(params=params):
                result = estimate_cost(
                    [{"service": service, "operation": operation, "params": params}]
                )
                self.assertIsNone(result["full_manifest"]["estimated_request_usd"])

    def test_bad_call_and_region_types_are_rejected(self):
        for calls in ([{}], [{"service": "sqs", "operation": None}]):
            with self.assertRaises(ValueError):
                estimate_cost(calls)
        with self.assertRaises(ValueError):
            estimate_cost([], region=True)
