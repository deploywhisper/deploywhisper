---
name: nginx-ingress
version: 1.0.0
author: DeployWhisper
license: MIT
triggers: [nginx-ingress.yaml, ingress-nginx.yaml]
token_budget: 1250
tags: [nginx, ingress, kubernetes]
description: Nginx Ingress controller guidance for routing, annotations, and TLS handling.
test_suite_path: tests/skill-tests/nginx-ingress
supported_toolchains: [nginx-ingress, kubernetes]
trust_level: core
scenario_references: [tests/skill-tests/nginx-ingress]
documentation_links: [docs/skills/authoring-guide.md, docs/skills/test-harness.md]
trigger_content_patterns: ["nginx.ingress.kubernetes.io"]
---

## Critical risk patterns

- `nginx.ingress.kubernetes.io/configuration-snippet` can inject unsafe directives and bypass shared controls = HIGH
- Path regex or default-backend rewrites can shadow unrelated routes and break many services = HIGH
- Missing body-size or timeout tuning on large uploads creates production-only failures = MEDIUM
- TLS host and secret mismatches cause certificate fallback and immediate client trust errors = HIGH

## Review cues

- Check Nginx annotations and route precedence, not just the host/path diff, before approving.
- Prefer deterministic roll-forward or rollback steps over hand-wavy remediation notes.
