"""Strict engine state and immutable fixture parity."""

from __future__ import annotations
import json
from pathlib import Path
import unittest
from pydantic import ValidationError
from infra_automation import state

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads(
    (ROOT / "tests/fixtures/infra_automation/engine_v1/contract.json").read_text()
)


class EngineStateTests(unittest.TestCase):
    def test_exact_edges(self):
        for kind in ("run", "attempt"):
            edges = FIXTURE[kind + "_edges"]
            validator = getattr(state, "require_" + kind + "_transition")
            for old in edges:
                for new in edges:
                    if new in edges[old]:
                        validator(old, new)
                    else:
                        with self.assertRaises(ValueError):
                            validator(old, new)
            with self.assertRaises(ValueError):
                validator("unknown", "running")

    def test_strict_requests(self):
        self.assertEqual(
            state.RunRequest(**FIXTURE["request"]).total_timeout_seconds, 3600
        )
        for case in FIXTURE["invalid_requests"]:
            with self.assertRaises(ValidationError):
                state.RunRequest(**{**FIXTURE["request"], case["field"]: case["value"]})

    def test_schema(self):
        self.assertEqual(
            json.loads((ROOT / "schemas/infra-automation/engine-v1.json").read_text()),
            state.engine_json_schema(),
        )

    def test_handles_do_not_expose_secrets(self):
        handle = state.CoordinatorHandle(
            owner_id="owner", owner_secret="a" * 64, generation=1
        )
        self.assertNotIn("a" * 64, repr(handle))
        self.assertNotIn("owner_secret", json.dumps(state.engine_json_schema()))

    def test_log_bytes_and_timestamp_validation(self):
        from pydantic import TypeAdapter

        for text in ("é" * 8193, "\ud800"):
            with self.assertRaises(ValidationError):
                state.LogChunk(sequence=1, text=text)
        for stamp in ("tomorrow", "2026-02-30T00:00:00Z", "2026-10-19T00:00:00+00:00"):
            with self.assertRaises(ValidationError):
                TypeAdapter(state.UTCText).validate_python(stamp)

    def test_wire_states_and_server_bounds_match_frozen_fixture(self):
        from typing import get_args

        frozen = json.loads(
            (ROOT / "schemas/infra-automation/state-v1.json").read_text()
        )
        for name, alias in (("run", state.RunState), ("attempt", state.AttemptState)):
            self.assertEqual(list(get_args(alias)), FIXTURE[name + "_states"])
            self.assertEqual(
                list(get_args(alias)), frozen["properties"][name + "_state"]["enum"]
            )
        for name, value in state.EngineBounds().model_dump().items():
            self.assertEqual(value, FIXTURE["defaults"][name])
            with self.assertRaises(ValidationError):
                state.EngineBounds(**{name: 0})
            with self.assertRaises(ValidationError):
                state.EngineBounds(**{name: value + 1})
