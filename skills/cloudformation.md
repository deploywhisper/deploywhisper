---
name: cloudformation
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [.yaml, .yml, .json, .template]
token_budget: 1500
tags: [cloudformation, aws, iac]
description: Deep CloudFormation risk intelligence covering resource replacement detection, deletion policies, drift patterns, stack dependencies, IAM resource risks, and service quota awareness.
test_suite_path: tests/skill-tests/cloudformation
trigger_content_patterns: [AWSTemplateFormatVersion, Resources, "AWS::", CloudFormation]
---

## Resource update behavior

### Replacement-required updates (CRITICAL)
- Any resource change that triggers `Replacement` instead of `Update` = CRITICAL — CloudFormation destroys the old resource and creates a new one; for stateful resources (RDS, DynamoDB, ElastiCache) this means DATA LOSS unless DeletionPolicy is Retain or Snapshot
- Common replacement triggers:
  - RDS: `Engine`, `DBInstanceIdentifier`, `MasterUsername`, `AvailabilityZone`, `StorageEncrypted` changes all force replacement
  - DynamoDB: `TableName`, `KeySchema` (partition/sort key), `BillingMode` change from PAY_PER_REQUEST to PROVISIONED (on some versions)
  - EC2: `InstanceType` change on instances without stop/start support, `ImageId` change, `AvailabilityZone` change
  - ElastiCache: `Engine`, `CacheNodeType` on some cluster modes, `NumCacheClusters` reduction
  - Lambda: `FunctionName` change forces replacement; `Runtime`, `Handler`, `Code` are in-place updates
  - S3: `BucketName` change = REPLACEMENT — and S3 bucket names are globally unique; the old name may not be reclaimable

### In-place update risks (HIGH)
- RDS `MultiAZ` change = triggers brief failover (60-120 seconds downtime)
- RDS `AllocatedStorage` increase = online for most engines; DECREASE is not supported and fails
- EC2 `InstanceType` change = requires stop/start; brief downtime during transition
- Auto Scaling Group `LaunchTemplate` version change = triggers rolling replacement of instances based on update policy
- ECS `TaskDefinition` revision change = triggers new deployment; old tasks drain based on `DeregistrationDelay`

### No-interruption updates (LOW)
- Tag changes on most resources = no interruption, no replacement
- CloudWatch alarm threshold changes = immediate effect
- Lambda environment variable changes = next invocation uses new values
- SNS topic `DisplayName` change = no operational impact

## Deletion policy analysis

### Missing DeletionPolicy (CRITICAL)
- RDS instance without `DeletionPolicy: Snapshot` or `DeletionPolicy: Retain` = CRITICAL — stack deletion or resource removal destroys the database with no backup; DEFAULT behavior is Delete
- DynamoDB table without `DeletionPolicy: Retain` = CRITICAL — table and all data destroyed on removal
- S3 bucket without `DeletionPolicy: Retain` = HIGH — bucket must be empty before CloudFormation can delete it; if not empty, stack deletion fails and leaves the stack in DELETE_FAILED state
- EBS volumes without `DeletionPolicy: Snapshot` = HIGH — data volumes destroyed without backup
- ElastiCache without `DeletionPolicy: Snapshot` = MEDIUM — cache data lost; acceptable if cache is rebuilt from persistent data source
- Elasticsearch/OpenSearch domain without snapshot = HIGH — index data lost

### DeletionPolicy changes (HIGH)
- `DeletionPolicy` changed from `Retain` to `Delete` = CRITICAL — previously protected resource is now vulnerable to stack deletion
- `DeletionPolicy` removed entirely = CRITICAL — reverts to default behavior which is Delete for most resources
- `UpdateReplacePolicy` missing when DeletionPolicy is set = MEDIUM — DeletionPolicy protects against stack deletion, but UpdateReplacePolicy protects against in-stack replacement; they serve different purposes and both should be set on stateful resources

## Drift-prone patterns

### Console-modified resources (HIGH)
- Resources frequently modified via AWS Console (security groups, IAM policies, S3 bucket policies) — console changes create drift between actual state and template state; next stack update may REVERT console changes silently
- Resources with `Metadata` section that doesn't match actual metadata = drift indicator
- Auto Scaling Group with manually adjusted `DesiredCapacity` — stack update resets to template value
- RDS instance with manually applied parameter group changes — stack update may revert to template-defined parameter group

### Parameter default masking (MEDIUM)
- Parameters with `Default` values that operators override via console — the override is not captured in the template; stack recreation uses the default, not the overridden value
- `Conditions` that reference parameters — changing a parameter default can flip conditions, enabling or disabling entire resource branches
- `Mappings` used with `AWS::Region` — ensure all required regions have entries; deploying to a new region with a missing mapping entry causes creation failure

## Stack dependency risks

### Cross-stack references (HIGH)
- `Fn::ImportValue` referencing another stack's `Export` = HIGH — creates an implicit dependency; the exporting stack cannot be updated to change or remove the export while any stack imports it; this creates stack lock-in
- `Export` name change = CRITICAL — all importing stacks immediately break; CloudFormation prevents this but nested reference chains can be complex
- Stack output used as parameter in another stack (manual wiring) = MEDIUM — less tightly coupled but requires deployment ordering discipline

### Nested stack risks (HIGH)
- Nested stack template URL change = HIGH — triggers nested stack update; ALL resources in the nested stack are re-evaluated
- Nested stack parameter change = propagates through the nested stack; side effects depend on which resources consume the parameter
- Parent stack rollback with nested stacks = complex — nested stack may succeed while parent fails; leaves inconsistent state
- Nested stack with `DeletionPolicy: Retain` on resources inside = the nested stack itself may be deleted but retained resources persist as orphans outside CloudFormation management

## IAM resource risks

### Overly broad policies (CRITICAL)
- `AWS::IAM::Policy` with `Action: "*"` = CRITICAL — administrative access to every AWS service
- `AWS::IAM::Policy` with `Resource: "*"` on sensitive actions = CRITICAL — action applies to every resource in the account
- `AWS::IAM::Role` with trust policy allowing `Principal: "*"` = CRITICAL — any AWS account can assume the role
- `AWS::IAM::Role` trust policy without `Condition` restricting `sts:ExternalId` for cross-account roles = HIGH — susceptible to confused deputy attack
- `AWS::IAM::ManagedPolicy` with `Path: "/"` attached to multiple roles = MEDIUM — broad attachment scope; change affects all attached roles

### IAM boundary and constraints
- Missing `PermissionsBoundary` on IAM roles created by the stack = MEDIUM — roles have no upper bound on permissions; a policy change can escalate beyond intended scope
- `AWS::IAM::InstanceProfile` change = HIGH — requires instance stop/start or replacement to take effect
- Service-linked role manipulation = HIGH — these are managed by AWS services; manual modification can break service functionality

## Service quota risks

### Capacity limits (MEDIUM)
- Creating multiple resources of the same type — check against account-level service quotas:
  - VPCs per region: default 5
  - Elastic IPs per region: default 5
  - RDS instances per region: default 40
  - Lambda concurrent executions: default 1000
  - S3 buckets per account: default 100
  - CloudFormation stacks per region: default 200
- Resources approaching quota limits may succeed in development (fewer resources) but fail in production (more resources)
- Quota increases require AWS support requests and take 1-5 business days

### Template limits
- Template body size limit: 51,200 bytes (direct upload) or 460,800 bytes (S3 URL)
- Resource limit per template: 500 resources — approaching this limit indicates the stack should be decomposed
- Output limit: 200 outputs per stack
- Parameter limit: 200 parameters per stack
- Mapping limit: 200 mappings with 200 key-value pairs each

## CloudFormation-specific failure modes

### Stack update failures
- Stack in `UPDATE_ROLLBACK_FAILED` state = CRITICAL — stack is stuck; requires manual intervention via `ContinueUpdateRollback` with resources to skip, or potentially stack recreation
- Circular dependency between resources = creation failure — `DependsOn` chains that form a cycle prevent stack creation; CloudFormation detects this at validation time
- Insufficient IAM permissions for CloudFormation execution role = creation/update failure — CloudFormation needs permission to create EVERY resource type in the template
- Resource creation order dependency not expressed in template — CloudFormation creates resources in parallel unless `DependsOn` specifies ordering; missing DependsOn on dependent resources causes race conditions

### Rollback risks
- Stack update with `--no-rollback` flag = CRITICAL — if update fails, stack remains in `UPDATE_FAILED` state with partial changes applied; no automatic recovery
- Stack creation with `--on-failure DO_NOTHING` = HIGH — failed stack persists with partial resources; useful for debugging but dangerous in automation
- Rollback of a stack that created resources with external dependencies (data was written to the new database, DNS was pointed to new load balancer) = the rollback destroys the new resources but the external dependencies are not rolled back
- Change set with `Replacement: True` on multiple resources = HIGH — if any replacement fails mid-update, rollback must recreate the ORIGINAL resources which may fail (name conflicts, quota limits)
