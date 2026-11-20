"""Bounded, screened scalar projection of the frozen AWS response field catalog."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
import re

from cloud.base import ResourceIdentity, SnapshotFact
from cloud.aws.allowlist import _CATALOG
from cloud.aws.response_status import response_complete, _dns_name, _rows, _value
from cloud.redaction import _numeric_value, _screen_numeric_text
from services.content_security import (
    REDACTED,
    redact_text,
    redact_value,
    sensitive_artifact_values,
)


@dataclass(frozen=True)
class Projection:
    facts: tuple[SnapshotFact, ...]
    complete: bool


def _bounded(value, state, depth=0):
    state[0] += 1
    if state[0] > 20000 or depth > 24:
        raise ValueError("projection_bound")
    if isinstance(value, datetime):
        value = value.isoformat()
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, str):
        state[1] += len(value.encode("utf-8"))
        if len(value) > 16384 or state[1] > 1024 * 1024:
            raise ValueError("projection_bound")
        return value
    if isinstance(value, list):
        return [_bounded(item, state, depth + 1) for item in value]
    if isinstance(value, dict) and all(isinstance(k, str) for k in value):
        return {
            _bounded(k, state, depth + 1): _bounded(v, state, depth + 1)
            for k, v in value.items()
        }
    raise ValueError("projection_shape")


def _tags(value, *, tag_container=False, tag_row=False):
    """Normalize both AWS tag pair conventions before shared secret discovery.

    SDK tag values are strings. Malformed selected tag containers cannot safely
    participate in projection because their private-key association is unknown.
    """
    found = []
    if isinstance(value, dict):
        if tag_container:
            if not all(isinstance(v, str) for v in value.values()):
                raise ValueError("invalid_tag_shape")
            return [value]
        if tag_row:
            keys = [v for k, v in value.items() if k.lower() == "key"]
            values = [v for k, v in value.items() if k.lower() == "value"]
            if (
                len(keys) != 1
                or len(values) != 1
                or not all(isinstance(v, str) for v in keys + values)
            ):
                raise ValueError("invalid_tag_shape")
            return [{keys[0]: values[0]}]
        for key, child in value.items():
            found.extend(
                _tags(child, tag_container=key.lower() in {"tags", "tagset", "taglist"})
            )
    elif isinstance(value, list):
        for child in value:
            if tag_container and not isinstance(child, dict):
                raise ValueError("invalid_tag_shape")
            found.extend(_tags(child, tag_row=tag_container))
    elif tag_container or tag_row:
        raise ValueError("invalid_tag_shape")
    return found


def _screen_metadata(value, known):
    # The shared metadata mode screens lexical echoes and sensitive fields.
    return redact_value({"metadata": value}, sensitive_values=known)["metadata"]


def _redrive_policy(value):
    if not isinstance(value, str):
        raise ValueError("invalid_redrive_policy")
    policy = json.loads(value)
    if not isinstance(policy, dict):
        raise ValueError("invalid_redrive_policy")
    arn = policy.get("deadLetterTargetArn")
    count = policy.get("maxReceiveCount")
    # AWS models the outer attribute as a string and uses both integer and
    # decimal-string counts inside the JSON policy.
    if (
        not isinstance(arn, str)
        or not arn
        or not (
            (type(count) is int and count > 0)
            or (
                isinstance(count, str)
                and count.isascii()
                and count.isdecimal()
                and count.strip("0")
            )
        )
    ):
        raise ValueError("invalid_redrive_policy")
    return {"deadLetterTargetArn": arn, "maxReceiveCount": count}


def project_response(entry, response, *, scope, sensitive_values=()) -> Projection:
    """Only immutable selected facts leave the SDK worker; no raw body escapes."""
    raw = _bounded(response, [0, 0])
    if not isinstance(raw, dict):
        return Projection((), False)
    screening = _bounded({"response": raw, "tags": _tags(raw)}, [0, 0])
    known = tuple(
        dict.fromkeys(
            (
                *sensitive_values,
                *sensitive_artifact_values(json.dumps(screening).encode()),
            )
        )
    )
    numeric_secrets = {
        number for secret in known if (number := _numeric_value(secret)) is not None
    }
    projection_input = raw
    truncated = False
    if entry.capability == "queue":
        attributes = raw.get("Attributes")
        if isinstance(attributes, dict) and "RedrivePolicy" in attributes:
            # Decode before screening so masking a numeric leaf cannot break
            # the outer JSON string and discard an unaffected sibling.
            attributes = dict(attributes)
            encoded = attributes.pop("RedrivePolicy")
            try:
                attributes["RedrivePolicy"] = _redrive_policy(encoded)
            except (ValueError, RecursionError):
                truncated = True
            projection_input = {**raw, "Attributes": attributes}
    clean = _screen_metadata(projection_input, known)
    screened = clean != projection_input
    complete = response_complete(entry.capability, entry.call().parameters, raw)
    identity_raw = {
        k: v
        for k, v in raw.items()
        if k
        not in {
            "NextToken",
            "NextMarker",
            "Marker",
            "IsTruncated",
            "LastEvaluatedKey",
            "failures",
            "Failures",
            "Error",
        }
    }
    identity_complete = response_complete(
        entry.capability, entry.call().parameters, identity_raw
    )
    expected = dict(entry.expected)
    # The static request may select a bounded parent list. Narrow to the exact
    # recorded child identity, rather than accepting its lexicographic neighbor.
    if entry.capability == "event_mapping":
        rows = raw.get("EventSourceMappings")
        selected = (
            [
                row
                for row in rows
                if isinstance(row, dict)
                and all(row.get(k) == v for k, v in expected.items())
            ]
            if isinstance(rows, list)
            else []
        )
        if len(selected) != 1:
            return Projection((), False)
        clean["EventSourceMappings"] = [_screen_metadata(selected[0], known)]
    if entry.capability == "record":
        rows = raw.get("ResourceRecordSets")
        selected = (
            [
                row
                for row in rows
                if isinstance(row, dict)
                and _dns_name(row.get("Name")) == _dns_name(expected.get("Name"))
                and row.get("Type") == expected.get("Type")
                and (
                    "SetIdentifier" not in row
                    if expected.get("SetIdentifier") is None
                    else row.get("SetIdentifier") == expected["SetIdentifier"]
                )
            ]
            if isinstance(rows, list)
            else []
        )
        if len(selected) != 1:
            return Projection((), False)
        # A selected weighted variant is known even though metadata-only 17.2
        # correctly refuses variants without this recorded identity descriptor.
        identity_complete = len(rows) == 1
        complete = identity_complete and not any(
            raw.get(k)
            for k in ("IsTruncated", "NextToken", "NextMarker", "Error", "failures")
        )
        clean["ResourceRecordSets"] = [_screen_metadata(selected[0], known)]
    if not identity_complete:
        return Projection((), False)
    complete = complete and not screened
    facts = []

    def screen_numeric(value):
        if not numeric_secrets:
            return value
        if _numeric_value(value) in numeric_secrets:
            return REDACTED
        if isinstance(value, str):
            return _screen_numeric_text(value, numeric_secrets)
        return value

    def scalar(name, value, depth=0):
        nonlocal truncated
        if len(facts) >= 1000 or depth > 16 or len(name) > 128:
            truncated = True
            return
        if isinstance(value, dict):
            for k, v in sorted(value.items()):
                # Structured policies are not raw JSON blobs. Only their fixed
                # semantic subset is selected; conditions and arbitrary Sids
                # are intentionally unavailable in this collection slice.
                if "PolicyDocument" in name and k not in {
                    "Version",
                    "Statement",
                    "Effect",
                    "Principal",
                    "AWS",
                    "Service",
                    "Action",
                }:
                    truncated = True
                    continue
                if (
                    not re.fullmatch(r"[A-Za-z0-9_.:-]+", k)
                    or redact_text(k, sensitive_values=known) != k
                    or screen_numeric(k) != k
                    or redact_value({k: "probe"}).get(k) != "probe"
                ):
                    truncated = True
                    continue
                scalar(name + "." + k, v, depth + 1)
            return
        if isinstance(value, list):
            if len(value) > entry.max_results:
                truncated = True
            for index, item in enumerate(value[: entry.max_results]):
                scalar(name + "." + str(index), item, depth + 1)
            return
        if isinstance(value, str) and (
            "\n" in value or "\r" in value or value.lstrip().startswith(("{", "["))
        ):
            truncated = True
            return
        if (
            not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", name)
            or redact_text(name, sensitive_values=known) != name
            or screen_numeric(name) != name
        ):
            truncated = True
            return
        screened_value = screen_numeric(value)
        truncated |= screened_value != value
        facts.append(SnapshotFact(name=name, value=screened_value))

    def field(value, parts, prefix):
        nonlocal truncated
        if not parts:
            scalar(prefix, value)
            return
        part = parts[0]
        many = part.endswith("[]")
        key = part[:-2] if many else part
        if not isinstance(value, dict) or key not in value:
            return
        child = value[key]
        if many:
            if not isinstance(child, list):
                truncated = True
                return
            if len(child) > entry.max_results:
                truncated = True
            for index, row in enumerate(child[: entry.max_results]):
                field(row, parts[1:], prefix + "." + key + "." + str(index))
        else:
            field(child, parts[1:], prefix + "." + key)

    for path in _CATALOG["operations"][entry.capability]["response_fields"]:
        field(clean, path.split("."), entry.capability)
    # Depth-one endpoint metadata is not a seed for another request.
    if entry.hop == 1 or entry.capability == "target_health":
        endpoint_paths = {
            "sg_reverse_in": ("SecurityGroups[]", "GroupId", "aws_security_group"),
            "sg_reverse_out": ("SecurityGroups[]", "GroupId", "aws_security_group"),
            "sg_eni_reverse": (
                "NetworkInterfaces[]",
                "NetworkInterfaceId",
                "aws_network_interface",
            ),
            "subnet_eni_reverse": (
                "NetworkInterfaces[]",
                "NetworkInterfaceId",
                "aws_network_interface",
            ),
            "vpc_eni_reverse": (
                "NetworkInterfaces[]",
                "NetworkInterfaceId",
                "aws_network_interface",
            ),
            "lb_groups": ("TargetGroups[]", "TargetGroupArn", "aws_lb_target_group"),
            "function_mappings": (
                "EventSourceMappings[]",
                "UUID",
                "aws_lambda_event_source_mapping",
            ),
            "queue_mappings": (
                "EventSourceMappings[]",
                "UUID",
                "aws_lambda_event_source_mapping",
            ),
            "target_health": (
                "TargetHealthDescriptions[]",
                "Target.Id",
                "aws_target_endpoint",
            ),
        }
        if entry.capability in endpoint_paths:
            path, key, kind = endpoint_paths[entry.capability]
            rows = _rows(clean, path)
            if rows is None:
                complete = False
            else:
                endpoints = []
                for index, row in enumerate(rows[: entry.max_results + 1]):
                    identity = _value(row, key)
                    if not isinstance(identity, str) or not identity:
                        complete = False
                        continue
                    endpoints.append(
                        ResourceIdentity(
                            address=f"{kind}.{index}",
                            resource_type=kind,
                            physical_id=identity,
                            region=entry.region,
                        )
                    )
                from cloud.reflection import expand_one_hop

                manifest, target, original_resources = scope
                expansion = expand_one_hop(
                    manifest,
                    entry,
                    endpoints,
                    target=target,
                    resources=original_resources,
                )
                scalar(entry.capability + ".expansion.hop", expansion.hop)
                scalar(entry.capability + ".expansion.bound", entry.max_results)
                scalar(entry.capability + ".expansion.reason", expansion.reason)
                scalar(
                    entry.capability + ".expansion.count",
                    min(len(endpoints), entry.max_results),
                )
                if len(endpoints) > entry.max_results:
                    truncated = True
    unique = {fact.name: fact for fact in facts}
    return Projection(
        tuple(unique[key] for key in sorted(unique)), complete and not truncated
    )
