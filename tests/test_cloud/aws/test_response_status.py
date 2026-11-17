"""Representative completion contracts for every frozen AWS capability."""

from __future__ import annotations

import copy
import unittest

from cloud.aws.allowlist import _CATALOG
from cloud.aws.response_status import response_complete

ID = "i-00000000000000001"
ARN = "arn:aws:lambda:us-east-1:000000000000:function:example"
CLUSTER = "arn:aws:ecs:us-east-1:000000000000:cluster/example"
NAME = "example"


def render(value):
    if isinstance(value, dict):
        return {k: render(v) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v) for v in value]
    return {
        "${id}": ID,
        "${arn}": ARN,
        "${cluster_arn}": CLUSTER,
        "${function_arn}": ARN,
        "${event_source_arn}": ARN,
        "${canonical_queue_url}": "https://sqs.us-east-1.amazonaws.com/000000000000/example",
        "${account}": "000000000000",
        "${name}": NAME,
        "${zone_id}": "Z123",
        "${record_type}": "A",
    }.get(value, value)


DIRECT = {
    "instance": {"Reservations": [{"Instances": [{"InstanceId": ID}]}]},
    "termination_protection": {
        "InstanceId": ID,
        "DisableApiTermination": {"Value": False},
    },
    "security_group": {"SecurityGroups": [{"GroupId": ID}]},
    "eni": {"NetworkInterfaces": [{"NetworkInterfaceId": ID}]},
    "subnet": {"Subnets": [{"SubnetId": ID}]},
    "vpc": {"Vpcs": [{"VpcId": ID}]},
    "route_table": {"RouteTables": [{"RouteTableId": ID}]},
    "volume": {"Volumes": [{"VolumeId": ID}]},
    "snapshot": {"Snapshots": [{"SnapshotId": ID}]},
    "lb": {"LoadBalancers": [{"LoadBalancerArn": ARN}]},
    "target_group": {"TargetGroups": [{"TargetGroupArn": ARN}]},
    "listener": {"Listeners": [{"ListenerArn": ARN}]},
    "asg": {"AutoScalingGroups": [{"AutoScalingGroupName": NAME}]},
    "db": {"DBInstances": [{"DBInstanceIdentifier": NAME}]},
    "db_cluster": {"DBClusters": [{"DBClusterIdentifier": NAME}]},
    "role": {"Role": {"RoleName": NAME}},
    "instance_profile": {"InstanceProfile": {"InstanceProfileName": NAME}},
    "ecs_cluster": {"clusters": [{"clusterArn": ARN}]},
    "ecs_service": {"services": [{"serviceArn": ARN, "clusterArn": CLUSTER}]},
    "eks_cluster": {"cluster": {"name": NAME, "arn": ARN}},
    "table": {"Table": {"TableName": NAME}},
}
RELATIONS = {
    "sg_reverse_in": {"SecurityGroups": [{"GroupId": ID}]},
    "sg_reverse_out": {"SecurityGroups": [{"GroupId": ID}]},
    "sg_eni_reverse": {"NetworkInterfaces": [{"NetworkInterfaceId": ID}]},
    "subnet_eni_reverse": {"NetworkInterfaces": [{"NetworkInterfaceId": ID}]},
    "vpc_eni_reverse": {"NetworkInterfaces": [{"NetworkInterfaceId": ID}]},
    "volume_snapshots": {"Snapshots": [{"SnapshotId": ID, "VolumeId": ID}]},
    "lb_groups": {"TargetGroups": [{"TargetGroupArn": ARN, "LoadBalancerArns": [ARN]}]},
    "target_health": {
        "TargetHealthDescriptions": [
            {"Target": {"Id": ID}, "TargetHealth": {"State": "healthy"}}
        ]
    },
    "db_snapshots": {
        "DBSnapshots": [{"DBSnapshotIdentifier": NAME, "DBInstanceIdentifier": NAME}]
    },
    "db_cluster_snapshots": {
        "DBClusterSnapshots": [
            {"DBClusterSnapshotIdentifier": NAME, "DBClusterIdentifier": NAME}
        ]
    },
    "function_mappings": {"EventSourceMappings": [{"UUID": NAME, "FunctionArn": ARN}]},
    "event_mapping": {
        "EventSourceMappings": [
            {"UUID": NAME, "FunctionArn": ARN, "EventSourceArn": ARN}
        ]
    },
    "queue_mappings": {"EventSourceMappings": [{"UUID": NAME, "EventSourceArn": ARN}]},
}
OTHER = {
    "lb_protection": {
        "Attributes": [{"Key": "deletion_protection.enabled", "Value": "false"}]
    },
    "bucket_versioning": {"ResponseMetadata": {"HTTPStatusCode": 200}},
    "bucket_tags": {"TagSet": []},
    "function_concurrency": {"ResponseMetadata": {"HTTPStatusCode": 200}},
    "function_tags": {"Tags": {}},
    "table_recovery": {
        "ContinuousBackupsDescription": {"ContinuousBackupsStatus": "ENABLED"}
    },
    "queue": {"Attributes": {"QueueArn": "arn:aws:sqs:us-east-1:000000000000:example"}},
    "record": {"ResourceRecordSets": [{"Name": NAME + ".", "Type": "A"}]},
}


class ResponseStatusTests(unittest.TestCase):
    def test_every_capability_has_positive_and_fail_closed_fixture(self):
        fixtures = {**DIRECT, **RELATIONS, **OTHER}
        self.assertEqual(set(fixtures), set(_CATALOG["operations"]))
        for capability, response in fixtures.items():
            parameters = render(_CATALOG["operations"][capability]["params"])
            with self.subTest(capability=capability):
                self.assertTrue(response_complete(capability, parameters, response))
                for absent in ({}, None, [], {"unknown": True}):
                    self.assertFalse(response_complete(capability, parameters, absent))
                for marker in (
                    "NextToken",
                    "NextMarker",
                    "Marker",
                    "IsTruncated",
                    "LastEvaluatedKey",
                    "failures",
                    "Failures",
                ):
                    self.assertFalse(
                        response_complete(
                            capability, parameters, {**response, marker: "present"}
                        )
                    )

    def test_direct_identity_mismatch_or_absence_never_complete(self):
        def replace(value):
            if isinstance(value, dict):
                return {k: replace(v) for k, v in value.items()}
            if isinstance(value, list):
                return [replace(v) for v in value]
            return "wrong-identity" if isinstance(value, str) else value

        for capability, response in DIRECT.items():
            parameters = render(_CATALOG["operations"][capability]["params"])
            with self.subTest(capability=capability):
                self.assertFalse(
                    response_complete(capability, parameters, replace(response))
                )
                root = next(iter(response))
                self.assertFalse(response_complete(capability, parameters, {root: []}))

    def test_empty_relations_are_complete_but_malformed_members_are_not(self):
        for capability, response in RELATIONS.items():
            parameters = render(_CATALOG["operations"][capability]["params"])
            root = next(iter(response))
            with self.subTest(capability=capability):
                self.assertTrue(response_complete(capability, parameters, {root: []}))
                self.assertFalse(
                    response_complete(capability, parameters, {root: [{}]})
                )
                self.assertFalse(
                    response_complete(capability, parameters, {root: [None]})
                )

    def test_scoped_relation_and_record_mismatch_never_complete(self):
        for capability in (
            "volume_snapshots",
            "lb_groups",
            "db_snapshots",
            "db_cluster_snapshots",
            "function_mappings",
            "event_mapping",
            "queue_mappings",
        ):
            response = copy.deepcopy(RELATIONS[capability])
            row = next(iter(response.values()))[0]
            row.update({key: "wrong-identity" for key in row if key != "UUID"})
            with self.subTest(capability=capability):
                self.assertFalse(
                    response_complete(
                        capability,
                        render(_CATALOG["operations"][capability]["params"]),
                        response,
                    )
                )
