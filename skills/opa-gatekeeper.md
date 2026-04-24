---
name: opa-gatekeeper
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [constrainttemplate.yaml, constraint.yaml, gatekeeper-policy.yaml]
token_budget: 1350
tags: [opa, gatekeeper, policy]
description: OPA Gatekeeper policy guidance for deny rollouts, match scope, and inventory sync safety.
test_suite_path: tests/skill-tests/opa-gatekeeper
trigger_content_patterns: ["templates.gatekeeper.sh", "constraints.gatekeeper.sh"]
---

## Critical risk patterns

- ConstraintTemplate or rego errors can remove enforcement when audit failures are ignored = HIGH
- Broad match exclusions take critical namespaces out of policy coverage = HIGH
- Rolling out deny policies without dry-run validation can block deployments cluster-wide = CRITICAL
- Sync config omissions mean policies evaluate stale inventory and create false confidence = MEDIUM

## Review cues

- Review Gatekeeper changes as policy rollouts with cluster-wide blast radius, not isolated YAML edits.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
