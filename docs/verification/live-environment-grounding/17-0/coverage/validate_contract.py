"""Offline SDK shape proof for the frozen disposable coverage contract."""

from __future__ import annotations

import json
from pathlib import Path
import re

import botocore
import botocore.session
from botocore.loaders import Loader
from botocore.validate import validate_parameters

BASE = Path(__file__).parent
# Version-one governance freeze, deliberately independent of the edited JSON.
APPROVED_FAMILIES = frozenset(
    {
        "aws_instance",
        "aws_security_group",
        "aws_network_interface",
        "aws_subnet",
        "aws_vpc",
        "aws_route_table",
        "aws_ebs_volume",
        "aws_ebs_snapshot",
        "aws_lb",
        "aws_lb_target_group",
        "aws_lb_listener",
        "aws_autoscaling_group",
        "aws_db_instance",
        "aws_rds_cluster",
        "aws_s3_bucket",
        "aws_iam_role",
        "aws_iam_instance_profile",
        "aws_ecs_cluster",
        "aws_ecs_service",
        "aws_eks_cluster",
        "aws_lambda_function",
        "aws_lambda_event_source_mapping",
        "aws_dynamodb_table",
        "aws_sqs_queue",
        "aws_route53_record",
    }
)
SYNTHETIC = {
    "partition": "aws",
    "region": "us-east-1",
    "account": "000000000000",
    "id": "i-00000000000000000",
    "arn": "arn:aws:lambda:us-east-1:000000000000:function:synthetic",
    "name": "synthetic",
    "path_name": "synthetic",
    "cluster_arn": "arn:aws:ecs:us-east-1:000000000000:cluster/synthetic",
    "function_arn": "arn:aws:lambda:us-east-1:000000000000:function:synthetic",
    "event_source_arn": "arn:aws:sqs:us-east-1:000000000000:synthetic",
    "canonical_queue_url": "https://sqs.us-east-1.amazonaws.com/000000000000/synthetic",
    "zone_id": "ZSYNTHETIC",
    "record_type": "A",
}


def substitute(value):
    if isinstance(value, str):
        return re.sub(r"\$\{([^}]+)\}", lambda m: SYNTHETIC[m[1]], value)
    if isinstance(value, list):
        return [substitute(item) for item in value]
    if isinstance(value, dict):
        return {key: substitute(item) for key, item in value.items()}
    return value


def validate_field(shape, path):
    for segment in path.split("."):
        is_list = segment.endswith("[]")
        key = segment[:-2] if is_list else segment
        if shape.type_name != "structure" or key not in shape.members:
            raise ValueError(f"unknown response field: {path}")
        shape = shape.members[key]
        if is_list:
            if shape.type_name != "list":
                raise ValueError(f"not a list: {path}")
            shape = shape.member
    return shape


def validate_contract():
    contract = json.loads((BASE / "coverage.json").read_text())
    policy = json.loads((BASE / "policy.json").read_text())
    operations = contract["operations"]
    version = contract.get("contract_version")
    if type(version) is not int or version != 1:
        raise ValueError("unqualified contract version")
    families = contract["families"]
    if not isinstance(families, dict) or set(families) != APPROVED_FAMILIES:
        raise ValueError("family freeze changed")
    referenced_operations = set()
    for family in families.values():
        references = family.get("operations") if isinstance(family, dict) else None
        if (
            not isinstance(references, list)
            or not references
            or any(
                not isinstance(key, str) or key not in operations for key in references
            )
            or len(references) != len(set(references))
        ):
            raise ValueError("invalid family operation references")
        referenced_operations.update(references)
    if referenced_operations != set(operations):
        raise ValueError("unreferenced allowed operation")
    expected = {item["iam_action"] for item in operations.values()}
    actual = {action for stmt in policy["Statement"] for action in stmt["Action"]}
    if expected != actual:
        raise ValueError("policy action mismatch")
    for stmt in policy["Statement"]:
        if set(stmt) != {"Effect", "Action", "Resource"} or stmt["Effect"] != "Allow":
            raise ValueError("unexpected IAM policy shape")
        for action in stmt["Action"]:
            if not re.fullmatch(
                r"[a-z0-9]+:(?:Describe|Get|List|Head|BatchGet)[A-Za-z0-9]+", action
            ):
                raise ValueError("mutating or wildcard action")
            resources = sorted(
                {
                    resource
                    for item in operations.values()
                    if item["iam_action"] == action
                    for resource in item["iam_resources"]
                }
            )
            if sorted(stmt["Resource"]) != resources:
                raise ValueError("policy resource mismatch")
    session = botocore.session.Session()
    trusted_data = str(Path(botocore.__file__).resolve().parent / "data")
    session.register_component(
        "data_loader",
        Loader(extra_search_paths=[trusted_data], include_default_search_paths=False),
    )
    for key, item in operations.items():
        if item["operation"] != item["iam_action"].split(":")[1]:
            raise ValueError("SDK operation differs from allowed IAM action")
        if not re.search(
            r"\$\{(?:id|name|arn|function_arn|zone_id|canonical_queue_url)\}",
            json.dumps(item["params"]),
        ):
            raise ValueError("missing plan identity selector")
        model = session.get_service_model(item["service"]).operation_model(
            item["operation"]
        )
        validate_parameters(substitute(item["params"]), model.input_shape)
        for field in item["response_fields"]:
            validate_field(model.output_shape, field)
        if (
            item["pagination"]
            != "first page only; any continuation token => incomplete; never follow token"
        ):
            raise ValueError("pagination contract changed")
        if not item["params"]:
            raise ValueError("unscoped operation")
    return {
        "families": 25,
        "operation_templates": len(operations),
        "iam_actions": len(expected),
        "credential_resolution": False,
        "provider_calls": 0,
    }


if __name__ == "__main__":
    print(json.dumps(validate_contract(), indent=2))
