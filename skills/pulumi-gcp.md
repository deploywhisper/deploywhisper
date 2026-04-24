---
name: pulumi-gcp
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [Pulumi.gcp.yaml, pulumi-gcp.ts]
token_budget: 1400
tags: [pulumi, gcp, iac]
description: Pulumi GCP guidance for IAM authority, project targeting, and state exposure risks.
test_suite_path: tests/skill-tests/pulumi-gcp
trigger_content_patterns: ["@pulumi/gcp", "pulumi_gcp"]
---

## Critical risk patterns

- Authoritative IAM bindings can remove required members and lock out workloads or operators = HIGH
- Cloud SQL or GKE replacements from region or name drift introduce avoidable downtime = HIGH
- Project or folder target changes move blast radius to the wrong tenant = CRITICAL
- Decrypting secrets into plain config or logs exposes sensitive state = CRITICAL

## Review cues

- Review project targeting, IAM authority, and replacement indicators together for Pulumi GCP changes.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
