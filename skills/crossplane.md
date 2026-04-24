---
name: crossplane
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [composition.yaml, xrd.yaml, claim.yaml]
token_budget: 1450
tags: [crossplane, platform, kubernetes]
description: Crossplane composition guidance for control-plane fan-out, provider config, and managed resource safety.
test_suite_path: tests/skill-tests/crossplane
trigger_content_patterns: ["apiextensions.crossplane.io", "pkg.crossplane.io"]
---

## Critical risk patterns

- Composition patch changes on network or database fields can fan out to every bound claim = CRITICAL
- Removing fields from an XRD schema breaks existing claims and composition compatibility = HIGH
- ProviderConfig credential-source changes can orphan reconciles or point resources at the wrong account = HIGH
- `deletionPolicy: Delete` on managed resources means claim removal deletes cloud assets too = CRITICAL

## Review cues

- Review Crossplane changes as control-plane mutations, not just single-resource YAML edits.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
