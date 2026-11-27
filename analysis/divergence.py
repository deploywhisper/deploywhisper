"""Compare a recorded plan with selected facts from a retained cloud observation."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Literal

from pydantic import ConfigDict, Field, StrictBool, StrictInt, StrictStr

from cloud.base import FrozenModel, LiveContextSnapshot, ReadStatus, validate_snapshot
from cloud.redaction import _numeric_value, _private_name, _raw_name, _raw_scalar
from cloud.redaction import _screen_numeric_text
from cloud.reflection import _ID_PREFIX
from services.content_security import redact_text, sensitive_artifact_values

ComparisonStatus = Literal["match", "diverged", "unknown", "unreadable"]
ObservationStatus = Literal["current", "stale", "unknown"]
ComparableScalar = StrictBool | StrictInt | StrictStr
_BEFORE = ("before_sensitive",)
_AFTER = ("after_sensitive", "after_unknown")
_PLAN_ACTIONS = frozenset(
    (
        frozenset(("no-op",)),
        frozenset(("read",)),
        frozenset(("create",)),
        frozenset(("update",)),
        frozenset(("delete",)),
        frozenset(("create", "delete")),
    )
)
_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(?P<fraction>\d+))?"
    r"(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)
_MARKERS = ("[REDACTED]", "[MASKED_ACCOUNT]", "[BLOCKED")
_ACCOUNT = re.compile(r"(?<![0-9])[0-9]{12}(?![0-9])")
_SCOPED_ARN = re.compile(
    r"arn:aws:(?P<service>[a-z0-9-]+):(?P<region>[a-z0-9-]*):"
    r"(?P<account>[0-9]{12}):[A-Za-z0-9_:/+.,=@-]+"
)
_TAG_KEY = re.compile(r"[A-Za-z0-9_.:/@+=-]{1,128}")
_EC2_GROUPS = "vpc_security_group_ids"
_EC2_GROUP_FACT_PREFIX = "instance.Reservations.0.Instances.0.SecurityGroups."
_EC2_GROUP_ID = re.compile(r"sg-(?:[0-9a-f]{8}|[0-9a-f]{17})")
# The names match scalar facts projected by the qualified 17.3 read catalog.
# A field is comparable only with the same type, exact identity and a complete read.
_FIELDS = {
    "aws_instance": (
        (
            "disable_api_termination",
            "termination_protection.DisableApiTermination.Value",
            bool,
            True,
        ),
        ("subnet_id", "instance.Reservations.0.Instances.0.SubnetId", str, True),
        (
            "availability_zone",
            "instance.Reservations.0.Instances.0.Placement.AvailabilityZone",
            str,
            False,
        ),
    ),
    "aws_security_group": (
        ("vpc_id", "security_group.SecurityGroups.0.VpcId", str, True),
    ),
    "aws_network_interface": (
        ("subnet_id", "eni.NetworkInterfaces.0.SubnetId", str, True),
    ),
    "aws_subnet": (
        ("vpc_id", "subnet.Subnets.0.VpcId", str, True),
        ("availability_zone", "subnet.Subnets.0.AvailabilityZone", str, False),
    ),
    "aws_vpc": (("cidr_block", "vpc.Vpcs.0.CidrBlock", str, True),),
    "aws_ebs_volume": (
        ("encrypted", "volume.Volumes.0.Encrypted", bool, True),
        ("availability_zone", "volume.Volumes.0.AvailabilityZone", str, False),
    ),
    "aws_ebs_snapshot": (("encrypted", "snapshot.Snapshots.0.Encrypted", bool, True),),
    "aws_db_instance": (
        ("deletion_protection", "db.DBInstances.0.DeletionProtection", bool, True),
        (
            "backup_retention_period",
            "db.DBInstances.0.BackupRetentionPeriod",
            int,
            True,
        ),
        ("multi_az", "db.DBInstances.0.MultiAZ", bool, False),
    ),
    "aws_rds_cluster": (
        (
            "deletion_protection",
            "db_cluster.DBClusters.0.DeletionProtection",
            bool,
            True,
        ),
        (
            "backup_retention_period",
            "db_cluster.DBClusters.0.BackupRetentionPeriod",
            int,
            True,
        ),
    ),
    "aws_dynamodb_table": (
        (
            "deletion_protection_enabled",
            "table.Table.DeletionProtectionEnabled",
            bool,
            True,
        ),
    ),
    "aws_lambda_function": (
        (
            "reserved_concurrent_executions",
            "function_concurrency.ReservedConcurrentExecutions",
            int,
            False,
        ),
    ),
}
_TAG_ARRAYS = {
    "aws_instance": "instance.Reservations.0.Instances.0.Tags.",
    "aws_security_group": "security_group.SecurityGroups.0.Tags.",
    "aws_s3_bucket": "bucket_tags.TagSet.",
    "aws_iam_role": "role.Role.Tags.",
}
_EXISTENCE_FACT = "resource.exists"
_PHYSICAL_ID_FACT = "resource.physical_id"


class DivergenceError(ValueError):
    """A closed plan comparison error that carries no input data."""


class _ComparisonModel(FrozenModel):
    model_config = ConfigDict(hide_input_in_errors=True)


class PlanFreshness(_ComparisonModel):
    status: Literal["current", "stale", "unknown"]
    plan_generated_at: datetime | None = None
    observed_at: datetime
    age_seconds: float | None = None
    threshold_seconds: int
    reason: (
        Literal["plan_timestamp_unavailable", "observation_predates_plan"] | None
    ) = None


class AttributeDivergence(_ComparisonModel):
    attribute: str
    recorded: ComparableScalar | None
    live: ComparableScalar
    planned: ComparableScalar | None
    planned_known: bool
    fact_name: str
    requires_caution: bool
    supporting_fact_names: tuple[str, ...] = Field(default=(), exclude=True)


class ResourceComparison(_ComparisonModel):
    address: str
    resource_type: str
    status: ComparisonStatus
    checked_attributes: tuple[str, ...] = ()
    differences: tuple[AttributeDivergence, ...] = ()
    reason: str | None = None
    missing_permission: str | None = None


class DivergenceAssessment(_ComparisonModel):
    live_context_version: Literal[1] = 1
    snapshot_digest: str
    freshness: PlanFreshness
    observation_status: ObservationStatus = "current"
    resources: tuple[ResourceComparison, ...]
    diverged: bool
    requires_caution: bool


class _PlanScreen:
    def __init__(self, sensitive: tuple[str, ...], *, mask_accounts: bool):
        self.sensitive = sensitive
        self.mask_accounts = mask_accounts
        self.numeric = {
            number
            for value in sensitive
            if (number := _numeric_value(value)) is not None
        }

    def text(self, value, *, maximum=2048) -> bool:
        return (
            isinstance(value, str)
            and 0 < len(value) <= maximum
            and all(ord(ch) >= 32 and ord(ch) != 127 for ch in value)
            and not _raw_scalar(value)
            and not any(marker in value for marker in _MARKERS)
            and not (self.mask_accounts and _ACCOUNT.search(value))
            and redact_text(value, sensitive_values=self.sensitive) == value
            and _screen_numeric_text(value, self.numeric) == value
        )

    def value(self, value, expected) -> bool:
        if type(value) is not expected:
            return False
        if expected is str:
            return self.text(value, maximum=256)
        return expected is bool or (
            -1 <= value <= 2**31 - 1 and _numeric_value(value) not in self.numeric
        )

    def tag_key(self, key) -> bool:
        return bool(
            self.text(key, maximum=128)
            and _TAG_KEY.fullmatch(key)
            and not _raw_name(key)
            and not _private_name(key)
        )


def _plan_freshness(
    plan: dict, observed_at: datetime, threshold: int, screen: _PlanScreen
) -> PlanFreshness:
    stamp = plan.get("timestamp")
    match = (
        _TIMESTAMP.fullmatch(stamp)
        if isinstance(stamp, str) and screen.text(stamp, maximum=64)
        else None
    )
    # datetime truncates nonzero sub-microsecond digits, potentially ordering
    # a post-observation plan at the observation's exact timestamp.
    generated = None
    if match and not (match["fraction"] or "")[6:].strip("0"):
        try:
            generated = datetime.fromisoformat(
                match[0].replace("Z", "+00:00")
            ).astimezone(timezone.utc)
        except (ValueError, OverflowError):
            generated = None
    if generated is None:
        return PlanFreshness(
            status="unknown",
            reason="plan_timestamp_unavailable",
            observed_at=observed_at,
            threshold_seconds=threshold,
        )
    age = (observed_at - generated).total_seconds()
    if age < 0:
        return PlanFreshness(
            status="unknown",
            reason="observation_predates_plan",
            plan_generated_at=generated,
            observed_at=observed_at,
            threshold_seconds=threshold,
        )
    return PlanFreshness(
        status="stale" if age > threshold else "current",
        plan_generated_at=generated,
        age_seconds=age,
        observed_at=observed_at,
        threshold_seconds=threshold,
    )


def _identity_text(value, max_length=2048):
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise DivergenceError("invalid_plan_identity")
    return value


def _prior_state(plan):
    state = plan.get("prior_state")
    if state is None:
        return {}
    if not isinstance(state, dict) or state.get("format_version", "1.0") != "1.0":
        raise DivergenceError("invalid_prior_state")
    values = state.get("values", {})
    if not isinstance(values, dict):
        raise DivergenceError("invalid_prior_state")
    modules = [values.get("root_module", {})]
    prior = {}
    count = 0
    while modules:
        module = modules.pop()
        count += 1
        if count > 10000 or not isinstance(module, dict):
            raise DivergenceError("invalid_prior_state")
        resources, children = (
            module.get("resources", []),
            module.get("child_modules", []),
        )
        if (
            not isinstance(resources, list)
            or not isinstance(children, list)
            or len(prior) + len(resources) > 10000
            or len(modules) + len(children) > 10000
        ):
            raise DivergenceError("invalid_prior_state")
        for row in resources:
            if not isinstance(row, dict):
                raise DivergenceError("invalid_prior_state")
            address = _identity_text(row.get("address"))
            if address in prior:
                raise DivergenceError("duplicate_plan_address")
            prior[address] = row
        modules.extend(children)
    return prior


def _blocked(mask, *path) -> bool:
    for key in path:
        if mask is None or mask is False:
            return False
        if not isinstance(mask, dict):
            return True
        mask = mask.get(key)
    return mask is True or bool(mask)


def _matching_identity(before, resource, snapshot, screen, before_masks):
    identity = resource.identity
    if identity.resource_type.startswith("aws_") and snapshot.provider != "aws":
        return False
    if identity.region and snapshot.regions and identity.region not in snapshot.regions:
        return False
    region = identity.region or (
        snapshot.regions[0] if len(snapshot.regions) == 1 else None
    )
    expected_region = before.get("region")
    if expected_region and region != expected_region:
        return False
    account = snapshot.scope if _ACCOUNT.fullmatch(snapshot.scope) else None
    expected_account = before.get("account_id")
    if expected_account and account and expected_account != account:
        return False

    matched_arn = matched_id = False
    identifier = "id" if before.get("id") else "uuid"
    for key, live in (
        ("arn", identity.arn),
        (identifier, identity.physical_id),
    ):
        if any(_blocked(mask, key) for mask in before_masks):
            continue
        candidate = before.get(key)
        arn = _SCOPED_ARN.fullmatch(candidate) if isinstance(candidate, str) else None
        if arn and (
            (account and arn["account"] != account)
            or (expected_account and arn["account"] != expected_account)
            or (arn["region"] and region and arn["region"] != region)
            or (
                arn["region"]
                and snapshot.regions
                and arn["region"] not in snapshot.regions
            )
        ):
            return False
        if not screen.text(candidate) or not screen.text(live):
            continue
        if candidate != live:
            # The collector deliberately reconstructs SQS URLs from the
            # authorized name, ARN and region. Only its recorded ARN can bind.
            if identity.resource_type == "aws_sqs_queue" and (
                candidate.startswith("https://") and live.startswith("https://")
            ):
                continue
            return False
        if arn and (arn["region"] or arn["service"] == "iam"):
            matched_arn = True
        if key == identifier:
            matched_id = True

    if snapshot.provider != "aws":
        return matched_arn or matched_id
    if matched_arn:
        return True
    if not matched_id:
        return False
    prefix = _ID_PREFIX.get(identity.resource_type)
    if prefix and re.fullmatch(
        prefix + r"-(?:[0-9a-f]{8}|[0-9a-f]{17})", identity.physical_id
    ):
        return True
    return bool(
        account
        and expected_account == account
        and expected_region
        and identity.region == expected_region
        and expected_region in snapshot.regions
        and not any(
            _blocked(mask, key)
            for mask in before_masks
            for key in ("account_id", "region")
        )
    )


def _live_tags(facts, family):
    if family == "aws_lambda_function":
        prefix = "function_tags.Tags."
        return {
            name.removeprefix(prefix): (name, value)
            for name, value in facts.items()
            if name.startswith(prefix)
        }
    prefix = _TAG_ARRAYS.get(family)
    tags = {}
    if prefix:
        for name, key in facts.items():
            index = name.removeprefix(prefix).split(".")[0]
            if (
                name != f"{prefix}{index}.Key"
                or not index.isascii()
                or not index.isdecimal()
            ):
                continue
            value_name = f"{prefix}{index}.Value"
            if not isinstance(key, str) or value_name not in facts:
                continue
            # A duplicate key invalidates the tag fact rather than choosing an
            # arbitrary value from malformed provider metadata.
            tags[key] = (
                (value_name, facts[value_name]) if key not in tags else ("", None)
            )
    return tags


def _tags_source(values):
    for key in ("tags_all", "tags"):
        if isinstance(values.get(key), dict):
            return values[key]
    return None


def _ec2_group_ids(value):
    """Return an order-independent set of exact group IDs from recorded values."""
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not _EC2_GROUP_ID.fullmatch(item) for item in value
    ):
        return None
    groups = set(value)
    return tuple(sorted(groups)) if len(groups) == len(value) else None


def _ec2_group_facts(facts):
    names = tuple(name for name in facts if name.startswith(_EC2_GROUP_FACT_PREFIX))
    # Projection has no explicit marker for an empty or omitted collection.
    # Missing projections and unexpected fact paths cannot prove membership.
    if not names or set(names) != {
        f"{_EC2_GROUP_FACT_PREFIX}{index}.GroupId" for index in range(len(names))
    }:
        return None
    groups = _ec2_group_ids([facts[name] for name in names])
    return (groups, names) if groups is not None else None


def _changed_fields(before, after):
    return {
        name
        for name in before.keys() | after.keys()
        if name not in before
        or name not in after
        or json.dumps(before[name], sort_keys=True)
        != json.dumps(after[name], sort_keys=True)
    }


def _recorded_before_conflicts(family, before, prior):
    identity_fields = {"id", "uuid", "arn", "account_id", "region"}
    comparable_fields = identity_fields | {
        field for field, *_ in _FIELDS.get(family, ())
    }
    if any(
        type(before[field]) is not type(prior[field]) or before[field] != prior[field]
        for field in comparable_fields & before.keys() & prior.keys()
    ):
        return True
    before_id = before.get("id") or before.get("uuid")
    prior_id = prior.get("id") or prior.get("uuid")
    if before_id and prior_id and before_id != prior_id:
        return True
    if family == "aws_instance" and _EC2_GROUPS in before and _EC2_GROUPS in prior:
        groups = _ec2_group_ids(before[_EC2_GROUPS])
        if groups is None or groups != _ec2_group_ids(prior[_EC2_GROUPS]):
            return True
    if family not in _TAG_ARRAYS and family != "aws_lambda_function":
        return False
    # Explicit maps for the same field describe membership. If the sources
    # expose different tag fields, compare only the keys both actually record.
    for field in ("tags_all", "tags"):
        old, recorded = before.get(field), prior.get(field)
        if (
            isinstance(old, dict)
            and isinstance(recorded, dict)
            and _changed_fields(old, recorded)
        ):
            return True
    old_tags, recorded_tags = _tags_source(before), _tags_source(prior)
    return (
        old_tags is not None
        and recorded_tags is not None
        and any(
            old_tags[key] != recorded_tags[key]
            for key in old_tags.keys() & recorded_tags.keys()
        )
    )


def _has_unknown_value(mask):
    if isinstance(mask, dict):
        return any(_has_unknown_value(value) for value in mask.values())
    if isinstance(mask, list):
        return any(_has_unknown_value(value) for value in mask)
    return mask is not None and mask is not False


def _covers_plan_change(before, change, checked, specs):
    after = change.get("after")
    if change["actions"] == ["delete"]:
        # The deletion depends on the resource's identity and observed prior
        # attributes, rather than the planned absence of every field.
        identity_fields = {"id", "uuid", "arn", "account_id", "region"}
        after = {key: value for key, value in before.items() if key in identity_fields}
    if after is None or change.get("after_unknown") is True:
        return False

    required_fields = set()
    required_tags = set()
    change_before = change.get("before")
    for recorded in (before, change_before if change_before is not None else before):
        for field in _changed_fields(recorded, after):
            old, new = recorded.get(field), after.get(field)
            if (
                field in {"tags", "tags_all"}
                and isinstance(old, dict)
                and isinstance(new, dict)
            ):
                required_tags.update(_changed_fields(old, new))
            else:
                required_fields.add(field)

    for field, mask in (change.get("after_unknown") or {}).items():
        if field in {"tags", "tags_all"} and isinstance(mask, dict):
            required_tags.update(
                key for key, value in mask.items() if _has_unknown_value(value)
            )
        elif _has_unknown_value(mask):
            required_fields.add(field)

    # Physical IDs may be checked under the normalized comparison name.
    covered_fields = {field for field, *_ in specs if field in checked}
    if _EC2_GROUPS in checked:
        covered_fields.add(_EC2_GROUPS)
    if "physical_id" in checked:
        covered_fields.add("id" if before.get("id") is not None else "uuid")
    return required_fields <= covered_fields and all(
        f"tags.{key}" in checked for key in required_tags
    )


def _compare_values(before, change, before_masks, resource, screen, destructive):
    facts = {fact.name: fact.value for fact in resource.facts}
    family = resource.identity.resource_type
    deleting = change["actions"] == ["delete"]
    after = {} if deleting else change.get("after") or {}
    after_masks = tuple(change.get(field) for field in _AFTER)
    checked = []
    differences = []
    # The current AWS projection cannot verify whole rule sets, including
    # empty sets. A covered tag edit alone cannot establish that they match.
    incomplete = family == "aws_security_group" and any(
        field in before or any(_blocked(mask, field) for mask in before_masks)
        for field in ("ingress", "egress")
    )

    def compare(
        attribute, fact_name, old, new, wanted, *, known, security, supporting=()
    ):
        checked.append(attribute)
        if old != new:
            differences.append(
                AttributeDivergence(
                    attribute=attribute,
                    recorded=old,
                    live=new,
                    planned=wanted if known else None,
                    planned_known=known,
                    fact_name=fact_name,
                    requires_caution=security or destructive,
                    supporting_fact_names=supporting,
                )
            )

    exists = facts.get(_EXISTENCE_FACT)
    if type(exists) is bool:
        if not exists:
            if set(facts) != {_EXISTENCE_FACT}:
                return (), (), True
            compare(
                "exists",
                _EXISTENCE_FACT,
                True,
                False,
                not deleting,
                known=deleting or bool(after),
                security=True,
            )
            return tuple(checked), tuple(differences), False
        checked.append("exists")
    observed_physical_id = facts.get(_PHYSICAL_ID_FACT)
    if observed_physical_id is not None:
        identity_key = "id" if before.get("id") is not None else "uuid"
        expected = before.get(identity_key)
        if (
            screen.value(expected, str)
            and screen.value(observed_physical_id, str)
            and not any(_blocked(mask, identity_key) for mask in before_masks)
        ):
            wanted = after.get(identity_key)
            compare(
                "physical_id",
                _PHYSICAL_ID_FACT,
                expected,
                observed_physical_id,
                wanted,
                known=deleting
                or (
                    screen.value(wanted, str)
                    and not any(_blocked(mask, identity_key) for mask in after_masks)
                ),
                security=True,
            )
        else:
            incomplete = True

    specs = _FIELDS.get(family, ())
    if family == "aws_instance" and (
        _EC2_GROUPS in before
        or any(_blocked(mask, _EC2_GROUPS) for mask in before_masks)
    ):
        recorded_groups = _ec2_group_ids(before.get(_EC2_GROUPS))
        live_groups_and_facts = _ec2_group_facts(facts)
        if (
            recorded_groups is None
            or live_groups_and_facts is None
            or any(_blocked(mask, _EC2_GROUPS) for mask in before_masks)
        ):
            incomplete = True
        else:
            live_groups, (fact_name, *supporting) = live_groups_and_facts
            if not all(
                screen.value(group, str) for group in (*recorded_groups, *live_groups)
            ):
                incomplete = True
            else:
                planned_groups = _ec2_group_ids(after.get(_EC2_GROUPS))
                known = deleting or (
                    planned_groups is not None
                    and all(screen.value(group, str) for group in planned_groups)
                    and not any(_blocked(mask, _EC2_GROUPS) for mask in after_masks)
                )
                compare(
                    _EC2_GROUPS,
                    fact_name,
                    ", ".join(recorded_groups),
                    ", ".join(live_groups),
                    ", ".join(planned_groups) if planned_groups is not None else None,
                    known=known,
                    security=True,
                    supporting=supporting,
                )
    if family in _TAG_ARRAYS or family == "aws_lambda_function":
        prior_tags = _tags_source(before)
        planned_tags = _tags_source(after)
        observed_tags = _live_tags(facts, family)
        if prior_tags is not None:
            for key in sorted(set(prior_tags) | set(observed_tags)):
                if not screen.tag_key(key) or any(
                    _blocked(mask, container, key)
                    for mask in before_masks
                    for container in ("tags", "tags_all")
                ):
                    incomplete = True
                    continue
                fact_name, observed = observed_tags.get(key, ("", None))
                prior = prior_tags.get(key)
                if (observed != "" and not screen.value(observed, str)) or (
                    key in prior_tags and prior != "" and not screen.value(prior, str)
                ):
                    incomplete = True
                    continue
                planned = planned_tags.get(key) if planned_tags is not None else None
                known = deleting or (
                    planned_tags is not None
                    and (
                        key not in planned_tags
                        or planned == ""
                        or screen.value(planned, str)
                    )
                    and not any(
                        _blocked(mask, container, key)
                        for mask in after_masks
                        for container in ("tags", "tags_all")
                    )
                )
                compare(
                    f"tags.{key}",
                    fact_name,
                    prior,
                    observed,
                    planned,
                    known=known,
                    security=False,
                )
    for attribute, fact_name, expected_type, security in specs:
        if attribute not in before:
            continue
        prior, live = before[attribute], facts.get(fact_name)
        if (
            not screen.value(prior, expected_type)
            or not screen.value(live, expected_type)
            or any(_blocked(mask, attribute) for mask in before_masks)
        ):
            incomplete = True
            continue
        planned = after.get(attribute)
        known = deleting or (
            screen.value(planned, expected_type)
            and not any(_blocked(mask, attribute) for mask in after_masks)
        )
        compare(
            attribute,
            fact_name,
            prior,
            live,
            planned,
            known=known,
            security=security,
        )
    return (
        tuple(sorted(checked)),
        tuple(sorted(differences, key=lambda item: item.attribute)),
        incomplete or not _covers_plan_change(before, change, checked, specs),
    )


def _compare_resource(
    address,
    family,
    row,
    change,
    state,
    observed,
    snapshot,
    screen,
    freshness,
    observation_status,
):
    base = {"address": address, "resource_type": family}
    if not screen.text(address) or not screen.text(family, maximum=128):
        return ResourceComparison(
            status="unknown",
            reason="identity_screened",
            address="[REDACTED]",
            resource_type="unknown",
        )
    if row.get("mode", "managed") != "managed":
        return ResourceComparison(
            status="unknown", reason="unmanaged_observation", **base
        )
    if observed is None or observed.identity.resource_type != family:
        return ResourceComparison(
            status="unknown", reason="observation_missing", **base
        )
    unreadable = (
        observed.status == ReadStatus.UNREADABLE
        or observed.missing_permission is not None
    )
    if observed.status != ReadStatus.READ and not unreadable:
        return ResourceComparison(
            status="unknown", reason="observation_incomplete", **base
        )
    before = change.get("before")
    previous = row.get("previous_address") or row["address"]
    prior = None
    if (
        row.get("deposed") is None
        and (change["actions"] != ["create"] or change.get("importing"))
        and (previous == row["address"] or before is None)
    ):
        prior = state.get(previous)
        if prior is None and previous != row["address"]:
            prior = state.get(row["address"])
        if prior is not None:
            if prior.get("type", family) != family:
                return ResourceComparison(
                    status="unknown", reason="prior_type_mismatch", **base
                )
            prior_values = prior.get("values")
            if isinstance(before, dict) and isinstance(prior_values, dict):
                if _recorded_before_conflicts(family, before, prior_values):
                    return ResourceComparison(
                        status="unknown", reason="recorded_prior_state_conflict", **base
                    )
                # A field recorded by only one source still carries evidence.
                # In particular, keep explicit scope from change.before.
                before = {**before, **prior_values}
            elif prior_values is not None:
                before = prior_values
    before_masks = (
        prior.get("sensitive_values") if prior is not None else None,
        *(change.get(field) for field in _BEFORE),
    )
    if (
        not isinstance(before, dict)
        or any(
            mask is not None and not isinstance(mask, (bool, dict))
            for mask in before_masks
        )
        or not _matching_identity(before, observed, snapshot, screen, before_masks)
    ):
        return ResourceComparison(
            status="unknown", reason="observation_identity_unverified", **base
        )
    if unreadable:
        permission = observed.missing_permission
        return ResourceComparison(
            status="unreadable",
            reason="observation_unreadable",
            missing_permission=permission
            if screen.text(permission, maximum=256)
            else None,
            **base,
        )
    if freshness.reason is not None:
        return ResourceComparison(status="unknown", reason=freshness.reason, **base)
    if observation_status != "current":
        return ResourceComparison(
            status="unknown", reason=f"observation_{observation_status}", **base
        )
    checked, differences, incomplete = _compare_values(
        before,
        change,
        before_masks,
        observed,
        screen,
        "delete" in change["actions"],
    )
    status: ComparisonStatus = (
        "diverged"
        if differences
        else "unknown"
        if not checked or incomplete
        else "match"
    )
    return ResourceComparison(
        status=status,
        checked_attributes=checked,
        differences=differences,
        reason="comparable_facts_incomplete" if not checked or incomplete else None,
        **base,
    )


def compare_plan(
    plan: dict,
    snapshot: LiveContextSnapshot,
    *,
    stale_after_seconds: int = 3600,
    sensitive_values: tuple[str, ...] = (),
    observation_status: ObservationStatus = "current",
) -> DivergenceAssessment:
    """Observe the supplied retained data without resolving credentials or making calls."""
    if (
        not isinstance(plan, dict)
        or plan.get("format_version") != "1.2"
        or type(stale_after_seconds) is not int
        or stale_after_seconds <= 0
        or observation_status not in ("current", "stale", "unknown")
    ):
        raise DivergenceError("invalid_divergence_input")
    if (
        plan.get("complete", True) is not True
        or plan.get("errored", False) is not False
        or plan.get("deferred_changes", []) != []
    ):
        raise DivergenceError("incomplete_divergence_plan")
    snapshot = validate_snapshot(snapshot)
    try:
        encoded = json.dumps(plan, allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError):
        raise DivergenceError("invalid_divergence_plan") from None
    if len(encoded) > 50 * 1024 * 1024:
        raise DivergenceError("divergence_plan_bound")
    changes = plan.get("resource_changes", [])
    if not isinstance(changes, list) or len(changes) > 10000:
        raise DivergenceError("invalid_divergence_plan")
    prior = _prior_state(plan)
    screen = _PlanScreen(
        tuple(dict.fromkeys((*sensitive_values, *sensitive_artifact_values(encoded)))),
        mask_accounts="[MASKED_ACCOUNT]" in snapshot.scope,
    )
    freshness = _plan_freshness(
        plan, snapshot.read_window_start, stale_after_seconds, screen
    )
    observed = {resource.identity.address: resource for resource in snapshot.resources}
    resources: list[ResourceComparison] = []
    seen: set[str] = set()
    for row in changes:
        if not isinstance(row, dict) or not isinstance(row.get("change"), dict):
            raise DivergenceError("invalid_divergence_plan")
        change = row["change"]
        actions = change.get("actions")
        if (
            not isinstance(actions, list)
            or not actions
            or not all(isinstance(action, str) for action in actions)
            or len(actions) != len(set(actions))
            or frozenset(actions) not in _PLAN_ACTIONS
            or any(
                change.get(key) is not None and not isinstance(change[key], dict)
                for key in ("before", "after", "importing")
            )
            or any(
                change.get(key) is not None
                and not isinstance(change[key], (bool, dict))
                for key in (*_BEFORE, *_AFTER)
            )
            or (
                actions == ["create"]
                and not change.get("importing")
                and change.get("before") is not None
            )
        ):
            raise DivergenceError("invalid_divergence_plan")
        address = _identity_text(row.get("address"))
        previous = row.get("previous_address")
        if previous is not None:
            _identity_text(previous)
        ordinary_noop = (
            actions == ["no-op"]
            and previous in (None, address)
            and not change.get("importing")
        )
        deposed = row.get("deposed")
        if deposed is not None:
            digest = sha256(
                json.dumps([address, _identity_text(deposed)]).encode()
            ).hexdigest()
            suffix = f"#deposed:{digest}"
            address = address[: 2048 - len(suffix)] + suffix
        if address in seen:
            raise DivergenceError("duplicate_or_unbounded_plan_address")
        seen.add(address)
        if ordinary_noop:
            before, after = change.get("before"), change.get("after")
            if (
                (before is None) != (after is None)
                or _changed_fields(before or {}, after or {})
                or _has_unknown_value(change.get("after_unknown"))
            ):
                raise DivergenceError("invalid_divergence_plan")
            continue
        if len(resources) >= 1000:
            raise DivergenceError("duplicate_or_unbounded_plan_address")
        family = _identity_text(row.get("type"), 128)
        resources.append(
            _compare_resource(
                address,
                family,
                row,
                change,
                prior,
                observed.get(address),
                snapshot,
                screen,
                freshness,
                observation_status,
            )
        )
    return DivergenceAssessment(
        snapshot_digest=snapshot.digest,
        freshness=freshness,
        observation_status=observation_status,
        resources=tuple(sorted(resources, key=lambda row: row.address)),
        diverged=any(row.status == "diverged" for row in resources),
        requires_caution=any(
            diff.requires_caution for row in resources for diff in row.differences
        ),
    )
