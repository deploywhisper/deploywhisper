---
name: pulumi
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [Pulumi.yaml, Pulumi.dev.yaml, Pulumi.prod.yaml]
token_budget: 1400
tags: [pulumi, iac, cloud]
description: Pulumi stack guidance for aliasing, protection, and stateful replacement risks.
test_suite_path: tests/skill-tests/pulumi
trigger_content_patterns: ["pulumi config", "@pulumi/"]
---

## Critical risk patterns

- Resource renames without aliases force replacements and can recreate live infrastructure unexpectedly = HIGH
- Turning `protect` off on databases, buckets, or queues removes a key deletion backstop = HIGH
- Promoting secret config into plain-text stack values leaks sensitive data into state and logs = CRITICAL
- Preview output can miss provider-computed replacements, so review replacement plans conservatively = MEDIUM

## Review cues

- Look for alias coverage, stack-secret handling, and protection changes before approving Pulumi updates.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
