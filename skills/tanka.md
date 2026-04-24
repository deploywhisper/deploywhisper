---
name: tanka
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [spec.json, environments/default/main.jsonnet]
token_budget: 1300
tags: [tanka, jsonnet, kubernetes]
description: Tanka guidance for environment fan-out, cluster targeting, and Jsonnet-driven drift.
test_suite_path: tests/skill-tests/tanka
trigger_content_patterns: ["tanka.dev/v1alpha1", "tk.libsonnet"]
---

## Critical risk patterns

- Environment-level library changes fan out to every rendered object = HIGH
- Server-side apply or force behavior can overwrite fields owned by other controllers = HIGH
- Namespace or environment target drift deploys to the wrong cluster = CRITICAL
- Hidden Jsonnet defaults make destructive deletions hard to spot in review = MEDIUM

## Review cues

- Review Tanka environment targets and rendered diff shape together before merge.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
