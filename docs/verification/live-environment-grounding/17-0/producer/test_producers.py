"""Recorded real producer shape and absent-prior-state fallback qualification."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / "spike"))
from qualification import extract  # noqa: E402
from generate import download  # noqa: E402


class ProducerTests(unittest.TestCase):
    def test_download_rejects_untrusted_url_before_connection(self):
        for url in (
            "file:///etc/passwd",
            "http://github.com/",
            "https://evil.invalid/",
            "https://user@github.com/",
            "https://github.com:444/",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                download(url, BASE / "must-not-exist")

    def test_four_real_producer_profiles_and_prior_state(self):
        fixtures = sorted(BASE.glob("terraform-*.json")) + sorted(
            BASE.glob("tofu-*.json")
        )
        self.assertEqual(len(fixtures), 4)
        for fixture in fixtures:
            with self.subTest(fixture=fixture.name):
                plan = json.loads(fixture.read_text())
                self.assertEqual(plan["format_version"], "1.2")
                rows = {row["address"]: row for row in extract(plan)}
                self.assertEqual(
                    rows["terraform_data.changed"]["source"], "prior_state"
                )
                self.assertEqual(
                    rows["terraform_data.changed"]["values"]["input"], "before"
                )
                self.assertEqual(
                    rows["terraform_data.removed"]["values"]["input"], "remove-me"
                )
                self.assertEqual(
                    rows["module.nested.terraform_data.nested"]["values"]["input"],
                    "nested-before",
                )
                self.assertEqual(
                    rows["terraform_data.created"]["status"], "no_live_counterpart"
                )
                for prior in ("absent", None):
                    fallback = copy.deepcopy(plan)
                    if prior == "absent":
                        fallback.pop("prior_state")
                    else:
                        fallback["prior_state"] = None
                    changed = {row["address"]: row for row in extract(fallback)}[
                        "terraform_data.changed"
                    ]
                    self.assertEqual(changed["source"], "change.before")
                    self.assertEqual(changed["values"]["input"], "before")
                missing = copy.deepcopy(plan)
                missing.pop("prior_state")
                next(
                    row
                    for row in missing["resource_changes"]
                    if row["address"] == "terraform_data.changed"
                )["change"]["before"] = None
                unknown = {row["address"]: row for row in extract(missing)}[
                    "terraform_data.changed"
                ]
                self.assertEqual(unknown["status"], "unknown")

    def test_projection_contains_only_synthetic_identity_and_input(self):
        fixtures = list(BASE.glob("terraform-*.json")) + list(BASE.glob("tofu-*.json"))
        self.assertEqual(len(fixtures), 4)
        for fixture in fixtures:
            with self.subTest(fixture=fixture.name):
                plan = json.loads(fixture.read_text())
                self.assertNotIn("configuration", plan)
                self.assertNotIn("planned_values", plan)
                for row in plan["resource_changes"]:
                    self.assertEqual(row["type"], "terraform_data")
                    for key in ("before", "after"):
                        value = row["change"][key]
                        if value is not None:
                            self.assertEqual(set(value), {"id", "input"})
                            self.assertIn(
                                value["input"],
                                {
                                    "before",
                                    "after",
                                    "new",
                                    "remove-me",
                                    "nested-before",
                                    "nested-after",
                                },
                            )


if __name__ == "__main__":
    unittest.main()
