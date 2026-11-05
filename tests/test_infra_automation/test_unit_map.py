"""Declared unit inventory rejects incomplete scope before deterministic scheduling."""

from __future__ import annotations

import copy
import itertools
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from infra_automation.unit_map import UnitMap, UnitMapError, plan_unit_map


def inventory():
    return {
        "version": 1,
        "affected": ["app"],
        "units": [
            {
                "id": name,
                "source": {
                    "kind": "declared_repository",
                    "repository_id": "repo",
                    "commit_sha": "a" * 40,
                    "path": name,
                },
                "environment": "test",
                "target": "target",
                "prerequisites": prerequisites,
            }
            for name, prerequisites in [
                ("app", ["db", "network"]),
                ("db", ["network"]),
                ("network", []),
            ]
        ],
    }


class UnitMapTests(unittest.TestCase):
    def test_permutations_have_identical_plan(self):
        expected = plan_unit_map(inventory())
        self.assertEqual(expected.waves, [["network"], ["db"], ["app"]])
        for permutation in itertools.permutations(inventory()["units"]):
            value = inventory()
            value["units"] = copy.deepcopy(list(permutation))
            for unit in value["units"]:
                unit["prerequisites"].reverse()
            self.assertEqual(plan_unit_map(value), expected)
        self.assertEqual(plan_unit_map(expected.inventory), expected)

    def test_unknown_duplicate_cycle_and_extra_scope_reject_with_location(self):
        mutations = [
            lambda v: v["units"].append(copy.deepcopy(v["units"][0])),
            lambda v: v["units"][0]["prerequisites"].append("missing"),
            lambda v: v["units"][0]["prerequisites"].append("db"),
            lambda v: v["units"][2]["prerequisites"].append("app"),
            lambda v: v["affected"].append("missing"),
            lambda v: v["affected"].append("app"),
            lambda v: v.update(affected=["network"]),
        ]
        for mutation in mutations:
            value = inventory()
            mutation(value)
            with self.subTest(value=value), self.assertRaises(UnitMapError) as caught:
                plan_unit_map(value)
            self.assertTrue(caught.exception.errors[0]["path"])

    def test_every_identity_mutation_changes_digest(self):
        original = plan_unit_map(inventory()).map_digest
        for field, replacement in [("environment", "prod"), ("target", "other")]:
            value = inventory()
            value["units"][0][field] = replacement
            self.assertNotEqual(plan_unit_map(value).map_digest, original)
        for field, replacement in [
            ("repository_id", "other"),
            ("commit_sha", "b" * 40),
            ("path", "other"),
        ]:
            value = inventory()
            value["units"][0]["source"][field] = replacement
            self.assertNotEqual(plan_unit_map(value).map_digest, original)

    def test_closed_strict_schema_and_paths(self):
        for path in [
            "/abs",
            "../up",
            "a/../b",
            "a//b",
            "./a",
            "a\\b",
            "a/",
            "",
            "a\x00b",
        ]:
            value = inventory()
            value["units"][0]["source"]["path"] = path
            with self.subTest(path=path), self.assertRaises(UnitMapError):
                plan_unit_map(value)
        for field, replacement in [
            ("version", True),
            ("version", "1"),
            ("extra", 1),
            ("affected", "app"),
        ]:
            value = inventory()
            value[field] = replacement
            with self.subTest(field=field), self.assertRaises(UnitMapError):
                plan_unit_map(value)

    def test_wire_duplicates_and_size_reject(self):
        with self.assertRaises(UnitMapError):
            plan_unit_map('{"version":1,"version":1,"units":[],"affected":[]}')
        with self.assertRaises(UnitMapError):
            plan_unit_map(b" " * 131073)
        with self.assertRaises(UnitMapError):
            plan_unit_map("[" * 1000)

    def test_unit_and_edge_boundaries(self):
        value = inventory()
        base = value["units"][0]
        value["units"] = [
            dict(copy.deepcopy(base), id=f"u{i:02}", prerequisites=[])
            for i in range(25)
        ]
        value["affected"] = [u["id"] for u in value["units"]]
        self.assertEqual(len(plan_unit_map(value).waves[0]), 25)
        value["units"].append(dict(copy.deepcopy(base), id="excess", prerequisites=[]))
        with self.assertRaises(UnitMapError):
            plan_unit_map(value)
        value["units"].pop()
        edges = [(i, j) for i in range(25) for j in range(i)]
        for i, j in edges[:200]:
            value["units"][i]["prerequisites"].append(f"u{j:02}")
        plan_unit_map(value)
        i, j = edges[200]
        value["units"][i]["prerequisites"].append(f"u{j:02}")
        with self.assertRaises(UnitMapError):
            plan_unit_map(value)

    def test_unchecked_construct_is_revalidated(self):
        value = UnitMap.model_construct(**inventory())
        value.__dict__["units"][0]["source"]["commit_sha"] = "invalid"
        with self.assertRaises(UnitMapError):
            plan_unit_map(value)

    def test_exact_byte_boundary_and_uploaded_root(self):
        value = inventory()
        value["units"][0]["source"] = {"kind": "uploaded", "path": "."}
        expected = plan_unit_map(value)
        self.assertEqual(
            expected.inventory.units[0].source.repository_source, "unavailable"
        )
        raw = json.dumps(value).encode()
        self.assertEqual(plan_unit_map(raw + b" " * (131072 - len(raw))), expected)
        with self.assertRaises(UnitMapError):
            plan_unit_map(raw + b" " * (131073 - len(raw)))
        value["units"][0]["source"]["commit_sha"] = "a" * 40
        with self.assertRaises(UnitMapError):
            plan_unit_map(value)

    def test_diagnostic_count_and_reflection_are_bounded(self):
        value = inventory()
        value["units"] = [copy.deepcopy(value["units"][0]) for _ in range(25)]
        for unit in value["units"]:
            unit["prerequisites"] = ["missing"] * 25
        with self.assertRaises(UnitMapError) as caught:
            plan_unit_map(value)
        self.assertEqual(len(caught.exception.errors), 50)
        value = inventory()
        value["private-secret-key"] = "private-secret-value"
        with self.assertRaises(UnitMapError) as caught:
            plan_unit_map(value)
        self.assertNotIn("private-secret", repr(caught.exception.errors))

    def test_affected_order_and_input_are_preserved(self):
        value = inventory()
        value["affected"] = ["network", "app"]
        before = copy.deepcopy(value)
        expected = plan_unit_map(value)
        self.assertEqual(value, before)
        value["affected"].reverse()
        self.assertEqual(plan_unit_map(value), expected)
        value["units"][0]["prerequisites"] = ["db"]
        changed = plan_unit_map(value)
        self.assertEqual(changed.waves, expected.waves)
        self.assertNotEqual(changed.map_digest, expected.map_digest)
        self.assertNotEqual(changed.waves_digest, expected.waves_digest)

    def test_key_byte_limits_reject_before_serialization(self):
        cases = [
            {"x" * 131073: None},
            {"é" * 65537: None},
            {"a" * 65536: None, "b" * 65537: None},
            {"a" * 65536: {"b" * 65537: None}},
        ]
        unchecked = UnitMap.model_construct(**inventory())
        unchecked.__dict__["x" * 131073] = None
        cases.append(unchecked)
        for value in cases:
            with self.subTest(type=type(value).__name__):
                with patch("infra_automation.unit_map._canonical") as serializer:
                    with self.assertRaises(UnitMapError) as caught:
                        plan_unit_map(value)
                    self.assertEqual(
                        caught.exception.errors[0]["code"], "resource_limit"
                    )
                    serializer.assert_not_called()

    def test_exported_schema_matches_model(self):
        schema = json.loads(
            Path("schemas/infra-automation/unit-map-v1.json").read_text()
        )
        self.assertEqual(schema, UnitMap.model_json_schema())
