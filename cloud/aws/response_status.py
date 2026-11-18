"""Validate completion metadata without retaining provider response payloads."""

from __future__ import annotations

from urllib.parse import urlsplit

# Exact reads must return the selected identity. Lists for reverse relations may
# legitimately be empty, but absent/malformed result containers are not success.
_DIRECT = {
    "instance": ("Reservations[].Instances[]", "InstanceId", "InstanceIds"),
    "termination_protection": ("", "InstanceId", "InstanceId"),
    "security_group": ("SecurityGroups[]", "GroupId", "GroupIds"),
    "eni": ("NetworkInterfaces[]", "NetworkInterfaceId", "NetworkInterfaceIds"),
    "subnet": ("Subnets[]", "SubnetId", "SubnetIds"),
    "vpc": ("Vpcs[]", "VpcId", "VpcIds"),
    "route_table": ("RouteTables[]", "RouteTableId", "RouteTableIds"),
    "volume": ("Volumes[]", "VolumeId", "VolumeIds"),
    "snapshot": ("Snapshots[]", "SnapshotId", "SnapshotIds"),
    "lb": ("LoadBalancers[]", "LoadBalancerArn", "LoadBalancerArns"),
    "target_group": ("TargetGroups[]", "TargetGroupArn", "TargetGroupArns"),
    "listener": ("Listeners[]", "ListenerArn", "ListenerArns"),
    "asg": ("AutoScalingGroups[]", "AutoScalingGroupName", "AutoScalingGroupNames"),
    "db": ("DBInstances[]", "DBInstanceIdentifier", "DBInstanceIdentifier"),
    "db_cluster": ("DBClusters[]", "DBClusterIdentifier", "DBClusterIdentifier"),
    "role": ("Role", "RoleName", "RoleName"),
    "instance_profile": (
        "InstanceProfile",
        "InstanceProfileName",
        "InstanceProfileName",
    ),
    "ecs_cluster": ("clusters[]", "clusterArn", "clusters"),
    "ecs_service": ("services[]", "serviceArn", "services"),
    "eks_cluster": ("cluster", "name", "name"),
    "table": ("Table", "TableName", "TableName"),
}
_RELATIONS = {
    "sg_reverse_in": ("SecurityGroups[]", "GroupId"),
    "sg_reverse_out": ("SecurityGroups[]", "GroupId"),
    "sg_eni_reverse": ("NetworkInterfaces[]", "NetworkInterfaceId"),
    "subnet_eni_reverse": ("NetworkInterfaces[]", "NetworkInterfaceId"),
    "vpc_eni_reverse": ("NetworkInterfaces[]", "NetworkInterfaceId"),
    "volume_snapshots": ("Snapshots[]", "SnapshotId"),
    "lb_groups": ("TargetGroups[]", "TargetGroupArn"),
    "target_health": ("TargetHealthDescriptions[]", "Target.Id"),
    "db_snapshots": ("DBSnapshots[]", "DBSnapshotIdentifier"),
    "db_cluster_snapshots": ("DBClusterSnapshots[]", "DBClusterSnapshotIdentifier"),
    "function_mappings": ("EventSourceMappings[]", "UUID"),
    "event_mapping": ("EventSourceMappings[]", "UUID"),
    "queue_mappings": ("EventSourceMappings[]", "UUID"),
}
_PAGINATION = ("NextToken", "NextMarker", "Marker", "IsTruncated", "LastEvaluatedKey")


def _rows(value, path):
    if not path:
        return [value] if isinstance(value, dict) else None
    current = [value]
    for component in path.split("."):
        many = component.endswith("[]")
        name = component[:-2] if many else component
        following = []
        for item in current:
            if not isinstance(item, dict) or name not in item:
                return None
            child = item[name]
            if many:
                if not isinstance(child, list):
                    return None
                following.extend(child)
            else:
                following.append(child)
        current = following
    return current if all(isinstance(item, dict) for item in current) else None


def _value(row, path):
    for component in path.split("."):
        if not isinstance(row, dict):
            return None
        row = row.get(component)
    return row


def _dns_name(name):
    return (
        name.replace("\\052", "*").lower().rstrip(".")
        if isinstance(name, str) and not name.endswith("..")
        else None
    )


def response_complete(capability, parameters, response):
    """Fail closed on unknown shapes, failures, pagination and identity mismatch."""
    if not isinstance(response, dict) or any(
        response.get(k) for k in (*_PAGINATION, "failures", "Failures", "Error")
    ):
        return False
    if capability in _DIRECT:
        path, identity, parameter = _DIRECT[capability]
        rows = _rows(response, path)
        selected = parameters[parameter]
        selected = selected if isinstance(selected, list) else [selected]
        if rows is None or len(rows) != len(selected):
            return False
        if sorted(_value(row, identity) or "" for row in rows) != sorted(selected):
            return False
        if capability == "ecs_service" and any(
            row.get("clusterArn") != parameters["cluster"] for row in rows
        ):
            return False
        return True
    if capability in _RELATIONS:
        path, identity = _RELATIONS[capability]
        rows = _rows(response, path)
        if rows is None or any(
            not isinstance(_value(row, identity), str) or not _value(row, identity)
            for row in rows
        ):
            return False
        constraints = {
            "volume_snapshots": (
                "VolumeId",
                parameters.get("Filters", [{}])[0].get("Values", [None])[0],
            ),
            "lb_groups": ("LoadBalancerArns", parameters.get("LoadBalancerArn")),
            "db_snapshots": (
                "DBInstanceIdentifier",
                parameters.get("DBInstanceIdentifier"),
            ),
            "db_cluster_snapshots": (
                "DBClusterIdentifier",
                parameters.get("DBClusterIdentifier"),
            ),
        }
        if capability in constraints:
            key, expected = constraints[capability]
            if any(
                expected not in row.get(key, [])
                if isinstance(row.get(key), list)
                else row.get(key) != expected
                for row in rows
            ):
                return False
        for request, key in (
            ("FunctionName", "FunctionArn"),
            ("EventSourceArn", "EventSourceArn"),
        ):
            if (
                capability in ("function_mappings", "event_mapping", "queue_mappings")
                and request in parameters
            ):
                if any(row.get(key) != parameters[request] for row in rows):
                    return False
        return True
    if capability == "record":
        rows = _rows(response, "ResourceRecordSets[]")
        return (
            rows is not None
            and len(rows) == 1
            and _dns_name(rows[0].get("Name"))
            == _dns_name(parameters["StartRecordName"])
            and rows[0].get("Type") == parameters["StartRecordType"]
            # The frozen manifest does not carry a selected routing variant.
            # Even malformed/null variant markers cannot prove exact identity.
            and "SetIdentifier" not in rows[0]
        )
    if capability == "queue":
        attributes = response.get("Attributes")
        target = urlsplit(parameters["QueueUrl"])
        account, name = target.path.strip("/").split("/")
        region = target.hostname.split(".")[1]
        return (
            isinstance(attributes, dict)
            and attributes.get("QueueArn") == f"arn:aws:sqs:{region}:{account}:{name}"
        )
    if capability in ("lb_protection", "bucket_tags"):
        rows = _rows(
            response, "Attributes[]" if capability == "lb_protection" else "TagSet[]"
        )
        return rows is not None and all(
            isinstance(row.get("Key"), str) and isinstance(row.get("Value"), str)
            for row in rows
        )
    if capability == "function_tags":
        tags = response.get("Tags")
        return isinstance(tags, dict) and all(
            isinstance(k, str) and isinstance(v, str) for k, v in tags.items()
        )
    if capability == "table_recovery":
        return isinstance(response.get("ContinuousBackupsDescription"), dict) and bool(
            response["ContinuousBackupsDescription"]
        )
    # These APIs legitimately omit their optional fact when unset. A modeled
    # successful HTTP response establishes completion, not a made-up fact.
    if capability in ("bucket_versioning", "function_concurrency"):
        metadata = response.get("ResponseMetadata")
        return isinstance(metadata, dict) and metadata.get("HTTPStatusCode") == 200
    return False
