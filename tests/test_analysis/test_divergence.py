"""Recorded plan-versus-observation comparison, with no provider access."""

from __future__ import annotations

import copy
from hashlib import sha256
import json
from pathlib import Path
import unittest

from analysis.divergence import compare_plan, DivergenceAssessment, DivergenceError
from cloud.base import build_snapshot, validate_snapshot
from services.divergence_service import divergence_gate_exit_code


_FIXTURES = (
    Path(__file__).resolve().parents[1] / "fixtures" / "live_environment_divergence"
)


class DivergenceTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((_FIXTURES / "plan.json").read_text())
        self.snapshot_fields = json.loads((_FIXTURES / "snapshot.json").read_text())

    def compare(self, **kwargs):
        return compare_plan(self.plan, build_snapshot(**self.snapshot_fields), **kwargs)

    def _change(self, label):
        return next(
            row["change"]
            for row in self.plan["resource_changes"]
            if row["address"] == f"aws_instance.{label}"
        )

    def _observation(self, label):
        return next(
            row
            for row in self.snapshot_fields["resources"]
            if row["identity"]["address"] == f"aws_instance.{label}"
        )

    def _prior(self, label):
        return next(
            row
            for row in self.plan["prior_state"]["values"]["root_module"]["resources"]
            if row["address"] == f"aws_instance.{label}"
        )

    def _ec2_attachments(self):
        row = next(
            row
            for row in self.plan["resource_changes"]
            if row["address"] == "aws_instance.match"
        )
        self.plan["resource_changes"] = [row]
        observation = self._observation("match")
        self.snapshot_fields["resources"] = [observation]
        groups = ["sg-0123456789abcdef0", "sg-2123456789abcdef0"]
        for values in (row["change"]["before"], row["change"]["after"]):
            values["vpc_security_group_ids"] = list(groups)
        return row["change"], observation, groups

    @staticmethod
    def _group_fact(index, value):
        return {
            "name": (
                f"instance.Reservations.0.Instances.0.SecurityGroups.{index}.GroupId"
            ),
            "value": value,
        }

    def test_ec2_attachment_order_does_not_affect_gate_or_plan_coverage(self):
        change, observation, groups = self._ec2_attachments()
        observation["facts"].extend(
            [self._group_fact(0, groups[1]), self._group_fact(1, groups[0])]
        )
        change["after"]["vpc_security_group_ids"] = [groups[1]]
        self._prior("match")["values"]["vpc_security_group_ids"] = groups[::-1]
        result = self.compare()
        self.assertEqual(divergence_gate_exit_code(result), 0)
        (row,) = result.resources
        self.assertEqual(row.status, "match")
        self.assertIn("vpc_security_group_ids", row.checked_attributes)

    def test_ec2_attachment_drift_records_planned_membership_and_requires_caution(self):
        change, observation, groups = self._ec2_attachments()
        live = [groups[0]]
        observation["facts"].append(self._group_fact(0, live[0]))
        change["after"]["vpc_security_group_ids"] = []
        result = self.compare()
        self.assertEqual(divergence_gate_exit_code(result), 3)
        self.assertTrue(result.requires_caution)
        (row,) = result.resources
        (difference,) = row.differences
        self.assertEqual(
            (
                difference.attribute,
                difference.recorded,
                difference.live,
                difference.planned,
                difference.planned_known,
                difference.fact_name,
            ),
            (
                "vpc_security_group_ids",
                ", ".join(groups),
                live[0],
                "",
                True,
                self._group_fact(0, live[0])["name"],
            ),
        )

        change["after_unknown"] = {"vpc_security_group_ids": [True]}
        (difference,) = self.compare().resources[0].differences
        self.assertFalse(difference.planned_known)
        self.assertIsNone(difference.planned)

    def test_ec2_attachment_incomplete_or_screened_evidence_never_clears_gate(self):
        change, observation, groups = self._ec2_attachments()
        scalar_facts = list(observation["facts"])
        for group_facts in (
            [],
            [self._group_fact(1, groups[0])],
            [self._group_fact(0, groups[0]), self._group_fact(2, groups[1])],
            [self._group_fact(0, groups[0]), self._group_fact(1, groups[0])],
            [self._group_fact(0, 17)],
            [self._group_fact(0, "[REDACTED]")],
        ):
            with self.subTest(group_facts=group_facts):
                observation["facts"] = scalar_facts + group_facts
                result = self.compare()
                self.assertEqual(divergence_gate_exit_code(result), 2)
                self.assertEqual(result.resources[0].status, "unknown")

        observation["facts"] = scalar_facts + [
            self._group_fact(0, groups[0]),
            self._group_fact(1, groups[1]),
        ]
        change["before_sensitive"] = {"vpc_security_group_ids": [True, False]}
        self.assertEqual(divergence_gate_exit_code(self.compare()), 2)
        change.pop("before_sensitive")
        self._prior("match")["values"]["vpc_security_group_ids"] = [groups[1]]
        result = self.compare()
        self.assertEqual(divergence_gate_exit_code(result), 2)
        self.assertEqual(result.resources[0].reason, "recorded_prior_state_conflict")

        observation.update(status="partial", cause="truncated_response")
        self.assertEqual(divergence_gate_exit_code(self.compare()), 2)

    def test_recorded_matrix_and_exact_evidence_triples(self):
        result = self.compare()
        rows = {
            item.address.removeprefix("aws_instance."): item
            for item in result.resources
        }
        self.assertEqual(
            {name: item.status for name, item in rows.items()},
            {
                "deleted": "diverged",
                "match": "match",
                "modified": "diverged",
                "partial": "unknown",
                "recreated": "diverged",
                "tag_only": "diverged",
                "unknown": "unknown",
                "unreadable": "unreadable",
            },
        )
        self.assertEqual(rows["unreadable"].missing_permission, "ec2:DescribeInstances")
        self.assertTrue(result.diverged)
        self.assertTrue(result.requires_caution)
        self.assertEqual(
            DivergenceAssessment.model_validate(result.model_dump(mode="json")),
            result,
        )
        self.assertEqual(
            result.snapshot_digest, build_snapshot(**self.snapshot_fields).digest
        )
        diff = rows["modified"].differences[0]
        self.assertEqual(
            (diff.attribute, diff.recorded, diff.live, diff.planned),
            ("disable_api_termination", True, False, True),
        )
        self.assertTrue(diff.planned_known)
        self.assertEqual(
            diff.fact_name, "termination_protection.DisableApiTermination.Value"
        )
        diff = rows["deleted"].differences[0]
        self.assertEqual(
            (diff.attribute, diff.recorded, diff.live, diff.planned),
            ("exists", True, False, False),
        )
        diff = rows["recreated"].differences[0]
        self.assertEqual(
            (diff.attribute, diff.recorded, diff.live, diff.planned),
            ("physical_id", "i-00000004", "i-00000024", "i-00000004"),
        )
        diff = rows["tag_only"].differences[0]
        self.assertEqual(
            (diff.attribute, diff.recorded, diff.live, diff.planned),
            ("tags.team", "platform", "operations", "review"),
        )
        self.assertFalse(diff.requires_caution)
        for row in rows.values():
            indexed = {
                f["name"]
                for f in next(
                    (
                        resource
                        for resource in self.snapshot_fields["resources"]
                        if resource["identity"]["address"] == row.address
                    ),
                    {},
                ).get("facts", [])
            }
            self.assertTrue(
                all(delta.fact_name in indexed for delta in row.differences)
            )

    def test_missing_or_different_observation_identity_is_unknown(self):
        row = self._observation("modified")
        row["identity"]["physical_id"] = "i-00000012"
        compared = next(
            r for r in self.compare().resources if r.address.endswith(".modified")
        )
        self.assertEqual(compared.status, "unknown")
        self.assertEqual(compared.differences, ())
        row["identity"]["physical_id"] = "i-00000002"
        row["facts"] = []
        compared = next(
            r for r in self.compare().resources if r.address.endswith(".modified")
        )
        self.assertEqual(compared.status, "unknown")

    def test_conflicting_recorded_identity_or_observed_value_cannot_match(self):
        self._observation("match")["facts"].append(
            {"name": "resource.physical_id", "value": "i-00000001"}
        )
        for field, conflicting in (
            ("id", "i-00000012"),
            ("disable_api_termination", False),
        ):
            with self.subTest(field=field):
                before = self._change("match")["before"]
                original = before[field]
                before[field] = conflicting
                try:
                    row = next(
                        item
                        for item in self.compare().resources
                        if item.address == "aws_instance.match"
                    )
                    self.assertEqual(row.status, "unknown")
                    self.assertEqual(row.reason, "recorded_prior_state_conflict")
                    self.assertEqual(row.differences, ())
                    self.assertEqual(row.checked_attributes, ())
                finally:
                    before[field] = original

    def test_conflicting_sensitive_tags_do_not_appear_in_a_result(self):
        canary = "demo-sensitive-comparison-value"
        change = self._change("tag_only")
        change["before"]["tags"]["team"] = canary
        change["before_sensitive"] = {"tags": {"team": True}}
        result = self.compare()
        row = next(
            item for item in result.resources if item.address.endswith(".tag_only")
        )
        self.assertEqual(row.reason, "recorded_prior_state_conflict")
        self.assertEqual(row.status, "unknown")
        self.assertNotIn(canary, result.model_dump_json())

    def test_omitted_before_values_do_not_conflict(self):
        del self._change("match")["before"]["disable_api_termination"]
        row = next(
            item for item in self.compare().resources if item.address.endswith(".match")
        )
        self.assertEqual(row.status, "match")

    def test_moves_and_deposed_objects_use_their_own_before_values(self):
        address = "aws_instance.match"
        row = next(
            item for item in self.plan["resource_changes"] if item["address"] == address
        )
        self._prior("match")["values"]["disable_api_termination"] = False
        row["previous_address"] = "aws_instance.previous"
        self._prior("match")["address"] = row["previous_address"]
        compared = next(
            item for item in self.compare().resources if item.address == address
        )
        self.assertEqual(compared.status, "match")

        self._prior("previous")["address"] = address
        del row["previous_address"]
        row["deposed"] = "deadbeef"
        digest = sha256(json.dumps([address, row["deposed"]]).encode()).hexdigest()
        deposed_address = f"{address}#deposed:{digest}"
        self._observation("match")["identity"]["address"] = deposed_address
        compared = next(
            item for item in self.compare().resources if item.address == deposed_address
        )
        self.assertEqual(compared.status, "match")

    def test_unknown_sensitive_and_arbitrary_plan_fields_never_escape(self):
        changed = self._change("modified")
        changed["after"]["disable_api_termination"] = True
        changed["after_unknown"] = {"disable_api_termination": True}
        changed["after"]["unmapped_raw"] = "private-placeholder"
        result = self.compare()
        row = next(r for r in result.resources if r.address.endswith(".modified"))
        self.assertEqual(row.status, "diverged")
        self.assertFalse(row.differences[0].planned_known)
        self.assertIsNone(row.differences[0].planned)
        self.assertNotIn("private-placeholder", result.model_dump_json())

        changed["before_sensitive"] = {"disable_api_termination": True}
        row = next(
            r for r in self.compare().resources if r.address.endswith(".modified")
        )
        self.assertEqual(row.status, "unknown")

    def test_tag_only_drift_floors_only_a_destructive_operation(self):
        change = next(
            row
            for row in self.plan["resource_changes"]
            if row["address"].endswith(".tag_only")
        )
        self.plan["resource_changes"] = [change]
        self.assertTrue(self.compare().diverged)
        self.assertFalse(self.compare().requires_caution)
        change["change"]["actions"] = ["delete", "create"]
        self.assertTrue(self.compare().requires_caution)

    def test_incomplete_tags_and_unmanaged_resources_never_match(self):
        self._observation("tag_only")["facts"] = []
        row = next(
            r for r in self.compare().resources if r.address.endswith(".tag_only")
        )
        self.assertEqual(row.status, "unknown")
        change = next(
            item
            for item in self.plan["resource_changes"]
            if item["address"].endswith(".match")
        )
        change["mode"] = "data"
        row = next(r for r in self.compare().resources if r.address.endswith(".match"))
        self.assertEqual(row.status, "unknown")

    def test_delete_does_not_expose_an_inconsistent_after_value(self):
        change = self._change("modified")
        change["actions"] = ["delete"]
        change["after"]["disable_api_termination"] = "never-publish"
        result = self.compare()
        row = next(r for r in result.resources if r.address.endswith(".modified"))
        self.assertTrue(row.differences[0].planned_known)
        self.assertIsNone(row.differences[0].planned)
        self.assertNotIn("never-publish", result.model_dump_json())

    def test_masked_account_scope_also_screens_planned_values(self):
        self.snapshot_fields["scope"] = "[MASKED_ACCOUNT]"
        self._change("tag_only")["after"]["tags"]["team"] = "account 123456789012"
        result = self.compare()
        row = next(r for r in result.resources if r.address.endswith(".tag_only"))
        self.assertEqual(row.status, "diverged")
        self.assertFalse(row.differences[0].planned_known)
        self.assertNotIn("123456789012", result.model_dump_json())

    def test_plan_freshness_is_measured_against_observation_and_threshold(self):
        result = self.compare()
        self.assertEqual(result.freshness.status, "stale")
        self.assertEqual(result.freshness.age_seconds, 7200)
        self.assertEqual(
            self.compare(stale_after_seconds=7200).freshness.status, "current"
        )
        self.plan["timestamp"] = "2026-11-20T12:00:01Z"
        run = self.compare()
        self.assertEqual(run.freshness.status, "unknown")
        self.assertFalse(run.diverged)
        self.plan["timestamp"] = "2026-11-20"
        self.assertEqual(self.compare().freshness.status, "unknown")
        with self.assertRaises(DivergenceError):
            self.compare(stale_after_seconds=True)

    def test_observed_unchanged_field_does_not_cover_unobserved_rule_edit(self):
        address = "aws_security_group.app"
        before = {
            "id": "sg-00000001",
            "vpc_id": "vpc-00000001",
            "ingress": [{"description": "recorded rule"}],
        }
        self.plan["resource_changes"] = [
            {
                "address": address,
                "type": "aws_security_group",
                "change": {
                    "actions": ["update"],
                    "before": before,
                    "after": {**before, "ingress": [{"description": "planned rule"}]},
                },
            }
        ]
        observation = {
            "identity": {
                "address": address,
                "resource_type": "aws_security_group",
                "physical_id": before["id"],
            },
            "status": "read",
            "facts": [
                {
                    "name": "security_group.SecurityGroups.0.VpcId",
                    "value": before["vpc_id"],
                },
                {"name": "resource.exists", "value": True},
            ],
        }
        self.snapshot_fields["resources"] = [observation]
        row = self.compare().resources[0]
        self.assertEqual(row.status, "unknown")
        self.assertEqual(row.reason, "comparable_facts_incomplete")
        self.assertIn("vpc_id", row.checked_attributes)

        observation["facts"][0]["value"] = "vpc-00000002"
        row = self.compare().resources[0]
        self.assertEqual(row.status, "diverged")
        self.assertEqual(row.reason, "comparable_facts_incomplete")
        self.assertEqual(row.differences[0].attribute, "vpc_id")

    def test_covered_plan_edit_matches_but_uncovered_unknown_mask_does_not(self):
        changed = self._change("match")
        changed["after"]["disable_api_termination"] = False
        for mask, expected in (
            ({"unobserved": [{"detail": False}]}, "match"),
            ({"unobserved": [{"detail": True}]}, "unknown"),
            (True, "unknown"),
        ):
            with self.subTest(mask=mask):
                changed["after_unknown"] = mask
                row = next(
                    r for r in self.compare().resources if r.address.endswith(".match")
                )
                self.assertEqual(row.status, expected)

    def test_security_group_tag_edit_requires_recorded_rule_coverage(self):
        address = "aws_security_group.app"
        before = {
            "id": "sg-00000001",
            "vpc_id": "vpc-00000001",
            "tags": {"environment": "test"},
        }
        change = {
            "actions": ["update"],
            "before": before,
            "after": {**before, "tags": {"environment": "stage"}},
        }
        self.plan["resource_changes"] = [
            {"address": address, "type": "aws_security_group", "change": change}
        ]
        tag_fact = {
            "name": "security_group.SecurityGroups.0.Tags.0.Value",
            "value": "test",
        }
        self.snapshot_fields["resources"] = [
            {
                "identity": {
                    "address": address,
                    "resource_type": "aws_security_group",
                    "physical_id": before["id"],
                },
                "status": "read",
                "facts": [
                    {
                        "name": "security_group.SecurityGroups.0.VpcId",
                        "value": before["vpc_id"],
                    },
                    {
                        "name": "security_group.SecurityGroups.0.Tags.0.Key",
                        "value": "environment",
                    },
                    tag_fact,
                ],
            }
        ]
        self.assertEqual(divergence_gate_exit_code(self.compare()), 0)
        for field, recorded in (
            ("ingress", []),
            ("egress", [{"description": "recorded rule"}]),
        ):
            with self.subTest(field=field):
                change["before"] = {**before, field: recorded}
                change["after"] = {
                    **change["before"],
                    "tags": {"environment": "stage"},
                }
                result = self.compare()
                row = result.resources[0]
                self.assertEqual(row.status, "unknown")
                self.assertEqual(row.reason, "comparable_facts_incomplete")
                self.assertIn("tags.environment", row.checked_attributes)
                self.assertEqual(divergence_gate_exit_code(result), 2)
        tag_fact["value"] = "drifted"
        result = self.compare()
        self.assertEqual(result.resources[0].status, "diverged")
        self.assertEqual(result.resources[0].reason, "comparable_facts_incomplete")
        self.assertEqual(divergence_gate_exit_code(result), 3)

    def test_name_based_cluster_requires_qualified_scope(self):
        address = "aws_rds_cluster.example"
        account = "000000000000"
        arn = f"arn:aws:rds:us-east-1:{account}:cluster:example"
        before = {"id": "example", "deletion_protection": True}
        self.plan["resource_changes"] = [
            {
                "address": address,
                "type": "aws_rds_cluster",
                "change": {"actions": ["update"], "before": before, "after": before},
            }
        ]
        identity = {
            "address": address,
            "resource_type": "aws_rds_cluster",
            "physical_id": "example",
            "arn": arn,
            "region": "us-east-1",
        }
        self.snapshot_fields["resources"] = [
            {
                "identity": identity,
                "status": "read",
                "facts": [
                    {
                        "name": "db_cluster.DBClusters.0.DeletionProtection",
                        "value": True,
                    }
                ],
            }
        ]
        self.assertEqual(self.compare().resources[0].status, "unknown")

        before["arn"] = arn
        self.assertEqual(self.compare().resources[0].status, "match")
        self.snapshot_fields["scope"] = "[MASKED_ACCOUNT]"
        identity["arn"] = arn.replace(account, "[MASKED_ACCOUNT]")
        self.assertEqual(self.compare().resources[0].status, "unknown")

        self.snapshot_fields["scope"] = account
        identity["arn"] = arn
        del before["arn"]
        before.update(account_id=account, region="us-east-1")
        self.assertEqual(self.compare().resources[0].status, "match")
        before["account_id"] = "111111111111"
        self.assertEqual(self.compare().resources[0].status, "unknown")

    def test_unproven_chronology_or_observation_age_preserves_a_denied_read(self):
        for timestamp, observation_status in (
            (None, "current"),
            ("2026-11-20T12:00:01Z", "current"),
            ("2026-11-20T10:00:00Z", "stale"),
            ("2026-11-20T10:00:00Z", "unknown"),
        ):
            with self.subTest(
                timestamp=timestamp, observation_status=observation_status
            ):
                self.plan["timestamp"] = timestamp
                result = self.compare(observation_status=observation_status)
                rows = {row.address.rsplit(".", 1)[-1]: row for row in result.resources}
                self.assertEqual(result.observation_status, observation_status)
                self.assertFalse(result.diverged)
                self.assertEqual(rows["match"].status, "unknown")
                self.assertEqual(rows["unreadable"].status, "unreadable")
                self.assertEqual(
                    rows["unreadable"].missing_permission, "ec2:DescribeInstances"
                )

    def test_denial_cannot_be_attributed_across_conflicting_resource_scope(self):
        self._observation("unreadable")["identity"]["region"] = "us-east-1"
        self._change("unreadable")["before"]["region"] = "us-west-2"
        row = next(
            item
            for item in self.compare().resources
            if item.address.endswith(".unreadable")
        )
        self.assertEqual(row.status, "unknown")
        self.assertEqual(row.reason, "observation_identity_unverified")
        self.assertIsNone(row.missing_permission)

        self._change("unreadable")["before"]["region"] = "us-east-1"
        self.plan["timestamp"] = None
        row = next(
            item
            for item in self.compare().resources
            if item.address.endswith(".unreadable")
        )
        self.assertEqual(row.status, "unreadable")
        self.assertEqual(row.missing_permission, "ec2:DescribeInstances")

    def test_out_of_range_utc_offset_leaves_chronology_unverified(self):
        for offset in ("+00:60", "-00:60", "+05:99", "+24:00"):
            with self.subTest(offset=offset):
                self.plan["timestamp"] = f"2026-11-20T10:00:00{offset}"
                result = self.compare()
                self.assertEqual(result.freshness.reason, "plan_timestamp_unavailable")
                self.assertFalse(result.diverged)
                matched = next(
                    item for item in result.resources if item.address.endswith(".match")
                )
                self.assertEqual(matched.status, "unknown")

        self.plan["timestamp"] = "2026-11-20T12:30:00+02:30"
        self.assertEqual(self.compare().freshness.age_seconds, 7200)

    def test_timestamp_submicrosecond_remainder_cannot_verify_chronology(self):
        self.plan["resource_changes"] = [
            row
            for row in self.plan["resource_changes"]
            if row["address"] == "aws_instance.match"
        ]
        for timestamp in (
            "2026-11-20T12:00:00.0000001Z",
            "2026-11-20T11:00:00.0000000001-01:00",
        ):
            with self.subTest(timestamp=timestamp):
                self.plan["timestamp"] = timestamp
                result = self.compare()
                self.assertEqual(result.freshness.reason, "plan_timestamp_unavailable")
                self.assertEqual(result.resources[0].status, "unknown")
                self.assertEqual(divergence_gate_exit_code(result), 2)

        self.plan["timestamp"] = "2026-11-20T12:00:00.000000000Z"
        result = self.compare()
        self.assertEqual(result.freshness.age_seconds, 0)
        self.assertEqual(divergence_gate_exit_code(result), 0)

    def test_noop_requires_consistent_values_and_unique_change_identity(self):
        update = next(
            row
            for row in self.plan["resource_changes"]
            if row["address"] == "aws_instance.match"
        )
        noop = copy.deepcopy(update)
        noop["change"]["actions"] = ["no-op"]
        noop["change"]["after"] = copy.deepcopy(noop["change"]["before"])
        self.plan["resource_changes"] = [noop]
        self.assertEqual(self.compare().resources, ())

        contradictory = copy.deepcopy(noop)
        contradictory["change"]["after"]["disable_api_termination"] = False
        unknown = copy.deepcopy(noop)
        unknown["change"]["after_unknown"] = {"disable_api_termination": True}
        for rows in (
            [contradictory],
            [unknown],
            [update, noop],
            [noop, update],
            [noop, noop],
        ):
            with self.subTest(rows=rows):
                self.plan["resource_changes"] = rows
                with self.assertRaises(DivergenceError):
                    self.compare()

    def test_pure_create_cannot_match_using_recorded_prior_values(self):
        row = next(
            row
            for row in self.plan["resource_changes"]
            if row["address"] == "aws_instance.match"
        )
        self.plan["resource_changes"] = [row]
        change = row["change"]
        change["actions"] = ["create"]
        with self.assertRaises(DivergenceError):
            self.compare()

        change["before"] = None
        result = self.compare()
        self.assertEqual(result.resources[0].status, "unknown")
        self.assertEqual(divergence_gate_exit_code(result), 2)

    def test_incomplete_or_errored_plans_cannot_clear_an_empty_comparison(self):
        self.plan["resource_changes"] = []
        self.assertEqual(self.compare().resources, ())
        for fields in (
            {"complete": False},
            {"errored": True},
            {"deferred_changes": [{"reason": "resource_config_unknown"}]},
        ):
            with self.subTest(fields=fields):
                original = self.plan
                self.plan = {**original, **fields}
                try:
                    with self.assertRaises(DivergenceError):
                        self.compare()
                finally:
                    self.plan = original
        self.plan.update(complete=True, errored=False, deferred_changes=[])
        self.assertEqual(self.compare().resources, ())

    def test_bad_snapshot_digest_invalid_plan_and_duplicate_changes_are_rejected(self):
        source = build_snapshot(**self.snapshot_fields)
        with self.assertRaises(ValueError):
            compare_plan(self.plan, source.model_copy(update={"digest": "0" * 64}))
        self.assertEqual(source, validate_snapshot(source))
        self.plan["resource_changes"].append(
            copy.deepcopy(self.plan["resource_changes"][0])
        )
        with self.assertRaises(DivergenceError):
            self.compare()
