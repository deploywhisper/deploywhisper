"""Immutable recorded-plan identities and statically bounded AWS manifests."""

from __future__ import annotations

import json
import re
from typing import Literal, Mapping

from pydantic import ConfigDict, Field, StrictInt, StrictStr, model_validator

from cloud.base import FrozenModel, ResourceIdentity
from cloud.aws.allowlist import _CATALOG
from cloud.aws.client import Call, _bucket_name
from cloud.aws.session import validate_config
from services.content_security import redact_text, sensitive_artifact_values

_MAX_RESOURCES = 1000
_MAX_PRIOR = 10000
_SELECTOR_FIELDS = frozenset(
    {
        "id",
        "arn",
        "name",
        "cluster_arn",
        "function_arn",
        "event_source_arn",
        "zone_id",
        "record_type",
        "set_identifier",
    }
)
_ID_PREFIX = {
    "aws_instance": "i",
    "aws_security_group": "sg",
    "aws_network_interface": "eni",
    "aws_subnet": "subnet",
    "aws_vpc": "vpc",
    "aws_route_table": "rtb",
    "aws_ebs_volume": "vol",
    "aws_ebs_snapshot": "snap",
}

_FAMILY_SERVICE = {
    family: _CATALOG["operations"][definition["operations"][0]]["service"]
    for family, definition in _CATALOG["families"].items()
}


class _ReflectionModel(FrozenModel):
    model_config = ConfigDict(hide_input_in_errors=True)


class ReflectionError(ValueError):
    """A closed validation error; never includes uploaded plan values."""

    def __init__(self, code="invalid_reflection_scope"):
        super().__init__(code)
        self.code = code


class ReflectionTarget(_ReflectionModel):
    """Trusted server constructor configuration, never caller authority."""

    account_id: StrictStr = Field(pattern=r"^[0-9]{12}$")
    regions: tuple[StrictStr, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def _target(self):
        if len(set(self.regions)) != len(self.regions):
            raise ValueError("Invalid authorized regions")
        for region in self.regions:
            validate_config({"region": region})
        object.__setattr__(self, "regions", tuple(sorted(self.regions)))
        return self


class ReflectedResource(_ReflectionModel):
    identity: ResourceIdentity
    source: Literal["prior_state", "change.before", "missing"]
    state: Literal["existing", "unknown", "no_live_counterpart"]
    selectors: tuple[tuple[StrictStr, StrictStr], ...] = ()
    cause: Literal["recorded_identity_missing", "recorded_identity_invalid"] | None = (
        None
    )

    @model_validator(mode="after")
    def _selected(self):
        keys = [k for k, _ in self.selectors]
        if len(set(keys)) != len(keys) or set(keys) - _SELECTOR_FIELDS:
            raise ValueError("Invalid identity selectors")
        if self.state == "unknown" and self.cause is None:
            raise ValueError("Unknown identity needs a closed cause")
        if self.state != "unknown" and self.cause is not None:
            raise ValueError("Resolved identity cannot carry failure cause")
        if self.state == "existing" and self.source == "missing":
            raise ValueError("Existing identity needs recorded provenance")
        if self.state != "existing" and self.selectors:
            raise ValueError("Unobserved physical identity has selectors")
        for _, value in self.selectors:
            _text(value)
        object.__setattr__(self, "selectors", tuple(sorted(self.selectors)))
        return self


def _target(value):
    try:
        return ReflectionTarget.model_validate(
            value.model_dump() if isinstance(value, ReflectionTarget) else value
        )
    except (ValueError, TypeError, AttributeError):
        raise ReflectionError() from None


def _text(value):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 2048
        or any(ord(c) < 32 for c in value)
        or redact_text(value) != value
    ):
        raise ReflectionError("invalid_recorded_identity")
    return value


def _scalar(values, *names):
    for name in names:
        value = values.get(name)
        if isinstance(value, str) and value:
            return _text(value)
    return None


def _arn(value, target, service=None, *, allow_bucket=False):
    if value is None:
        return None
    value = _text(value)
    # Botocore client keys and ARN namespaces differ for ELBv2.
    service = "elasticloadbalancing" if service == "elbv2" else service
    if allow_bucket and value.startswith("arn:aws:s3:::"):
        if not _bucket_name(value[len("arn:aws:s3:::") :]):
            raise ReflectionError("recorded_target_mismatch")
        return value
    match = re.fullmatch(
        r"arn:aws:([a-z0-9-]+):([^:]*):([0-9]{12}):([A-Za-z0-9_:/+.,=@-]+)", value
    )
    if (
        not match
        or match[3] != target.account_id
        or (match[2] and match[2] not in target.regions)
        or (service and match[1] != service)
    ):
        raise ReflectionError("recorded_target_mismatch")
    return value


def _resource(address, family, values, source, actions, target):
    address, family = _text(address), _text(family)
    if len(family) > 128:
        raise ReflectionError()
    if values is None:
        state = "no_live_counterpart" if actions == ["create"] else "unknown"
        return ReflectedResource(
            identity=ResourceIdentity(address=address, resource_type=family),
            source="missing",
            state=state,
            cause=None
            if state == "no_live_counterpart"
            else "recorded_identity_missing",
        )
    if not isinstance(values, dict):
        raise ReflectionError("invalid_recorded_values")
    identifier = _scalar(values, "id", "uuid")
    arn = _scalar(values, "arn")
    if arn is None and identifier and identifier.startswith("arn:"):
        arn = identifier
    arn = _arn(
        arn, target, _FAMILY_SERVICE.get(family), allow_bucket=family == "aws_s3_bucket"
    )
    if identifier and identifier.startswith("arn:") and arn != identifier:
        raise ReflectionError("recorded_identity_mismatch")
    explicit_region = _scalar(values, "region")
    if explicit_region and explicit_region not in target.regions:
        raise ReflectionError("recorded_target_mismatch")
    arn_region = arn.split(":")[3] if arn else None
    if explicit_region and arn_region and explicit_region != arn_region:
        raise ReflectionError("recorded_target_mismatch")
    region = (
        explicit_region
        or arn_region
        or (target.regions[0] if len(target.regions) == 1 else None)
    )
    if family in {"aws_iam_role", "aws_iam_instance_profile"} and region is None:
        # IAM is global; the canonical client still needs one allowed region.
        region = target.regions[0]
    selectors = {}
    if identifier:
        selectors["id"] = identifier
    if arn:
        selectors["arn"] = arn
    aliases = {
        "aws_autoscaling_group": ("name", "id"),
        "aws_db_instance": ("identifier", "id"),
        "aws_rds_cluster": ("cluster_identifier", "id"),
        "aws_s3_bucket": ("bucket", "id", "name"),
        "aws_iam_role": ("name", "id"),
        "aws_iam_instance_profile": ("name", "id"),
        "aws_eks_cluster": ("name", "id"),
        "aws_dynamodb_table": ("name", "id"),
        "aws_sqs_queue": ("name", "queue_name"),
        "aws_route53_record": ("name",),
    }
    name = _scalar(values, *aliases[family]) if family in aliases else None
    if name:
        selectors["name"] = name
    if family == "aws_s3_bucket" and arn and arn != "arn:aws:s3:::" + (name or ""):
        raise ReflectionError("recorded_identity_mismatch")
    if family == "aws_sqs_queue":
        # Never retain or forward an uploaded URL, even a plausible AWS URL.
        identifier = None
        selectors.pop("id", None)
        if name and region:
            identifier = (
                f"https://sqs.{region}.amazonaws.com/{target.account_id}/{name}"
            )
            selectors["id"] = identifier
    if family == "aws_sqs_queue" and not arn and name and region:
        arn = f"arn:aws:sqs:{region}:{target.account_id}:{name}"
        selectors["arn"] = _arn(arn, target, "sqs")
    if family == "aws_ecs_service":
        parent = _scalar(values, "cluster_arn", "cluster")
        if parent:
            selectors["cluster_arn"] = _arn(parent, target, "ecs")
    if family == "aws_lambda_event_source_mapping":
        parent = _scalar(values, "function_arn", "function_name")
        event = _scalar(values, "event_source_arn")
        if parent:
            selectors["function_arn"] = _arn(parent, target, "lambda")
        if event:
            selectors["event_source_arn"] = _arn(event, target)
    if family == "aws_route53_record":
        for key, aliases_ in (
            ("zone_id", ("zone_id",)),
            ("record_type", ("type", "record_type")),
            ("set_identifier", ("set_identifier",)),
        ):
            value = _scalar(values, *aliases_)
            if value:
                selectors[key] = value
    identity = ResourceIdentity(
        address=address,
        resource_type=family,
        physical_id=identifier,
        arn=arn,
        name=name,
        region=region,
    )
    if (
        family in _ID_PREFIX
        and identifier
        and re.fullmatch(
            _ID_PREFIX[family] + r"-(?:[0-9a-f]{8}|[0-9a-f]{17})", identifier
        )
        is None
    ):
        return ReflectedResource(
            identity=ResourceIdentity(
                address=address, resource_type=family, region=region
            ),
            source=source,
            state="unknown",
            cause="recorded_identity_invalid",
        )
    # Missing selectors are handled per capability, not replaced by discovery.
    return ReflectedResource(
        identity=identity,
        source=source,
        state="existing",
        selectors=tuple(selectors.items()),
    )


def extract_resources(
    plan: Mapping, *, target: ReflectionTarget
) -> tuple[ReflectedResource, ...]:
    """Select recorded identities without SDK imports, credentials or provider calls."""
    target = _target(target)
    try:
        if not isinstance(plan, dict) or plan.get("format_version") != "1.2":
            raise ReflectionError("unqualified_plan_format")
        encoded = json.dumps(plan, allow_nan=False).encode("utf-8")
        if len(encoded) > 50 * 1024 * 1024:
            raise ReflectionError("reflection_plan_bound")
        sensitive = sensitive_artifact_values(encoded)
        changes = plan.get("resource_changes")
        if not isinstance(changes, list) or len(changes) > _MAX_RESOURCES:
            raise ReflectionError("reflection_resource_bound")
        prior_state = plan.get("prior_state")
        if prior_state is not None and not isinstance(prior_state, dict):
            raise ReflectionError()
        if prior_state and prior_state.get("format_version", "1.0") != "1.0":
            raise ReflectionError("unqualified_state_format")
        prior = {}
        stack = [((prior_state or {}).get("values") or {}).get("root_module", {})]
        modules = 0
        while stack:
            module = stack.pop()
            modules += 1
            if modules > _MAX_PRIOR or not isinstance(module, dict):
                raise ReflectionError("reflection_prior_bound")
            resources, children = (
                module.get("resources", []),
                module.get("child_modules", []),
            )
            if not isinstance(resources, list) or not isinstance(children, list):
                raise ReflectionError()
            if (
                len(prior) + len(resources) > _MAX_PRIOR
                or len(stack) + len(children) > _MAX_PRIOR
            ):
                raise ReflectionError("reflection_prior_bound")
            for resource in resources:
                if not isinstance(resource, dict):
                    raise ReflectionError()
                address = _text(resource.get("address"))
                if address in prior:
                    raise ReflectionError("duplicate_recorded_identity")
                prior[address] = resource.get("values")
            stack.extend(children)
        rows, seen = [], set()
        for resource in changes:
            if not isinstance(resource, dict) or not isinstance(
                resource.get("change"), dict
            ):
                raise ReflectionError()
            address = _text(resource.get("address"))
            if address in seen:
                raise ReflectionError("duplicate_recorded_identity")
            seen.add(address)
            change = resource["change"]
            actions = change.get("actions")
            if (
                not isinstance(actions, list)
                or not actions
                or len(set(actions)) != len(actions)
                or set(actions) - {"create", "delete", "update", "read", "no-op"}
            ):
                raise ReflectionError("invalid_recorded_actions")
            if set(actions) not in (
                {"create"},
                {"delete"},
                {"update"},
                {"read"},
                {"no-op"},
                {"create", "delete"},
            ):
                raise ReflectionError("invalid_recorded_actions")
            values, source = prior.get(address), "prior_state"
            if values is None:
                values = change.get("before")
                source = "change.before" if values is not None else "missing"
            rows.append(
                _resource(
                    address, resource.get("type"), values, source, actions, target
                )
            )
        for row in rows:
            rendered = row.model_dump_json()
            if redact_text(rendered, sensitive_values=sensitive) != rendered:
                raise ReflectionError("sensitive_recorded_identity")
        return tuple(sorted(rows, key=lambda row: row.identity.address))
    except ReflectionError:
        raise
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
        raise ReflectionError() from None


class ReflectionIssue(_ReflectionModel):
    address: StrictStr
    capability: StrictStr | None = None
    cause: Literal[
        "unsupported_family",
        "recorded_identity_missing",
        "recorded_identity_invalid",
        "ambiguous_region",
        "missing_selector",
        "invalid_selector",
        "manifest_capacity",
    ]


class BoundCall(_ReflectionModel):
    """Frozen scope descriptor; .call() returns a fresh mutable SDK input copy."""

    address: StrictStr
    capability: StrictStr
    region: StrictStr
    parameters_json: StrictStr = Field(max_length=16384)
    expected: tuple[tuple[StrictStr, StrictStr | None], ...] = ()
    hop: StrictInt = Field(ge=0, le=1)
    reason: StrictStr
    max_results: StrictInt = Field(ge=1, le=100)

    @model_validator(mode="after")
    def _descriptor(self):
        _text(self.address)
        validate_config({"region": self.region})
        call = Call(
            capability=self.capability, parameters=json.loads(self.parameters_json)
        )
        if len({k for k, _ in self.expected}) != len(self.expected):
            raise ValueError("Duplicate response identity selector")
        object.__setattr__(
            self,
            "parameters_json",
            json.dumps(call.parameters, sort_keys=True, separators=(",", ":")),
        )
        object.__setattr__(self, "expected", tuple(sorted(self.expected)))
        return self

    def call(self) -> Call:
        return Call(
            capability=self.capability, parameters=json.loads(self.parameters_json)
        )


class ReflectionManifest(_ReflectionModel):
    target: ReflectionTarget
    resources: tuple[ReflectedResource, ...]
    entries: tuple[BoundCall, ...]
    issues: tuple[ReflectionIssue, ...] = ()
    planned_calls: StrictInt = Field(ge=0)
    max_calls: StrictInt = Field(default=1000, ge=1, le=1000)


def _render(value, bindings):
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return bindings[value[2:-1]]
    if isinstance(value, list):
        return [_render(item, bindings) for item in value]
    if isinstance(value, dict):
        return {key: _render(item, bindings) for key, item in value.items()}
    return value


def _resources(resources, target):
    if not isinstance(resources, (tuple, list)) or len(resources) > _MAX_RESOURCES:
        raise ReflectionError("reflection_resource_bound")
    rows = []
    for resource in resources:
        row = ReflectedResource.model_validate(
            resource.model_dump()
            if isinstance(resource, ReflectedResource)
            else resource
        )
        _text(row.identity.address)
        _text(row.identity.resource_type)
        if (
            row.identity.region is not None
            and row.identity.region not in target.regions
        ):
            raise ReflectionError("recorded_target_mismatch")
        values = dict(row.selectors)
        for key, actual in (
            ("id", row.identity.physical_id),
            ("arn", row.identity.arn),
            ("name", row.identity.name),
        ):
            if key in values and values[key] != actual:
                raise ReflectionError("recorded_identity_mismatch")
        if row.identity.tags:
            raise ReflectionError("unexpected_identity_tags")
        if row.identity.arn:
            _arn(
                row.identity.arn,
                target,
                _FAMILY_SERVICE.get(row.identity.resource_type),
                allow_bucket=row.identity.resource_type == "aws_s3_bucket",
            )
        for key in ("arn", "cluster_arn", "function_arn", "event_source_arn"):
            if values.get(key):
                _arn(
                    values[key],
                    target,
                    _FAMILY_SERVICE.get(row.identity.resource_type)
                    if key == "arn"
                    else "ecs"
                    if key == "cluster_arn"
                    else "lambda"
                    if key == "function_arn"
                    else None,
                    allow_bucket=key == "arn"
                    and row.identity.resource_type == "aws_s3_bucket",
                )
                region = values[key].split(":")[3]
                if region and row.identity.region and region != row.identity.region:
                    raise ReflectionError("recorded_target_mismatch")
        rows.append(row)
    if len({row.identity.address for row in rows}) != len(rows):
        raise ReflectionError("duplicate_recorded_identity")
    return tuple(sorted(rows, key=lambda row: row.identity.address))


def build_manifest(
    resources, *, target: ReflectionTarget, max_calls: int = 1000
) -> ReflectionManifest:
    """Render only frozen templates from immutable recorded selectors.

    Filtered reverse calls are one hop. Their response endpoint identities may be
    retained as metadata but must never become another manifest or SDK request.
    """
    target = _target(target)
    try:
        if type(max_calls) is not int or not 1 <= max_calls <= 1000:
            raise ReflectionError("reflection_manifest_bound")
        rows = _resources(resources, target)
        entries, issues, planned = [], [], 0
        for row in rows:
            family, address = row.identity.resource_type, row.identity.address
            if row.state == "no_live_counterpart":
                continue
            if row.state == "unknown":
                issues.append(
                    ReflectionIssue(
                        address=address,
                        cause=row.cause
                        if row.cause
                        in {"recorded_identity_missing", "recorded_identity_invalid"}
                        else "recorded_identity_missing",
                    )
                )
                continue
            if family not in _CATALOG["families"]:
                issues.append(
                    ReflectionIssue(address=address, cause="unsupported_family")
                )
                continue
            values = dict(row.selectors)
            region = row.identity.region
            for key in _CATALOG["families"][family]["operations"]:
                operation = _CATALOG["operations"][key]
                if region is None:
                    issues.append(
                        ReflectionIssue(
                            address=address, capability=key, cause="ambiguous_region"
                        )
                    )
                    continue
                bindings = dict(
                    values, account=target.account_id, region=region, partition="aws"
                )
                if family == "aws_sqs_queue" and values.get("name"):
                    name = values["name"]
                    if re.fullmatch(r"[A-Za-z0-9_-]{1,80}(?:\.fifo)?", name) is None:
                        issues.append(
                            ReflectionIssue(
                                address=address,
                                capability=key,
                                cause="invalid_selector",
                            )
                        )
                        continue
                    bindings["canonical_queue_url"] = (
                        f"https://sqs.{region}.amazonaws.com/{target.account_id}/{name}"
                    )
                expected = ()
                if family == "aws_lambda_event_source_mapping":
                    if (
                        not values.get("id")
                        or re.fullmatch(
                            r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",
                            values["id"],
                        )
                        is None
                    ):
                        issues.append(
                            ReflectionIssue(
                                address=address,
                                capability=key,
                                cause="missing_selector",
                            )
                        )
                        continue
                    if not values.get("function_arn") or not values.get(
                        "event_source_arn"
                    ):
                        issues.append(
                            ReflectionIssue(
                                address=address,
                                capability=key,
                                cause="missing_selector",
                            )
                        )
                        continue
                    expected = (
                        ("UUID", values["id"]),
                        ("FunctionArn", values["function_arn"]),
                        ("EventSourceArn", values["event_source_arn"]),
                    )
                if family == "aws_route53_record":
                    expected = (
                        ("Name", values.get("name")),
                        ("Type", values.get("record_type")),
                        ("SetIdentifier", values.get("set_identifier")),
                    )
                try:
                    params = _render(operation["params"], bindings)
                    call = Call(capability=key, parameters=params)
                except KeyError:
                    issues.append(
                        ReflectionIssue(
                            address=address, capability=key, cause="missing_selector"
                        )
                    )
                    continue
                except (ValueError, TypeError):
                    issues.append(
                        ReflectionIssue(
                            address=address, capability=key, cause="invalid_selector"
                        )
                    )
                    continue
                planned += 1
                if len(entries) >= max_calls:
                    issues.append(
                        ReflectionIssue(
                            address=address, capability=key, cause="manifest_capacity"
                        )
                    )
                    continue
                hop = 1 if operation["relation"].startswith("one-hop") else 0
                limit = params.get(
                    "MaxResults", params.get("MaxItems", params.get("PageSize", 100))
                )
                entries.append(
                    BoundCall(
                        address=address,
                        capability=key,
                        region=region,
                        parameters_json=json.dumps(
                            call.parameters, sort_keys=True, separators=(",", ":")
                        ),
                        expected=expected,
                        hop=hop,
                        reason=operation["relation"],
                        max_results=min(100, int(limit)),
                    )
                )
        return ReflectionManifest(
            target=target,
            resources=rows,
            entries=tuple(entries),
            issues=tuple(issues),
            planned_calls=planned,
            max_calls=max_calls,
        )
    except ReflectionError:
        raise
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
        raise ReflectionError() from None


def guard_manifest(
    manifest, *, target: ReflectionTarget, resources=None
) -> ReflectionManifest:
    """Reject added, broadened or rebound calls before constructing a client."""
    target = _target(target)
    try:
        source = ReflectionManifest.model_validate(
            manifest.model_dump()
            if isinstance(manifest, ReflectionManifest)
            else manifest
        )
        expected = build_manifest(
            source.resources if resources is None else resources,
            target=target,
            max_calls=source.max_calls,
        )
        if source != expected:
            raise ReflectionError("manifest_scope_mismatch")
        return expected
    except ReflectionError:
        raise
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
        raise ReflectionError("manifest_scope_mismatch") from None


class OneHopExpansion(_ReflectionModel):
    origin_address: StrictStr
    capability: StrictStr
    hop: Literal[1] = 1
    reason: StrictStr
    limit: StrictInt = Field(ge=1, le=100)
    endpoints: tuple[ResourceIdentity, ...] = ()
    truncated: bool = False


def expand_one_hop(
    manifest, entry, endpoints, *, target: ReflectionTarget, resources=None
) -> OneHopExpansion:
    """Record bounded selected endpoints without fetching their details.

    Observed endpoints may describe external dependencies; only the original
    private plan resources authorize requests. This return value is metadata,
    never a source of additional collection requests.
    """
    approved = guard_manifest(manifest, target=target, resources=resources)
    try:
        entry = BoundCall.model_validate(
            entry.model_dump() if isinstance(entry, BoundCall) else entry
        )
        if entry not in approved.entries or (
            entry.hop != 1 and entry.capability != "target_health"
        ):
            raise ReflectionError("unapproved_expansion")
        if not isinstance(endpoints, (tuple, list)):
            raise ReflectionError("invalid_expansion_endpoints")
        result = []
        seen = set()
        for value in endpoints[: entry.max_results]:
            identity = ResourceIdentity.model_validate(
                value.model_dump() if isinstance(value, ResourceIdentity) else value
            )
            if identity.tags:
                raise ReflectionError("unexpected_identity_tags")
            for field in (
                "address",
                "resource_type",
                "physical_id",
                "arn",
                "name",
                "region",
            ):
                text = getattr(identity, field)
                if text is not None:
                    _text(text)
            if identity.address in seen:
                raise ReflectionError("duplicate_expansion_identity")
            seen.add(identity.address)
            result.append(identity)
        return OneHopExpansion(
            origin_address=entry.address,
            capability=entry.capability,
            reason=entry.reason
            if entry.hop == 1
            else "one-hop selected target health endpoints",
            limit=entry.max_results,
            endpoints=tuple(result),
            truncated=len(endpoints) > entry.max_results,
        )
    except ReflectionError:
        raise
    except (ValueError, TypeError, AttributeError, KeyError):
        raise ReflectionError("invalid_expansion_endpoints") from None
