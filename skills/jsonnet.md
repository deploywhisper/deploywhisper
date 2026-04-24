---
name: jsonnet
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [jsonnetfile.json, config.jsonnet, main.jsonnet, .jsonnet]
token_budget: 1200
tags: [jsonnet, templating, kubernetes]
description: Jsonnet guidance for import-graph drift, hidden defaults, and rendered secret exposure.
test_suite_path: tests/skill-tests/jsonnet
---

## Critical risk patterns

- Import graph changes can rewrite many generated manifests indirectly = HIGH
- Hidden fields or local mixins can mask production-only config drift = MEDIUM
- Evaluated secret literals leak directly into rendered output and review artifacts = CRITICAL
- Deleting list elements in generators can remove live permissions or routes = HIGH

## Review cues

- Review rendered output and source-level abstraction changes together for Jsonnet edits.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
