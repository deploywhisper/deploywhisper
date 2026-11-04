"""Qualification console output exposes only a fixed public outcome."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import unittest

from scripts.qualify_runner_isolation import emit_status


class QualificationConsoleTests(unittest.TestCase):
    def test_success_and_failure_emit_only_the_public_boolean(self):
        for outcome in (True, False):
            with self.subTest(outcome=outcome):
                output = io.StringIO()
                with redirect_stdout(output):
                    emit_status(outcome)
                self.assertEqual(json.loads(output.getvalue()), {"qualified": outcome})
                self.assertEqual(len(output.getvalue().splitlines()), 1)

    def test_report_objects_and_other_values_cannot_be_logged(self):
        marker = "synthetic-sensitive-value"
        values = (None, 0, 1, marker, {"qualified": True, "secret": marker})
        for index, value in enumerate(values):
            with self.subTest(index=index):
                output, errors = io.StringIO(), io.StringIO()
                with redirect_stdout(output), redirect_stderr(errors):
                    with self.assertRaises(ValueError) as caught:
                        emit_status(value)
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(errors.getvalue(), "")
                self.assertNotIn(marker, str(caught.exception))

    def test_invalid_values_are_not_coerced_or_formatted(self):
        class SensitiveObject:
            def __bool__(self):
                raise AssertionError("Must not inspect arbitrary payloads")

            def __repr__(self):
                raise AssertionError("Must not format arbitrary payloads")

        with self.assertRaises(ValueError):
            emit_status(SensitiveObject())
