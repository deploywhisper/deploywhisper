import json
import unittest
from unittest.mock import patch

from infra_automation.contracts import ValidationLimits
from infra_automation.workflow_validation import (
    IssueCollector,
    _parse_definition,
    validate_workflow,
)
from tests.test_infra_automation.test_workflow_schema import workflow


class ParsingTests(unittest.TestCase):
    def test_json_unicode_representations_preserve_canonical_round_trip(self):
        for value in (
            "🚀",
            "a\u0085b",
            "\u007f\u0080\u0084\u0086\u009f",
            "\ufffe\uffff",
        ):
            raw = workflow()
            raw["inputs"] = {
                "note": {"type": "string", "required": False, "default": value}
            }
            digests = []
            for escaped in (True, False):
                with self.subTest(value=repr(value), escaped=escaped):
                    result = validate_workflow(
                        json.dumps(raw, ensure_ascii=escaped).encode()
                    )
                    self.assertTrue(result.valid, result.errors)
                    self.assertEqual(result.definition.inputs["note"].default, value)
                    repeated = validate_workflow(result.canonical_bytes)
                    self.assertTrue(repeated.valid, repeated.errors)
                    self.assertEqual(repeated.canonical_bytes, result.canonical_bytes)
                    self.assertEqual(repeated.digest, result.digest)
                    digests.append(result.digest)
            self.assertEqual(len(set(digests)), 1)

    def test_json_numbers_never_become_string_identifiers(self):
        raw = json.dumps(workflow())
        for token in ("1e3", "1e999", "1.0e3", "-1e3"):
            with self.subTest(token=token):
                result = validate_workflow(raw.replace('"project-1"', token).encode())
                self.assertFalse(result.valid)
                self.assertIsNone(result.canonical_bytes)

    def test_json_policy_checks_preserve_yaml_flow_fallback(self):
        for prefix in ('"project_id": 1e3', '"project_id": NaN', "project_id: p"):
            raw = (
                "{" + prefix + ", workflow_version: 2, environment: production, "
                "inputs: {note: {type: string, required: false, default: '"
                + "["
                * 20
                + "'}}, steps: [{id: s, kind: uploaded_intake, depends_on: [], "
                "source: {kind: uploaded}}]}"
            )
            with self.subTest(prefix=prefix):
                self.assertTrue(validate_workflow(raw.encode()).valid)

    def test_json_guards_reject_unsafe_numbers_duplicates_and_isolated_surrogates(self):
        raw = json.dumps(workflow())
        for token in ("9" * 10000, "9007199254740992", "-9007199254740992"):
            with self.subTest(token=token[:20]):
                result = validate_workflow(raw.replace('"project-1"', token).encode())
                self.assertFalse(result.valid)
                self.assertEqual(result.errors[0].code, "resource_limit")
        for escaped in ('"\\ud800"', '"\\udc00"', '"\\ud800x"'):
            with self.subTest(escaped=escaped):
                self.assertFalse(
                    validate_workflow(
                        raw.replace('"project-1"', escaped).encode()
                    ).valid
                )
        duplicated = raw.replace(
            '"project_id":', '"project_id": "p", "project_\\u0069d":'
        )
        result = validate_workflow(duplicated.encode())
        self.assertEqual(result.errors[0].code, "yaml_duplicate_key")
        deeply_nested = ("[" * 10000 + "0" + "]" * 10000).encode()
        self.assertEqual(
            validate_workflow(deeply_nested).errors[0].code, "resource_limit"
        )

    def test_percent_inside_quoted_data_is_not_a_directive(self):
        raw = (
            "workflow_version: 2\nproject_id: p\nenvironment: prod\n"
            "inputs:\n  note:\n    type: string\n    required: false\n"
            '    default: "first\n% literal data\nlast"\n'
            "steps:\n- id: s\n  kind: uploaded_intake\n  depends_on: []\n"
            "  source: {kind: uploaded}\n"
        )
        result, issues = self.parse(raw)
        self.assertFalse(issues.errors)
        self.assertEqual(result.inputs["note"].default, "first % literal data last")

    def test_unsupported_execution_has_explicit_scope_errors(self):
        for kind in ("apply", "destroy", "remediation", "shell", "plugin"):
            raw = workflow()
            raw["steps"][0]["kind"] = kind
            with self.subTest(kind=kind):
                self.assertEqual(
                    self.parse(json.dumps(raw))[1].errors[0].code, "scope_unsupported"
                )
        for key in ("when", "finally", "script", "auto_approve", "continue_on_error"):
            raw = workflow()
            raw["steps"][0][key] = True
            with self.subTest(key=key):
                self.assertEqual(
                    self.parse(json.dumps(raw))[1].errors[0].code, "scope_unsupported"
                )

    def parse(self, raw, **limits):
        issues = IssueCollector(limits.get("max_errors", 50))
        result = _parse_definition(
            raw.encode() if type(raw) is str else raw,
            ValidationLimits(**limits),
            issues,
        )
        return result, issues

    def test_yaml_and_json_and_exact_byte_limit(self):
        raw = json.dumps(workflow())
        self.assertIsNotNone(self.parse(raw)[0])
        self.assertIsNotNone(self.parse(raw.encode(), max_bytes=len(raw))[0])
        self.assertIsNone(self.parse(raw, max_bytes=len(raw) - 1)[0])
        self.assertEqual(self.parse(b"\xff")[1].errors[0].code, "invalid_input")

    def test_forbidden_features_and_escaped_duplicate_keys(self):
        cases = [
            "a: &anchor 1",
            "a: *anchor",
            "a: !!str x",
            "%YAML 1.1\n---\na: b",
            "---\na: b\n---\na: c",
            'a: 1\n"\\u0061": 2',
            "a: {<<: {x: 1}}",
            "1: x",
            "a: 2026-01-01",
            "a: .inf",
            "a: 1.5",
            'a: "\\uD800"',
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                value, issues = self.parse(raw)
                self.assertIsNone(value)
                self.assertTrue(issues.errors)

    def test_container_depth_includes_indentless_sequences(self):
        for depth in (16, 17):
            raw = "[" * depth + "0" + "]" * depth
            with self.subTest(depth=depth):
                self.assertEqual(
                    self.parse(raw)[1].errors[0].code == "resource_limit", depth > 16
                )
        self.assertEqual(
            self.parse("a:\n- b:\n  - c", max_depth=3)[1].errors[0].code,
            "resource_limit",
        )
        self.assertNotEqual(
            self.parse("a:\n- b:\n  - c", max_depth=4)[1].errors[0].code,
            "resource_limit",
        )

    def test_numeric_guard_precedes_integer_and_float_conversion(self):
        for raw in [
            "a: " + "9" * 10000,
            "a: 0x" + "f" * 10000,
            "a: 0b" + "1" * 10000,
            "a: " + "0" * 10000 + "7",
            "a: 1:99",
            "a: 9007199254740992",
        ]:
            with self.subTest(prefix=raw[:20]):
                value, issues = self.parse(raw)
                self.assertIsNone(value)
                self.assertTrue(issues.errors)
        with patch(
            "yaml.constructor.SafeConstructor.construct_yaml_float",
            side_effect=AssertionError("conversion"),
        ):
            self.assertIsNone(self.parse("a: 1.5")[0])

    def test_diagnostics_never_echo_keys_values_or_exception_content(self):
        raw = workflow()
        raw["SECRET_RAW_KEY"] = "SECRET_RAW_VALUE"
        raw["inputs"] = {"PRIVATE_NAME": {"type": "SECRET_TYPE"}}
        _, issues = self.parse(json.dumps(raw))
        self.assertNotIn("SECRET", repr(issues.errors))
        self.assertNotIn("PRIVATE", repr(issues.errors))
        self.assertTrue(
            all(len(x.path) <= 20 and len(x.message) <= 160 for x in issues.errors)
        )

    def test_error_cap_marks_only_actual_omission(self):
        issues = IssueCollector(1)
        issues.add("schema_field")
        self.assertFalse(issues.truncated)
        issues.add("schema_field")
        self.assertTrue(issues.truncated)
        self.assertEqual(len(issues.errors), 1)

    def test_lowered_step_and_input_bounds_and_forged_limits(self):
        raw = workflow()
        raw["steps"] *= 2
        self.assertEqual(
            self.parse(json.dumps(raw), max_steps=1)[1].errors[0].code, "resource_limit"
        )
        raw = workflow()
        raw["inputs"] = {"a": {"type": "string"}, "b": {"type": "string"}}
        self.assertEqual(
            self.parse(json.dumps(raw), max_inputs=1)[1].errors[0].code,
            "resource_limit",
        )
        issues = IssueCollector()
        self.assertIsNone(
            _parse_definition(
                b"{}", ValidationLimits.model_construct(max_bytes=999999999), issues
            )
        )
        self.assertEqual(issues.errors[0].code, "invalid_input")

    def test_raw_interface_is_exact_bytes_and_exception_messages_are_private(self):
        class BytesSubclass(bytes):
            pass

        for raw in ["{}", bytearray(b"{}"), {}, BytesSubclass(b"{}")]:
            issues = IssueCollector()
            self.assertIsNone(_parse_definition(raw, ValidationLimits(), issues))
            self.assertEqual(issues.errors[0].code, "invalid_input")
        with patch("yaml.parse", side_effect=RuntimeError("PRIVATE_EXCEPTION")):
            _, issues = self.parse(b"{}")
        self.assertNotIn("PRIVATE", repr(issues.errors))

    def test_numeric_notations_stay_bounded_without_large_int_conversion(self):
        template = json.dumps(
            {
                **workflow(),
                "inputs": {
                    "number": {"type": "integer", "required": False, "default": "VALUE"}
                },
            }
        )
        for token, expected in [
            ("9007199254740991", 9007199254740991),
            ("-9007199254740991", -9007199254740991),
            ("0x10", 16),
            ("0b10", 2),
            ("010", 8),
            ("1:01", 61),
            ("0" * 10000 + "7", 7),
        ]:
            with self.subTest(token=token[:20]):
                value, issues = self.parse(template.replace('"VALUE"', token))
                self.assertFalse(issues.errors)
                self.assertEqual(value.inputs["number"].default, expected)
        for token in [
            "9007199254740992",
            "-9007199254740992",
            "0x20000000000000",
            "1:00:00:00:00:00:00:00:00:00",
        ]:
            with self.subTest(token=token):
                self.assertEqual(
                    self.parse(template.replace('"VALUE"', token))[1].errors[0].code,
                    "resource_limit",
                )

    def test_utf8_size_counts_bytes_and_escaped_duplicate_before_child(self):
        raw = workflow()
        raw["inputs"] = {"value": {"type": "string", "required": False, "default": "é"}}
        encoded = json.dumps(raw, ensure_ascii=False).encode()
        self.assertIsNotNone(self.parse(encoded, max_bytes=len(encoded))[0])
        self.assertEqual(
            self.parse(encoded, max_bytes=len(encoded) - 1)[1].errors[0].code,
            "resource_limit",
        )
        self.assertEqual(
            self.parse('a: 1\n"\\u0061": .inf')[1].errors[0].code, "yaml_duplicate_key"
        )
        self.assertEqual(
            self.parse("%UNKNOWN anything\n---\na: b")[1].errors[0].code,
            "yaml_feature_forbidden",
        )

    def test_event_generator_closed_at_first_budget_failure(self):
        from yaml.events import MappingStartEvent, MappingEndEvent

        closed = []

        def events(*args, **kwargs):
            try:
                yield MappingStartEvent(None, None, True)
                yield MappingStartEvent(None, None, True)
                raise AssertionError("must not advance")
                yield MappingEndEvent()
            finally:
                closed.append(True)

        with patch("yaml.parse", events):
            self.assertEqual(
                self.parse("a: b", max_depth=1)[1].errors[0].code, "resource_limit"
            )
        self.assertEqual(closed, [True])

    def test_diagnostic_paths_remove_internal_discriminator_labels(self):
        raw = workflow()
        raw["steps"][0]["source"]["repository_id"] = "forbidden"
        _, issues = self.parse(json.dumps(raw))
        self.assertEqual(issues.errors[0].path, ("steps", 0, "source", "repository_id"))
        raw = workflow()
        raw["inputs"] = {
            "PRIVATE": {"type": "identifier", "required": False, "default": "bad/path"}
        }
        _, issues = self.parse(json.dumps(raw))
        self.assertEqual(issues.errors[0].path, ("inputs", "<input>", "default"))
