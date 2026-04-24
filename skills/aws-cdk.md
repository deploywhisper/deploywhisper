---
name: aws-cdk
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [cdk.json, cdk.context.json]
token_budget: 1350
tags: [aws, cdk, iac]
description: AWS CDK guidance for logical IDs, removal policies, and synth-time environment drift.
test_suite_path: tests/skill-tests/aws-cdk
trigger_content_patterns: ["aws-cdk-lib", "PolicyStatement"]
---

## Critical risk patterns

- Logical ID changes force CloudFormation replacement even when code edits look cosmetic = HIGH
- `RemovalPolicy.DESTROY` on stateful constructs risks permanent data loss = CRITICAL
- Context lookups can differ between synth environments and change plans unexpectedly = MEDIUM
- Broad IAM `PolicyStatement` grants expose entire accounts or regions = HIGH

## Review cues

- Review synthesized logical IDs, removal policies, and IAM grants together for CDK changes.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
