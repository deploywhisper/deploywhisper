# Frozen initial AWS coverage contract v1

Decision date: 2026-11-12. The maintainer authorized choosing the best fit and completing Story 17.0. Freeze these 25 Terraform families and the exact 42 operation templates / 33 IAM action union in `coverage.json` and `policy.json`. This is the first implementation contract, not a claim of product implementation or production IAM qualification.

All calls are statically derived from validated recorded plan identities. Missing physical IDs, unknown families, pure creates or missing parent identities do not trigger discovery; record `unknown` or `no_live_counterpart`. No account-wide, region-wide or unfiltered List/Describe call is permitted. IDs discovered in responses never create a second request in this profile. One-hop filtered reads retain returned endpoint identities only; they do not fetch those endpoints' details. There is no second hop. First page only: any provider continuation token means `incomplete`. Deadline, call/byte/node caps and cancellation can only reduce completeness; they cannot produce a clean result.

| Family | Exact operation templates | Available evidence; absent evidence remains unknown |
| --- | --- | --- |
| aws_instance | instance, termination_protection | State/AZ, declared network/storage edges, termination protection |
| aws_security_group | security_group, sg_reverse_in, sg_reverse_out, sg_eni_reverse | Group-reference and attached-interface first-hop endpoints |
| aws_network_interface | eni | Exact interface attachment, subnet, VPC and status |
| aws_subnet | subnet, subnet_eni_reverse | AZ and first-hop attached interfaces |
| aws_vpc | vpc, vpc_eni_reverse | VPC state and first-hop attached interfaces, capped |
| aws_route_table | route_table | Declared route and association endpoints |
| aws_ebs_volume | volume, volume_snapshots | Attachment and bounded own-volume snapshot metadata |
| aws_ebs_snapshot | snapshot | Exact snapshot state, source volume and timestamp |
| aws_lb | lb, lb_protection, lb_groups | LB state/AZ, deletion protection, first-hop target groups |
| aws_lb_target_group | target_group, target_health | LB relationships and target health first-hop endpoints |
| aws_lb_listener | listener | Parent LB and default target group |
| aws_autoscaling_group | asg | Exact group capacity, instance/AZ/health facts and target groups |
| aws_db_instance | db, db_snapshots | Protection, backup window, restore timestamp, replica identities, snapshot metadata |
| aws_rds_cluster | db_cluster, db_cluster_snapshots | Protection, backup window, restore timestamp, member/replica identities, snapshot metadata |
| aws_s3_bucket | bucket_versioning, bucket_tags | Versioning/MFA-delete and redacted ownership tags; no object access |
| aws_iam_role | role | Trust policy and redacted tags; no credentials or policy mutation |
| aws_iam_instance_profile | instance_profile | Profile-to-role identities |
| aws_ecs_cluster | ecs_cluster | Cluster status and running-task/service counts |
| aws_ecs_service | ecs_service | Service status/counts, target groups and network identities |
| aws_eks_cluster | eks_cluster | Cluster status, protection and network/role identities; no kubeconfig |
| aws_lambda_function | function_concurrency, function_tags, function_mappings | Reserved concurrency, redacted tags, known function's first-hop mappings; runtime liveness unknown |
| aws_lambda_event_source_mapping | event_mapping | Plan-known function/event-source pair; retain exact UUID only |
| aws_dynamodb_table | table, table_recovery | Table status, protection, stream/replica identities and PITR window |
| aws_sqs_queue | queue, queue_mappings | Selected queue attributes and first-hop Lambda mappings; never messages |
| aws_route53_record | record | Exact known hosted-zone/name/type/set identifier; alias target metadata only |

## Permission and request constraints

`coverage.json` maps every template to service, SDK operation, exact IAM action, parameters, selected response fields and IAM resource templates. `policy.json` is mechanically generated from their exact union; no wildcard action or unlisted privilege is allowed. It is a policy **template**: `${partition}`, `${account}`, `${region}` and physical identities must be bound only from trusted operator scope and validated plan identities. IAM role/profile paths use validated full paths. Never attach the unresolved template, or widen a denied ARN to make a test pass. RDS snapshot resource wildcards are limited to the authorized account/region; source-DB/cluster filters still constrain requests. Region restrictions may further narrow unscopable APIs where supported.

AWS's [EC2 authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html) requires `Resource: "*"` for the selected broad Describe actions, but supports an instance ARN for DescribeInstanceAttribute. The request contract therefore provides a necessary second boundary: IDs/filters cannot be omitted. The attribute is fixed to `disableApiTermination`; UserData is excluded.

The [ELBv2](https://docs.aws.amazon.com/service-authorization/latest/reference/list_elbv2.html) and [Auto Scaling](https://docs.aws.amazon.com/service-authorization/latest/reference/list_autoscaling.html) references likewise do not support resource ARNs for these Describe actions. This is unavoidable IAM breadth, not permission for the application to inventory resources. LB attribute output is restricted to `deletion_protection.enabled`. [RDS](https://docs.aws.amazon.com/service-authorization/latest/reference/list_rds.html) supports DB/cluster/snapshot resource types: bind the scoped templates published per operation rather than granting `rds:*`.

Other scopes are explicit: [IAM](https://docs.aws.amazon.com/service-authorization/latest/reference/list_iam.html) role/profile ARNs; [ECS](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ecs.html) cluster/service ARNs; [EKS](https://docs.aws.amazon.com/service-authorization/latest/reference/list_eks.html) cluster ARN; [Lambda](https://docs.aws.amazon.com/service-authorization/latest/reference/list_lambda.html) function ARNs for concurrency/tags, but unavoidable `Resource: "*"` for ListEventSourceMappings; [DynamoDB](https://docs.aws.amazon.com/service-authorization/latest/reference/list_dynamodb.html) table ARN; [SQS](https://docs.aws.amazon.com/service-authorization/latest/reference/list_sqs.html) queue ARN; [S3](https://docs.aws.amazon.com/service-authorization/latest/reference/list_s3.html) bucket ARN; [Route 53](https://docs.aws.amazon.com/service-authorization/latest/reference/list_route53.html) hosted-zone ARN. `iam-reference-evidence.json` records action/resource-type cells retrieved from these sources on the decision date, with row-continuation limits explicitly stated.

## Deliberate limits and degradation

- [Security-group reference filters](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSecurityGroups.html) and [ENI filters](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeNetworkInterfaces.html) support bounded first-hop references. They are not a complete ownership graph, and managed service inference from ENI description is prohibited.
- [DescribeTargetGroups](https://docs.aws.amazon.com/elasticloadbalancing/latest/APIReference/API_DescribeTargetGroups.html) accepts a known LB ARN; [DescribeTargetHealth](https://docs.aws.amazon.com/elasticloadbalancing/latest/APIReference/API_DescribeTargetHealth.html) accepts a known target-group ARN. There is no permitted instance-to-every-target-group or LB-to-every-DNS-record scan. Those reverse relationships are `unknown` unless already plan-declared.
- [ListEventSourceMappings](https://docs.aws.amazon.com/lambda/latest/api/API_ListEventSourceMappings.html) is allowed only with known function or event-source filters. GetFunction, GetFunctionConfiguration and GetEventSourceMapping are excluded to avoid code/environment or plaintext filter payload exposure. No account-wide ListFunctions is granted.
- Route 53 [starts at a lexicographic position](https://docs.aws.amazon.com/Route53/latest/APIReference/API_ListResourceRecordSets.html), not an exact record predicate. Require `MaxItems=1`, known hosted-zone/name/type, then exact returned name/type/set-identifier equality. A next record is missing, never a substitute. Multiple variants or a continuation are incomplete. Reverse aliases outside the plan are unknown.
- SQS URLs are reconstructed using a trusted canonical endpoint and authorized account/name; never forward a caller URL. Attributes are explicitly selected; All, ReceiveMessage and messages are prohibited.
- S3 HeadBucket is excluded because its IAM permission also permits bucket listing. No GetObject, object version listing, secret retrieval, SSM parameter values, Lambda code or user data is granted. Selected tag/map/trust values still cross the existing redactor before output.
- Recoverability is not inferred from resource existence or versioning alone. RDS final-snapshot intent comes from the plan, not a live protection API. [DynamoDB PITR](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_DescribeContinuousBackups.html) describes an available time window, not a performed restore. Missing restore proof, backup age, deletion protection or retention facts remain `unknown`.
- This scope deliberately provides partial graph and recoverability coverage across all 25 families. It does not promise every relationship, liveness timestamp or restore path. No missing datum can reduce severity or increase confidence.

## Executable model evidence

Run from the repository root:

```sh
/tmp/dw17-qualification-venv/bin/python docs/verification/live-environment-grounding/17-0/coverage/validate_contract.py
/tmp/dw17-qualification-venv/bin/python -m unittest discover -s docs/verification/live-environment-grounding/17-0/coverage -v
```

The validator loads only the installed botocore model directory (ignoring AWS_DATA_PATH and home-directory models), validates all parameter and response-field paths without resolving credentials or creating clients, and asserts exact action/resource policy equality. Eleven tests pass, including network-denied model validation and deliberately introduced mutating action, unscoped request and policy-resource mismatch failures. These checks establish SDK shape and internal equivalence, not live IAM authorization, service response correctness or production qualification.
