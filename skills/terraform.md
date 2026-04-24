---
name: terraform
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [.tf, .tfvars, .tfvars.json, terraform-plan.json, tfplan.json]
token_budget: 1800
tags: [terraform, iac, infrastructure]
description: Deep Terraform risk knowledge covering provider-specific patterns, state operations, lifecycle rules, and common failure modes across AWS, GCP, and Azure.
test_suite_path: tests/skill-tests/terraform
---

## Critical risk patterns

### Security exposure (CRITICAL)
- Security group or firewall rule with `0.0.0.0/0` or `::/0` on any port other than 80/443 = CRITICAL — database ports (3306, 5432, 6379, 27017) exposed to the internet are an immediate data breach risk
- IAM policy with `Action: "*"` or `Resource: "*"` = CRITICAL — grants god-mode access; every resource in the account is exposed
- S3 bucket without `block_public_access` enabled = CRITICAL — data exfiltration risk; default should always be block-all
- S3 bucket policy with `Principal: "*"` = CRITICAL — public read/write to the bucket
- KMS key policy with overly broad access grants = HIGH — encryption key compromise affects all encrypted resources
- RDS instance with `publicly_accessible = true` = CRITICAL — database directly reachable from the internet
- EC2 instance or cloud VM in a public subnet without security group restriction = HIGH
- IAM role with `sts:AssumeRole` trust policy allowing external accounts without conditions = CRITICAL — cross-account privilege escalation

### Data loss risk (CRITICAL)
- RDS instance without `deletion_protection = true` = CRITICAL — a `terraform destroy` or accidental removal deletes the database permanently
- RDS instance without `final_snapshot_identifier` = HIGH — no backup taken before deletion
- DynamoDB table without `point_in_time_recovery` enabled = HIGH — no recovery from accidental data corruption
- S3 bucket without versioning enabled containing production data = HIGH — no recovery from accidental overwrites or deletes
- EBS volume with `delete_on_termination = true` on production data volumes = HIGH
- ElastiCache cluster without `snapshot_retention_limit > 0` = MEDIUM — no recovery from cache corruption or accidental flush

### Network risks (HIGH)
- VPC peering connection or transit gateway route change affecting production subnets = HIGH — can break inter-service communication
- Route table modification removing default routes = CRITICAL — isolates all resources in the subnet
- NAT gateway removal or replacement = HIGH — breaks outbound internet access for private subnets
- Load balancer listener rule changes = MEDIUM — can misroute traffic if ordering is wrong
- DNS record changes (Route53, Cloud DNS) = HIGH — propagation delays mean rollback takes 60-300 seconds depending on TTL

## State-sensitive operations

### Lifecycle rules
- Resources with `prevent_destroy = true` — flag as CRITICAL if a `destroy` action appears for this resource; Terraform will error but CI pipelines may not surface this clearly
- Resources with `ignore_changes` on security-relevant attributes — warn that drift may exist between actual state and desired state; the ignored attributes could have been manually changed to something dangerous
- Resources with `create_before_destroy = true` — during replacement, both old and new resources exist simultaneously; watch for naming conflicts, IP address changes, and brief service duplication
- Resources with `replace_triggered_by` — replacement cascades to dependent resources; verify the full chain is understood

### State operations
- Backend configuration changes (switching from local to S3, changing bucket/key, changing workspace) = CRITICAL — risk of state loss, state corruption, or resources becoming orphaned (exist in cloud but unknown to Terraform)
- `terraform state mv` or `terraform state rm` commands in CI/CD = CRITICAL — manual state manipulation can orphan or duplicate resources
- State lock contention — concurrent `terraform apply` from multiple CI pipelines on the same state file causes lock failures and potential corruption
- Large state files (>10MB) indicate poor module decomposition and increase plan/apply latency

### Provider version changes
- Provider major version upgrade (e.g., AWS provider 4.x → 5.x) = HIGH — may change resource behavior, rename attributes, or require state migration
- Provider minor version upgrade = LOW — but check changelog for deprecation warnings
- Terraform core version upgrade = MEDIUM — new versions may change plan behavior, especially around `moved` blocks and refactoring

## Common failure modes

### Plan/apply divergence
- Data sources that reference frequently changing values (e.g., `aws_ami` with `most_recent = true`) — the AMI ID can change between plan and apply, causing unexpected instance recreation
- Resources depending on external state that changes outside Terraform — plan shows no-op but apply triggers changes
- `timestamp()` or `uuid()` functions in resource attributes — forces replacement on every apply

### Module pitfalls
- Module version upgrade that changes resource addresses internally — forces recreation of resources that should be updated in-place (e.g., renaming a resource inside a module from `aws_instance.web` to `aws_instance.app` destroys and recreates the instance)
- `count` vs `for_each` migration — switching from `count` to `for_each` on existing resources forces destruction and recreation of ALL instances because the state key format changes (numeric index vs string key)
- `count` index shift — removing an item from a list used with `count` causes all subsequent resources to shift indices, triggering cascading destroys and recreates (e.g., removing server[1] causes server[2] to become server[1], which Terraform interprets as a replacement)

### Timing and ordering
- Resources that require propagation time — IAM policies in AWS take 5-10 seconds to propagate; applying an EC2 instance immediately after an IAM role creation may fail with access denied
- RDS modifications with `apply_immediately = true` — triggers immediate reboot; without it, changes are deferred to the next maintenance window
- Auto Scaling Group changes — `min_size`/`max_size`/`desired_capacity` changes take effect gradually; setting desired to 0 kills all instances immediately
- ECS service deployments — if `deployment_minimum_healthy_percent` is too low, rolling deployments may cause downtime

## Provider-specific risks

### AWS
- Eventual consistency on IAM — role/policy propagation takes 5-10 seconds across all regions; race conditions are common in rapid provisioning
- RDS Multi-AZ failover during modification — some changes trigger an automatic failover, causing 60-120 seconds of downtime
- Lambda function code changes — zip hash changes trigger a full redeployment; cold start latency spikes during transition
- ECS task definition — new revision creates a new resource, old revision is deregistered; in-flight requests may be dropped if drain timeout is too short
- CloudFront distribution changes take 15-30 minutes to propagate globally

### GCP
- Project-level IAM bindings are AUTHORITATIVE — `google_project_iam_binding` removes all other bindings for the specified role; use `google_project_iam_member` for additive bindings
- GKE cluster upgrades are destructive — node pool replacement may drain all pods; surge upgrade settings control blast radius
- Cloud SQL instance name is globally unique and reserved for 7 days after deletion — you cannot recreate with the same name immediately

### Azure
- Resource group deletion cascades to ALL contained resources — deleting a resource group is equivalent to deleting every resource inside it
- Azure Policy assignments take 5-15 minutes to evaluate — new resources may temporarily violate policies
- Key Vault soft-delete is enabled by default — deleted vaults retain the name for 90 days, blocking recreation with the same name
- App Service plan tier changes may cause brief downtime during scale operation

## Risk weight reference

| Resource type | Base risk weight | Rationale |
|---|---|---|
| Security group / firewall rule | 0.90 | Direct network exposure |
| IAM policy / role | 0.90 | Access control, blast radius if compromised |
| RDS / Cloud SQL / database | 0.95 | Data loss, downtime |
| S3 / GCS / storage bucket | 0.80 | Data exposure, lifecycle |
| VPC / network | 0.85 | Infrastructure connectivity |
| EC2 / VM / compute | 0.50 | Replaceable, stateless (usually) |
| Lambda / Cloud Function | 0.40 | Stateless, fast rollback |
| Load balancer | 0.70 | Traffic routing, potential downtime |
| DNS record | 0.75 | Propagation delay makes rollback slow |
| Tags / labels | 0.05 | Cosmetic, no operational impact |
| CloudWatch / monitoring | 0.15 | Observability, not runtime |
| SNS / SQS / messaging | 0.60 | Message loss potential |
