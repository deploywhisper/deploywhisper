"""Contextual Terraform secrets cannot enter runner upload persistence."""

from __future__ import annotations

import json
import unittest

from infra_automation.lifecycle import LifecycleError
from infra_automation.runner.claims import screened_upload
from services.infra_automation_support import canonical, digest


class RunnerSensitiveDefaultsTests(unittest.TestCase):
    def upload(self, name, content):
        raw = canonical([{"name": name, "content": content}])
        return screened_upload(raw, digest(raw))

    def test_hcl_contextual_defaults_are_rejected_without_echo(self):
        for content in (
            'variable "password" { default = "synthetic-secret-value" }',
            'variable "db_password" { default = { nested = "synthetic-secret-value" } }',
            'variable "innocent" { sensitive = true\n default = "synthetic-secret-value" }',
            'variable "innocent" { default = "synthetic-secret-value"\n sensitive = true }',
            'variable "pass\\u0077ord" { default = "synthetic-secret-value" }',
            'output "innocent" { sensitive = true\n value = "synthetic-secret-value" }',
        ):
            with self.subTest(content=content):
                with self.assertRaises(LifecycleError) as caught:
                    self.upload("main.tf", content)
                self.assertNotIn("synthetic-secret-value", str(caught.exception))

    def test_tf_json_contextual_defaults_are_rejected(self):
        for document in (
            {"variable": {"password": {"default": "synthetic-secret-value"}}},
            {
                "variable": {
                    "innocent": {"default": "synthetic-secret-value", "sensitive": True}
                }
            },
            {
                "output": {
                    "innocent": {"value": "synthetic-secret-value", "sensitive": True}
                }
            },
        ):
            with self.subTest(document=document), self.assertRaises(LifecycleError):
                self.upload("main.tf.json", json.dumps(document))

    def test_plain_defaults_and_required_sensitive_inputs_remain_valid(self):
        for name, content in (
            ("main.tf", 'variable "region" { default = "us-east-1" }'),
            ("main.tf", 'variable "password" { type = string }'),
            (
                "main.tf",
                'variable "private_input" { sensitive = true\n type = string }',
            ),
        ):
            with self.subTest(name=name, content=content):
                self.assertIsInstance(self.upload(name, content), bytes)

    def test_invalid_hcl_is_denied_without_parser_echo(self):
        with self.assertRaises(LifecycleError) as caught:
            self.upload(
                "main.tf", 'variable "innocent" { default = "synthetic-secret-value"'
            )
        self.assertNotIn("synthetic-secret-value", str(caught.exception))
