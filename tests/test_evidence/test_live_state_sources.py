"""Additive cloud evidence vocabulary and exact legacy serialization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args
import unittest

from evidence.models import (
    ContextSourceFreshness,
    ContextSourceMetadata,
    ContextSourceType,
    EvidenceItem,
    EvidenceSourceKind,
    EvidenceSourceType,
    Finding,
)
from services.content_security import redact_value


class LiveStateSourceTests(unittest.TestCase):
    def test_source_values_append_without_reordering_legacy_members(self):
        self.assertEqual(
            get_args(ContextSourceType),
            (
                "artifact",
                "topology",
                "incident",
                "parser",
                "evidence",
                "ownership",
                "external_scanner",
                "user_context",
                "live_state",
            ),
        )
        self.assertEqual(
            get_args(EvidenceSourceType),
            (
                "artifact",
                "topology",
                "incident",
                "history",
                "heuristic",
                "skill",
                "external_scanner",
                "user_context",
                "live_state",
            ),
        )
        self.assertEqual(get_args(EvidenceSourceKind), get_args(EvidenceSourceType))

    def test_live_state_uses_existing_determinism_and_all_freshness_states(self):
        for state in get_args(ContextSourceFreshness):
            with self.subTest(freshness=state):
                context = ContextSourceMetadata(
                    source_id="snapshot-ref",
                    source_type="live_state",
                    source_ref="live_state://1/" + "a" * 64,
                    scope="opaque-connection",
                    freshness_status=state,
                )
                evidence = EvidenceItem(
                    evidence_id="live-evidence",
                    analysis_id=0,
                    finding_id="live-finding",
                    source_type="live_state",
                    source_ref="live_state://1/" + "a" * 64 + "#resource-hash",
                    summary="Observed state is running",
                    severity_hint="low",
                    deterministic=True,
                    confidence=1,
                    context_source=context,
                )
                self.assertEqual(evidence.source_kind, "live_state")
                self.assertEqual(evidence.determinism_level, "deterministic")
                self.assertEqual(evidence.context_source.freshness_status, state)

    def test_legacy_model_dumps_remain_exactly_unchanged(self):
        path = Path(__file__).parents[1] / "fixtures/cloud/legacy_evidence_models.json"
        cases = json.loads(path.read_text())
        for name, model in [
            ("context", ContextSourceMetadata),
            ("evidence", EvidenceItem),
            ("finding", Finding),
        ]:
            with self.subTest(model=name):
                self.assertEqual(
                    model.model_validate(cases[name]).model_dump(mode="json"),
                    cases[name],
                )

    def test_shared_redactor_recognizes_additive_source_protocol_value(self):
        value = {"source_type": "live_state", "source_kind": "live_state"}
        self.assertEqual(redact_value(value), value)
