"""Runtime approval evidence, all-path and freshness regressions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import unittest

from infra_automation.approval_eligibility import (
    EvidenceFacts,
    LiveBinding,
    evaluate_evidence,
    evaluate_handoff,
    evaluate_decision,
    eligibility_from_reasons,
)
from infra_automation.contracts import ProfileContract, RegistryContract

NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
DIGEST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64


class ApprovalEligibilityTests(unittest.TestCase):
    def evidence(self, **changes):
        values = dict(
            source_kind="collected",
            source_verified=True,
            collected_at=NOW - timedelta(minutes=10),
            evidence_deadline=NOW + timedelta(minutes=50),
            complete=True,
            report_available=True,
            recommendation="go",
            should_block=False,
            insufficient_context=False,
            policy_status="advisory",
            policy_passed=True,
            artifact_step_id="collect",
            report_step_id="analyze",
        )
        values.update(changes)
        return EvidenceFacts(**values)

    def live(self, **changes):
        values = dict(
            expected_tuple_digest=DIGEST,
            current_tuple_digest=DIGEST,
            membership_active=True,
            target_available=True,
            custody_available=True,
            approval_deadline=NOW + timedelta(minutes=5),
            custody_deadline=NOW + timedelta(minutes=20),
            source_deadline=NOW + timedelta(minutes=50),
            target_id="target",
            environment="test",
            authorization_kind="exact_plan",
        )
        values.update(changes)
        return LiveBinding(**values)

    def test_retained_typed_reasons_keep_recovery_and_unknown_codes_deny(self):
        projected = eligibility_from_reasons(("binding_changed", "stale_evidence"))
        self.assertFalse(projected.eligible)
        self.assertEqual(projected.reasons, ("binding_changed", "stale_evidence"))
        self.assertEqual(len(projected.limitations), 2)
        self.assertEqual(len(projected.context_todos), 2)
        for codes in (("unknown",), ("stale_evidence",) * 51, "stale_evidence"):
            self.assertIn("invalid_evidence", eligibility_from_reasons(codes).reasons)

    def test_missing_explicit_policy_success_never_authorizes(self):
        evidence = self.evidence().model_dump()
        evidence.pop("policy_passed")
        result = evaluate_evidence(EvidenceFacts(**evidence), self.live(), now=NOW)
        self.assertIn("policy_denied", result.reasons)

    def test_current_collected_evidence_is_eligible_at_all_stages(self):
        for phase in ("decision", "dispatch", "consume"):
            with self.subTest(phase=phase):
                self.assertTrue(
                    evaluate_evidence(
                        self.evidence(), self.live(), now=NOW, phase=phase
                    ).eligible
                )

    def test_each_earliest_deadline_denies_at_equality(self):
        cases = (
            (self.evidence(evidence_deadline=NOW), self.live(), "stale_evidence"),
            (self.evidence(), self.live(approval_deadline=NOW), "approval_expired"),
            (self.evidence(), self.live(custody_deadline=NOW), "custody_expired"),
            (self.evidence(), self.live(source_deadline=NOW), "source_expired"),
        )
        for evidence, live, reason in cases:
            for phase in ("decision", "dispatch", "consume"):
                with self.subTest(reason=reason, phase=phase):
                    result = evaluate_evidence(evidence, live, now=NOW, phase=phase)
                    self.assertFalse(result.eligible)
                    self.assertIn(reason, result.reasons)

    def test_delayed_receiver_consumption_rechecks_previously_valid_dispatch(self):
        evidence, live = self.evidence(), self.live()
        self.assertTrue(
            evaluate_evidence(evidence, live, now=NOW, phase="decision").eligible
        )
        self.assertTrue(
            evaluate_evidence(evidence, live, now=NOW, phase="dispatch").eligible
        )
        delayed = evaluate_evidence(
            evidence, live, now=NOW + timedelta(minutes=5), phase="consume"
        )
        self.assertIn("approval_expired", delayed.reasons)
        delayed = evaluate_evidence(
            evidence,
            self.live(
                approval_deadline=NOW + timedelta(days=1),
                custody_deadline=NOW + timedelta(days=1),
            ),
            now=NOW + timedelta(minutes=50),
            phase="consume",
        )
        self.assertIn("stale_evidence", delayed.reasons)

    def test_approval_extension_never_extends_evidence(self):
        result = evaluate_evidence(
            self.evidence(),
            self.live(approval_deadline=NOW + timedelta(days=1)),
            now=NOW + timedelta(hours=1),
        )
        self.assertIn("stale_evidence", result.reasons)

    def test_maximum_and_stricter_ttl_and_future_collection(self):
        for changes in (
            dict(evidence_deadline=NOW + timedelta(minutes=51)),
            dict(collected_at=NOW + timedelta(seconds=1)),
            dict(evidence_deadline=NOW - timedelta(minutes=11)),
        ):
            with self.subTest(changes=changes):
                self.assertIn(
                    "invalid_freshness",
                    evaluate_evidence(
                        self.evidence(**changes), self.live(), now=NOW
                    ).reasons,
                )
        self.assertTrue(
            evaluate_evidence(
                self.evidence(evidence_deadline=NOW + timedelta(seconds=1)),
                self.live(),
                now=NOW,
            ).eligible
        )

    def test_partial_missing_stale_and_unverified_explain_recovery(self):
        for changes, reason in (
            (dict(complete=False), "incomplete_evidence"),
            (dict(report_available=False), "missing_report"),
            (dict(source_kind="uploaded"), "unverified_source"),
            (dict(source_verified=False), "unverified_source"),
            (dict(insufficient_context=True), "insufficient_context"),
        ):
            with self.subTest(reason=reason):
                result = evaluate_evidence(
                    self.evidence(**changes), self.live(), now=NOW
                )
                self.assertIn(reason, result.reasons)
                self.assertTrue(result.limitations)
                self.assertTrue(result.context_todos)

    def test_canonical_vocabulary_and_explicit_policy_are_separate(self):
        for recommendation in ("go", "caution", "no-go"):
            evidence = self.evidence(recommendation=recommendation)
            before = evidence.model_dump_json()
            self.assertTrue(evaluate_evidence(evidence, self.live(), now=NOW).eligible)
            self.assertEqual(before, evidence.model_dump_json())
            self.assertFalse(evidence.should_block)
        for changes, reason in (
            (dict(recommendation="no_go"), "unsupported_recommendation"),
            (dict(recommendation="insufficient_context"), "unsupported_recommendation"),
            (dict(policy_status="unknown"), "unsupported_policy"),
            (dict(policy_status="hard-block"), "policy_denied"),
            (dict(policy_status="soft-block"), "policy_denied"),
            (dict(policy_passed=False), "policy_denied"),
            (dict(should_block=True), "canonical_contract_changed"),
        ):
            with self.subTest(reason=reason):
                self.assertIn(
                    reason,
                    evaluate_evidence(
                        self.evidence(**changes), self.live(), now=NOW
                    ).reasons,
                )

    def test_live_revocation_binding_and_custody_fail_closed(self):
        for changes, reason in (
            (dict(current_tuple_digest=OTHER), "binding_changed"),
            (dict(membership_active=False), "membership_revoked"),
            (dict(target_available=False), "target_unavailable"),
            (dict(custody_available=False), "custody_unavailable"),
            (dict(approval_deadline=None), "missing_approval"),
        ):
            with self.subTest(reason=reason):
                self.assertIn(
                    reason,
                    evaluate_evidence(
                        self.evidence(), self.live(**changes), now=NOW, phase="consume"
                    ).reasons,
                )

    def test_unchecked_model_copies_cannot_extend_freshness_or_remove_custody(self):
        for evidence, live in (
            (
                self.evidence().model_copy(
                    update={
                        "evidence_ttl_seconds": 7200,
                        "evidence_deadline": NOW + timedelta(minutes=100),
                    }
                ),
                self.live(),
            ),
            (
                self.evidence(),
                self.live().model_copy(
                    update={"authorization_kind": "unknown", "custody_available": False}
                ),
            ),
            (self.evidence().model_copy(update={"complete": "yes"}), self.live()),
            (EvidenceFacts.model_construct(source_kind="collected"), self.live()),
        ):
            with self.subTest(evidence=evidence, live=live):
                result = evaluate_evidence(evidence, live, now=NOW)
                self.assertFalse(result.eligible)
                self.assertIn("invalid_evidence", result.reasons)
                self.assertIn(
                    "invalid_evidence",
                    self.handoff(evidence=evidence, live=live).reasons,
                )

    def test_invalid_clock_and_unknown_stage_fail_closed(self):
        for now, phase in ((NOW.replace(tzinfo=None), "decision"), (NOW, "unknown")):
            self.assertFalse(
                evaluate_evidence(
                    self.evidence(), self.live(), now=now, phase=phase
                ).eligible
            )

    def workflow(self):
        def reference(name, output):
            return dict(ref="step", step_id=name, output=output)

        return dict(
            workflow_version=2,
            project_id="project",
            workspace_id="workspace",
            environment="test",
            steps=[
                dict(
                    id="collect",
                    kind="admitted_collection",
                    depends_on=[],
                    source=dict(
                        kind="collected",
                        repository_id="repo",
                        commit_sha="a" * 40,
                        profile_digest=DIGEST,
                    ),
                ),
                dict(
                    id="analyze",
                    kind="shared_analysis",
                    depends_on=["collect"],
                    artifact=reference("collect", "screened_artifacts"),
                ),
                dict(
                    id="gate",
                    kind="policy_evaluation",
                    depends_on=["analyze"],
                    report=reference("analyze", "report"),
                    target_id="target",
                    environment="test",
                    authorization_kind="exact_plan",
                ),
                dict(
                    id="decision",
                    kind="human_decision",
                    depends_on=["gate"],
                    binding=reference("gate", "action_binding"),
                ),
                dict(
                    id="handoff",
                    kind="registered_github_handoff",
                    depends_on=["decision"],
                    binding=reference("gate", "action_binding"),
                    decision=reference("decision", "decision_receipt"),
                    target_id="target",
                    environment="test",
                    authorization_kind="exact_plan",
                ),
            ],
        )

    def handoff(self, *, workflow=None, states=None, **changes):
        values = dict(
            definition_bytes=json.dumps(workflow or self.workflow()).encode(),
            registry_contract=RegistryContract(
                profiles=(
                    ProfileContract(
                        digest=DIGEST,
                        tool="opentofu",
                        authorization_kinds=("exact_plan",),
                    ),
                )
            ),
            handoff_step_id="handoff",
            step_states=states
            or tuple(
                (name, "succeeded")
                for name in ("collect", "analyze", "gate", "decision")
            ),
            evidence=self.evidence(),
            live=self.live(),
            now=NOW,
            decision_binding_digest=DIGEST,
            decision_approved=True,
        )
        values.update(changes)
        return evaluate_handoff(**values)

    def test_all_matching_successful_lineage_is_eligible(self):
        self.assertTrue(self.handoff().eligible)

    def test_skipped_failed_missing_or_unrelated_success_never_qualifies(self):
        for name in ("collect", "analyze", "gate", "decision"):
            for state in (
                "skipped",
                "failed",
                "running",
                "unknown",
                "cancelled",
                "timed_out",
            ):
                states = tuple(
                    (other, state if other == name else "succeeded")
                    for other in ("collect", "analyze", "gate", "decision")
                ) + (("unrelated", "succeeded"),)
                with self.subTest(name=name, state=state):
                    self.assertIn(
                        "prerequisite_unsuccessful", self.handoff(states=states).reasons
                    )
        self.assertFalse(self.handoff(states=(("unrelated", "succeeded"),)).eligible)

    def test_decision_phase_requires_its_pending_human_step_and_successful_gate(self):
        states = tuple(
            (name, "pending" if name == "decision" else "succeeded")
            for name in ("collect", "analyze", "gate", "decision")
        )
        self.assertTrue(
            self.handoff(
                states=states,
                phase="decision",
                decision_binding_digest=None,
                decision_approved=False,
                live=self.live(approval_deadline=None),
            ).eligible
        )
        self.assertFalse(self.handoff(states=states, phase="dispatch").eligible)
        self.assertFalse(
            self.handoff(
                states=states + (("gate", "succeeded"),), phase="decision"
            ).eligible
        )
        self.assertIn(
            "scope_unresolved",
            self.handoff(workflow=dict(self.workflow(), workspace_id=None)).reasons,
        )

    def test_each_alternate_handoff_requires_its_own_successful_decision(self):
        workflow = self.workflow()
        alternate = json.loads(json.dumps(workflow["steps"]))
        for step in alternate:
            step["id"] += "_second"
            step["depends_on"] = [name + "_second" for name in step["depends_on"]]
            for value in step.values():
                if isinstance(value, dict) and value.get("ref") == "step":
                    value["step_id"] += "_second"
            if "target_id" in step:
                step["target_id"] = "other-target"
        workflow["steps"].extend(alternate)
        first = tuple(
            (name, "succeeded") for name in ("collect", "analyze", "gate", "decision")
        )
        arguments = dict(
            workflow=workflow,
            handoff_step_id="handoff_second",
            evidence=self.evidence(
                artifact_step_id="collect_second", report_step_id="analyze_second"
            ),
            live=self.live(target_id="other-target"),
        )
        self.assertIn(
            "prerequisite_unsuccessful", self.handoff(states=first, **arguments).reasons
        )
        second = tuple(
            (name + "_second", "succeeded")
            for name in ("collect", "analyze", "gate", "decision")
        )
        self.assertTrue(self.handoff(states=first + second, **arguments).eligible)
        skipped = tuple(
            (name, "skipped" if name == "decision_second" else state)
            for name, state in second
        )
        self.assertFalse(self.handoff(states=first + skipped, **arguments).eligible)

    def test_mandatory_human_without_direct_handoff_can_request_and_recheck(self):
        workflow = self.workflow()
        workflow["steps"].insert(
            -1,
            dict(
                id="parallel",
                kind="human_decision",
                depends_on=["gate"],
                binding=dict(ref="step", step_id="gate", output="action_binding"),
            ),
        )
        workflow["steps"][-1]["depends_on"].append("parallel")
        arguments = dict(
            definition_bytes=json.dumps(workflow).encode(),
            registry_contract=RegistryContract(
                profiles=(
                    ProfileContract(
                        digest=DIGEST,
                        tool="opentofu",
                        authorization_kinds=("exact_plan",),
                    ),
                )
            ),
            decision_step_id="parallel",
            evidence=self.evidence(),
            live=self.live(),
            now=NOW,
        )
        states = tuple(
            (name, "pending" if name in {"decision", "parallel"} else "succeeded")
            for name in ("collect", "analyze", "gate", "decision", "parallel")
        )
        self.assertTrue(evaluate_decision(step_states=states, **arguments).eligible)
        for state in ("failed", "unknown", "skipped"):
            broken = tuple(
                (name, state if name == "gate" else current) for name, current in states
            )
            self.assertIn(
                "prerequisite_unsuccessful",
                evaluate_decision(step_states=broken, **arguments).reasons,
            )
        approved = tuple(
            (name, "succeeded" if name == "parallel" else current)
            for name, current in states
        )
        for phase in ("dispatch", "consume"):
            self.assertTrue(
                evaluate_decision(
                    step_states=approved,
                    decision_binding_digest=DIGEST,
                    decision_approved=True,
                    phase=phase,
                    **arguments,
                ).eligible
            )
            self.assertIn(
                "decision_missing",
                evaluate_decision(
                    step_states=approved, phase=phase, **arguments
                ).reasons,
            )
        self.assertIn(
            "decision_missing",
            evaluate_decision(
                step_states=states, **dict(arguments, decision_step_id="unknown")
            ).reasons,
        )
        self.assertFalse(self.handoff(workflow=workflow, states=approved).eligible)

    def test_parallel_decision_can_start_before_handoff_only_human_dependency(self):
        workflow = self.workflow()
        workflow["steps"].insert(
            -1,
            dict(
                id="parallel",
                kind="human_decision",
                depends_on=["gate"],
                binding=dict(ref="step", step_id="gate", output="action_binding"),
            ),
        )
        workflow["steps"][-1]["depends_on"].append("parallel")
        states = tuple(
            (name, "pending" if name in {"decision", "parallel"} else "succeeded")
            for name in ("collect", "analyze", "gate", "decision", "parallel")
        )
        self.assertTrue(
            self.handoff(workflow=workflow, states=states, phase="decision").eligible
        )
        self.assertFalse(
            self.handoff(workflow=workflow, states=states, phase="dispatch").eligible
        )
        first_approved = tuple(
            (name, "succeeded" if name == "decision" else state)
            for name, state in states
        )
        self.assertFalse(
            self.handoff(
                workflow=workflow, states=first_approved, phase="consume"
            ).eligible
        )
        all_approved = tuple((name, "succeeded") for name, _ in states)
        self.assertTrue(
            self.handoff(
                workflow=workflow, states=all_approved, phase="dispatch"
            ).eligible
        )

    def test_serial_prior_decision_must_succeed_before_current_decision(self):
        workflow = self.workflow()
        workflow["steps"].insert(
            -2,
            dict(
                id="earlier",
                kind="human_decision",
                depends_on=["gate"],
                binding=dict(ref="step", step_id="gate", output="action_binding"),
            ),
        )
        next(step for step in workflow["steps"] if step["id"] == "decision")[
            "depends_on"
        ].append("earlier")
        states = tuple(
            (name, "pending" if name in {"earlier", "decision"} else "succeeded")
            for name in ("collect", "analyze", "gate", "earlier", "decision")
        )
        self.assertIn(
            "prerequisite_unsuccessful",
            self.handoff(workflow=workflow, states=states, phase="decision").reasons,
        )
        prior_approved = tuple(
            (name, "succeeded" if name == "earlier" else state)
            for name, state in states
        )
        self.assertTrue(
            self.handoff(
                workflow=workflow, states=prior_approved, phase="decision"
            ).eligible
        )

    def test_wrong_branch_decision_report_target_and_alternate_path_deny(self):
        self.assertIn(
            "decision_mismatch", self.handoff(decision_binding_digest=OTHER).reasons
        )
        self.assertIn("decision_missing", self.handoff(decision_approved=False).reasons)
        self.assertIn(
            "lineage_mismatch",
            self.handoff(evidence=self.evidence(report_step_id="other")).reasons,
        )
        self.assertIn(
            "lineage_mismatch", self.handoff(live=self.live(target_id="other")).reasons
        )
        workflow = self.workflow()
        workflow["steps"][-1]["depends_on"] = ["analyze"]
        self.assertIn("invalid_workflow", self.handoff(workflow=workflow).reasons)


if __name__ == "__main__":
    unittest.main()
