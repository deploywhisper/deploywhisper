"""Regression checks for the production fuzz target's security invariants."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
FUZZ_DIR = ROOT / ".clusterfuzzlite"
SPEC = importlib.util.spec_from_file_location(
    "content_security_fuzzer", FUZZ_DIR / "content_security_fuzzer.py"
)
assert SPEC is not None and SPEC.loader is not None
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


class FuzzingContractTests(unittest.TestCase):
    def test_all_generated_container_modes_screen_credentials(self):
        for mode in range(5):
            for suffix in (b"", bytes(range(256)), b"%25" * 1024):
                with self.subTest(mode=mode, suffix_length=len(suffix)):
                    HARNESS.check_input(bytes([mode]) + suffix)

    def test_seed_corpus_exercises_the_real_invariants(self):
        for seed in sorted((FUZZ_DIR / "corpus").iterdir()):
            with self.subTest(seed=seed.name):
                HARNESS.check_input(seed.read_bytes())

    def test_yaml_object_tags_never_execute_commands(self):
        with patch("os.system") as execute:
            HARNESS.check_input((FUZZ_DIR / "corpus" / "object-tag").read_bytes())
        execute.assert_not_called()

    def test_invariants_reject_a_broken_redactor(self):
        # Prove the harness reports a lost security property rather than merely
        # calling the parser or accepting every outcome.
        with patch(
            "services.content_security.redact_value", side_effect=lambda value: value
        ):
            with self.assertRaisesRegex(AssertionError, "sibling credential echo"):
                HARNESS.check_input(b"synthetic-mutation")

    def test_invariants_detect_input_mutation(self):
        from services.content_security import redact_value

        def mutating_redactor(value):
            screened = redact_value(value)
            value["unexpected_mutation"] = True
            return screened

        with patch(
            "services.content_security.redact_value", side_effect=mutating_redactor
        ):
            with self.assertRaisesRegex(AssertionError, "mutated its input"):
                HARNESS.check_input(b"synthetic-mutation")


if __name__ == "__main__":
    unittest.main()
