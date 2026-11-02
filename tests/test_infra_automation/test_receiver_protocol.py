"""Production receiver wire identity qualified against frozen v1 evidence."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

from infra_automation.decisions import DecisionBinding, binding_digest
from infra_automation.receiver_protocol import (
    ReceiverBinding,
    ReceiverMessage,
    receiver_binding_bytes,
    receiver_binding_digest,
    receiver_binding_from_decision,
    receiver_message_bytes,
    validate_receiver_message,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/infra_automation/qualification/16_0/contracts"
SPEC = importlib.util.spec_from_file_location(
    "frozen_receiver_contract", FIXTURES / "prototype.py"
)
assert SPEC is not None and SPEC.loader is not None
PROTOTYPE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PROTOTYPE
SPEC.loader.exec_module(PROTOTYPE)
VALID = json.loads((FIXTURES / "valid.json").read_text())
INVALID = json.loads((FIXTURES / "invalid.json").read_text())


def decision_binding() -> DecisionBinding:
    value = copy.deepcopy(VALID["receiver"][0]["binding"])
    value.update(project_id=100, workspace_id=200, revision_id="revision-1")
    return DecisionBinding.model_validate_json(json.dumps(value))


class ReceiverProtocolTests(unittest.TestCase):
    def test_actual_frozen_vectors_have_identical_defaults_bytes_and_identity(self):
        for vector in VALID["receiver"]:
            with self.subTest(operation=vector["operation"], state=vector["state"]):
                expected = PROTOTYPE.validate("receiver", vector)
                actual = validate_receiver_message(vector)
                self.assertEqual(
                    actual.model_dump(mode="json"), expected.model_dump(mode="json")
                )
                self.assertEqual(
                    receiver_message_bytes(actual),
                    PROTOTYPE.canonical_bytes(expected.model_dump(mode="json")),
                )
                self.assertEqual(
                    receiver_binding_bytes(actual.binding),
                    PROTOTYPE.canonical_bytes(expected.binding.model_dump(mode="json")),
                )
                self.assertEqual(
                    receiver_binding_digest(actual.binding), vector["binding_digest"]
                )
                self.assertEqual(
                    validate_receiver_message(receiver_message_bytes(actual)), actual
                )

    def test_actual_frozen_invalid_receiver_and_provenance_vectors_deny(self):
        for vector in INVALID:
            if vector["contract"] not in ("receiver", "provenance"):
                continue
            with self.subTest(case=vector["case"]):
                value = vector["value"]
                if vector["contract"] == "provenance":
                    value = copy.deepcopy(VALID["receiver"][0])
                    value["binding"]["provenance"] = vector["value"]
                    with self.assertRaises(ValueError):
                        receiver_binding_bytes(value["binding"])
                with self.assertRaises(ValueError):
                    validate_receiver_message(value)

    def test_translation_retains_decision_identity_and_all_other_wire_fields(self):
        decision = decision_binding()
        before = decision.model_dump_json()
        wire = receiver_binding_from_decision(decision)
        expected = decision.model_dump(mode="json", exclude={"revision_id"})
        expected.update(project_id="100", workspace_id="200")
        frozen = PROTOTYPE.Binding.model_validate(expected)
        self.assertEqual(wire.model_dump(mode="json"), expected)
        self.assertEqual(
            receiver_binding_bytes(decision),
            PROTOTYPE.canonical_bytes(frozen.model_dump(mode="json")),
        )
        self.assertNotEqual(receiver_binding_digest(decision), binding_digest(decision))
        self.assertEqual(decision.model_dump_json(), before)
        for representation in (
            wire,
            expected,
            json.dumps(expected),
            receiver_binding_bytes(wire),
        ):
            with self.subTest(representation=type(representation).__name__):
                self.assertEqual(
                    receiver_binding_bytes(representation),
                    receiver_binding_bytes(decision),
                )
                self.assertEqual(
                    receiver_binding_digest(representation),
                    receiver_binding_digest(decision),
                )

    def test_optional_versions_and_nulls_match_frozen_canonical_expansion(self):
        value = copy.deepcopy(VALID["receiver"][0])
        del value["version"]
        del value["binding"]["version"]
        del value["binding"]["provenance"]["version"]
        del value["binding"]["provenance"]["source"]["version"]
        self.assertNotIn("custody", value["binding"]["provenance"])
        expected = PROTOTYPE.validate("receiver", value)
        self.assertEqual(
            receiver_message_bytes(value),
            PROTOTYPE.canonical_bytes(expected.model_dump(mode="json")),
        )
        for missing in ("kind", "repository_source", "limitation"):
            invalid = copy.deepcopy(value)
            del invalid["binding"]["provenance"]["source"][missing]
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                validate_receiver_message(invalid)

    def test_wire_versions_scope_and_unknown_fields_never_coerce(self):
        for path, bad in (
            (("version",), True),
            (("version",), "1"),
            (("version",), 2),
            (("binding", "version"), 1.0),
            (("binding", "provenance", "version"), False),
            (("binding", "provenance", "source", "version"), "1"),
            (("binding", "project_id"), 100),
            (("binding", "workspace_id"), None),
            (("binding", "revision_id"), "revision"),
            (("sequence",), True),
            (("sequence",), 2**53),
            (("sequence",), 1.0),
            (("state",), "cancelled"),
            (("operation",), "dispatch"),
            (("arbitrary",), True),
            (("binding", "evidence_deadline"), "2026-02-30T12:00:00Z"),
            (("binding", "approval_deadline"), "2026-10-09T12:00:00+00:00"),
        ):
            value = copy.deepcopy(VALID["receiver"][0])
            cursor = value
            for part in path[:-1]:
                cursor = cursor[part]
            cursor[path[-1]] = bad
            with self.subTest(path=path, bad=bad), self.assertRaises(ValueError):
                ReceiverMessage.model_validate(value)

    def test_model_copy_construct_and_nested_mutation_are_revalidated(self):
        decision = decision_binding()
        for bad in (
            decision.model_copy(update={"project_id": True}),
            decision.model_copy(update={"revision_id": ""}),
            DecisionBinding.model_construct(
                **{**decision.__dict__, "workspace_id": "200"}
            ),
            decision.model_copy(update={"extra_field": "hidden"}),
        ):
            with self.subTest(decision=bad), self.assertRaises(ValueError):
                receiver_binding_from_decision(bad)
        message = validate_receiver_message(VALID["receiver"][0])
        for bad in (
            message.model_copy(update={"state": "accepted"}),
            ReceiverMessage.model_construct(**{**message.__dict__, "version": True}),
            message.model_copy(update={"unknown": "hidden"}),
        ):
            with self.subTest(message=bad), self.assertRaises(ValueError):
                receiver_message_bytes(bad)
            with self.subTest(direct_message=bad), self.assertRaises(ValueError):
                ReceiverMessage.model_validate(bad)
        for bad in (
            message.binding.model_copy(update={"report_id": True}),
            message.binding.model_copy(update={"unexpected": "hidden"}),
            ReceiverBinding.model_construct(
                **{**message.binding.__dict__, "version": 2}
            ),
        ):
            with self.subTest(binding=bad), self.assertRaises(ValueError):
                receiver_binding_bytes(bad)
            with self.subTest(direct_binding=bad), self.assertRaises(ValueError):
                ReceiverBinding.model_validate(bad)
        message.binding.screened_artifact_digests.append("invalid")
        with self.assertRaises(ValueError):
            receiver_message_bytes(message)

    def test_exact_plan_and_collected_source_deadline_semantics_match_prototype(self):
        value = copy.deepcopy(VALID["receiver"][0]["binding"])
        value["authorization_kind"] = "exact_plan"
        value["provenance"] = copy.deepcopy(
            next(
                p
                for p in VALID["provenance"]
                if p["authorization_kind"] == "exact_plan"
            )
        )
        # Receiver v1 uses the minimum of all deadlines; it does not rewrite them.
        expected = PROTOTYPE.Binding.model_validate(value)
        self.assertEqual(
            receiver_binding_bytes(value),
            PROTOTYPE.canonical_bytes(expected.model_dump(mode="json")),
        )
        self.assertEqual(
            ReceiverBinding.model_validate(value).deadline(), expected.deadline()
        )
        for changes in (
            {"source_deadline": "2026-10-09T12:00:00Z"},
            {"collected_at": "2026-02-30T10:00:00Z"},
            {"redaction_version": 2},
            {"screened_transport_digest": "sha256:" + "c" * 64},
        ):
            bad = copy.deepcopy(value)
            bad["provenance"]["source"].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                receiver_binding_bytes(bad)

    def test_only_consume_and_outcome_have_frozen_state_restrictions(self):
        value = copy.deepcopy(VALID["receiver"][0])
        for operation in ("consume", "receipt", "status", "outcome", "reconcile"):
            for state in (
                "consumed",
                "accepted",
                "running",
                "succeeded",
                "failed",
                "delivery_unknown",
                "cancel_requested",
            ):
                value.update(operation=operation, state=state)
                allowed = (operation != "consume" or state == "consumed") and (
                    operation != "outcome"
                    or state in ("succeeded", "failed", "delivery_unknown")
                )
                with self.subTest(operation=operation, state=state):
                    if allowed:
                        self.assertEqual(validate_receiver_message(value).state, state)
                    else:
                        with self.assertRaises(ValueError):
                            validate_receiver_message(value)

    def test_wire_parser_rejects_duplicate_keys_nonfinite_values_depth_and_size(self):
        raw = json.dumps(VALID["receiver"][0])
        for bad in (
            '{"version":1,"version":1,' + raw[1:],
            raw.replace('"sequence": 1', '"sequence": NaN'),
            b"\xff",
            b" " * (128 * 1024 + 1),
            '{"unknown":' + "[" * 17 + "null" + "]" * 17 + "}",
        ):
            with (
                self.subTest(value_type=type(bad).__name__),
                self.assertRaises(ValueError),
            ):
                validate_receiver_message(bad)
        value = copy.deepcopy(VALID["receiver"][0])
        value["unknown"] = "x" * (128 * 1024)
        with self.assertRaises(ValueError):
            validate_receiver_message(value)

    @unittest.skipUnless(
        importlib.util.find_spec("jsonschema"), "optional jsonschema unavailable"
    )
    def test_canonical_outputs_validate_against_actual_frozen_schema(self):
        from jsonschema import Draft202012Validator

        validator = Draft202012Validator(
            json.loads((ROOT / "schemas/infra-automation/receiver-v1.json").read_text())
        )
        for value in VALID["receiver"]:
            validator.validate(json.loads(receiver_message_bytes(value)))
        value = copy.deepcopy(VALID["receiver"][0])
        value["binding"] = json.loads(receiver_binding_bytes(decision_binding()))
        value["binding_digest"] = receiver_binding_digest(decision_binding())
        validator.validate(json.loads(receiver_message_bytes(value)))


if __name__ == "__main__":
    unittest.main()
